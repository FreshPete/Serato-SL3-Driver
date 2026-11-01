#include "windows/usbdk_stream.hpp"
#include "windows/continuous_peer.hpp"
#include "windows/worker_process.hpp"
#include <atomic>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <new>
#include <stdexcept>

using namespace sl3;
using namespace sl3::worker;
static std::atomic<std::size_t> allocations{0};
void* operator new(std::size_t n){allocations.fetch_add(1);if(auto* p=std::malloc(n?n:1))return p;throw std::bad_alloc();}
void* operator new[](std::size_t n){return ::operator new(n);}
void operator delete(void* p) noexcept{std::free(p);}
void operator delete[](void* p) noexcept{std::free(p);}
void operator delete(void* p,std::size_t) noexcept{std::free(p);}
void operator delete[](void* p,std::size_t) noexcept{std::free(p);}
static void require(bool good,const char* message){if(!good)throw std::runtime_error(message);}
static HANDLE redirect_handle(){return reinterpret_cast<HANDLE>(0x1111);}
static HANDLE system_handle(){return reinterpret_cast<HANDLE>(0x2222);}
static std::uint8_t count(std::uint64_t batch,unsigned p){return std::uint8_t(1+(batch+p)%7);}
static std::uint8_t byte(std::uint64_t batch,unsigned p,std::size_t k){return std::uint8_t(batch*17+p*13+k);}
struct Harness {
    struct Entry {USB_DK_TRANSFER_REQUEST* request=nullptr;OVERLAPPED* overlapped=nullptr;DWORD error=0;};
    std::array<Entry,8> entries{};
    std::uint64_t input=0,output=0,ticks=100000;
    TransferResult mode=TransferSuccessAsync;
    bool auto_complete=true,bad=false,reset_failure=false,wait_failure=false,cancel_not_found=false,close_failure=false;
    unsigned creates=0,closes=0,reset_calls=0,result_calls=0,cancel_calls=0,fail_create=~0u;
    unsigned locate(USB_DK_TRANSFER_REQUEST* req,OVERLAPPED* ov,bool out){
        const unsigned begin=out?4:0,end=out?8:4;
        for(unsigned i=begin;i<end;++i)if(entries[i].request==req){if(entries[i].overlapped!=ov)bad=true;return i;}
        for(unsigned i=begin;i<end;++i)if(!entries[i].request){entries[i]={req,ov,0};return i;}
        bad=true;return begin;
    }
    Entry* find(OVERLAPPED* ov){for(auto& e:entries)if(e.overlapped==ov)return &e;bad=true;return nullptr;}
    void complete(unsigned slot,DWORD error=0){entries[slot].error=error;SetEvent(entries[slot].overlapped->hEvent);}
};
static Harness* h=nullptr;
static HANDLE WINAPI create_event(LPSECURITY_ATTRIBUTES security,BOOL manual,BOOL initial,LPCWSTR name){
    if(security || !manual || initial || name)h->bad=true;
    if(h->creates++==h->fail_create){SetLastError(ERROR_NOT_ENOUGH_MEMORY);return nullptr;}
    return CreateEventW(nullptr,TRUE,FALSE,nullptr);
}
static BOOL WINAPI reset_event(HANDLE event){++h->reset_calls;if(h->reset_failure){SetLastError(ERROR_ACCESS_DENIED);return FALSE;}return ResetEvent(event);}
static BOOL WINAPI close_handle(HANDLE event){
    if(event==redirect_handle() || event==system_handle())h->bad=true;
    if(h->close_failure){SetLastError(ERROR_INVALID_HANDLE);return FALSE;}
    const auto ok=CloseHandle(event);if(ok)++h->closes;return ok;
}
static DWORD WINAPI wait_event(HANDLE event,DWORD ms){
    if(ms)h->bad=true;if(h->wait_failure){SetLastError(ERROR_INVALID_HANDLE);return WAIT_FAILED;}return WaitForSingleObject(event,ms);
}
static BOOL WINAPI result(HANDLE handle,LPOVERLAPPED ov,LPDWORD bytes,BOOL waiting){
    ++h->result_calls;if(handle!=system_handle() || waiting || !bytes)h->bad=true;
    const auto* entry=h->find(ov);if(!entry){SetLastError(ERROR_INVALID_PARAMETER);return FALSE;}
    if(entry->error){SetLastError(entry->error);return FALSE;}
    ov->Internal=0x55;ov->InternalHigh=123;*bytes=123;return TRUE;
}
static BOOL WINAPI cancel(HANDLE handle,LPOVERLAPPED ov){
    ++h->cancel_calls;if(handle!=system_handle())h->bad=true;
    auto* entry=h->find(ov);if(!entry){SetLastError(ERROR_INVALID_PARAMETER);return FALSE;}
    if(h->cancel_not_found){SetLastError(ERROR_NOT_FOUND);return FALSE;}
    entry->error=ERROR_OPERATION_ABORTED;SetEvent(ov->hEvent);return TRUE;
}
static BOOL WINAPI counter(LARGE_INTEGER* value){value->QuadPart=static_cast<LONGLONG>(h->ticks);return TRUE;}
static BOOL WINAPI frequency(LARGE_INTEGER* value){value->QuadPart=10000000;return TRUE;}
static TransferResult transfer(HANDLE handle,PUSB_DK_TRANSFER_REQUEST req,LPOVERLAPPED ov,bool output){
    if(handle!=redirect_handle() || !ov || !ov->hEvent || ov->Internal || ov->InternalHigh || ov->Offset || ov->OffsetHigh ||
       WaitForSingleObject(ov->hEvent,0)!=WAIT_TIMEOUT || req->EndpointAddress!=(output?6u:0x82u) || req->TransferType!=IsochronousTransferType ||
       req->IsochronousPacketsArraySize<8 || req->IsochronousPacketsArraySize>64 || req->IsochronousPacketsArraySize%8)h->bad=true;
    const auto slot=h->locate(req,ov,output);h->entries[slot].error=0;
    if(h->mode==TransferFailure){SetLastError(ERROR_GEN_FAILURE);return TransferFailure;}
    auto* lengths=static_cast<ULONG64*>(req->IsochronousPacketsArray);
    auto* packets=static_cast<USB_DK_ISO_TRANSFER_RESULT*>(req->Result.IsochronousResultsArray);
    auto* pcm=static_cast<std::uint8_t*>(req->Buffer);
    if(req->Result.GenResult.UsbdStatus || req->Result.GenResult.BytesTransferred)h->bad=true;
    for(unsigned p=0;p<64;++p)if(packets[p].ActualLength || packets[p].TransferResult)h->bad=true;
    const auto batch=output?h->output++:h->input++;
    const auto intervals=static_cast<unsigned>(req->IsochronousPacketsArraySize);std::size_t offset=0;
    for(unsigned p=0;p<intervals;++p){
        const auto bytes=unsigned(count(batch,p))*18;
        if(lengths[p]!=(output?bytes:126u))h->bad=true;
        if(output){for(unsigned k=0;k<bytes;++k)if(pcm[offset++]!=byte(batch,p,k))h->bad=true;}
        else{for(unsigned k=0;k<bytes;++k)pcm[p*126+k]=byte(batch,p,k);}
        packets[p].ActualLength=output?~ULONG64(0):bytes; // Deliberately meaningless OUT lengths.
    }
    if(req->BufferLength!=(output?offset:intervals*126))h->bad=true;
    if(h->mode==TransferSuccessAsync && h->auto_complete)SetEvent(ov->hEvent);
    return h->mode;
}
static TransferResult read_pipe(HANDLE handle,PUSB_DK_TRANSFER_REQUEST req,LPOVERLAPPED ov){return transfer(handle,req,ov,false);}
static TransferResult write_pipe(HANDLE handle,PUSB_DK_TRANSFER_REQUEST req,LPOVERLAPPED ov){return transfer(handle,req,ov,true);}
static OverlappedApi boundary(){OverlappedApi win;win.create_event=create_event;win.reset_event=reset_event;win.close_handle=close_handle;
    win.wait=wait_event;win.result=result;win.cancel=cancel;win.counter=counter;win.frequency=frequency;return win;}
static std::unique_ptr<UsbDkStreamBackend> backend(Harness& state){h=&state;return std::make_unique<UsbDkStreamBackend>(UsbDkStreamApi{read_pipe,write_pipe},redirect_handle(),system_handle(),boundary());}
static AudioBlock block(unsigned intervals=8){
    AudioBlock value;value.packet_count=intervals;value.reported_rate_hz=44100;std::size_t offset=0;
    for(unsigned p=0;p<intervals;++p){value.frames_per_packet[p]=count(0,p);for(unsigned k=0;k<unsigned(count(0,p))*18;++k)value.pcm[offset++]=byte(0,p,k);}
    return value;
}
static void basic(){
    Harness state;auto io=backend(state);require(io->valid() && io->now_ns()==10000000,"Validated function table, borrowed handles and integer QPC conversion");
    require(!io->prepare(8,8) && !io->prepare(0,9) && !state.creates,"Bad preparation makes no event/resource");
    require(io->prepare(0,8) && !io->prepare(0,8),"Prepare once only");
    state.auto_complete=false;require(io->submit_input(0,false),"Native asynchronous IN accepted");
    require(!io->immediate_poll() && io->pending_event(0)==state.entries[0].overlapped->hEvent && !io->pending_event(8),"Borrowed event wait covers only valid pending native leases");
    const auto requests=state.input;StreamInput snapshot;snapshot.packet_count=999;
    require(!io->submit_input(0,true) && !io->release(0) && state.input==requests &&
            io->poll(0,&snapshot)==StreamPoll::pending && snapshot.packet_count==999,"Pending lease blocks rearm/release and leaves snapshot unchanged");
    state.complete(0,ERROR_IO_INCOMPLETE);require(io->poll(0,&snapshot)==StreamPoll::pending,"Signalled event alone cannot prove completion");
    state.complete(0,ERROR_INVALID_HANDLE);require(io->poll(0,&snapshot)==StreamPoll::unproven && snapshot.packet_count==999 &&
            !io->release(0),"Failed observation keeps the same lease and caller output");
    state.complete(0);require(io->poll(0,&snapshot)==StreamPoll::success && snapshot.packet_count==8,"Recovered observation proves terminal IN");
    for(unsigned p=0;p<8;++p){require(snapshot.packets[p].length==unsigned(count(0,p))*18,"Full-width packet result");
        for(unsigned k=0;k<unsigned(count(0,p))*18;++k)require(snapshot.pcm[p*126+k]==byte(0,p,k),"Native snapshot keeps fixed-stride actual data");}
    require(io->submit_input(0,true),"Terminal slot rearms with same stable addresses and cleared OVERLAPPED/event/results");
    state.cancel_not_found=true;require(!io->cancel(0) && io->last_error()==ERROR_NOT_FOUND && io->poll(0,nullptr)==StreamPoll::pending &&
            !io->release(0),"Cancel-not-found is neither terminal proof nor permission to free");
    state.cancel_not_found=false;require(io->cancel(0) && io->poll(0,nullptr)==StreamPoll::failure && io->release(0),"Cancelled status observed before event/storage release");
    require(state.creates==state.closes && !state.bad,"Exact handles, parameters and lifetime at the Windows boundary");
}
static void output_and_errors(){
    Harness state;auto io=backend(state);require(io->prepare(4,8),"Prepare output");auto pcm=block();
    auto invalid=pcm;invalid.frames_per_packet[8]=1;
    require(!io->submit_output(4,invalid,false) && !state.output,"Reject inactive output metadata before native call");
    require(io->submit_output(4,pcm,false),"Packed variable OUT lengths accepted");
    const auto* retained=static_cast<const std::uint8_t*>(state.entries[4].request->Buffer);
    require(retained!=pcm.pcm.data(),"Output points at private native storage");pcm.pcm.fill(0xee);
    require(retained[0]==byte(0,0,0),"Caller may immediately reuse its buffer after copy");
    require(io->poll(4,nullptr)==StreamPoll::success && io->release(4),"Meaningless full-width OUT ActualLength ignored on successful statuses");
    require(!state.bad && state.creates==state.closes,"Native variable-packet OUT shape exact");
    for(unsigned kind=0;kind<4;++kind){
        Harness errors;auto native=backend(errors);require(native->prepare(kind>=2?4:0,8),"Prepare error case");
        if(kind>=2){auto out=block();require(native->submit_output(4,out,false),"Submit output error case");}
        else require(native->submit_input(0,false),"Submit input error case");
        const auto index=kind>=2?4u:0u;auto* req=errors.entries[index].request;
        if(kind%2==0)req->Result.GenResult.UsbdStatus=ULONG64(1)<<32;
        else static_cast<USB_DK_ISO_TRANSFER_RESULT*>(req->Result.IsochronousResultsArray)[0].TransferResult=ULONG64(1)<<32;
        StreamInput raw;const auto polled=native->poll(index,kind>=2?nullptr:&raw);
        require(polled==(kind==1?StreamPoll::success:StreamPoll::failure),"Aggregate/OUT packet errors tested without truncation");
        if(kind==1)require(raw.packets[0].status==(ULONG64(1)<<32),"IN packet status preserved for core validation");
        require(native->release(index) && !errors.bad,"Terminal error still permits safe release");
    }
}
static void preparation_and_sync(){
    Harness state;auto io=backend(state);state.fail_create=0;
    require(!io->prepare(0,8) && io->last_error()==ERROR_NOT_ENOUGH_MEMORY && !state.closes,"Failed event creation owns no resource");
    state.fail_create=~0u;require(io->prepare(0,8),"Retry preparation after no-lease failure");
    state.reset_failure=true;require(!io->submit_input(0,false) && !state.input,"Reset failure submits no native I/O");
    state.reset_failure=false;state.mode=TransferFailure;
    require(!io->submit_input(0,false) && io->last_error()==ERROR_GEN_FAILURE,"Known helper rejection acquires no pending lease");
    state.mode=TransferSuccess;require(io->submit_input(0,false) && io->immediate_poll() && !io->pending_event(0) && io->poll(0,nullptr)==StreamPoll::success && !state.result_calls,
        "Synchronous native success needs no asynchronous observation");
    state.mode=TransferSuccessAsync;require(io->submit_input(0,true),"Reuse after synchronous completion");
    state.wait_failure=true;require(io->poll(0,nullptr)==StreamPoll::unproven && !io->release(0),"Wait failure cannot clear ownership");
    state.wait_failure=false;require(io->poll(0,nullptr)==StreamPoll::success && io->release(0) && !state.bad,"Same event/request observation can recover");
    // Exercise the real default event and QPC functions, without a transfer.
    UsbDkStreamBackend real_clock({read_pipe,write_pipe},redirect_handle(),system_handle());
    const auto before=real_clock.now_ns();require(real_clock.valid() && before && real_clock.prepare(0,8) &&
        real_clock.release(0) && real_clock.now_ns()>=before,"Default Windows event/monotonic-clock smoke check, no USB calls");
}
static void pipeline(){
    for(unsigned rate:{44100u,48000u})for(unsigned intervals:{8u,64u}){
        Harness state;auto io=backend(state);auto host=Mailbox::create();auto worker=Mailbox::open(host->name());MailboxStreamPeer peer(*worker);
        ContinuousStream stream(*io,peer);require(stream.start({rate,intervals,20,2}),"Start actual adapter/engine/shared-queue software path");
        const auto allocated=allocations.load();AudioBlock data;
        for(unsigned n=0;n<500;++n){
            state.ticks+=1000;require(stream.step()==StreamState::running,"Native-boundary simulation keeps rearming");
            for(;;){const auto got=host->try_pop_audio(AudioDirection::input,data);if(got==AudioResult::empty)break;
                require(got==AudioResult::ok && data.reported_rate_hz==rate && data.packet_count==intervals &&
                        host->try_push_audio(AudioDirection::output,data)==AudioResult::ok,"Copy exact completed input schedule/PCM through both checked queues");}
        }
        require(allocations.load()==allocated,"No C++ allocations in native adapter/engine/real shared queues after preparation");
        require(stream.stats().input_blocks==2000 && stream.stats().output_submissions==1996 && !state.bad,
                "2,000 input/1,996 native output batches per shape; every output byte checked at helper boundary");
        stream.stop();require(stream.step()==StreamState::stopped && !stream.stats().retained_mask && state.creates==8 && state.closes==8,
                "All eight native events/storage leases retire on software stop");
    }
    auto host=Mailbox::create();MailboxStreamPeer wrong(*host);AudioBlock data;
    require(wrong.publish_input(data)==StreamExchange::failure && wrong.receive_output(data)==StreamExchange::failure,
            "Worker peer wrapper cannot silently accept wrong mailbox role");
}
static int child(const std::wstring& mode){
    Harness state;auto io=backend(state);
    if(mode==L"--die-release"){require(io->prepare(0,8),"Prepare failed release child");state.close_failure=true;require(!io->release(0),"Close failure retained");}
    else{
        state.auto_complete=false;
        if(mode==L"--die-unknown")state.mode=static_cast<TransferResult>(99);
        require(io->prepare(0,8) && io->submit_input(0,false),"Child accepted/uncertain lease");
        if(mode==L"--die-observation"){state.complete(0,ERROR_INVALID_HANDLE);require(io->poll(0,nullptr)==StreamPoll::unproven,"Unproved observation child");}
    }
    io.reset();return 99; // Destructor MUST contain this isolated process first.
}
int wmain(int argc,wchar_t** argv){
    try{
        if(argc==2)return child(argv[1]);require(argc==1,"Unexpected arguments");
        basic();output_and_errors();preparation_and_sync();pipeline();
        const auto self=std::filesystem::absolute(argv[0]);const auto hash=Process::executable_sha256(self);
        for(const auto* mode:{L"--die-pending",L"--die-unknown",L"--die-observation",L"--die-release"}){
            Process worker;worker.launch(self,hash,{mode});require(worker.wait_for_exit(2000) && worker.observe().exit_code==70,
                "Unproved native lease/release contains only its isolated process");
            require(worker.terminate_and_wait().state.job_empty,"Contained test worker leaves no descendant");
        }
        std::cout<<"Native UsbDk/Windows adapter: 8,000 input + 7,984 output batches through actual shared queues with simulated helper I/O, stable request reuse, zero measured C++ allocations and four isolated fail-stop cases passed; no USB/helper loaded\n";
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
