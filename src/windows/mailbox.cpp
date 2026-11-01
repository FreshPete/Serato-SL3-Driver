#include "windows/mailbox.hpp"
#include "windows/mailbox_layout.hpp"
#include <sddl.h>
#include <bcrypt.h>
#include <algorithm>
#include <array>
#include <cstring>
#include <limits>
#include <stdexcept>

namespace sl3::worker {
namespace {
[[noreturn]] void failed(const char* text){throw std::runtime_error(std::string(text)+": Win32="+std::to_string(GetLastError()));}
struct Handle {HANDLE value=nullptr;~Handle(){if(value)CloseHandle(value);}};
struct Security {
    PSECURITY_DESCRIPTOR descriptor=nullptr;
    SECURITY_ATTRIBUTES attributes{sizeof(attributes),nullptr,FALSE};
    Security(){
        Handle token;
        if(!OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token.value))failed("Query channel owner token");
        DWORD required=0;GetTokenInformation(token.value,TokenUser,nullptr,0,&required);
        std::vector<std::uint8_t> storage(required);
        if(!required || !GetTokenInformation(token.value,TokenUser,storage.data(),required,&required))failed("Read channel owner SID");
        LPWSTR sid=nullptr;
        if(!ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(storage.data())->User.Sid,&sid))failed("Format channel owner SID");
        const std::wstring dacl=L"D:P(A;;GA;;;"+std::wstring(sid)+L")";
        LocalFree(sid);
        if(!ConvertStringSecurityDescriptorToSecurityDescriptorW(dacl.c_str(),SDDL_REVISION_1,&descriptor,nullptr))failed("Build owner-only channel DACL");
        attributes.lpSecurityDescriptor=descriptor;
    }
    ~Security(){if(descriptor)LocalFree(descriptor);}
};
bool valid_name(const std::wstring& name){
    const std::wstring prefix=L"Local\\SL3Mailbox-";
    return name.size()==prefix.size()+32 && name.compare(0,prefix.size(),prefix)==0 &&
        std::all_of(name.begin()+static_cast<std::ptrdiff_t>(prefix.size()),name.end(),[](wchar_t c){return (c>=L'0' && c<=L'9') || (c>=L'a' && c<=L'f');});
}
void timeout_bound(DWORD timeout){if(timeout>10000)throw std::invalid_argument("Mailbox wait exceeds ten seconds");}
bool header(const wire::Shared* value){
    return value->magic_value==wire::magic && value->version_value==wire::version && value->structure_bytes==sizeof(wire::Shared) &&
        std::all_of(std::begin(value->reserved),std::end(value->reserved),[](std::uint32_t v){return v==0;});
}
LONG phase(wire::Shared* value){return InterlockedCompareExchange(&value->phase,0,0);}
}
struct Mailbox::State {
    Handle mapping,request_event,reply_event,input_event,output_event;
    wire::Shared* shared=nullptr;
    std::wstring name;
    bool host=false;
    std::uint32_t next=1,pending=0,opcode=0,lease=0;
    std::array<std::uint64_t,2> write_position{},read_position{},write_time{},read_time{};
    ~State(){
        if(shared){
            if(host){
                InterlockedExchange(&shared->phase,wire::closed);
                for(const auto event:{request_event.value,input_event.value,output_event.value})if(event)SetEvent(event);
            }
            UnmapViewOfFile(shared);
        }
    }
};
Mailbox::Mailbox(std::unique_ptr<State> state) noexcept:state_(std::move(state)){}
Mailbox::~Mailbox()=default;
const std::wstring& Mailbox::name() const noexcept{return state_->name;}
HANDLE Mailbox::request_event() const noexcept{return state_->request_event.value;}
HANDLE Mailbox::input_event() const noexcept{return state_->input_event.value;}
HANDLE Mailbox::output_event() const noexcept{return state_->output_event.value;}
HANDLE Mailbox::mapping_handle() const noexcept{return state_->mapping.value;}
std::shared_ptr<const void> Mailbox::hold_audio_reference(HANDLE process,HANDLE remote,const std::wstring& name){
    if(!valid_name(name) || !remote || remote==INVALID_HANDLE_VALUE)throw std::invalid_argument("Invalid audio mapping reference");
    Handle expected,copy;
    expected.value=OpenFileMappingW(FILE_MAP_READ,FALSE,(name+L"-map").c_str());
    if(!expected.value)failed("Open named audio mapping for identity check");
    if(!DuplicateHandle(process,remote,GetCurrentProcess(),&copy.value,FILE_MAP_READ,FALSE,0))failed("Duplicate client audio mapping reference");
    // This SDK lacks Kernelbase.lib. Resolve the documented Windows 10+ API
    // only from the already loaded system module; absence refuses admission.
    using Compare=BOOL(WINAPI*)(HANDLE,HANDLE);
    const auto module=GetModuleHandleW(L"kernelbase.dll");
    const auto address=module?GetProcAddress(module,"CompareObjectHandles"):nullptr;
    Compare compare=nullptr;static_assert(sizeof(compare)==sizeof(address),"Windows function pointer size");
    std::memcpy(&compare,&address,sizeof(compare));
    if(!compare || !compare(expected.value,copy.value))throw std::runtime_error("Client mapping reference does not match audio channel");
    auto result=std::shared_ptr<const void>(copy.value,[](const void* p){CloseHandle(const_cast<void*>(p));});
    copy.value=nullptr;return result;
}
std::unique_ptr<Mailbox> Mailbox::create(){
    auto state=std::make_unique<State>();state->host=true;
    std::array<UCHAR,16> random{};
    if(BCryptGenRandom(nullptr,random.data(),ULONG(random.size()),BCRYPT_USE_SYSTEM_PREFERRED_RNG)<0)throw std::runtime_error("Generate private channel identity");
    state->name=L"Local\\SL3Mailbox-";
    constexpr wchar_t hex[]=L"0123456789abcdef";
    for(const auto byte:random){state->name+=hex[byte>>4];state->name+=hex[byte&15];}
    Security security;
    state->mapping.value=CreateFileMappingW(INVALID_HANDLE_VALUE,&security.attributes,PAGE_READWRITE,0,sizeof(wire::Shared),(state->name+L"-map").c_str());
    if(!state->mapping.value)failed("Create private channel mapping");
    if(GetLastError()==ERROR_ALREADY_EXISTS)throw std::runtime_error("Channel identity collision; never attach existing objects");
    state->request_event.value=CreateEventW(&security.attributes,FALSE,FALSE,(state->name+L"-request").c_str());
    if(!state->request_event.value)failed("Create request event");
    if(GetLastError()==ERROR_ALREADY_EXISTS)throw std::runtime_error("Request event identity collision");
    state->reply_event.value=CreateEventW(&security.attributes,FALSE,FALSE,(state->name+L"-reply").c_str());
    if(!state->reply_event.value)failed("Create reply event");
    if(GetLastError()==ERROR_ALREADY_EXISTS)throw std::runtime_error("Reply event identity collision");
    state->input_event.value=CreateEventW(&security.attributes,FALSE,FALSE,(state->name+L"-input-ready").c_str());
    if(!state->input_event.value)failed("Create input data event");
    if(GetLastError()==ERROR_ALREADY_EXISTS)throw std::runtime_error("Input event identity collision");
    state->output_event.value=CreateEventW(&security.attributes,FALSE,FALSE,(state->name+L"-output-ready").c_str());
    if(!state->output_event.value)failed("Create output data event");
    if(GetLastError()==ERROR_ALREADY_EXISTS)throw std::runtime_error("Output event identity collision");
    state->shared=static_cast<wire::Shared*>(MapViewOfFile(state->mapping.value,FILE_MAP_ALL_ACCESS,0,0,sizeof(wire::Shared)));
    if(!state->shared)failed("Map private channel");
    std::memset(state->shared,0,sizeof(wire::Shared));
    state->shared->magic_value=wire::magic;state->shared->version_value=wire::version;state->shared->structure_bytes=sizeof(wire::Shared);
    InterlockedExchange(&state->shared->phase,wire::idle);
    return std::unique_ptr<Mailbox>(new Mailbox(std::move(state)));
}
std::unique_ptr<Mailbox> Mailbox::open(const std::wstring& name){
    if(!valid_name(name))throw std::invalid_argument("Invalid local mailbox identity");
    auto state=std::make_unique<State>();state->name=name;
    state->mapping.value=OpenFileMappingW(FILE_MAP_ALL_ACCESS,FALSE,(name+L"-map").c_str());
    if(!state->mapping.value)failed("Open private channel mapping");
    state->shared=static_cast<wire::Shared*>(MapViewOfFile(state->mapping.value,FILE_MAP_ALL_ACCESS,0,0,sizeof(wire::Shared)));
    if(!state->shared)failed("Map peer channel");
    if(phase(state->shared)==wire::closed || !header(state->shared))throw std::runtime_error("Incompatible/closed channel header");
    state->request_event.value=OpenEventW(SYNCHRONIZE|EVENT_MODIFY_STATE,FALSE,(name+L"-request").c_str());
    state->reply_event.value=OpenEventW(SYNCHRONIZE|EVENT_MODIFY_STATE,FALSE,(name+L"-reply").c_str());
    state->input_event.value=OpenEventW(SYNCHRONIZE|EVENT_MODIFY_STATE,FALSE,(name+L"-input-ready").c_str());
    state->output_event.value=OpenEventW(SYNCHRONIZE|EVENT_MODIFY_STATE,FALSE,(name+L"-output-ready").c_str());
    if(!state->request_event.value || !state->reply_event.value || !state->input_event.value || !state->output_event.value)failed("Open channel events");
    if(InterlockedCompareExchange(&state->shared->peer_pid,LONG(GetCurrentProcessId()),0)!=0)throw std::runtime_error("Channel already has a peer; create a new session identity");
    return std::unique_ptr<Mailbox>(new Mailbox(std::move(state)));
}
void Mailbox::close() noexcept{
    InterlockedExchange(&state_->shared->phase,wire::closed);
    SetEvent(state_->request_event.value);SetEvent(state_->reply_event.value);
    SetEvent(state_->input_event.value);SetEvent(state_->output_event.value);
}
bool Mailbox::send(std::uint32_t opcode,const std::uint8_t* data,std::size_t count){
    auto& s=*state_;auto* value=s.shared;
    if(!s.host || !opcode || count>wire::capacity || (count && !data) || !s.next || s.pending)return false;
    if(!header(value)){close();return false;}
    if(InterlockedCompareExchange(&value->phase,wire::writing,wire::idle)!=wire::idle)return false;
    value->request_sequence=s.next;value->opcode=opcode;value->request_bytes=std::uint32_t(count);
    if(count)std::memcpy(value->request_data.data(),data,count);
    s.pending=s.next++;s.opcode=opcode;
    if(InterlockedCompareExchange(&value->phase,wire::request,wire::writing)!=wire::writing){close();return false;}
    if(!SetEvent(s.request_event.value)){close();failed("Publish mailbox request");}
    return true;
}
MessageResult Mailbox::await_reply(HANDLE peer,DWORD timeout,Message& output){
    timeout_bound(timeout);auto& s=*state_;auto* value=s.shared;
    if(!s.host || !s.pending)throw std::logic_error("No host request is pending");
    if(phase(value)==wire::closed)return MessageResult::closed;
    const DWORD peer_pid=GetProcessId(peer);
    if(!peer_pid)throw std::invalid_argument("An owned peer process handle is required");
    const HANDLE handles[]={s.reply_event.value,peer};
    const auto wait=WaitForMultipleObjects(2,handles,FALSE,timeout);
    if(wait==WAIT_TIMEOUT){close();return MessageResult::timeout;}
    if(wait==WAIT_OBJECT_0+1){close();return MessageResult::peer_exited;}
    if(wait!=WAIT_OBJECT_0){close();failed("Wait for mailbox reply/peer");}
    if(phase(value)==wire::closed)return MessageResult::closed;
    if(InterlockedCompareExchange(&value->phase,wire::reading,wire::reply)!=wire::reply){close();return MessageResult::protocol_error;}
    const auto sequence=value->reply_sequence,opcode=value->opcode,count=value->reply_bytes,status=value->status;
    if(!header(value) || sequence!=s.pending || opcode!=s.opcode || count>wire::capacity ||
       DWORD(InterlockedCompareExchange(&value->peer_pid,0,0))!=peer_pid){close();return MessageResult::protocol_error;}
    Message candidate;candidate.sequence=sequence;candidate.opcode=opcode;candidate.status=status;
    candidate.bytes.assign(value->reply_data.begin(),value->reply_data.begin()+count);
    if(InterlockedCompareExchange(&value->phase,wire::idle,wire::reading)!=wire::reading){close();return MessageResult::closed;}
    s.pending=0;output=std::move(candidate);return MessageResult::ok;
}
MessageResult Mailbox::receive(DWORD timeout,Message& output){
    timeout_bound(timeout);auto& s=*state_;auto* value=s.shared;
    if(s.host || s.lease)throw std::logic_error("Peer role requires retiring its prior request");
    const auto begin=GetTickCount64();
    for(;;){
        const auto current=phase(value);
        if(current==wire::closed)return MessageResult::closed;
        if(!header(value) || current==wire::processing || current<wire::idle || current>wire::writing){close();return MessageResult::protocol_error;}
        // A combined worker wait may already have consumed the auto-reset edge.
        // Published ownership remains authoritative. An earlier fast-path read
        // can also leave a late/stale signal; keep the ORIGINAL wait deadline.
        if(current==wire::request)break;
        const auto elapsed=GetTickCount64()-begin;
        if(timeout && elapsed>=timeout)return MessageResult::timeout;
        const auto left=elapsed<timeout?timeout-DWORD(elapsed):0;
        const auto wait=WaitForSingleObject(s.request_event.value,left);
        if(wait!=WAIT_OBJECT_0 && wait!=WAIT_TIMEOUT){close();failed("Wait for mailbox request");}
        if(wait==WAIT_TIMEOUT && phase(value)!=wire::request)return phase(value)==wire::closed?MessageResult::closed:MessageResult::timeout;
        if(!timeout && phase(value)!=wire::request)return phase(value)==wire::closed?MessageResult::closed:MessageResult::timeout;
    }
    const auto previous=InterlockedCompareExchange(&value->phase,wire::processing,wire::request);
    if(previous==wire::closed)return MessageResult::closed;
    if(previous!=wire::request){close();return MessageResult::protocol_error;}
    const auto sequence=value->request_sequence,opcode=value->opcode,count=value->request_bytes;
    if(!header(value) || sequence!=s.next || !opcode || count>wire::capacity){close();return MessageResult::protocol_error;}
    Message candidate;candidate.sequence=sequence;candidate.opcode=opcode;
    candidate.bytes.assign(value->request_data.begin(),value->request_data.begin()+count);
    s.lease=s.next++;s.opcode=opcode;output=std::move(candidate);return MessageResult::ok;
}
bool Mailbox::respond(std::uint32_t status,const std::uint8_t* data,std::size_t count){
    auto& s=*state_;auto* value=s.shared;
    if(s.host || !s.lease || count>wire::capacity || (count && !data))return false;
    if(!header(value) || phase(value)!=wire::processing){close();return false;}
    value->reply_sequence=s.lease;value->reply_bytes=std::uint32_t(count);value->status=status;
    if(count)std::memcpy(value->reply_data.data(),data,count);
    if(InterlockedCompareExchange(&value->phase,wire::reply,wire::processing)!=wire::processing){close();return false;}
    s.lease=0;
    if(!SetEvent(s.reply_event.value)){close();failed("Publish mailbox reply");}
    return true;
}
namespace {
LONG atomic_read(volatile LONG& value){return InterlockedCompareExchange(&value,0,0);}
AudioResult ring_fault(wire::Shared* shared,HANDLE input,HANDLE output,AudioResult result) noexcept {
    InterlockedCompareExchange(&shared->audio_fault,LONG(result),0);SetEvent(input);SetEvent(output);return result;
}
std::size_t packet_bytes(const std::array<std::uint8_t,64>& packets,std::uint32_t count) noexcept {
    if(count<8 || count>64 || count%8)return 0;
    std::size_t frames=0;
    for(std::size_t i=0;i<packets.size();++i){
        const auto value=packets[i];
        if(i<count){if(value<1 || value>7)return 0;frames+=value;}
        else if(value)return 0;
    }
    return frames*18;
}
}
bool Mailbox::audio_pristine() const noexcept {
    auto* value=state_->shared;
    if(!header(value) || phase(value)!=wire::idle || InterlockedCompareExchange(&value->audio_fault,0,0) ||
       InterlockedCompareExchange(&value->audio_rate,0,0))return false;
    for(auto* queue:{&value->input,&value->output}){
        if(InterlockedCompareExchange(&queue->read,0,0) || InterlockedCompareExchange(&queue->write,0,0) ||
           !std::all_of(std::begin(queue->reserved),std::end(queue->reserved),[](std::uint32_t v){return v==0;}))return false;
    }
    return true;
}
AudioResult Mailbox::audio_fault() const noexcept {
    const auto value=atomic_read(state_->shared->audio_fault);
    if(!value)return AudioResult::ok;
    return value>=LONG(AudioResult::invalid_packet) && value<=LONG(AudioResult::protocol_error)?AudioResult(value):AudioResult::protocol_error;
}
AudioResult Mailbox::try_push_audio(AudioDirection direction,const AudioBlock& block) noexcept {
    auto& s=*state_;auto* shared=s.shared;
    if(direction!=AudioDirection::input && direction!=AudioDirection::output)return AudioResult::invalid_argument;
    if((s.host && direction==AudioDirection::input) || (!s.host && direction==AudioDirection::output))return AudioResult::wrong_role;
    if(phase(shared)==wire::closed)return AudioResult::closed;
    if(atomic_read(shared->audio_fault))return AudioResult::faulted;
    auto fault=[&](AudioResult result){return ring_fault(shared,s.input_event.value,s.output_event.value,result);};
    if(!header(shared))return fault(AudioResult::protocol_error);
    const auto bytes=packet_bytes(block.frames_per_packet,block.packet_count);
    if(!bytes || (block.reported_rate_hz!=44100 && block.reported_rate_hz!=48000))return fault(AudioResult::invalid_packet);
    const std::size_t index=direction==AudioDirection::input?0:1;
    const auto frames=bytes/18;
    if(block.first_frame!=s.write_position[index] || block.first_frame>std::numeric_limits<std::uint64_t>::max()-frames)return fault(AudioResult::discontinuity);
    if(block.host_observation_ns<s.write_time[index])return fault(AudioResult::clock_regression);
    const auto rate=InterlockedCompareExchange(&shared->audio_rate,LONG(block.reported_rate_hz),0);
    if(rate && rate!=LONG(block.reported_rate_hz))return fault(AudioResult::rate_changed);
    auto& queue=index==0?shared->input:shared->output;
    if(!std::all_of(std::begin(queue.reserved),std::end(queue.reserved),[](std::uint32_t value){return value==0;}))return fault(AudioResult::protocol_error);
    const auto write=std::uint32_t(atomic_read(queue.write)),read=std::uint32_t(atomic_read(queue.read));
    const auto used=write-read;
    if(used>wire::audio_slots)return fault(AudioResult::protocol_error);
    if(used==wire::audio_slots)return AudioResult::full;
    auto& slot=queue.slots[write&(wire::audio_slots-1)];
    slot.first_frame=block.first_frame;slot.host_observation_ns=block.host_observation_ns;
    slot.reported_rate_hz=block.reported_rate_hz;slot.pcm_bytes=std::uint32_t(bytes);
    slot.packet_count=block.packet_count;
    slot.frames_per_packet=block.frames_per_packet;
    std::memcpy(slot.pcm.data(),block.pcm.data(),bytes);
    // Publication is the producer's linearization point. Concurrent close may
    // overlap this operation; caller shutdown must still retire its data threads.
    InterlockedExchange(&queue.write,LONG(write+1u));
    s.write_position[index]+=frames;s.write_time[index]=block.host_observation_ns;
    if(!SetEvent(index==0?s.input_event.value:s.output_event.value))return fault(AudioResult::protocol_error);
    return AudioResult::ok;
}
AudioResult Mailbox::try_pop_audio(AudioDirection direction,AudioBlock& output) noexcept {
    auto& s=*state_;auto* shared=s.shared;
    if(direction!=AudioDirection::input && direction!=AudioDirection::output)return AudioResult::invalid_argument;
    if((s.host && direction==AudioDirection::output) || (!s.host && direction==AudioDirection::input))return AudioResult::wrong_role;
    if(phase(shared)==wire::closed)return AudioResult::closed;
    if(atomic_read(shared->audio_fault))return AudioResult::faulted;
    auto fault=[&](AudioResult result){return ring_fault(shared,s.input_event.value,s.output_event.value,result);};
    if(!header(shared))return fault(AudioResult::protocol_error);
    const std::size_t index=direction==AudioDirection::input?0:1;
    auto& queue=index==0?shared->input:shared->output;
    if(!std::all_of(std::begin(queue.reserved),std::end(queue.reserved),[](std::uint32_t value){return value==0;}))return fault(AudioResult::protocol_error);
    const auto read=std::uint32_t(atomic_read(queue.read)),write=std::uint32_t(atomic_read(queue.write));
    const auto used=write-read;
    if(used>wire::audio_slots)return fault(AudioResult::protocol_error);
    if(!used)return AudioResult::empty;
    const auto& slot=queue.slots[read&(wire::audio_slots-1)];
    AudioBlock candidate;candidate.first_frame=slot.first_frame;candidate.host_observation_ns=slot.host_observation_ns;
    candidate.reported_rate_hz=slot.reported_rate_hz;candidate.frames_per_packet=slot.frames_per_packet;candidate.packet_count=slot.packet_count;
    const auto recorded_bytes=slot.pcm_bytes,bytes=std::uint32_t(packet_bytes(candidate.frames_per_packet,candidate.packet_count));
    if(!bytes || recorded_bytes!=bytes || !std::all_of(std::begin(slot.reserved),std::end(slot.reserved),[](std::uint32_t value){return value==0;}))return fault(AudioResult::invalid_packet);
    if(LONG(candidate.reported_rate_hz)!=atomic_read(shared->audio_rate) || (candidate.reported_rate_hz!=44100 && candidate.reported_rate_hz!=48000))return fault(AudioResult::rate_changed);
    const auto frames=bytes/18;
    if(candidate.first_frame!=s.read_position[index] || candidate.first_frame>std::numeric_limits<std::uint64_t>::max()-frames)return fault(AudioResult::discontinuity);
    if(candidate.host_observation_ns<s.read_time[index])return fault(AudioResult::clock_regression);
    std::memcpy(candidate.pcm.data(),slot.pcm.data(),bytes);
    InterlockedExchange(&queue.read,LONG(read+1u));
    s.read_position[index]+=frames;s.read_time[index]=candidate.host_observation_ns;
    // Full-duplex work wake: retiring IN frees worker publication space;
    // retiring OUT frees host publication space. Wakes can carry no new PCM,
    // just like existing stale-event wakes; queue counters remain authoritative.
    if(!SetEvent(index==0?s.output_event.value:s.input_event.value))return fault(AudioResult::protocol_error);
    output=candidate;return AudioResult::ok;
}
AudioResult Mailbox::wait_pop_audio(AudioDirection direction,DWORD timeout,AudioBlock& output) noexcept {
    if(timeout>10000)return AudioResult::invalid_argument;
    const auto initial=try_pop_audio(direction,output);
    if(initial!=AudioResult::empty)return initial;
    const auto event=direction==AudioDirection::input?state_->input_event.value:state_->output_event.value;
    const auto wait=WaitForSingleObject(event,timeout);
    if(wait==WAIT_TIMEOUT)return AudioResult::timeout;
    if(wait!=WAIT_OBJECT_0)return ring_fault(state_->shared,state_->input_event.value,state_->output_event.value,AudioResult::protocol_error);
    // A prior publication's wake can remain signalled after the queue drained.
    return try_pop_audio(direction,output);
}
}
