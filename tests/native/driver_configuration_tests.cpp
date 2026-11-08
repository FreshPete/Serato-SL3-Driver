#include "asio/driver_configuration.hpp"
#include "asio/broker_activation.hpp"
#include "asio/com_identity.hpp"
#include "com_activation_fixture.hpp"
#include "iasiodrv.h"
#include "windows/broker_record.hpp"
#include "windows/broker_pipe.hpp"
#include <future>
#include <fstream>
#include <iostream>
#include <stdexcept>

using namespace sl3::asio;
static void require(bool good,const char* text){if(!good)throw std::runtime_error(text);}
template<class F>static void rejects(F operation){bool rejected=false;try{operation();}catch(const std::exception&){rejected=true;}require(rejected,"Malformed/mismatched configuration accepted");}
static void write(const std::filesystem::path& path,const std::string& bytes){std::ofstream stream(path,std::ios::binary);stream<<bytes;require(bool(stream),"Write temporary synthetic configuration record");}
static std::string digest(const std::filesystem::path& path){return sl3::worker::Process::executable_sha256(path);}
struct Fixture {
    std::filesystem::path folder=std::filesystem::temp_directory_path()/(L"SL3Config-"+std::to_wstring(GetCurrentProcessId())+L"-"+std::to_wstring(GetTickCount64()));
    std::filesystem::path config=folder/L"sl3-asio.conf",timing=folder/L"timing.txt",measurement=folder/L"measurement-\u6d4b\u91cf.txt",dll=folder/L"sl3-native-provider-test.dll",session=folder/L"broker-session.txt",audit=folder/L"broker-audit.txt";
    std::filesystem::path target=folder/L"live-session.conf",pointer=folder/L"current-session.txt",image_copy=folder/L"other-broker.exe";
    std::string worker_hash,worker_path,helper_path,timing_text,config_text;
    Fixture(const std::filesystem::path& worker,const std::filesystem::path& helper){
        require(std::filesystem::create_directory(folder),"Create unique temporary configuration folder");
        require(digest(helper)==reviewed_helper_sha256,"Tests require reviewed helper bytes; never loaded");
        worker_hash=digest(worker);worker_path=worker.u8string();helper_path=helper.u8string();
        write(measurement,"SYNTHETIC CONFIGURATION PARSER TEST ONLY. No physical timing measurement or approval.\n");
        timing_text="SL3-ASIO-TIMING-1\nreview=approved\nworker_sha256="+worker_hash+"\nhelper_sha256="+reviewed_helper_sha256+
            "\nrate_hz=48000\nbuffer_frames=128\nintervals=8\nrequests_per_direction=4\ninput_extra_frames=7\noutput_extra_frames=11\nmeasurement_file="+measurement.u8string()+"\nmeasurement_sha256="+digest(measurement)+"\n";
        reset();
    }
    void reset(){write(timing,timing_text);config_text="SL3-ASIO-CONFIG-1\nworker="+worker_path+"\nworker_sha256="+worker_hash+"\nhelper="+helper_path+
        "\ntiming_record="+timing.u8string()+"\ntiming_record_sha256="+digest(timing)+"\n";write(config,config_text);}
    void replace_timing(const std::string& from,const std::string& to){auto value=timing_text;const auto at=value.find(from);require(at!=std::string::npos,"Test mutation field exists");value.replace(at,from.size(),to);write(timing,value);
        auto config_value=config_text;config_value.replace(config_value.find("timing_record_sha256=")+21,64,digest(timing));write(config,config_value);}
    ~Fixture(){for(const auto& item:{dll,config,timing,measurement,session,audit,target,pointer,image_copy}){std::error_code error;std::filesystem::remove(item,error);}std::error_code error;std::filesystem::remove(folder,error);}
};
static bool locked(const std::filesystem::path& path){
    const auto handle=CreateFileW(path.c_str(),GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(handle==INVALID_HANDLE_VALUE)return GetLastError()==ERROR_SHARING_VIOLATION;CloseHandle(handle);return false;
}
static void records(Fixture& fixture){
    const auto unicode=fixture.folder/L"session-\u4f1a\u8bdd.conf";
    const auto pointer=sl3::asio::parse_session_pointer(sl3::asio::session_pointer_text(unicode,fixture.worker_hash));
    require(pointer.configuration==unicode && pointer.sha256==fixture.worker_hash,"Shared pointer codec round-trips UTF-8 path and hash without target I/O");
    rejects([&]{sl3::asio::session_pointer_text("relative.conf",fixture.worker_hash);});
    rejects([&]{sl3::asio::session_pointer_text(unicode,std::string(64,'A'));});
    rejects([&]{sl3::asio::parse_session_pointer(std::string(65537,'x'));});
    {
        const auto config=load_driver_entry_configuration(fixture.config);
        require(config.worker.kind==sl3::session::Kind::native && config.worker.lifetime==DeviceLifetime::retained && config.worker.sha256==fixture.worker_hash && config.latency.rate_hz==48000 && config.latency.buffer_frames==128 &&
            config.latency.input_extra_frames==7 && config.latency.output_extra_frames==11,"Strict config binds only native mode and exact timing profile");
        for(const auto& item:{fixture.config,fixture.timing,fixture.measurement,config.worker.executable,config.worker.helper})require(locked(item),"All reviewed bytes remain write/delete locked");
    }
    require(!locked(fixture.config) && !locked(fixture.timing),"Configuration lease releases file locks");
    fixture.replace_timing("SL3-ASIO-TIMING-1","SL3-ASIO-TIMING-2");
    require(load_driver_configuration(fixture.config).keepalive_timing_sha256==digest(fixture.timing),
        "Keepalive profile binds exact timing bytes for the controller");
    rejects([&]{load_driver_entry_configuration(fixture.config);});
    fixture.reset();
    for(const auto& value:{fixture.config_text+"extra=1\n",fixture.config_text.substr(0,fixture.config_text.size()-1),std::string("\xef\xbb\xbf")+fixture.config_text,fixture.config_text+"\n"}){
        write(fixture.config,value);rejects([&]{load_driver_configuration(fixture.config);});
    }
    fixture.reset();write(fixture.measurement,"Changed synthetic bytes\n");rejects([&]{load_driver_configuration(fixture.config);});
    write(fixture.measurement,"SYNTHETIC CONFIGURATION PARSER TEST ONLY. No physical timing measurement or approval.\n");fixture.reset();
    for(const auto& change:std::vector<std::pair<std::string,std::string>>{
        {"review=approved","review=pending"},{"rate_hz=48000","rate_hz=96000"},{"buffer_frames=128","buffer_frames=96"},
        {"intervals=8","intervals=64"},{"requests_per_direction=4","requests_per_direction=8"},
        {"input_extra_frames=7","input_extra_frames=4294967295"},{"output_extra_frames=11","output_extra_frames=-1"},
        {"rate_hz=48000","rate_hz=048000"},{"helper_sha256="+std::string(reviewed_helper_sha256),"helper_sha256="+std::string(64,'0')},
        {"worker_sha256="+fixture.worker_hash,"worker_sha256="+std::string(64,'0')},{"measurement_file="+fixture.measurement.u8string(),"measurement_file=relative.txt"}}){
        fixture.reset();fixture.replace_timing(change.first,change.second);rejects([&]{load_driver_configuration(fixture.config);});
    }
    fixture.reset();
    // Timing bytes must be unchanged even when their internal fields still parse.
    write(fixture.timing,fixture.timing_text+"\n");rejects([&]{load_driver_configuration(fixture.config);});fixture.reset();
    auto config=fixture.config_text;config.replace(config.find("worker_sha256=")+14,64,std::string(64,'0'));write(fixture.config,config);rejects([&]{load_driver_configuration(fixture.config);});fixture.reset();
    for(const auto& rejected_path:{std::string("relative.exe"),std::string("\\\\server\\share\\worker.exe"),std::string("\\\\.\\pipe\\worker"),fixture.worker_path+":stream"}){
        auto value=fixture.config_text;value.replace(value.find("worker=")+7,fixture.worker_path.size(),rejected_path);write(fixture.config,value);
        rejects([&]{load_driver_configuration(fixture.config);});
    }
    fixture.reset();
    const auto adjacent=production_configuration_path();require(adjacent.is_absolute() && adjacent.filename()==L"sl3-asio.conf" && adjacent.parent_path()==std::filesystem::path([]{std::vector<wchar_t> value(32768);const auto n=GetModuleFileNameW(nullptr,value.data(),DWORD(value.size()));return std::wstring(value.data(),n);}()).parent_path(),"Configuration follows containing module, not working directory");
}
static void diagnostic_timing(Fixture& f){
    const auto text="SL3-ASIO-DIAGNOSTIC-TIMING-1\nworker_sha256="+f.worker_hash+
        "\nhelper_sha256="+reviewed_helper_sha256+"\nrate_hz=44100\nbuffer_frames=128\n";
    const auto set_timing=[&](const std::string& timing){
        write(f.timing,timing);
        auto config=f.config_text;
        config.replace(config.find("timing_record_sha256=")+21,64,digest(f.timing));
        write(f.config,config);
    };
    rejects([&]{load_driver_configuration(f.config,TimingPolicy::unmeasured_diagnostic);});
    set_timing(text);
    rejects([&]{load_driver_configuration(f.config);});
    rejects([&]{load_driver_entry_configuration(f.config);});
    {
        const auto result=load_driver_entry_configuration(f.config,TimingPolicy::unmeasured_diagnostic);
        require(!result.latency.report_latency && result.latency.rate_hz==44100 &&
                result.latency.buffer_frames==128 && result.keepalive_timing_sha256.empty(),
                "Explicit diagnostic policy preserves fixed clock and unavailable latency");
    }
    auto wrong_rate=text;
    wrong_rate.replace(wrong_rate.find("44100"),5,"48000");
    set_timing(wrong_rate);
    rejects([&]{load_driver_configuration(f.config,TimingPolicy::unmeasured_diagnostic);});
    for(unsigned frames:{32u,64u}){
        auto trial=text;
        trial.replace(trial.find("buffer_frames=128"),17,"buffer_frames="+std::to_string(frames));
        set_timing(trial);
        rejects([&]{load_driver_configuration(f.config,TimingPolicy::unmeasured_diagnostic);});
        trial.replace(trial.find("TIMING-1"),8,"TIMING-2");
        set_timing(trial);
        const auto result=load_driver_configuration(f.config,TimingPolicy::unmeasured_diagnostic);
        require(result.latency.buffer_frames==frames && !result.latency.report_latency &&
                result.keepalive_timing_sha256==digest(f.timing),
                "Lower diagnostic bank pins the keepalive profile without claiming latency");
    }
    f.reset();
}
static void production_abi(Fixture& fixture,const std::filesystem::path& source,bool activate_com=false){
    std::unique_ptr<sl3::test::ComApartment> apartment;std::unique_ptr<sl3::test::ComActivation> activation;
    if(!std::filesystem::exists(fixture.dll))require(std::filesystem::copy_file(source,fixture.dll),"Copy production DLL into isolated test folder");
    else require(digest(source)==digest(fixture.dll),"Reuse only identical isolated production DLL bytes");
    if(activate_com){apartment=std::make_unique<sl3::test::ComApartment>(COINIT_APARTMENTTHREADED);activation=std::make_unique<sl3::test::ComActivation>(fixture.dll);}
    const auto module=LoadLibraryExW(fixture.dll.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);require(module!=nullptr,"Load isolated production ASIO DLL");
    using GetClass=HRESULT(__stdcall*)(REFCLSID,REFIID,void**);using CanUnload=HRESULT(__stdcall*)();
    const auto get=reinterpret_cast<GetClass>(GetProcAddress(module,"DllGetClassObject"));const auto unload=reinterpret_cast<CanUnload>(GetProcAddress(module,"DllCanUnloadNow"));
    require(get && unload && !GetProcAddress(module,"sl3_test_configure") && !GetProcAddress(module,"sl3_test_configure_broker") && !GetProcAddress(module,"DllRegisterServer"),"Production exports exclude test provider and registration");
    IClassFactory* factory=nullptr;require(get(sl3::asio::driver_clsid,IID_IClassFactory,reinterpret_cast<void**>(&factory))==S_OK,"Production COM factory");
    IASIO* device=nullptr;const auto result=activate_com?CoCreateInstance(sl3::asio::driver_clsid,nullptr,CLSCTX_INPROC_SERVER,sl3::asio::driver_clsid,reinterpret_cast<void**>(&device)):
        factory->CreateInstance(nullptr,sl3::asio::driver_clsid,reinterpret_cast<void**>(&device));
    require(result==S_OK,"Production IASIO object through selected activation path");
    require(device->init(nullptr)==ASIOFalse,"Production rejects truthful simulated-kind worker before clock/device access");
    char message[124]{};device->getErrorMessage(message);
    require(std::string(message).find("worker/clock inspection failed")!=std::string::npos && locked(fixture.config),"Actual native provider consumed adjacent config and retained its lease, then failed handshake");
    long input=77,output=78;require(device->getChannels(&input,&output)==ASE_NotPresent && input==77 && output==78,"Production rejection never publishes ASIO readiness");
    device->Release();factory->Release();require(unload()==S_OK && FreeLibrary(module) && !locked(fixture.config),"Production failure releases COM/module/configuration ownership");
    if(activate_com)CoFreeUnusedLibrariesEx(0,0);
}
static void locator_records(Fixture& f,const std::filesystem::path& image,const std::string& session_text){
    write(f.target,session_text);
    const auto pointer_text="SL3-ASIO-SESSION-POINTER-1\nconfiguration="+f.target.u8string()+"\nconfiguration_sha256="+digest(f.target)+"\n";
    const auto locator="SL3-ASIO-LOCATOR-1\nsession_pointer="+f.pointer.u8string()+"\nbroker="+image.u8string()+"\nbroker_sha256="+digest(image)+"\nworker_sha256="+f.worker_hash+"\n";
    write(f.pointer,pointer_text);write(f.config,locator);
    {
        const auto selected=load_driver_entry_configuration(f.config);
        require(selected.broker && selected.broker->worker_sha256==f.worker_hash,"Locator selects native-only broker configuration");
        for(const auto& file:{f.config,f.target,f.session,f.timing,f.measurement,image})require(locked(file),"Locator, target and reviewed identities remain pinned");
        require(!locked(f.pointer),"Mutable pointer lease ends after resolution");
        const auto endpoint=selected.broker->endpoint;const auto server=selected.broker->server->handle();
        write(f.pointer,"Changed pointer after resolution\n");
        require(selected.broker->endpoint==endpoint && selected.broker->server->handle()==server && WaitForSingleObject(server,0)==WAIT_TIMEOUT,
                "Pointer change cannot redirect existing attachment/process reference");
        rejects([&]{load_driver_entry_configuration(f.config);});write(f.pointer,pointer_text);
    }
    require(!locked(f.config) && !locked(f.target),"Locator and target leases retire");
    for(const auto& malformed:{pointer_text+"extra=1\n",pointer_text.substr(0,pointer_text.size()-1),std::string("\xef\xbb\xbf")+pointer_text,
                              std::string("SL3-ASIO-SESSION-POINTER-2\nconfiguration=")+f.target.u8string()+"\nconfiguration_sha256="+digest(f.target)+"\n",
                              std::string("SL3-ASIO-SESSION-POINTER-1\nconfiguration=relative.conf\nconfiguration_sha256=")+digest(f.target)+"\n"}){
        write(f.pointer,malformed);rejects([&]{load_driver_entry_configuration(f.config);});
    }
    write(f.pointer,pointer_text);
    for(const auto& key:{"broker_sha256=","worker_sha256="}){
        auto bad=locator;bad.replace(bad.find(key)+std::string(key).size(),64,std::string(64,'0'));write(f.config,bad);
        rejects([&]{load_driver_entry_configuration(f.config);});
    }
    for(const auto& bad:{locator+"extra=1\n",locator.substr(0,locator.size()-1),std::string("\xef\xbb\xbf")+locator}){
        write(f.config,bad);rejects([&]{load_driver_entry_configuration(f.config);});
    }
    write(f.config,locator);auto mismatch=pointer_text;mismatch.replace(mismatch.find("configuration_sha256=")+21,64,std::string(64,'0'));
    write(f.pointer,mismatch);rejects([&]{load_driver_entry_configuration(f.config);});write(f.pointer,pointer_text);
    require(std::filesystem::copy_file(image,f.image_copy),"Distinct broker image with identical bytes");
    auto wrong_identity=locator;wrong_identity.replace(wrong_identity.find("broker=")+7,image.u8string().size(),f.image_copy.u8string());write(f.config,wrong_identity);
    rejects([&]{load_driver_entry_configuration(f.config);});write(f.config,locator);
    // No pointer/locator chaining, cycles or private-worker fallback.
    write(f.pointer,"SL3-ASIO-SESSION-POINTER-1\nconfiguration="+f.config.u8string()+"\nconfiguration_sha256="+digest(f.config)+"\n");
    rejects([&]{load_driver_entry_configuration(f.config);});
    write(f.target,f.config_text);write(f.pointer,"SL3-ASIO-SESSION-POINTER-1\nconfiguration="+f.target.u8string()+"\nconfiguration_sha256="+digest(f.target)+"\n");
    rejects([&]{load_driver_entry_configuration(f.config);});
    write(f.target,session_text);write(f.pointer,pointer_text);
}
static void broker_records(Fixture& f,const std::filesystem::path& worker,const std::filesystem::path& library){
    f.reset();sl3::worker::BrokerListener listener;
    std::vector<wchar_t> name(32768);const auto count=GetModuleFileNameW(nullptr,name.data(),DWORD(name.size()));require(count && count<name.size(),"Test process image path");
    const std::filesystem::path image(std::wstring(name.data(),count));
    write(f.session,sl3::worker::broker_record_text(listener.name(),f.worker_hash));
    auto text=f.config_text;text.replace(0,std::string("SL3-ASIO-CONFIG-1").size(),"SL3-ASIO-BROKER-CONFIG-1");
    text+="broker="+image.u8string()+"\nbroker_sha256="+digest(image)+"\nsession_record="+f.session.u8string()+"\nsession_record_sha256="+digest(f.session)+"\n";write(f.config,text);
    {
        const auto config=load_driver_configuration(f.config);
        require(config.broker && config.broker->kind==sl3::session::Kind::native && config.broker->worker_sha256==f.worker_hash &&
            config.broker->endpoint==listener.name() && GetProcessId(config.broker->server->handle())==GetCurrentProcessId(),"Production broker schema binds native kind, worker contract and exact live server");
        require(locked(f.config) && locked(f.session) && locked(f.timing) && locked(f.measurement),"Broker and timing bytes remain pinned together");
    }
    require(!locked(f.session),"Broker record lease ends after configuration release");
    for(const auto key:{"broker_sha256=","session_record_sha256="}){
        auto bad=text;const auto start=bad.find(key)+std::string(key).size();bad.replace(start,64,std::string(64,'0'));write(f.config,bad);rejects([&]{load_driver_configuration(f.config);});
    }
    write(f.config,text);
    locator_records(f,image,text);
    struct Event {HANDLE value=CreateEventW(nullptr,TRUE,FALSE,nullptr);~Event(){if(value)CloseHandle(value);}} ready,stop;
    require(ready.value && stop.value,"Broker configuration test events");
    auto server=std::async(std::launch::async,[&]{
        sl3::worker::BrokerSpec spec;spec.executable=worker;spec.sha256=f.worker_hash;spec.kind=sl3::session::Kind::simulated;spec.fixture_mode=L"audit:"+f.audit.native();
        sl3::worker::RetainedBroker owner(spec);require(owner.open(),"Explicit simulated broker startup");SetEvent(ready.value);
        const auto deadline=GetTickCount64()+10000;bool rejected=false;
        while(GetTickCount64()<deadline && WaitForSingleObject(stop.value,0)==WAIT_TIMEOUT){
            std::string diagnostic;const auto result=sl3::worker::serve_broker_client(listener,owner,stop.value,&diagnostic);
            if(result!=sl3::worker::BrokerServeResult::no_client){rejected=result==sl3::worker::BrokerServeResult::rejected && diagnostic=="Broker greeting/worker kind mismatch";break;}
        }
        const auto final=owner.close();return rejected && !final.failed && final.device.device_released && final.process.process_exited && final.process.job_empty;
    });
    require(WaitForSingleObject(ready.value,8000)==WAIT_OBJECT_0,"Simulated broker ready");
    production_abi(f,library,true);
    require(server.get(),"Actual production DLL consumed broker record and refused simulated kind before client admission");
    std::ifstream audit(f.audit);std::vector<std::string> lines;for(std::string line;std::getline(audit,line);)lines.push_back(line);
    require(lines==std::vector<std::string>({"acquire","rate","release"}),"Native-only production rejection issues no client clock/audio operation");
    f.reset();
}
int wmain(int argc,wchar_t** argv){
    if(argc==3 && std::wstring(argv[1])==L"--inspect-activation"){
        try{
            const auto config=load_driver_entry_configuration(std::filesystem::absolute(argv[2]),TimingPolicy::unmeasured_diagnostic);
            require(config.activation && !config.broker && config.activation->kind==sl3::session::Kind::native &&
                    config.activation->output.empty(),"Native passive activation record required");
            require(!GetModuleHandleW(L"UsbDkHelper.dll10") && !GetModuleHandleW(L"UsbDkHelper.dll"),"Inspector must not load the USB helper");
            std::cout<<"{\"schema\":\"sl3.activation-config-inspection.v1\",\"accepted\":true,\"nativeKind\":true,"
                       "\"unmeasuredDiagnostic\":true,\"activationAttempted\":false,\"helperLoaded\":false,\"deviceAccess\":false}\n";
            return 0;
        }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
    }
    try{require(argc==4,"Simulated fixture, reviewed helper and production DLL paths required");Fixture fixture(argv[1],argv[2]);records(fixture);diagnostic_timing(fixture);production_abi(fixture,argv[3]);broker_records(fixture,argv[1],argv[3]);
        require(!GetModuleHandleW(L"UsbDkHelper.dll10") && !GetModuleHandleW(L"UsbDkHelper.dll"),"Helper never loaded in test host");
        std::cout<<"Strict direct/locator/pointer configuration/hash/profile bindings, held file leases and actual production ASIO provider rejection of simulated worker passed; synthetic records only, no physical USB\n";
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
