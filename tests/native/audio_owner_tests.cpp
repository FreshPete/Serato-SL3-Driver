#include "asio/audio_owner.hpp"
#include "core/session_protocol.hpp"
#include <atomic>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <new>
#include <stdexcept>

using namespace sl3;
using namespace sl3::asio;
using namespace sl3::worker;
static std::atomic<std::size_t> allocations{0};
void* operator new(std::size_t n){allocations.fetch_add(1);if(auto* p=std::malloc(n?n:1))return p;throw std::bad_alloc();}
void* operator new[](std::size_t n){return ::operator new(n);}
void operator delete(void* p) noexcept{std::free(p);}
void operator delete[](void* p) noexcept{std::free(p);}
void operator delete(void* p,std::size_t) noexcept{std::free(p);}
void operator delete[](void* p,std::size_t) noexcept{std::free(p);}
static void require(bool good,const char* message){if(!good)throw std::runtime_error(message);}
struct Event {HANDLE value=CreateEventW(nullptr,TRUE,FALSE,nullptr);Event(){require(value!=nullptr,"Test event");}~Event(){CloseHandle(value);}};
struct Host {
    std::array<ASIOBufferInfo,12> info{};
    Event entered,release;
    std::atomic<unsigned> calls{0};std::atomic<bool> bad{false};
    bool block=false,throws=false;unsigned intervals=8;AudioOwner* owner=nullptr;BufferLease* buffers=nullptr;
    Host(){for(long c=0;c<6;++c){info[std::size_t(c)]={ASIOTrue,c,{}};info[std::size_t(6+c)]={ASIOFalse,c,{}};}}
};
static Host* host=nullptr;
static void callback(long bank,ASIOBool direct){
    auto& h=*host;const auto number=h.calls.load();
    if(direct!=ASIOTrue || bank!=long(number%2))h.bad=true;
    if(h.owner){const auto observation=h.owner->observation();
        if(!observation.valid || observation.bank!=unsigned(bank) || observation.first_frame!=std::uint64_t(number)*64 ||
           !h.owner->stop(0).reentrant || h.buffers->dispose()!=ASE_InvalidMode)h.bad=true;}
    SetEvent(h.entered.value);
    if(h.throws)throw std::runtime_error("Deliberate host callback exception");
    if(h.block)WaitForSingleObject(h.release.value,INFINITE);
    for(unsigned c=0;c<6;++c){
        const auto* input=static_cast<const std::uint8_t*>(h.info[c].buffers[bank]);
        for(unsigned frame=0;frame<64;++frame){
            const auto position=std::uint64_t(number)*64+frame,batch=position/(h.intervals*6),packet=(position%(h.intervals*6))/6,within=position%6;
            for(unsigned b=0;b<3;++b)if(input[frame*3+b]!=std::uint8_t(batch*17+packet*13+within*18+c*3+b))h.bad=true;
        }
        std::memcpy(h.info[6+c].buffers[bank],h.info[5-c].buffers[bank],64*3);
    }
    h.calls.fetch_add(1);
}
static ASIOCallbacks callbacks(){ASIOCallbacks value{};value.bufferSwitch=callback;return value;}
struct Link {
    std::shared_ptr<Mailbox> channel{Mailbox::create()};std::shared_ptr<Process> process=std::make_shared<Process>();
    Link(const std::filesystem::path& fixture){process->launch(fixture,Process::executable_sha256(fixture),{channel->name(),L"normal"});
        require(session::decode_hello(call(session::Command::hello).bytes)==session::Kind::simulated,"Explicit simulated target");}
    Message call(session::Command command,const std::vector<std::uint8_t>& body={}){
        require(channel->send(std::uint32_t(command),body.data(),body.size()),"Send owner lifecycle command");Message result;
        require(channel->await_reply(process->process_handle(),2000,result)==MessageResult::ok && result.status==0,"Owner lifecycle reply");return result;
    }
    void start(unsigned intervals=8){call(session::Command::start,session::encode_start({48000,intervals,1000,20}));}
    void stop(){const auto snapshot=session::decode_snapshot(call(session::Command::stop).bytes);require(snapshot.io_retired && snapshot.device_released,"Worker retirement is separate from host callback retirement");}
    void quit(){call(session::Command::quit);require(process->wait_for_exit(2000) && process->terminate_and_wait().state.job_empty,"Worker retired normally");}
};
struct Release {
    Host& h;AudioOwner& owner;
    ~Release(){SetEvent(h.release.value);owner.stop(2000);}
};
static void normal(const std::filesystem::path& fixture){
    auto buffers=std::make_shared<BufferLease>();Host h;host=&h;const auto cb=callbacks();h.buffers=buffers.get();
    require(buffers->create(h.info.data(),12,64,&cb)==ASE_OK,"Prepare stable SDK planes");const auto stable=h.info[0].buffers[0];
    for(unsigned cycle=0;cycle<2;++cycle){
        Link link(fixture);h.calls=0;AudioOwner owner(buffers,link.channel,link.process);h.owner=&owner;Release release{h,owner};
        require(owner.start(48000),"Audio thread prepared before worker start");link.start();
        require(WaitForSingleObject(h.entered.value,2000)==WAIT_OBJECT_0,"SDK host callback reached");
        const auto before=allocations.load();Sleep(50);require(allocations.load()==before,"Steady audio-owner/callback path observes zero C++ allocations");
        require(buffers->dispose()==ASE_InvalidMode,"Live buffers cannot be disposed");
        owner.request_stop();link.stop();const auto report=owner.stop(2000);
        require(report.retired && !report.active_callbacks && report.exit==AudioExit::stopped && report.callbacks_started==report.callbacks_completed &&
                report.callbacks_completed>0 && report.published_frames>0 && !h.bad && h.info[0].buffers[0]==stable,"Dedicated thread, SDK callback mapping, reentry guard and completed retirement");
        link.quit();ResetEvent(h.entered.value);
    }
    h.owner=nullptr;require(buffers->dispose()==ASE_OK,"Stable planes disposed only after both fresh sessions retire");
}
static void blocked(const std::filesystem::path& fixture){
    auto buffers=std::make_shared<BufferLease>();Host h;host=&h;h.block=true;h.intervals=64;h.buffers=buffers.get();const auto cb=callbacks();
    require(buffers->create(h.info.data(),12,64,&cb)==ASE_OK,"Prepare blocked callback planes");Link link(fixture);
    AudioOwner owner(buffers,link.channel,link.process);h.owner=&owner;Release release{h,owner};require(owner.start(48000),"Begin blocked owner");link.start(64);
    require(WaitForSingleObject(h.entered.value,2000)==WAIT_OBJECT_0,"Host callback deliberately blocked");owner.request_stop();link.stop();
    const auto pending=owner.stop(20);require(!pending.retired && pending.active_callbacks==1 && buffers->dispose()==ASE_InvalidMode,
        "Worker cleanup cannot release buffers belonging to an executing host callback");
    SetEvent(h.release.value);const auto done=owner.stop(2000);
    require(done.retired && !done.active_callbacks && done.callbacks_started==1 && done.callbacks_completed==1 && h.calls==1 && !h.bad,
        "No additional callback lease after stop, including remaining switches within the same large batch");link.quit();require(buffers->dispose()==ASE_OK,"Release blocked planes after actual retirement");
}
static void faults(const std::filesystem::path& fixture){
    for(bool throwing:{false,true}){
        auto buffers=std::make_shared<BufferLease>();Host h;host=&h;h.throws=throwing;h.buffers=buffers.get();const auto cb=callbacks();
        require(buffers->create(h.info.data(),12,64,&cb)==ASE_OK,"Prepare fault case");Link link(fixture);AudioOwner owner(buffers,link.channel,link.process);h.owner=&owner;Release release{h,owner};
        require(owner.start(48000),"Prepare fault audio thread");
        if(throwing){link.start();require(WaitForSingleObject(h.entered.value,2000)==WAIT_OBJECT_0,"Throwing callback reached");}
        else link.process->terminate_and_wait(2000);
        const auto begin=GetTickCount64();while(!owner.report().retired){require(GetTickCount64()-begin<2000,"Bounded host fault retirement");Sleep(1);}
        const auto report=owner.report();
        require(report.retired && !report.active_callbacks && report.exit==(throwing?AudioExit::pump_fault:AudioExit::worker_exited),"Fault stops host processing without terminating host");
        if(throwing)require(report.pump_failure.bridge==BridgeStatus::callback_failure && report.callbacks_started==1 && !report.callbacks_completed,"Throwing callback releases its lease and preserves cause");
        require(link.process->wait_for_exit(2000) && link.process->terminate_and_wait().state.job_empty && buffers->dispose()==ASE_OK,"Faulted thread, worker and buffers retire independently");
    }
}
template<class F>static F symbol(HMODULE module,const char* name){const auto address=GetProcAddress(module,name);require(address!=nullptr,"Fixture DLL export");F result;static_assert(sizeof(result)==sizeof(address));std::memcpy(&result,&address,sizeof(result));return result;}
static void dll_retention(const std::filesystem::path& fixture,const std::filesystem::path& library){
    Host h;host=&h;h.block=true;const auto cb=callbacks();
    HMODULE module=LoadLibraryExW(library.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);require(module!=nullptr,"Load unregistered test DLL");
    using Create=BOOL(*)(const wchar_t*,const char*,ASIOBufferInfo*,long,long,const ASIOCallbacks*);
    using Destroy=void(*)();using Report=void(*)(AudioReport*);using Pid=DWORD(*)();
    const auto create=symbol<Create>(module,"owner_create");const auto destroy=symbol<Destroy>(module,"owner_destroy");
    const auto report=symbol<Report>(module,"owner_report");const auto pid=symbol<Pid>(module,"owner_worker_pid");
    bool created=false,freed=false;
    try{
        const auto hash=Process::executable_sha256(fixture);require(create(fixture.c_str(),hash.c_str(),h.info.data(),12,64,&cb),"DLL fixture starts simulated session");created=true;
        require(WaitForSingleObject(h.entered.value,2000)==WAIT_OBJECT_0,"DLL callback blocked before destroy/unload");
        HANDLE worker=OpenProcess(SYNCHRONIZE,FALSE,pid());require(worker!=nullptr,"Retain exact fixture worker observation handle");
        AudioReport running;report(&running);require(!running.retired && running.active_callbacks==1,"DLL owns active callback lease");
        destroy();created=false;require(FreeLibrary(module),"Drop caller DLL reference");freed=true;
        require(GetModuleHandleW(library.filename().c_str())==module,"Audio-thread module reference survives owner destruction and caller unload");
        require(WaitForSingleObject(worker,2000)==WAIT_OBJECT_0,"Worker can retire while callback and planes remain leased");CloseHandle(worker);
        SetEvent(h.release.value);const auto begin=GetTickCount64();
        while(GetModuleHandleW(library.filename().c_str())){require(GetTickCount64()-begin<3000,"DLL unload after thread/reaper retirement");Sleep(1);}
        require(h.calls==1 && !h.bad,"Blocked host callback reads valid planes after owner destruction and finishes before DLL unload");
    }catch(...){SetEvent(h.release.value);if(created)destroy();if(!freed)FreeLibrary(module);
        const auto begin=GetTickCount64();while(GetModuleHandleW(library.filename().c_str()) && GetTickCount64()-begin<3000)Sleep(1);throw;}
}
int wmain(int argc,wchar_t** argv){
    try{require(argc==3,"Session fixture and unregistered owner test DLL required");normal(argv[1]);blocked(argv[1]);faults(argv[1]);dll_retention(argv[1],argv[2]);
        std::cout<<"ASIO audio owner: real worker processes/SDK callbacks, stable repeated-session planes, zero observed steady C++ allocations, bounded blocked-callback stop, worker/callback faults and actual DLL retain/unload passed; simulated I/O only\n";
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
