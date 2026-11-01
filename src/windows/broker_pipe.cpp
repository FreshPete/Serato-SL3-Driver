#include "windows/broker_pipe.hpp"
#include <sddl.h>
#include <bcrypt.h>
#include <array>
#include <algorithm>
#include <cstring>
#include <stdexcept>
#include <optional>

namespace sl3::worker {
namespace {
struct Handle {
    HANDLE value=nullptr;
    ~Handle(){if(value && value!=INVALID_HANDLE_VALUE)CloseHandle(value);}
    Handle()=default;Handle(const Handle&)=delete;Handle& operator=(const Handle&)=delete;
};
struct PipeError:std::runtime_error {DWORD code;PipeError(const char* text,DWORD error):std::runtime_error(std::string(text)+": "+std::to_string(error)),code(error){}};
[[noreturn]] void fail(const char* text){throw PipeError(text,GetLastError());}
struct Identity {std::vector<std::uint8_t> sid;LUID authentication{};DWORD session=0,integrity=0;bool elevated=false;};
std::vector<std::uint8_t> info(HANDLE token,TOKEN_INFORMATION_CLASS kind){
    DWORD size=0;GetTokenInformation(token,kind,nullptr,0,&size);std::vector<std::uint8_t> bytes(size);
    if(!size || !GetTokenInformation(token,kind,bytes.data(),size,&size))fail("Read broker peer token");return bytes;
}
Identity identity(HANDLE token){
    Identity result;const auto user=info(token,TokenUser);const auto sid=reinterpret_cast<const TOKEN_USER*>(user.data())->User.Sid;
    result.sid.resize(GetLengthSid(sid));if(!CopySid(DWORD(result.sid.size()),result.sid.data(),sid))fail("Copy broker peer SID");
    const auto stats=info(token,TokenStatistics);result.authentication=reinterpret_cast<const TOKEN_STATISTICS*>(stats.data())->AuthenticationId;
    const auto session=info(token,TokenSessionId);std::memcpy(&result.session,session.data(),sizeof(DWORD));
    const auto elevation=info(token,TokenElevation);result.elevated=reinterpret_cast<const TOKEN_ELEVATION*>(elevation.data())->TokenIsElevated!=0;
    const auto label=info(token,TokenIntegrityLevel);const auto integrity=reinterpret_cast<const TOKEN_MANDATORY_LABEL*>(label.data())->Label.Sid;
    const auto count=*GetSidSubAuthorityCount(integrity);if(!count)throw std::runtime_error("Invalid broker integrity SID");
    result.integrity=*GetSidSubAuthority(integrity,count-1);return result;
}
Identity process_identity(HANDLE process){Handle token;if(!OpenProcessToken(process,TOKEN_QUERY,&token.value))fail("Open broker process token");return identity(token.value);}
bool same(const Identity& a,const Identity& b){
    return !a.elevated && !b.elevated && a.integrity>=SECURITY_MANDATORY_MEDIUM_RID && a.integrity==b.integrity &&
        a.session==b.session && a.authentication.LowPart==b.authentication.LowPart && a.authentication.HighPart==b.authentication.HighPart &&
        EqualSid(const_cast<std::uint8_t*>(a.sid.data()),const_cast<std::uint8_t*>(b.sid.data()));
}
struct Security {
    PSECURITY_DESCRIPTOR descriptor=nullptr;SECURITY_ATTRIBUTES attributes{sizeof(attributes),nullptr,FALSE};
    Security(){
        const auto owner=process_identity(GetCurrentProcess());if(owner.elevated || owner.integrity<SECURITY_MANDATORY_MEDIUM_RID)
            throw std::runtime_error("Broker endpoint requires an ordinary medium-or-higher user token");
        LPWSTR sid=nullptr;if(!ConvertSidToStringSidW(const_cast<std::uint8_t*>(owner.sid.data()),&sid))fail("Format broker owner SID");
        const auto dacl=L"D:P(A;;GA;;;"+std::wstring(sid)+L")";LocalFree(sid);
        if(!ConvertStringSecurityDescriptorToSecurityDescriptorW(dacl.c_str(),SDDL_REVISION_1,&descriptor,nullptr))fail("Create broker owner DACL");
        attributes.lpSecurityDescriptor=descriptor;
    }
    ~Security(){if(descriptor)LocalFree(descriptor);}
};
bool endpoint(const std::wstring& name){
    const std::wstring prefix=L"\\\\.\\pipe\\SL3Broker-";
    return name.size()==prefix.size()+32 && name.compare(0,prefix.size(),prefix)==0 &&
        std::all_of(name.begin()+std::ptrdiff_t(prefix.size()),name.end(),[](wchar_t c){return (c>=L'0' && c<=L'9') || (c>=L'a' && c<=L'f');});
}
constexpr unsigned magic=0x42334c53,version=1,maximum=2048;
enum class Op:unsigned {hello=1,proof=2,clock=3,start=4,stop=5,detach=6};
struct Frame {unsigned sequence=0,opcode=0,status=0;std::vector<std::uint8_t> bytes;};
void put32(std::vector<std::uint8_t>& out,unsigned value){for(unsigned n=0;n<4;++n)out.push_back(std::uint8_t(value>>(8*n)));}
unsigned get32(const std::vector<std::uint8_t>& b,std::size_t at){unsigned v=0;for(unsigned n=0;n<4;++n)v|=unsigned(b.at(at+n))<<(8*n);return v;}
void put_handle(std::vector<std::uint8_t>& out,HANDLE handle){auto value=reinterpret_cast<std::uintptr_t>(handle);for(unsigned n=0;n<8;++n)out.push_back(std::uint8_t(std::uint64_t(value)>>(8*n)));}
HANDLE get_handle(const std::vector<std::uint8_t>& b){std::uint64_t value=0;for(unsigned n=0;n<8;++n)value|=std::uint64_t(b.at(n))<<(8*n);return reinterpret_cast<HANDLE>(std::uintptr_t(value));}
// Every overlapped operation retires before its buffer/event leaves scope.
// If cancellation cannot establish that, fail-stop this owning process.
bool finish(HANDLE pipe,OVERLAPPED& operation,bool immediate,DWORD error,DWORD timeout,HANDLE peer,DWORD& bytes){
    if(!immediate && error!=ERROR_IO_PENDING){if(error==ERROR_PIPE_CONNECTED)return true;SetLastError(error);fail("Begin broker pipe operation");}
    if(!immediate){
        const HANDLE waits[]={operation.hEvent,peer};
        const auto wait=WaitForMultipleObjects(peer?2:1,waits,FALSE,timeout);
        if(wait!=WAIT_OBJECT_0){
            if(!CancelIoEx(pipe,&operation) && GetLastError()!=ERROR_NOT_FOUND)std::terminate();
            if(WaitForSingleObject(operation.hEvent,1000)!=WAIT_OBJECT_0)std::terminate();
            DWORD retired=0;const auto completed=GetOverlappedResult(pipe,&operation,&retired,FALSE);const auto completion_error=GetLastError();
            if(wait==WAIT_TIMEOUT){
                if(completed){bytes=retired;return true;}
                if(completion_error==ERROR_OPERATION_ABORTED)return false;
                SetLastError(completion_error);fail("Retire broker pipe operation");
            }
            throw std::runtime_error("Broker pipe peer ended or wait failed");
        }
    }
    if(!GetOverlappedResult(pipe,&operation,&bytes,FALSE))fail("Complete broker pipe operation");return true;
}
bool transfer(HANDLE pipe,bool output,std::vector<std::uint8_t>& bytes,DWORD timeout,HANDLE peer){
    Handle event;event.value=CreateEventW(nullptr,TRUE,FALSE,nullptr);if(!event.value)fail("Create broker I/O event");
    OVERLAPPED operation{};operation.hEvent=event.value;DWORD count=0;
    const auto immediate=output?WriteFile(pipe,bytes.data(),DWORD(bytes.size()),&count,&operation):ReadFile(pipe,bytes.data(),DWORD(bytes.size()),&count,&operation);
    const auto error=GetLastError();if(!finish(pipe,operation,immediate!=FALSE,error,timeout,peer,count))return false;
    if(output && count!=bytes.size())throw std::runtime_error("Short broker pipe write");
    if(!output)bytes.resize(count);return true;
}
std::optional<Frame> read(HANDLE pipe,DWORD timeout,HANDLE peer){
    std::vector<std::uint8_t> bytes(maximum+24);if(!transfer(pipe,false,bytes,timeout,peer))return std::nullopt;
    if(bytes.size()<24 || get32(bytes,0)!=magic || get32(bytes,4)!=version || get32(bytes,20)!=bytes.size()-24)
        throw std::runtime_error("Invalid broker frame");
    Frame frame{get32(bytes,8),get32(bytes,12),get32(bytes,16),{bytes.begin()+24,bytes.end()}};
    if(!frame.sequence || frame.opcode<1 || frame.opcode>6)throw std::runtime_error("Invalid broker frame identity");return frame;
}
DWORD remaining(ULONGLONG deadline) noexcept {const auto now=GetTickCount64();return now>=deadline?0:DWORD(deadline-now);}
void write(HANDLE pipe,const Frame& frame,HANDLE peer,DWORD timeout=6000){
    if(frame.bytes.size()>maximum)throw std::invalid_argument("Broker payload too large");std::vector<std::uint8_t> bytes;
    for(unsigned n:{magic,version,frame.sequence,frame.opcode,frame.status,unsigned(frame.bytes.size())})put32(bytes,n);
    bytes.insert(bytes.end(),frame.bytes.begin(),frame.bytes.end());if(!transfer(pipe,true,bytes,timeout,peer))throw std::runtime_error("Broker write deadline");
}
void request(const Frame& f,unsigned sequence,Op op){
    if(f.sequence!=sequence || f.opcode!=unsigned(op) || f.status || !f.bytes.empty())throw std::runtime_error("Invalid broker handshake/control request");
}
struct Impersonation {
    explicit Impersonation(HANDLE pipe){if(!ImpersonateNamedPipeClient(pipe))fail("Identify broker pipe client");}
    ~Impersonation(){if(!RevertToSelf())std::terminate();}
};
}
struct BrokerListener::State {Handle pipe;std::wstring name;};
BrokerListener::BrokerListener():state_(std::make_unique<State>()){
    std::array<UCHAR,16> random{};if(BCryptGenRandom(nullptr,random.data(),ULONG(random.size()),BCRYPT_USE_SYSTEM_PREFERRED_RNG)<0)throw std::runtime_error("Generate broker endpoint");
    state_->name=L"\\\\.\\pipe\\SL3Broker-";constexpr wchar_t hex[]=L"0123456789abcdef";
    for(auto byte:random){state_->name+=hex[byte>>4];state_->name+=hex[byte&15];}
    Security security;state_->pipe.value=CreateNamedPipeW(state_->name.c_str(),PIPE_ACCESS_DUPLEX|FILE_FLAG_OVERLAPPED|FILE_FLAG_FIRST_PIPE_INSTANCE,
        PIPE_TYPE_MESSAGE|PIPE_READMODE_MESSAGE|PIPE_WAIT|PIPE_REJECT_REMOTE_CLIENTS,1,maximum+24,maximum+24,0,&security.attributes);
    if(state_->pipe.value==INVALID_HANDLE_VALUE)fail("Create private broker endpoint");
}
BrokerListener::~BrokerListener()=default;
const std::wstring& BrokerListener::name() const noexcept{return state_->name;}

class BrokerConnection {
    HANDLE pipe_;RetainedBroker& owner_;Handle client_;std::uint64_t lease_=0;
    std::shared_ptr<const void> audio_reference_;
    bool accepted_=false;
    std::string* diagnostic_;
public:
    BrokerConnection(BrokerListener& listener,RetainedBroker& owner,std::string* diagnostic):pipe_(listener.state_->pipe.value),owner_(owner),diagnostic_(diagnostic){}
    ~BrokerConnection(){if(accepted_)DisconnectNamedPipe(pipe_);}
    BrokerServeResult run(HANDLE stop){
        Handle event;event.value=CreateEventW(nullptr,TRUE,FALSE,nullptr);if(!event.value)fail("Create broker accept event");
        OVERLAPPED operation{};operation.hEvent=event.value;DWORD ignored=0;
        const auto immediate=ConnectNamedPipe(pipe_,&operation);const auto error=GetLastError();
        if(!immediate && (error==ERROR_NO_DATA || error==ERROR_PIPE_NOT_CONNECTED)){
            DisconnectNamedPipe(pipe_);return BrokerServeResult::rejected;
        }
        if(!finish(pipe_,operation,immediate!=FALSE,error,100,nullptr,ignored))return BrokerServeResult::no_client;accepted_=true;
        try{
            const auto hello=read(pipe_,5000,nullptr);if(!hello)throw std::runtime_error("Broker greeting deadline");
            if(hello->sequence!=1 || hello->opcode!=unsigned(Op::hello) || hello->status || device_session::decode_hello(hello->bytes)!=owner_.kind())
                throw std::runtime_error("Broker greeting/worker kind mismatch");
            DWORD pid=0;if(!GetNamedPipeClientProcessId(pipe_,&pid) || !pid || pid==GetCurrentProcessId())throw std::runtime_error("Invalid broker client PID");
            client_.value=OpenProcess(SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION|PROCESS_DUP_HANDLE,FALSE,pid);
            if(!client_.value || WaitForSingleObject(client_.value,0)!=WAIT_TIMEOUT)throw std::runtime_error("Broker client not live");
            const auto owner_identity=process_identity(GetCurrentProcess()),process=process_identity(client_.value);
            {Impersonation impersonate(pipe_);Handle token;if(!OpenThreadToken(GetCurrentThread(),TOKEN_QUERY,TRUE,&token.value))fail("Read pipe identity token");
                if(!same(owner_identity,process) || !same(owner_identity,identity(token.value)))throw std::runtime_error("Broker client token differs from ordinary owner");}
            DWORD again=0;if(!GetNamedPipeClientProcessId(pipe_,&again) || again!=pid)throw std::runtime_error("Broker client identity changed");
            // A pipe-reported PID plus token is insufficient against process-ID
            // reuse. Prove the pipe client can use a fresh event in this exact
            // opened process object. Never close a possibly reused remote value.
            Handle challenge;challenge.value=CreateEventW(nullptr,TRUE,FALSE,nullptr);if(!challenge.value)fail("Create broker process challenge");
            HANDLE remote=nullptr;if(!DuplicateHandle(GetCurrentProcess(),challenge.value,client_.value,&remote,EVENT_MODIFY_STATE,FALSE,0))fail("Grant broker process challenge");
            Frame challenge_reply{1,unsigned(Op::hello),0,{}};put_handle(challenge_reply.bytes,remote);write(pipe_,challenge_reply,client_.value);
            const auto proof=read(pipe_,5000,client_.value);if(!proof)throw std::runtime_error("Broker process proof deadline");request(*proof,2,Op::proof);
            if(WaitForSingleObject(challenge.value,0)!=WAIT_OBJECT_0 || WaitForSingleObject(client_.value,0)!=WAIT_TIMEOUT)
                throw std::runtime_error("Broker process challenge not satisfied");
            lease_=owner_.attach(client_.value);if(!lease_)throw std::runtime_error("Client exited during broker admission");
            HANDLE worker=nullptr;if(!DuplicateHandle(GetCurrentProcess(),owner_.worker_process_handle(),client_.value,&worker,
                SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,0))fail("Grant worker wait reference");
            Frame admitted{2,unsigned(Op::proof),0,{}};put_handle(admitted.bytes,worker);
            const auto kind=device_session::encode_hello(owner_.kind());admitted.bytes.insert(admitted.bytes.end(),kind.begin(),kind.end());
            const auto snapshot=device_session::encode_snapshot(owner_.report().device);admitted.bytes.insert(admitted.bytes.end(),snapshot.begin(),snapshot.end());write(pipe_,admitted,client_.value);
            unsigned sequence=3;
            for(;;){
                if(WaitForSingleObject(stop,0)!=WAIT_TIMEOUT){owner_.abandon();return BrokerServeResult::stopped;}
                owner_.poll_client();const auto state=owner_.report();
                if(state.failed || state.phase==BrokerPhase::closed)return BrokerServeResult::owner_failed;
                if(!state.client_attached){lease_=0;return BrokerServeResult::detached;}
                const auto frame=read(pipe_,50,client_.value);if(!frame)continue;
                if(frame->sequence!=sequence++ || !sequence || frame->status)throw std::runtime_error("Broker request sequence/status mismatch");
                device_session::Snapshot result;
                if(frame->opcode==unsigned(Op::start)){
                    if(frame->bytes.size()<8)throw std::runtime_error("Missing client mapping reference");
                    const auto start=device_session::decode_start({frame->bytes.begin()+8,frame->bytes.end()});
                    auto reference=Mailbox::hold_audio_reference(client_.value,get_handle(frame->bytes),start.audio_channel);
                    result=owner_.start(lease_,start);audio_reference_=std::move(reference);
                }else{
                    if(!frame->bytes.empty())throw std::runtime_error("Unexpected broker command payload");
                    if(frame->opcode==unsigned(Op::clock)){owner_.clock(lease_);result=owner_.report().device;}
                    else if(frame->opcode==unsigned(Op::stop)){result=owner_.stop(lease_);audio_reference_.reset();}
                    else if(frame->opcode==unsigned(Op::detach)){
                        if(!owner_.detach(lease_))throw std::runtime_error("Broker detach failed");lease_=0;audio_reference_.reset();result=owner_.report().device;
                    }else throw std::runtime_error("Unsupported broker operation");
                }
                write(pipe_,{frame->sequence,frame->opcode,0,device_session::encode_snapshot(result)},client_.value);
                if(frame->opcode==unsigned(Op::detach)){
                    // DisconnectNamedPipe discards unread replies. Require the
                    // client's terminal acknowledgement, never an unbounded flush.
                    const auto ack=read(pipe_,5000,client_.value);
                    if(!ack)throw std::runtime_error("Broker detach acknowledgement deadline");
                    request(*ack,sequence,Op::detach);return BrokerServeResult::detached;
                }
            }
        }catch(...){
            if(diagnostic_)try{throw;}catch(const std::exception& e){*diagnostic_=e.what();}catch(...){*diagnostic_="Unknown broker connection failure";}
            // Pipe handles can close during process teardown before the process
            // object signals. For an idle lease only, observe that exact object
            // for at most one second; never infer death from a broken pipe.
            if(lease_ && owner_.report().phase==BrokerPhase::leased && client_.value)WaitForSingleObject(client_.value,1000);
            owner_.poll_client();const auto s=owner_.report();
            if(lease_ && s.client_attached)owner_.abandon();
            return owner_.report().failed?BrokerServeResult::owner_failed:BrokerServeResult::rejected;
        }
    }
};
BrokerServeResult serve_broker_client(BrokerListener& listener,RetainedBroker& owner,HANDLE stop,std::string* diagnostic){
    if(diagnostic)diagnostic->clear();
    if(!stop)throw std::invalid_argument("Explicit broker stop event required");
    if(WaitForSingleObject(stop,0)!=WAIT_TIMEOUT)return BrokerServeResult::stopped;
    BrokerConnection connection(listener,owner,diagnostic);return connection.run(stop);
}

struct BrokerClient::State {
    Handle pipe,server,worker;bool attached=false;unsigned sequence=3;
    device_session::Snapshot observed;
    Frame exchange(Op op,const std::vector<std::uint8_t>& bytes={},DWORD timeout=7000){
        if(!attached || !sequence)throw std::runtime_error("Broker client is detached/sealed");
        if(!timeout || timeout>7000)throw std::invalid_argument("Broker client command needs a bounded deadline");
        const auto deadline=GetTickCount64()+timeout;
        const auto current=sequence++;
        try{
            write(pipe.value,{current,unsigned(op),0,bytes},server.value,remaining(deadline));
            const auto reply=read(pipe.value,remaining(deadline),server.value);
            if(!reply || reply->sequence!=current || reply->opcode!=unsigned(op) || reply->status)throw std::runtime_error("Broker reply unavailable/mismatched");return *reply;
        }catch(...){attached=false;throw;}
    }
    device_session::Snapshot command(Op op,const std::vector<std::uint8_t>& bytes={},DWORD timeout=7000){
        try{
            observed=device_session::decode_snapshot(exchange(op,bytes,timeout).bytes);
            if(observed.failure!=session::Failure::none || observed.stream_fault!=StreamFault::none || observed.device_released ||
               (op==Op::start?(observed.phase!=device_session::Phase::running || observed.io_retired):
                (observed.phase!=device_session::Phase::ready || !observed.io_retired)))
                throw std::runtime_error("Broker reply does not confirm requested held state");
            return observed;
        }
        catch(...){attached=false;throw;}
    }
};
BrokerClient::BrokerClient(const std::wstring& name,HANDLE expected,session::Kind expected_kind):state_(std::make_unique<State>()){
    if(!endpoint(name) || (expected_kind!=session::Kind::native && expected_kind!=session::Kind::simulated))throw std::invalid_argument("Invalid explicit broker endpoint/kind");
    if(!DuplicateHandle(GetCurrentProcess(),expected,GetCurrentProcess(),&state_->server.value,SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,0))fail("Retain exact broker process reference");
    if(WaitForSingleObject(state_->server.value,0)!=WAIT_TIMEOUT || !same(process_identity(GetCurrentProcess()),process_identity(state_->server.value)))throw std::runtime_error("Broker server is not a live ordinary-user peer");
    // Wait for this explicit pipe instance to accept a client, not for USB
    // recovery. One CreateFile follows; no process launch or reconnect loop.
    if(!WaitNamedPipeW(name.c_str(),2000))fail("Wait for explicit broker endpoint availability");
    if(WaitForSingleObject(state_->server.value,0)!=WAIT_TIMEOUT)throw std::runtime_error("Expected broker exited before connection");
    state_->pipe.value=CreateFileW(name.c_str(),GENERIC_READ|GENERIC_WRITE,0,nullptr,OPEN_EXISTING,
        FILE_FLAG_OVERLAPPED|SECURITY_SQOS_PRESENT|SECURITY_IDENTIFICATION,nullptr);
    if(state_->pipe.value==INVALID_HANDLE_VALUE)fail("Connect explicit broker endpoint");
    DWORD mode=PIPE_READMODE_MESSAGE;if(!SetNamedPipeHandleState(state_->pipe.value,&mode,nullptr,nullptr))fail("Set broker message mode");
    ULONG pid=0;if(!GetNamedPipeServerProcessId(state_->pipe.value,&pid) || pid!=GetProcessId(state_->server.value) || WaitForSingleObject(state_->server.value,0)!=WAIT_TIMEOUT)
        throw std::runtime_error("Broker endpoint does not belong to expected process");
    write(state_->pipe.value,{1,unsigned(Op::hello),0,device_session::encode_hello(expected_kind)},state_->server.value);
    const auto challenge=read(state_->pipe.value,7000,state_->server.value);
    if(!challenge || challenge->sequence!=1 || challenge->opcode!=unsigned(Op::hello) || challenge->status || challenge->bytes.size()!=8)throw std::runtime_error("Invalid broker challenge");
    {Handle event;event.value=get_handle(challenge->bytes);if(!SetEvent(event.value))fail("Answer broker process challenge");}
    write(state_->pipe.value,{2,unsigned(Op::proof),0,{}},state_->server.value);
    const auto reply=read(state_->pipe.value,7000,state_->server.value);
    constexpr std::size_t hello_size=40;
    if(!reply || reply->sequence!=2 || reply->opcode!=unsigned(Op::proof) || reply->status || reply->bytes.size()<8+hello_size)throw std::runtime_error("Broker admission failed");
    state_->worker.value=get_handle(reply->bytes);
    if(!GetProcessId(state_->worker.value) || WaitForSingleObject(state_->worker.value,0)!=WAIT_TIMEOUT)throw std::runtime_error("Invalid broker worker wait reference");
    if(device_session::decode_hello({reply->bytes.begin()+8,reply->bytes.begin()+8+hello_size})!=expected_kind)throw std::runtime_error("Broker worker kind mismatch");
    state_->observed=device_session::decode_snapshot({reply->bytes.begin()+8+hello_size,reply->bytes.end()});
    if(state_->observed.phase!=device_session::Phase::ready || !state_->observed.io_retired || state_->observed.device_released ||
       state_->observed.failure!=session::Failure::none || state_->observed.stream_fault!=StreamFault::none)throw std::runtime_error("Broker admission state is not idle/held");
    state_->attached=true;
}
BrokerClient::~BrokerClient(){if(state_ && state_->attached)try{detach();}catch(...){}}
unsigned BrokerClient::clock(){return state_->command(Op::clock).rate_hz;}
device_session::Snapshot BrokerClient::start(Mailbox& audio,StreamConfig config){
    std::vector<std::uint8_t> bytes;put_handle(bytes,audio.mapping_handle());const auto start=device_session::encode_start({config,audio.name()});bytes.insert(bytes.end(),start.begin(),start.end());
    const auto result=state_->command(Op::start,bytes);
    if(result.rate_hz!=config.rate_hz || result.intervals!=config.intervals){state_->attached=false;throw std::runtime_error("Broker started a different stream mode");}return result;
}
device_session::Snapshot BrokerClient::stop(DWORD timeout){return state_->command(Op::stop,{},timeout);}
device_session::Snapshot BrokerClient::detach(DWORD timeout){
    if(!timeout || timeout>7000)throw std::invalid_argument("Broker detach needs a bounded deadline");
    const auto deadline=GetTickCount64()+timeout;
    const auto s=state_->command(Op::detach,{},timeout);state_->attached=false;
    if(!state_->sequence)throw std::runtime_error("Broker detach acknowledgement sequence exhausted");
    write(state_->pipe.value,{state_->sequence++,unsigned(Op::detach),0,{}},state_->server.value,remaining(deadline));
    try{
        (void)read(state_->pipe.value,remaining(deadline),state_->server.value);
        throw std::runtime_error("Broker detach did not end the connection");
    }catch(const PipeError& e){
        if(e.code!=ERROR_BROKEN_PIPE && e.code!=ERROR_PIPE_NOT_CONNECTED && e.code!=ERROR_NO_DATA)throw;
    }
    return s;
}
void BrokerClient::disconnect() noexcept {
    state_->attached=false;if(state_->pipe.value && state_->pipe.value!=INVALID_HANDLE_VALUE)CloseHandle(state_->pipe.value);state_->pipe.value=nullptr;
}
const device_session::Snapshot& BrokerClient::observation() const noexcept{return state_->observed;}
HANDLE BrokerClient::worker_process_handle() const noexcept{return state_->worker.value;}
}
