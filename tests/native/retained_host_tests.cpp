#include "asio/driver_facade.hpp"
#include <atomic>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>

using namespace sl3::asio;
using namespace sl3::worker;
static void require(bool good,const char* text){if(!good)throw std::runtime_error(text);}
static WorkerSpec spec(const std::filesystem::path& executable,const std::wstring& mode=L"normal"){
    WorkerSpec s;s.executable=executable;s.sha256=Process::executable_sha256(executable);s.kind=sl3::session::Kind::simulated;
    s.fixture_mode=mode;s.lifetime=DeviceLifetime::retained;return s;
}
struct File {
    std::filesystem::path path=std::filesystem::temp_directory_path()/(L"SL3RetainedHost-"+std::to_wstring(GetCurrentProcessId())+L"-"+std::to_wstring(GetTickCount64())+L".txt");
    File(){require(!std::filesystem::exists(path),"Fresh retained-host fixture file");}
    ~File(){std::error_code ec;std::filesystem::remove(path,ec);}
    void rate(unsigned rate){std::ofstream out(path);out<<rate;require(bool(out),"Write fixture clock");}
    std::vector<std::string> lines(){std::ifstream in(path);std::vector<std::string> result;for(std::string line;std::getline(in,line);)result.push_back(line);return result;}
};
struct Host {
    std::array<ASIOBufferInfo,12> planes{};HostSession* session=nullptr;
    HANDLE entered=CreateEventW(nullptr,TRUE,FALSE,nullptr),release=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    std::atomic<unsigned> calls{0};std::atomic<bool> bad{false};bool block=false,throws=false;unsigned frames=128;
    Host(){require(entered && release,"Retained host events");for(long c=0;c<6;++c){planes[std::size_t(c)]={ASIOTrue,c,{}};planes[std::size_t(c+6)]={ASIOFalse,c,{}};}}
    ~Host(){SetEvent(release);CloseHandle(entered);CloseHandle(release);}
};
static Host* host=nullptr;
static void callback(long bank,ASIOBool direct){
    auto& h=*host;const auto position=h.session->observation();
    if(direct!=ASIOTrue || bank!=long(h.calls.load()%2) || !position.valid || position.first_frame!=std::uint64_t(h.calls.load())*h.frames)h.bad=true;
    const auto stopped=h.session->stop(0),closed=h.session->close(0);
    if(!stopped.reentrant || !closed.reentrant || stopped.io_retired || closed.device_released || !stopped.audio.reentrant ||
       h.session->dispose_buffers()!=ASE_InvalidMode || h.session->inspect() || h.session->inspect_controls() ||
       h.session->select_control({sl3::control::AudioControlSetting::through,0,1}).command_attempted || h.session->start() || h.session->start_checked(48000))h.bad=true;
    SetEvent(h.entered);if(h.throws)throw std::runtime_error("Retained host callback failed");
    if(h.block)WaitForSingleObject(h.release,INFINITE);
    for(unsigned c=0;c<6;++c){auto* out=static_cast<unsigned char*>(h.planes[c+6].buffers[bank]);for(unsigned i=0;i<h.frames*3;++i)out[i]=0;}
    h.calls.fetch_add(1);
}
static ASIOCallbacks callbacks(){ASIOCallbacks cb{};cb.bufferSwitch=callback;return cb;}
struct Close {Host& host;HostSession& session;~Close(){SetEvent(host.release);session.close(2000);}};
static void ready(const HostReport& r){
    if(r.failure!=HostFailure::none || !r.audio.retired || r.device_released || !r.device_held || r.process.process_exited)
        std::cerr<<"ready failure="<<unsigned(r.failure)<<" audio exit="<<unsigned(r.audio.exit)<<" retired="<<r.audio.retired<<" held="<<r.device_held<<" released="<<r.device_released<<" process exited="<<r.process.process_exited<<'\n';
    require(r.failure==HostFailure::none && !r.running && r.io_retired && !r.device_released && r.device_held && r.audio.retired &&
        !r.audio.active_callbacks && r.process.started && r.process.job_assigned && !r.process.process_exited && !r.termination_requested &&
        r.device_snapshot.phase==sl3::device_session::Phase::ready,"Successful stop retains idle device, not an exited process");
}
static void released(const HostReport& r){
    require(!r.running && !r.device_held && r.io_retired && r.device_released && r.audio.retired && r.process.process_exited && r.process.job_empty &&
        !r.termination_requested,"Final release retires device, process/job and audio owner independently");
}
static void lifecycle(const std::filesystem::path& fixture){
    File audit;Host h;host=&h;HostSession session(spec(fixture,L"audit:"+audit.path.native()));h.session=&session;Close close{h,session};
    require(!session.start() && !session.start_checked(48000) && !session.report().process.started,"No retained audio before acquisition");
    require(session.inspect() && session.inspect(),"Initialization retains one acquired device and is idempotent");ready(session.report());
    ready(session.stop());
    const auto cb=callbacks();require(session.create_buffers(h.planes.data(),12,h.frames,&cb)==ASE_OK,"Create buffers while device retained");
    const auto plane=h.planes[0].buffers[0];
    for(unsigned cycle=0;cycle<3;++cycle){
        h.calls=0;ResetEvent(h.entered);require(session.start(cycle==1?64:8),"Restart uses fresh audio queues on held device");
        require(!session.start() && WaitForSingleObject(h.entered,2000)==WAIT_OBJECT_0,"Duplicate start rejected; actual SDK callback reached");
        const auto deadline=GetTickCount64()+2000;
        while(h.calls<12){require(GetTickCount64()<deadline,"Several callback banks require simulated output pipeline progress");Sleep(1);}
        require(session.dispose_buffers()==ASE_InvalidMode,"Running buffers cannot be disposed");
        const auto stopped=session.stop();ready(stopped);
        if(!stopped.audio.callbacks_completed || !stopped.device_snapshot.stats.output_completions || h.planes[0].buffers[0]!=plane || h.bad)
            std::cerr<<"cycle="<<cycle<<" callbacks="<<stopped.audio.callbacks_completed<<" output completions="<<stopped.device_snapshot.stats.output_completions<<" bad="<<h.bad<<" stable="<<(h.planes[0].buffers[0]==plane)<<'\n';
        require(stopped.audio.callbacks_completed>0 && stopped.device_snapshot.stats.output_completions>0 && h.planes[0].buffers[0]==plane && !h.bad,
                "Fresh callback positions, stable planes and retired native output across restarts");
    }
    require(session.dispose_buffers()==ASE_OK,"Dispose buffers without releasing idle device");
    h.frames=64;h.calls=0;ResetEvent(h.entered);
    require(session.create_buffers(h.planes.data(),12,h.frames,&cb)==ASE_OK && session.start() && WaitForSingleObject(h.entered,2000)==WAIT_OBJECT_0,
            "Recreate buffers and restart without a new redirect");
    ready(session.stop());require(session.dispose_buffers()==ASE_OK && !h.bad,"Recreated planes retired");
    const auto result=session.close();released(result);require(result.failure==HostFailure::none,"Normal final close is not containment");
    require(!session.inspect() && !session.start() && !session.start_checked(48000),"Final release seals owner against implicit reacquisition");
    require(audit.lines()==std::vector<std::string>({"acquire","rate","rate","begin","end","rate","begin","end","rate","begin","end","rate","begin","end","release"}),
            "Exactly one acquire/final release with fresh clock and target per ASIO start");
}
static void blocked(const std::filesystem::path& fixture){
    Host h;host=&h;h.block=true;HostSession session(spec(fixture));h.session=&session;Close close{h,session};const auto cb=callbacks();
    require(session.inspect() && session.create_buffers(h.planes.data(),12,h.frames,&cb)==ASE_OK && session.start(64),"Start retained blocked callback");
    require(WaitForSingleObject(h.entered,2000)==WAIT_OBJECT_0,"Blocked callback entered");
    const auto pending=session.stop(500);
    require(pending.io_retired && pending.device_held && !pending.device_released && !pending.process.process_exited && !pending.audio.retired &&
        pending.audio.active_callbacks==1 && session.dispose_buffers()==ASE_InvalidMode && !session.start() && !session.inspect() && !session.inspect_controls() &&
        !session.select_control({sl3::control::AudioControlSetting::through,0,1}).command_attempted,
        "Retired native I/O does not release blocked callback planes or admit another stream");
    SetEvent(h.release);ready(session.stop(2000));
    require(h.calls==1 && !h.bad && session.dispose_buffers()==ASE_OK,"Late callback retirement permits disposal while device stays retained");released(session.close());
}
static void controls(const std::filesystem::path& fixture){
    File audit;Host h;host=&h;HostSession session(spec(fixture,L"audit:"+audit.path.native()));h.session=&session;Close close{h,session};
    require(!session.inspect_controls() && !session.report().process.started,"Control inspection never launches or acquires implicitly");
    require(session.inspect(),"Acquire once for explicit controls");
    const auto first=session.inspect_controls();require(first && first->received_frames==4 && first->audio.raw[0]==17 && first->audio.raw[21]==38,"Typed controls and receive count survive real worker IPC");ready(session.report());
    const auto cb=callbacks();require(session.create_buffers(h.planes.data(),12,h.frames,&cb)==ASE_OK && session.start(),"Controls preserve buffer/audio admission");
    require(WaitForSingleObject(h.entered,2000)==WAIT_OBJECT_0 && !session.inspect_controls(),"Active audio and callback reentry cannot query controls");
    ready(session.stop());const auto second=session.inspect_controls();
    require(second && second->audio.raw==first->audio.raw && second->received_frames==4 && !h.bad,"Fresh post-stop inspection on retained device");
    require(session.dispose_buffers()==ASE_OK,"Controls do not retain callback buffers");released(session.close());
    require(!session.inspect_controls() && audit.lines()==std::vector<std::string>({"acquire","rate","controls","rate","begin","end","controls","release"}),
            "Controls preserve one acquire/final release and never run in rejected states");
    for(const auto mode:{L"fail-controls",L"bad-controls",L"hang-controls"}){
        HostSession failed(spec(fixture,mode));require(failed.inspect() && !failed.inspect_controls(),"Failed or stalled inspection yields no snapshot");
        const auto r=failed.close();require(r.failure==HostFailure::inspection && r.audio.retired && r.process.process_exited && r.process.job_empty && !r.device_held,
                                           "Inspection failure contains the private process and releases host ownership");
        if(std::wstring(mode)==L"hang-controls")require(!r.io_retired && !r.device_released,"Unobserved query cannot reuse the earlier idle cleanup proof");
        else require(r.io_retired && r.device_released,"Reported query failure retires I/O and releases device normally");
        require(!failed.inspect_controls() && !failed.inspect(),"No inspection or acquisition retry after control failure");
    }
    auto temporary=spec(fixture);temporary.lifetime=DeviceLifetime::temporary;HostSession temp(temporary);
    require(!temp.inspect_controls() && !temp.report().process.started,"Temporary mode cannot silently create a controls-only redirect");
}
static void selection(const std::filesystem::path& fixture){
    const sl3::control::selection_wire::Target target{sl3::control::AudioControlSetting::through,0,1};
    File audit;Host h;host=&h;HostSession session(spec(fixture,L"audit:"+audit.path.native()));h.session=&session;Close close{h,session};
    require(!session.select_control(target).command_attempted && !session.report().process.started,"Selection does not acquire implicitly");
    require(session.inspect(),"Acquire for explicit selection");
    require(!session.select_control({target.setting,3,1}).command_attempted,"Invalid target sends no request");ready(session.report());
    const auto changed=session.select_control(target);
    require(changed.command_attempted && !changed.outcome_unknown && changed.device_may_have_changed && changed.outcome &&
        changed.outcome->selection.verified && changed.outcome->selection.verified->raw[8]==1 && changed.outcome->native_error==1168,
        "Checked selected state crosses real worker IPC independently of final ownership");ready(session.report());
    const auto noop=session.select_control(target);
    require(noop.outcome && !noop.device_may_have_changed && !noop.outcome_unknown && !noop.outcome->selection.setter_attempts,
        "Already-selected command is a verified no-op");
    const auto cb=callbacks();require(session.create_buffers(h.planes.data(),12,h.frames,&cb)==ASE_OK && session.start(),"Audio remains admissible after selection");
    require(WaitForSingleObject(h.entered,2000)==WAIT_OBJECT_0 && !session.select_control(target).command_attempted,"Active audio/reentry rejects selection");
    ready(session.stop());released(session.close());
    require(!session.select_control(target).command_attempted && !h.bad &&
        audit.lines()==std::vector<std::string>({"acquire","rate","select","select","rate","begin","end","release"}),"No extra acquire, automatic query or retry");
    {HostSession unsupported(spec(fixture,L"selection-unsupported"));require(unsupported.inspect(),"Acquire unsupported fixture");
        require(!unsupported.select_control(target).command_attempted,"Host honours explicit unsupported capability");ready(unsupported.report());released(unsupported.close());}
    for(const auto mode:{L"fail-selection",L"mismatch-selection",L"selection-fail-close"}){
        HostSession failed(spec(fixture,mode));require(failed.inspect(),"Acquire selection fault fixture");
        const auto result=failed.select_control(target);const auto owner=failed.report();
        require(result.command_attempted && !result.outcome_unknown && result.device_may_have_changed && result.outcome &&
            result.outcome->selection.initial && !result.outcome->selection.verified && owner.failure==HostFailure::control &&
            owner.io_retired && owner.process.process_exited && owner.process.job_empty,"Failed operation preserves partial evidence and retires worker independently");
        require(owner.device_released==(std::wstring(mode)!=L"selection-fail-close"),"A failed final close cannot erase observations or claim redirect release");
        require(!failed.select_control(target).command_attempted && !failed.inspect(),"Selection failure seals owner against retry");
    }
    for(const auto mode:{L"throw-selection",L"bad-selection",L"hang-selection"}){
        HostSession failed(spec(fixture,mode));require(failed.inspect(),"Acquire unknown selection fixture");
        const auto result=failed.select_control(target);const auto owner=failed.report();
        require(result.command_attempted && result.outcome_unknown && result.device_may_have_changed && !result.outcome &&
            owner.process.process_exited && owner.process.job_empty,"Missing/malformed outcome preserves conservative possible-write uncertainty");
        if(std::wstring(mode)==L"hang-selection")require(!owner.io_retired && !owner.device_released,"Stalled selection cannot reuse prior idle cleanup proof");
    }
    {HostSession failed_close(spec(fixture,L"selection-success-close"));require(failed_close.inspect(),"Acquire final-close fault fixture");
        const auto result=failed_close.select_control(target);require(result.outcome && result.outcome->selection.verified,"Verified selection before final-close failure");
        const auto owner=failed_close.close();
        require(result.outcome->selection.verified && !owner.device_released && owner.io_retired && owner.process.process_exited && owner.process.job_empty,
            "Verified observation survives later failed redirect release without claiming cleanup success");}
    {HostSession slow(spec(fixture,L"slow-selection"));require(slow.inspect(),"Acquire delayed selection fixture");
        const auto entered=GetTickCount64();const auto result=slow.select_control(target);
        require(result.outcome && !result.outcome_unknown && GetTickCount64()-entered>=5000,"Selection uses its own eight-second reply allowance, not getter's five seconds");
        ready(slow.report());released(slow.close());}
    auto temporary=spec(fixture);temporary.lifetime=DeviceLifetime::temporary;HostSession temp(temporary);
    require(!temp.select_control(target).command_attempted && !temp.report().process.started,"Temporary mode cannot create an implicit settings redirect");
}
static void destruction(const std::filesystem::path& fixture){
    {
        File audit;
        {HostSession session(spec(fixture,L"audit:"+audit.path.native()));require(session.inspect(),"Acquire before idle owner destruction");}
        require(audit.lines()==std::vector<std::string>({"acquire","rate","release"}),"Idle owner destructor performs ordinary final redirect release");
    }
    Host h;host=&h;h.block=true;auto session=std::make_unique<HostSession>(spec(fixture));h.session=session.get();
    const auto cb=callbacks();require(session->inspect() && session->create_buffers(h.planes.data(),12,h.frames,&cb)==ASE_OK && session->start(64),"Start retained owner-destruction callback");
    require(WaitForSingleObject(h.entered,2000)==WAIT_OBJECT_0,"Executing callback before owner destruction");
    const auto begin=GetTickCount64();session.reset();require(GetTickCount64()-begin<1000 && h.calls==0,"Control destruction does not wait for blocked callback");
    SetEvent(h.release);const auto deadline=GetTickCount64()+2000;
    while(!h.calls){require(GetTickCount64()<deadline,"Retained callback can return after owner destruction");Sleep(1);}
    require(h.calls==1 && !h.bad,"Callback/module/buffer leases survive control owner destruction");
}
static void blocked_final_close(const std::filesystem::path& fixture){
    Host h;host=&h;h.block=true;HostSession session(spec(fixture));h.session=&session;Close close{h,session};const auto cb=callbacks();
    require(session.inspect() && session.create_buffers(h.planes.data(),12,h.frames,&cb)==ASE_OK && session.start(64),"Start before final close with blocked callback");
    require(WaitForSingleObject(h.entered,2000)==WAIT_OBJECT_0,"Callback entered before final release");
    const auto pending=session.close(500);
    require(pending.io_retired && pending.device_released && !pending.device_held && pending.process.process_exited && pending.process.job_empty &&
        !pending.audio.retired && pending.audio.active_callbacks==1 && session.dispose_buffers()==ASE_InvalidMode && !session.inspect(),
        "Final native release does not dispose blocked callback planes or reacquire device");
    SetEvent(h.release);const auto done=session.close(2000);released(done);
    require(done.failure==HostFailure::none && done.audio.callbacks_completed==1 && !h.bad && session.dispose_buffers()==ASE_OK,
            "Late callback returns into retained old mapping after final native release without a false queue fault");
}
static void failures(const std::filesystem::path& fixture,const std::filesystem::path& native){
    {
        File clock;clock.rate(48000);Host h;host=&h;HostSession session(spec(fixture,L"clock:"+clock.path.native()));h.session=&session;Close close{h,session};const auto cb=callbacks();
        require(session.inspect() && session.create_buffers(h.planes.data(),12,h.frames,&cb)==ASE_OK,"Acquire original actual fixture clock");clock.rate(44100);
        require(!session.start(),"Same held handle is freshly checked before native activation");const auto r=session.close();released(r);
        require(r.failure==HostFailure::rate_changed && r.observed_rate_hz==44100 && r.audio.callbacks_started==0 && h.calls==0 &&
            !session.inspect() && session.dispose_buffers()==ASE_OK,"Changed clock preserves cause, sends no audio and requires a new owner");
    }
    for(const auto mode:{L"fail-acquire",L"invalid-clock",L"hang-acquire",L"hang-rate"}){
        HostSession session(spec(fixture,mode));require(!session.inspect(),"Failed acquisition does not claim ASIO readiness");
        const auto r=session.close();require(r.failure!=HostFailure::none && r.process.process_exited && r.process.job_empty && !r.device_held &&
            !session.inspect() && !session.start(),"Failed retained acquisition is sealed and private process retires");
    }
    for(const auto mode:{L"fail-start",L"partial-start",L"hang-start",L"hang-submit"}){
        Host h;host=&h;HostSession session(spec(fixture,mode));h.session=&session;Close close{h,session};const auto cb=callbacks();
        require(session.inspect() && session.create_buffers(h.planes.data(),12,h.frames,&cb)==ASE_OK && !session.start(),"Failed/partial/stalled retained startup rejected");
        const auto r=session.close();require(r.failure!=HostFailure::none && r.audio.retired && r.audio.callbacks_started==0 && r.process.process_exited &&
            r.process.job_empty && !r.device_held && session.dispose_buffers()==ASE_OK,"Failed start cannot leak callback planes or advertise healthy held device");
        if(std::wstring(mode)==L"hang-start" || std::wstring(mode)==L"hang-submit")
            require(!r.io_retired && !r.device_released,"An old idle reply cannot certify retirement after an unobserved/stalled native start");
    }
    {
        Host h;host=&h;h.throws=true;HostSession session(spec(fixture));h.session=&session;Close close{h,session};const auto cb=callbacks();
        require(session.inspect() && session.create_buffers(h.planes.data(),12,h.frames,&cb)==ASE_OK,"Prepare retained callback fault");session.start();
        require(WaitForSingleObject(h.entered,2000)==WAIT_OBJECT_0,"Faulting callback ran");const auto deadline=GetTickCount64()+2000;
        while(!session.report().audio.retired){require(GetTickCount64()<deadline,"Faulting callback retires");Sleep(1);}
        const auto r=session.stop();require(r.failure!=HostFailure::none && !r.device_held && r.process.process_exited && r.process.job_empty && r.audio.retired &&
            r.audio.callbacks_started==1 && r.audio.callbacks_completed==0,"Audio fault forces final release instead of healthy retained stop");
    }
    {
        auto wrong=spec(fixture);wrong.kind=sl3::session::Kind::native;wrong.helper=L"C:/deliberately-absent-retained-helper.dll";
        HostSession session(wrong);require(!session.inspect() && session.report().failure==HostFailure::handshake,"Simulated retained worker cannot impersonate native implementation");
        auto actual=wrong;actual.executable=native;actual.sha256=Process::executable_sha256(native);require(!std::filesystem::exists(actual.helper),"Native negative helper is absent");
        HostSession real(actual);require(!real.inspect(),"Native retained acquisition enforces absent-helper gate");const auto r=real.close();
        require(r.failure==HostFailure::inspection && r.io_retired && r.device_released && r.process.process_exited && r.process.job_empty && !r.device_held,
                "Native negative acquisition releases process without hardware readiness");
    }
    {
        File audit;DriverFacade wrong_profile(spec(fixture,L"audit:"+audit.path.native()),{7,11,44100,128});
        require(wrong_profile.init()==ASIOFalse && audit.lines()==std::vector<std::string>({"acquire","rate","release"}),
                "Timing-profile mismatch promptly releases retained device before failed init returns");
    }
}
static void diagnostic_configuration(const std::filesystem::path& native){
    WorkerSpec allowed;allowed.executable=native;allowed.sha256=Process::executable_sha256(native);
    allowed.helper=L"C:/deliberately-absent-control-test-helper.dll";allowed.lifetime=DeviceLifetime::retained;
    allowed.diagnostic_directory=std::filesystem::temp_directory_path();
    allowed.diagnostic_control_target=sl3::control::selection_wire::Target{sl3::control::AudioControlSetting::through,0,1};
    for(unsigned mutation=0;mutation<4;++mutation){
        auto bad=allowed;
        if(mutation==0)bad.lifetime=DeviceLifetime::temporary;
        if(mutation==1)bad.kind=sl3::session::Kind::simulated;
        if(mutation==2)bad.diagnostic_directory.clear();
        if(mutation==3)bad.diagnostic_control_target->value=2;
        bool rejected=false;try{HostSession session(bad);}catch(const std::invalid_argument&){rejected=true;}
        require(rejected,"Invalid diagnostic grant rejects at construction before launch");
    }
    HostSession session(allowed);
    require(!session.start() && !session.start_checked(44100) && !session.report().process.started,
            "Diagnostic host refuses audio without creating a worker");
}
static void facade_scope(const std::filesystem::path& fixture){
    auto temporary=spec(fixture);temporary.lifetime=DeviceLifetime::temporary;
    HostSession shut(temporary);shut.request_shutdown();
    require(!shut.inspect() && !shut.start_checked(48000) && !shut.report().process.started,
            "Nonwaiting shutdown seals temporary inspection and checked-start entries before launch");
    File audit;auto owner=std::make_shared<DriverOwner>(spec(fixture,L"audit:"+audit.path.native()));
    bool rejected=false;
    try{DriverFacade invalid(owner,{0,0,96000,128});}catch(const std::invalid_argument&){rejected=true;}
    require(rejected,"Invalid profile cannot consume the scope's exclusive borrow");
    for(unsigned object=0;object<2;++object){
        DriverFacade facade(owner,{7,11});require(facade.init()==ASIOTrue,"Reuse one held worker across facade identities");
        require(!owner->close(),"Scope close cannot race an outstanding facade borrow");
        ASIOBufferInfo plane{};plane.isInput=ASIOTrue;auto cb=callbacks();
        require(facade.createBuffers(&plane,1,128,&cb)==ASE_OK,
                "Next facade receives clean buffers after predecessor destruction");
        // No start: destruction must dispose idle planes before handoff.
    }
    require(audit.lines()==std::vector<std::string>({"acquire","rate","rate"}),"Recreated facade refreshes its clock without release or reacquisition");
    const auto closed=owner->close();require(bool(closed),"Unborrowed scope can close");released(*closed);
    require(audit.lines()==std::vector<std::string>({"acquire","rate","rate","release"}),"Scope makes exactly one final release");
    rejected=false;try{DriverFacade after(owner,{7,11});}catch(const std::runtime_error&){rejected=true;}
    require(rejected,"Explicitly closed owner cannot be lent again");
    auto failed=std::make_shared<DriverOwner>(spec(fixture,L"fail-acquire"));
    {DriverFacade facade(failed,{7,11});require(facade.init()==ASIOFalse,"Shared owner records failed acquisition");}
    rejected=false;try{DriverFacade after(failed,{7,11});}catch(const std::runtime_error&){rejected=true;}
    require(rejected,"Failed acquisition seals the scope against automatic retry");
}
struct FacadeCallback {
    HANDLE entered=CreateEventW(nullptr,TRUE,FALSE,nullptr),resume=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    std::atomic<unsigned> calls{0};std::array<ASIOBufferInfo,2> planes{};
    FacadeCallback(){require(entered && resume,"Shared facade callback events");planes[0].isInput=ASIOTrue;planes[1].isInput=ASIOFalse;}
    ~FacadeCallback(){SetEvent(resume);CloseHandle(entered);CloseHandle(resume);}
};
static FacadeCallback* facade_callback=nullptr;
static void scope_callback(long bank,ASIOBool){
    auto& c=*facade_callback;SetEvent(c.entered);WaitForSingleObject(c.resume,INFINITE);
    // Original planes must survive destruction of the facade.
    std::memcpy(c.planes[1].buffers[bank],c.planes[0].buffers[bank],128*3);++c.calls;
}
static void blocked_facade_scope(const std::filesystem::path& fixture){
    FacadeCallback cb;facade_callback=&cb;auto owner=std::make_shared<DriverOwner>(spec(fixture));
    auto facade=std::make_unique<DriverFacade>(owner,LatencyProfile{7,11});ASIOCallbacks callbacks{};callbacks.bufferSwitch=scope_callback;
    require(facade->init()==ASIOTrue && facade->createBuffers(cb.planes.data(),2,128,&callbacks)==ASE_OK &&
            facade->start()==ASE_OK && WaitForSingleObject(cb.entered,2000)==WAIT_OBJECT_0,"Block callback on shared facade");
    const auto start=GetTickCount64();facade.reset();require(GetTickCount64()-start<1000 && !cb.calls,"Shared facade destruction is nonwaiting");
    bool rejected=false;try{DriverFacade next(owner,{7,11});}catch(const std::runtime_error&){rejected=true;}
    require(rejected,"Active callback destruction seals the persistent owner against reuse");
    SetEvent(cb.resume);const auto deadline=GetTickCount64()+2000;
    while(!cb.calls){require(GetTickCount64()<deadline,"Retained callback returns through original planes");Sleep(1);}
    const auto closed=owner->close();require(closed && closed->audio.retired && closed->process.process_exited && closed->process.job_empty && cb.calls==1,
            "Deferred callback and private process retire without admitting further callbacks");
}
static void fresh_clock(const std::filesystem::path& fixture){
    File clock;clock.rate(48000);HostSession session(spec(fixture,L"clock:"+clock.path.native()));
    require(!session.inspect_rate() && !session.report().process.started,"Clock refresh never acquires implicitly");
    require(session.inspect(),"Acquire before explicit fresh clock read");clock.rate(44100);
    require(session.inspect_rate()==44100u && session.report().observed_rate_hz==44100,"Fresh getter updates observed held-device metadata");ready(session.report());
    ASIOBufferInfo plane{};plane.isInput=ASIOTrue;auto cb=callbacks();
    require(session.create_buffers(&plane,1,128,&cb)==ASE_OK && !session.inspect_rate() && session.dispose_buffers()==ASE_OK,
            "Fresh clock query refused while client buffers are prepared");released(session.close());require(!session.inspect_rate(),"No refresh after final release");
    auto owner=std::make_shared<DriverOwner>(spec(fixture,L"clock:"+clock.path.native()));
    {DriverFacade facade(owner,{7,11});require(facade.init()==ASIOTrue,"Initialize first scoped metadata object");}
    clock.rate(48000);
    {DriverFacade facade(owner,{7,11});ASIOSampleRate observed=0;
        require(facade.init()==ASIOTrue && facade.getSampleRate(&observed)==ASE_OK && observed==48000,
                "Recreated ASIO object publishes newly observed rate instead of cached rate");}
    released(*owner->close());
    auto failed=std::make_shared<DriverOwner>(spec(fixture,L"fail-rate-refresh"));
    {DriverFacade first(failed,{7,11});require(first.init()==ASIOTrue,"Acquire before injected fresh-clock failure");}
    {DriverFacade next(failed,{7,11});require(next.init()==ASIOFalse,"Failed refresh cannot fall back to the earlier cached rate");}
    const auto ended=failed->close();require(ended && ended->device_released && ended->io_retired && ended->process.process_exited && ended->process.job_empty,
            "Failed fresh getter retires the held device and private process");
    clock.rate(48000);auto bound=std::make_shared<DriverOwner>(spec(fixture,L"clock:"+clock.path.native()));
    {DriverFacade first(bound,{7,11,48000,128});require(first.init()==ASIOTrue,"First clock matches bound timing profile");}
    clock.rate(44100);
    {DriverFacade next(bound,{7,11,48000,128});require(next.init()==ASIOFalse,"Recreated object rejects a freshly observed clock outside its timing profile");}
    released(*bound->close());
}
int wmain(int argc,wchar_t** argv){
    try{require(argc==3,"Retained fixture and native worker required");fresh_clock(argv[1]);facade_scope(argv[1]);blocked_facade_scope(argv[1]);diagnostic_configuration(argv[2]);lifecycle(argv[1]);blocked(argv[1]);blocked_final_close(argv[1]);destruction(argv[1]);controls(argv[1]);selection(argv[1]);failures(argv[1],argv[2]);
        std::cout<<"Retained ASIO host acquire/restart/recreate/final-release, callback ownership, native kind/absent-helper and fault tests passed; simulated positive lifetime only\n";return 0;}
    catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
