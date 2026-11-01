#include "asio/driver_facade.hpp"
#include "asio/driver_configuration.hpp"
#include "windows/diagnostic.hpp"
#include <array>
#include <fstream>
#include <iostream>
#include <set>

namespace {
using namespace sl3::asio;
using sl3::diagnostic::quote;
void require(bool ok,const char* text){if(!ok)throw std::runtime_error(text);}
#ifdef SL3_SCOPE_PROBE_SIMULATED
constexpr bool simulated=true;
#else
constexpr bool simulated=false;
#endif
struct Metadata {unsigned rate=0;};
struct Result {
    std::string phase="prepared",failed_phase,error,started=sl3::diagnostic::utc_now(),completed,worker_hash;
    unsigned attempted=0,count=0;std::array<Metadata,3> rows{};
    bool finished=false,successful=false;HostReport final{};
    void save(const std::filesystem::path& path){
        std::ofstream out(path,std::ios::trunc);require(bool(out),"Open scope evidence");
        out<<"{\"schema\":\"sl3.facade-scope-probe.v1\",\"phase\":"<<quote(phase)<<",\"failed_phase\":"<<quote(failed_phase)
           <<",\"error\":"<<quote(error)<<",\"started_utc\":"<<quote(started)<<",\"completed_utc\":"<<quote(completed)
           <<",\"simulated\":"<<(simulated?"true":"false")<<",\"finished\":"<<(finished?"true":"false")
           <<",\"successful\":"<<(successful?"true":"false")<<",\"probe_pid\":"<<GetCurrentProcessId()
           <<",\"worker_sha256\":"<<quote(worker_hash)<<",\"object_attempts\":"<<attempted<<",\"objects\":[";
        for(unsigned i=0;i<count;++i){if(i)out<<',';out<<"{\"index\":"<<i<<",\"rate_hz\":"<<rows[i].rate
            <<",\"inputs\":6,\"outputs\":6,\"packed_24\":true,\"channels_inactive\":true,\"latency_unavailable\":true}";}
        out<<"],\"audio_start_attempts\":0,\"buffers_created\":false,\"rate_setters\":0,\"firmware_requests\":0,\"timing_calibration_verified\":false,\"serato_admission_verified\":false"
           <<",\"final\":{\"failure\":"<<unsigned(final.failure)<<",\"io_retired\":"<<(final.io_retired?"true":"false")
           <<",\"device_released\":"<<(final.device_released?"true":"false")<<",\"device_held\":"<<(final.device_held?"true":"false")
           <<",\"audio_retired\":"<<(final.audio.retired?"true":"false")<<",\"termination_requested\":"<<(final.termination_requested?"true":"false")
           <<",\"process_started\":"<<(final.process.started?"true":"false")<<",\"process_exited\":"<<(final.process.process_exited?"true":"false")
           <<",\"private_job_empty\":"<<(final.process.job_empty?"true":"false")
           <<",\"audio_callbacks\":"<<final.audio.callbacks_started<<",\"input_submissions\":"<<final.device_snapshot.stats.input_submissions
           <<",\"output_submissions\":"<<final.device_snapshot.stats.output_submissions<<"}}\n";
        out.flush();require(bool(out),"Persist scope evidence");
    }
};
void normal_token(){
    HANDLE token=nullptr;require(OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token)!=0,"Query probe token");
    TOKEN_ELEVATION elevation{};DWORD size=0;const bool ok=GetTokenInformation(token,TokenElevation,&elevation,sizeof(elevation),&size)!=0;
    CloseHandle(token);require(ok && !elevation.TokenIsElevated,"Native scope probe requires an ordinary user token");
}
void inspect(DriverFacade& facade,Metadata& result){
    require(facade.init()==ASIOTrue,"Facade clock initialization failed");
    long inputs=0,outputs=0;ASIOSampleRate rate=0;
    require(facade.getChannels(&inputs,&outputs)==ASE_OK && inputs==6 && outputs==6 &&
            facade.getSampleRate(&rate)==ASE_OK && (rate==44100 || rate==48000),"Invalid scope metadata");
    for(long direction=0;direction<2;++direction)for(long channel=0;channel<6;++channel){
        ASIOChannelInfo info{};info.channel=channel;info.isInput=direction?ASIOFalse:ASIOTrue;
        require(facade.getChannelInfo(&info)==ASE_OK && info.type==ASIOSTInt24LSB && info.isActive==ASIOFalse,"Invalid inactive channel metadata");
    }
    long input_latency=71,output_latency=72;
    require(facade.getLatencies(&input_latency,&output_latency)==ASE_InvalidMode && input_latency==71 && output_latency==72,
            "Unmeasured metadata diagnostic must not report latency");
    result.rate=unsigned(rate);
}
}
int wmain(int argc,wchar_t** argv){
    try{
        bool run=false,plan=false;std::filesystem::path worker,helper,output;std::string hash;std::wstring mode=L"normal";std::set<std::wstring> seen;
        for(int i=1;i<argc;++i){const std::wstring key=argv[i];require(seen.insert(key).second,"Duplicate scope option");
            if(key==L"--run")run=true;else if(key==L"--plan")plan=true;
            else{
                require(i+1<argc,"Missing scope option value");const std::wstring value=argv[++i];
                if(key==L"--worker")worker=value;else if(key==L"--helper")helper=value;else if(key==L"--output")output=value;
                else if(key==L"--worker-sha256"){
                    for(const auto c:value){require((c>=L'0' && c<=L'9') || (c>=L'a' && c<=L'f'),"Expected lowercase worker SHA256");hash.push_back(static_cast<char>(c));}
                }
                else if(key==L"--fixture-mode" && simulated)mode=value;else throw std::invalid_argument("Unknown scope option");
            }
        }
        if(!run){require(argc==1 || (argc==2 && plan),"Plan accepts no runtime arguments");
            std::cout<<"{\"plan_only\":true,\"simulated\":"<<(simulated?"true":"false")
                     <<",\"facade_objects\":3,\"acquisitions\":1,\"clock_reads\":3,\"audio_starts\":0,\"rate_setters\":0,\"requires_timing_profile\":false,\"watchdog_ms\":20000}\n";return 0;
        }
        require(!plan && worker.is_absolute() && output.is_absolute() && !std::filesystem::exists(output) &&
                std::filesystem::is_directory(output.parent_path()),"Use a fresh absolute output directory and absolute worker");
        require(hash.size()==64 && sl3::worker::Process::executable_sha256(worker)==hash,"Scope worker identity differs");
        if(!simulated){normal_token();require(helper.is_absolute() && sl3::worker::Process::executable_sha256(helper)==reviewed_helper_sha256,"Scope helper identity differs");}
        else require(helper.empty(),"Simulated scope accepts no helper");
        require(std::filesystem::create_directory(output),"Scope evidence directory already exists");Result result;result.worker_hash=hash;const auto record=output/L"probe.json";result.save(record);
        sl3::diagnostic::Watchdog watchdog;
        std::shared_ptr<DriverOwner> owner;
        try{
            WorkerSpec spec;spec.executable=worker;spec.sha256=hash;spec.helper=helper;
            spec.kind=simulated?sl3::session::Kind::simulated:sl3::session::Kind::native;spec.lifetime=DeviceLifetime::retained;spec.fixture_mode=mode;
            if(!simulated)spec.diagnostic_directory=output;
            owner=std::make_shared<DriverOwner>(spec);
            for(unsigned i=0;i<3;++i){
                result.phase="object-"+std::to_string(i);++result.attempted;result.save(record);
                {DriverFacade facade(owner,LatencyProfile{0,0});inspect(facade,result.rows[i]);}
                ++result.count;result.save(record);
                require(result.rows[i].rate==result.rows[0].rate,"Clock changed during metadata scope");
            }
            result.phase="closing";result.save(record);const auto final=owner->close();require(bool(final),"Scope owner still borrowed");result.final=*final;
            require(final->failure==HostFailure::none && final->io_retired && final->device_released && !final->device_held && final->audio.retired &&
                    final->process.started && final->process.process_exited && final->process.job_empty && !final->termination_requested &&
                    !final->audio.callbacks_started && !final->device_snapshot.stats.input_submissions && !final->device_snapshot.stats.output_submissions,
                    "Scope final retirement or no-audio check failed");result.successful=true;
        }catch(const std::exception& error){
            result.failed_phase=result.phase;result.error=error.what();
            if(owner){const auto final=owner->close();if(final)result.final=*final;}
        }
        owner.reset();result.finished=true;result.phase="finished";result.completed=sl3::diagnostic::utc_now();result.save(record);
        std::cout<<"Scope metadata diagnostic finished; simulated="<<simulated<<", success="<<result.successful<<"\n";return result.successful?0:1;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
