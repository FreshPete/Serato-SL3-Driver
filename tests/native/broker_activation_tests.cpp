#include "asio/broker_activation.hpp"
#include <array>
#include <cstring>
#include <fstream>
#include <iostream>
#include <thread>

using namespace sl3;using namespace sl3::asio;
namespace {
void require(bool value,const char* text){if(!value)throw std::runtime_error(text);}
void write(const std::filesystem::path& path,const std::string& value){
    require(!std::filesystem::exists(path),"Fresh fixture file required");std::ofstream out(path,std::ios::binary);out<<value;require(out.good(),"Write fixture file");
}
template<class F>void refuses(F operation){try{operation();}catch(const std::exception&){return;}throw std::runtime_error("Expected activation refusal");}
std::filesystem::path self(){std::array<wchar_t,32768> buffer{};const auto size=GetModuleFileNameW(nullptr,buffer.data(),DWORD(buffer.size()));
    require(size && size<buffer.size(),"Find fixture executable");return std::wstring(buffer.data(),size);}
std::atomic<unsigned> callbacks{0};std::array<ASIOBufferInfo,12> planes{};
void callback(long bank,ASIOBool){
    for(unsigned channel=6;channel<12;++channel)std::memset(planes[channel].buffers[bank],0,128*3);
    callbacks.fetch_add(1);
}
void stream(DriverConfiguration& config){
    require(config.broker.has_value(),"Activation returned broker configuration");
    auto audio_owner=std::make_shared<DriverOwner>(*config.broker,config.files);
    {
    DriverFacade driver(audio_owner,config.latency);
    require(driver.init()==ASIOTrue,"Activated broker initializes ASIO facade");
    for(unsigned channel=0;channel<12;++channel)planes[channel]={channel<6?ASIOTrue:ASIOFalse,long(channel%6),{}};
    ASIOCallbacks calls{};calls.bufferSwitch=callback;
    require(driver.createBuffers(planes.data(),12,128,&calls)==ASE_OK,"Create activated ASIO buffers");
    for(unsigned cycle=0;cycle<2;++cycle){
        const auto before=callbacks.load();require(driver.start()==ASE_OK,"Start activated simulated audio");
        const auto began=GetTickCount64();while(callbacks.load()<before+12){require(GetTickCount64()-began<5000,"Activation callback deadline");Sleep(5);}
        require(driver.stop()==ASE_OK,"Stop activated simulated audio");
    }
    require(driver.disposeBuffers()==ASE_OK,"Dispose activated ASIO buffers");
    }
    const auto final=audio_owner->close();require(final.has_value() && driver_session_closed(*final),"Detach activated ASIO facade");
}
}
int wmain(int argc,wchar_t** argv){
    try{
        // A separate owned child deliberately misses startup readiness. It
        // accepts no input contents and does not open a worker/helper/device.
        if(argc==8 && std::wstring(argv[1])==L"--run"){
            Sleep(1000);write(std::filesystem::path(std::wstring(argv[5])+L".fixture-exited"),"normal\n");return 0;
        }
        require(argc==5,"Expected simulated controller, worker, reviewed helper and fresh output directory");
        const auto root=std::filesystem::absolute(argv[4]);require(!std::filesystem::exists(root),"New fixture root required");
        std::filesystem::create_directory(root);
        const auto worker=std::filesystem::absolute(argv[2]),helper=std::filesystem::absolute(argv[3]);
        const auto worker_hash=worker::Process::executable_sha256(worker),helper_hash=worker::Process::executable_sha256(helper);
        const auto timing=root/L"timing.txt",input=root/L"input.conf";
        write(timing,"SL3-ASIO-DIAGNOSTIC-TIMING-1\nworker_sha256="+worker_hash+"\nhelper_sha256="+helper_hash+"\nrate_hz=44100\nbuffer_frames=128\n");
        write(input,"SL3-ASIO-CONFIG-1\nworker="+worker.u8string()+"\nworker_sha256="+worker_hash+"\nhelper="+helper.u8string()+
                    "\ntiming_record="+timing.u8string()+"\ntiming_record_sha256="+worker::Process::executable_sha256(timing)+"\n");
        BrokerActivationSpec spec;spec.controller=std::filesystem::absolute(argv[1]);spec.controller_sha256=worker::Process::executable_sha256(spec.controller);
        spec.input=input;spec.input_sha256=worker::Process::executable_sha256(input);spec.output=root/L"session";
        spec.timing=TimingPolicy::unmeasured_diagnostic;spec.kind=session::Kind::simulated;spec.lifetime_ms=60000;
        {
            auto bad=spec;bad.input_sha256=std::string(64,'0');refuses([&]{BrokerActivation::start(bad);});
            require(!std::filesystem::exists(spec.output),"Wrong input refuses before controller output");
            bad=spec;bad.controller_sha256=std::string(64,'0');refuses([&]{BrokerActivation::start(bad);});
            require(!std::filesystem::exists(spec.output),"Wrong controller refuses before process launch");
            bad=spec;bad.output=root;refuses([&]{BrokerActivation::start(bad);});
            bad=spec;bad.lifetime_ms=600001;refuses([&]{BrokerActivation::start(bad);});
            bad=spec;bad.controller=self();bad.controller_sha256=worker::Process::executable_sha256(self());bad.output=root/L"delayed";
            bad.startup_timeout_ms=100;bad.startup_failure_grace_ms=2000;
            try{BrokerActivation::start(bad);throw std::runtime_error("Expected delayed startup refusal");}
            catch(const BrokerActivationError& error){require(error.cleanup.controller.process_exited && error.cleanup.controller.job_empty &&
                !error.cleanup.termination_requested,"Failed startup exposes normal owned-child retirement");}
            require(std::filesystem::exists(root/L"delayed.fixture-exited"),"Failed startup waits for exact owned child normal exit");
            bad.output=root/L"forced";bad.startup_failure_grace_ms=0;
            try{BrokerActivation::start(bad);throw std::runtime_error("Expected contained startup refusal");}
            catch(const BrokerActivationError& error){require(error.cleanup.termination_requested && error.cleanup.controller.process_exited &&
                error.cleanup.controller.job_empty,"Failed startup exposes forced containment separately");}
            require(!std::filesystem::exists(root/L"forced.fixture-exited"),"Contained fixture cannot finish its delayed operation");
        }
        {
            auto owner=BrokerActivation::start(spec);auto observed=owner->observe();
            require(observed.ready && observed.controller.started && !observed.controller.process_exited,"On-demand owned controller became ready");
            {
                auto selected=owner->configuration();
                const auto deferred=owner->close(0);
                require(deferred.retirement_deferred && !deferred.stop_requested && !deferred.termination_requested,"Live configuration defers activation retirement");
                require(owner->close(16000).retirement_deferred,"Invalid grace cannot bypass a retained configuration");
                stream(selected);
                require(!owner->observe().controller.process_exited,"Controller stays live until final configuration retires");
            }
            const auto final=owner->close();
            require(final.stop_requested && final.controller.process_exited && final.controller.job_empty &&
                    final.controller.exit_code_known && final.controller.exit_code==0 && !final.termination_requested && final.cleanup_error.empty(),
                    "Owned activation stops cleanly after configuration retirement");
            const auto again=owner->close();require(again.controller.process_exited && !again.termination_requested,"Activation close is repeatable");
        }
        {
            spec.output=root/L"retained";auto owner=BrokerActivation::start(spec);auto selected=owner->configuration();
            auto wait=selected.broker->server;std::weak_ptr<BrokerActivation> weak=owner;owner.reset();
            require(!weak.expired() && WaitForSingleObject(wait->handle(),0)==WAIT_TIMEOUT,"Returned configuration retains activation lifetime");
            selected=DriverConfiguration{};
            require(weak.expired() && WaitForSingleObject(wait->handle(),0)==WAIT_OBJECT_0,"Final configuration releases and retires activation");
        }
        std::cout<<"{\"schema\":\"sl3.broker-activation-tests.v1\",\"passed\":true,\"simulatedSessions\":2,"
                   "\"asioStartStopCycles\":2,\"callbacks\":"<<callbacks.load()<<",\"nativeDeviceAccess\":false,"
                   "\"failedStartupNormalExitObserved\":true,\"failedStartupForcedContainmentObserved\":true,"
                   "\"serviceInstalled\":false,\"productionAsioEntryChanged\":false}\n";return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
