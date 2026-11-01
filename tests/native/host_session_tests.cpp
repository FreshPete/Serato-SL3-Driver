#include "asio/host_session.hpp"
#include <atomic>
#include <fstream>
#include <iostream>
#include <stdexcept>

using namespace sl3::asio;
using namespace sl3::worker;
static void require(bool condition,const char* text){if(!condition)throw std::runtime_error(text);}
struct Host {
    std::array<ASIOBufferInfo,12> planes{};
    HANDLE entered=CreateEventW(nullptr,TRUE,FALSE,nullptr),release=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    std::atomic<unsigned> calls{0};std::atomic<bool> bad{false};
    bool block=false,throws=false;HostSession* session=nullptr;
    Host(){require(entered && release,"Host fixture events");for(long c=0;c<6;++c){planes[std::size_t(c)]={ASIOTrue,c,{}};planes[std::size_t(6+c)]={ASIOFalse,c,{}};}}
    ~Host(){CloseHandle(entered);CloseHandle(release);}
};
static Host* host=nullptr;
static void callback(long bank,ASIOBool direct){
    auto& h=*host;
    if(direct!=ASIOTrue || bank<0 || bank>1)h.bad=true;
    const auto nested=h.session->stop(0);
    if(!nested.reentrant || !nested.audio.reentrant || nested.io_retired || nested.device_released ||
       h.session->dispose_buffers()!=ASE_InvalidMode || h.session->inspect() || h.session->start() || h.session->start_checked(48000))h.bad=true;
    SetEvent(h.entered);
    if(h.throws)throw std::runtime_error("Host callback exception");
    if(h.block)WaitForSingleObject(h.release,INFINITE);
    // Touch both banks only while the callback lease is held.
    for(unsigned c=0;c<6;++c){auto* out=static_cast<unsigned char*>(h.planes[6+c].buffers[bank]);
        const auto* in=static_cast<const unsigned char*>(h.planes[c].buffers[bank]);
        for(unsigned i=0;i<64*3;++i)out[i]=in[i];}
    h.calls.fetch_add(1);
}
static ASIOCallbacks callbacks(){ASIOCallbacks value{};value.bufferSwitch=callback;return value;}
static WorkerSpec spec(const std::filesystem::path& executable,const std::wstring& mode=L"normal"){
    WorkerSpec value;value.executable=executable;value.sha256=Process::executable_sha256(executable);
    value.kind=sl3::session::Kind::simulated;value.fixture_mode=mode;return value;
}
struct Release {
    Host& host;HostSession& session;
    ~Release(){SetEvent(host.release);session.stop(2000);}
};
static void healthy(const std::filesystem::path& fixture){
    Host h;host=&h;HostSession session(spec(fixture));h.session=&session;Release release{h,session};
    require(!session.start(),"No startup before clock inspection and buffers");
    const auto ok=session.inspect();const auto inspected=session.report();
    if(!ok)std::cerr<<"inspect failure="<<unsigned(inspected.failure)<<" rate="<<inspected.observed_rate_hz<<" started="<<inspected.process.started<<" exit="<<inspected.process.exit_code<<" empty="<<inspected.process.job_empty<<" io="<<inspected.io_retired<<" dev="<<inspected.device_released<<" termination="<<inspected.termination_requested<<"\n";
    require(ok,"Observe clock through temporary worker");
    require(inspected.observed_rate_hz==48000 && inspected.process.process_exited && inspected.process.job_empty && inspected.io_retired && inspected.device_released &&
            !inspected.running && !inspected.termination_requested,"Inspection worker is already gone; metadata is not live readiness");
    const auto cb=callbacks();require(session.create_buffers(h.planes.data(),12,64,&cb)==ASE_OK,"Create SDK planes after inspection");
    const auto first=h.planes[0].buffers[0];
    for(unsigned cycle=0;cycle<3;++cycle){
        ResetEvent(h.entered);h.calls=0;require(session.start(cycle==1?64:8),"Fresh process/channel start with same planes");
        require(WaitForSingleObject(h.entered,2000)==WAIT_OBJECT_0,"Audio owner delivers actual SDK callback");
        require(session.dispose_buffers()==ASE_InvalidMode,"Running session cannot dispose callback planes");
        const auto stopped=session.stop();
        require(!stopped.running && stopped.failure==HostFailure::none && stopped.io_retired && stopped.device_released && stopped.audio.retired && !stopped.audio.active_callbacks &&
                stopped.audio.callbacks_completed>0 && stopped.process.process_exited && stopped.process.job_empty && !stopped.termination_requested &&
                h.planes[0].buffers[0]==first && !h.bad,"Both ownership domains retire; planes remain stable and reentry is rejected");
        require(stopped.worker_snapshot.phase==sl3::session::Phase::stopped &&
                stopped.worker_snapshot.failure==sl3::session::Failure::none && stopped.worker_snapshot.stats.input_frames>0 &&
                !stopped.worker_snapshot.stats.pending_mask && !stopped.worker_snapshot.stats.retained_mask,
                "Final control snapshot preserves stream counters and retirement");
    }
    require(session.dispose_buffers()==ASE_OK,"Dispose after all sessions retire");
}
static void checked_start(const std::filesystem::path& fixture){
    // If the old inspector is accidentally invoked, this fixture hangs/fails.
    Host h;host=&h;HostSession session(spec(fixture,L"hang-inspect"));h.session=&session;Release release{h,session};
    require(!session.start_checked(48000),"No checked start before buffer ownership is prepared");
    const auto cb=callbacks();require(session.create_buffers(h.planes.data(),12,64,&cb)==ASE_OK,"Prepare planes without claiming a device inspection");
    require(!session.start_checked(0) && !session.start_checked(96000) && !session.start_checked(48000,7),"Invalid metadata or interval shape launches no session");
    require(!session.report().process.started && session.report().observed_rate_hz==0,"Supplied metadata is not observed readiness");
    require(session.start_checked(48000,64),"Factory-checked startup avoids the temporary inspection/reopen");
    require(WaitForSingleObject(h.entered,2000)==WAIT_OBJECT_0,"One-open fixture reaches actual SDK callback");
    const auto stopped=session.stop();
    require(stopped.failure==HostFailure::none && stopped.observed_rate_hz==48000 && stopped.io_retired && stopped.device_released &&
            stopped.audio.retired && stopped.process.process_exited && stopped.process.job_empty && !h.bad,"Checked startup retires both ownership domains");
    require(session.dispose_buffers()==ASE_OK,"Checked startup planes disposed after retirement");
    Host rejected;host=&rejected;HostSession mismatch(spec(fixture));rejected.session=&mismatch;Release mismatch_release{rejected,mismatch};
    require(mismatch.create_buffers(rejected.planes.data(),12,64,&cb)==ASE_OK && !mismatch.start_checked(44100),"Factory rejects mismatched actual rate before making its target");
    const auto failed=mismatch.stop();
    require(failed.failure!=HostFailure::none && failed.observed_rate_hz==0 && failed.audio.callbacks_started==0 && rejected.calls==0 &&
            failed.process.process_exited && failed.process.job_empty && failed.io_retired && failed.device_released &&
            !mismatch.start_checked(48000),"Failed checked startup cannot publish clock success or silently retry");
}
static void blocked(const std::filesystem::path& fixture){
    Host h;host=&h;h.block=true;HostSession session(spec(fixture));h.session=&session;Release release{h,session};
    const auto cb=callbacks();require(session.inspect() && session.create_buffers(h.planes.data(),12,64,&cb)==ASE_OK && session.start(64),"Start blocked-callback session");
    require(WaitForSingleObject(h.entered,2000)==WAIT_OBJECT_0,"Blocked host callback entered");
    const auto pending=session.stop(1000);
    require(pending.io_retired && pending.device_released && pending.process.process_exited && pending.process.job_empty &&
            !pending.audio.retired && pending.audio.active_callbacks==1 && session.dispose_buffers()==ASE_InvalidMode && !session.start(),"Worker retirement does not release the blocked callback or permit restart");
    SetEvent(h.release);const auto done=session.stop(2000);
    require(done.failure==HostFailure::none && done.audio.retired && done.audio.callbacks_started==1 && done.audio.callbacks_completed==1 && !h.bad && session.dispose_buffers()==ASE_OK,"Late callback retirement after ordinary queue closure releases planes without a spurious fault or second callback");
}
static void destroyed_with_callback(const std::filesystem::path& fixture){
    Host h;host=&h;h.block=true;auto session=std::make_unique<HostSession>(spec(fixture));h.session=session.get();
    struct Unblock {Host& h;~Unblock(){SetEvent(h.release);}} unblock{h};
    const auto cb=callbacks();require(session->inspect() && session->create_buffers(h.planes.data(),12,64,&cb)==ASE_OK && session->start(64),"Start owner-destruction case");
    require(WaitForSingleObject(h.entered,2000)==WAIT_OBJECT_0,"Callback entered before owner destruction");
    const auto begin=GetTickCount64();session.reset();
    require(GetTickCount64()-begin<1000 && h.calls==0,"Host control destruction does not wait on blocked user code");
    // Callback already passed reentry checks. It touches its original planes
    // after destruction, then returns through AudioOwner's retained code/state.
    SetEvent(h.release);const auto released=GetTickCount64();
    while(!h.calls){require(GetTickCount64()-released<2000,"Retained callback returns after control owner destruction");Sleep(1);}
    require(h.calls==1 && !h.bad,"Executing callback retains valid planes across control owner destruction");
    // Callback no longer accesses Host after publishing calls. Its worker and
    // audio thread retire independently; no force-termination of host threads.
}
static void failures(const std::filesystem::path& fixture,const std::filesystem::path& native){
    {
        auto rejected=spec(fixture);rejected.sha256.assign(64,'0');HostSession session(rejected);
        require(!session.inspect() && session.report().failure==HostFailure::launch && !session.report().process.started,"Executable hash rejection launches no worker and preserves first cause");
    }
    {
        struct ClockFile {
            std::filesystem::path path=std::filesystem::temp_directory_path()/(L"SL3Clock-"+std::to_wstring(GetCurrentProcessId())+L"-"+std::to_wstring(GetTickCount64())+L".txt");
            void set(unsigned rate){std::ofstream file(path);file<<rate;require(bool(file),"Write simulated observed rate");}
            ~ClockFile(){std::error_code error;std::filesystem::remove(path,error);}
        } clock;
        clock.set(48000);Host h;host=&h;HostSession session(spec(fixture,L"clock:"+clock.path.native()));h.session=&session;Release release{h,session};
        const auto cb=callbacks();require(session.inspect() && session.create_buffers(h.planes.data(),12,64,&cb)==ASE_OK,"Prepare at original observed rate");
        clock.set(44100);require(!session.start(),"Fresh startup rechecks clock changed since host inspection");const auto state=session.stop();
        require(state.failure==HostFailure::rate_changed && state.observed_rate_hz==44100 && state.audio.callbacks_started==0 && state.audio.retired && state.io_retired && state.device_released &&
                state.process.process_exited && state.process.job_empty && h.calls==0 && !session.start(),"Rate change requires new explicit inspection and starts no audio owner");
        require(session.inspect() && session.report().observed_rate_hz==44100 && session.start(),"Host can re-inspect and use 44.1 kHz metadata explicitly");
        require(WaitForSingleObject(h.entered,2000)==WAIT_OBJECT_0 && session.stop().audio.retired,"Re-inspected metadata reaches SDK callback");
    }
    for(const auto* mode:{L"fail-inspect",L"invalid-clock",L"hang-inspect"}){
        HostSession session(spec(fixture,mode));require(!session.inspect() && !session.start(),"Inspection failure never makes host usable");
        const auto state=session.stop();require(state.failure==HostFailure::inspection && state.process.process_exited && state.process.job_empty && !state.running,"Inspection failure preserves first cause and retires private process");
    }
    for(const auto* mode:{L"fail-start",L"partial-start",L"hang-start",L"hang-submit"}){
        Host h;host=&h;HostSession session(spec(fixture,mode));h.session=&session;Release release{h,session};const auto cb=callbacks();
        require(session.inspect() && session.create_buffers(h.planes.data(),12,64,&cb)==ASE_OK && !session.start(),"Failed/partial/stalled worker start never publishes host running");
        const auto state=session.stop();require(state.failure!=HostFailure::none && state.process.process_exited && state.process.job_empty && state.audio.retired &&
            !state.running && h.calls==0 && session.dispose_buffers()==ASE_OK,"All startup fault domains retire without fabricated callback success");
        if(std::wstring(mode)==L"hang-start" || std::wstring(mode)==L"hang-submit")
            require(!state.io_retired && !state.device_released,"Temporary inspection cannot certify retirement of an unobserved later startup");
    }
    {
        Host h;host=&h;h.throws=true;HostSession session(spec(fixture));h.session=&session;Release release{h,session};const auto cb=callbacks();
        require(session.inspect() && session.create_buffers(h.planes.data(),12,64,&cb)==ASE_OK,"Prepare callback-fault session");
        session.start();require(WaitForSingleObject(h.entered,2000)==WAIT_OBJECT_0,"Faulting host callback ran");
        const auto begin=GetTickCount64();while(!session.report().audio.retired){require(GetTickCount64()-begin<2000,"Bounded callback fault exit");Sleep(1);}
        const auto state=session.stop();require(state.failure!=HostFailure::none && !state.running && state.audio.retired && state.audio.callbacks_started==1 &&
            state.audio.callbacks_completed==0 && state.process.process_exited && state.process.job_empty,"Callback failure cannot be reported as healthy running");
    }
    {
        auto wrong=spec(fixture);wrong.kind=sl3::session::Kind::native;wrong.helper=L"C:/deliberately-missing-sl3-session-helper.dll";
        // Fixture accepts the native-shaped CLI but still truthfully says simulated.
        HostSession session(wrong);require(!session.inspect() && session.stop().failure==HostFailure::handshake,"No simulated worker may impersonate native readiness");
    }
    {
        WorkerSpec value;value.executable=native;value.sha256=Process::executable_sha256(native);value.helper=L"C:/deliberately-missing-sl3-session-helper.dll";
        require(!std::filesystem::exists(value.helper),"Native negative test requires deliberately absent helper");
        HostSession session(value);require(!session.inspect(),"Real native helper/service gate rejects before hardware access");
        const auto state=session.stop();require(state.failure==HostFailure::inspection && state.process.process_exited && state.process.job_empty && state.io_retired && state.device_released && !session.start(),"Native failure safely closed and cannot become ASIO availability");
        Host h;host=&h;HostSession direct(value);h.session=&direct;Release release{h,direct};const auto cb=callbacks();
        require(direct.create_buffers(h.planes.data(),12,64,&cb)==ASE_OK && !direct.start_checked(48000),"Checked native startup still enforces the absent-helper gate");
        const auto rejected=direct.stop();
        require(rejected.failure!=HostFailure::none && rejected.observed_rate_hz==0 && rejected.audio.callbacks_started==0 &&
                rejected.io_retired && rejected.device_released && rejected.process.process_exited && rejected.process.job_empty &&
                !rejected.termination_requested && h.calls==0,"Checked native rejection retires without hardware availability or audio claims");
    }
}
int wmain(int argc,wchar_t** argv){
    try{require(argc==3,"Session fixture and native executable paths required");healthy(argv[1]);blocked(argv[1]);checked_start(argv[1]);destroyed_with_callback(argv[1]);failures(argv[1],argv[2]);
        std::cout<<"Host temporary clock inspection, fresh continuous sessions, SDK callbacks, independent worker/audio retirement, failed startup and native absent-helper rejection passed; no physical USB or registered ASIO\n";
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
