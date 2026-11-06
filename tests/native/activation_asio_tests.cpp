#include "asio/broker_activation.hpp"
#include "asio/com_identity.hpp"
#include "asio/scope_interface.hpp"
#include "iasiodrv.h"
#include <array>
#include <cstring>
#include <fstream>
#include <iostream>

using namespace sl3;using namespace sl3::asio;
namespace {
void require(bool value,const char* text){if(!value)throw std::runtime_error(text);}
void write(const std::filesystem::path& path,const std::string& bytes){
    require(!std::filesystem::exists(path),"Fresh activation fixture file required");std::ofstream stream(path,std::ios::binary);stream<<bytes;
    require(stream.good(),"Write activation fixture input");
}
template<class T>T function(HMODULE library,const char* name){const auto value=GetProcAddress(library,name);require(value!=nullptr,"Fixture export missing");
    T result;static_assert(sizeof(result)==sizeof(value));std::memcpy(&result,&value,sizeof(value));return result;}
std::atomic<unsigned> callbacks{0};std::array<ASIOBufferInfo,12> planes{};
std::atomic<bool> block{false};std::atomic<unsigned> blocked_completed{0};HANDLE entered=nullptr,release=nullptr;
void callback(long bank,ASIOBool){
    const bool held=block.load();if(held){SetEvent(entered);WaitForSingleObject(release,INFINITE);}
    for(unsigned n=6;n<12;++n)std::memset(planes[n].buffers[bank],0,128*3);
    callbacks.fetch_add(1);if(held)blocked_completed.fetch_add(1);
}
void play(IASIO* device){
    require(device->init(nullptr)==ASIOTrue,"IASIO init activates simulated broker");
    long input=0,output=0;require(device->getChannels(&input,&output)==ASE_OK && input==6 && output==6,"Activated IASIO channels");
    for(unsigned channel=0;channel<12;++channel)planes[channel]={channel<6?ASIOTrue:ASIOFalse,long(channel%6),{}};
    ASIOCallbacks calls{};calls.bufferSwitch=callback;require(device->createBuffers(planes.data(),12,128,&calls)==ASE_OK,"Create activated IASIO planes");
    const auto before=callbacks.load();require(device->start()==ASE_OK,"Start activated IASIO stream");
    const auto began=GetTickCount64();while(callbacks.load()<before+12){require(GetTickCount64()-began<5000,"IASIO callback deadline");Sleep(2);}
    require(device->stop()==ASE_OK && device->disposeBuffers()==ASE_OK,"Stop/dispose activated IASIO stream");
}
std::size_t sessions(const std::filesystem::path& root){
    std::size_t count=0;for(const auto& child:std::filesystem::directory_iterator(root))count+=child.is_directory();return count;
}
}
int wmain(int argc,wchar_t** argv){
    HMODULE library=nullptr;IClassFactory* factory=nullptr;IASIO* device=nullptr;sl3::asio::DeviceScope* scope=nullptr;
    try{
        require(argc==6,"Activation DLL, simulated controller/worker, reviewed helper and fresh output required");
        require(SUCCEEDED(CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED)),"Initialize fixture COM apartment");
        const auto root=std::filesystem::absolute(argv[5]);require(!std::filesystem::exists(root),"Fresh activation ASIO root");std::filesystem::create_directory(root);
        const auto worker=std::filesystem::absolute(argv[3]),helper=std::filesystem::absolute(argv[4]);
        const auto controller=std::filesystem::absolute(argv[2]);const auto timing=root/L"timing.txt",input=root/L"input.conf",entry=root/L"activation.conf";
        const auto worker_hash=worker::Process::executable_sha256(worker),helper_hash=worker::Process::executable_sha256(helper);
        write(timing,"SL3-ASIO-DIAGNOSTIC-TIMING-1\nworker_sha256="+worker_hash+"\nhelper_sha256="+helper_hash+"\nrate_hz=44100\nbuffer_frames=128\n");
        write(input,"SL3-ASIO-CONFIG-1\nworker="+worker.u8string()+"\nworker_sha256="+worker_hash+"\nhelper="+helper.u8string()+
            "\ntiming_record="+timing.u8string()+"\ntiming_record_sha256="+worker::Process::executable_sha256(timing)+"\n");
        write(entry,"SL3-ASIO-ACTIVATION-1\ncontroller="+controller.u8string()+"\ncontroller_sha256="+worker::Process::executable_sha256(controller)+
            "\ninput="+input.u8string()+"\ninput_sha256="+worker::Process::executable_sha256(input)+
            "\nstartup_timeout_ms=15000\nstartup_failure_grace_ms=5000\nlifetime_ms=60000\n");
        {auto inspected=load_driver_entry_configuration(entry,TimingPolicy::unmeasured_diagnostic);
            require(inspected.activation && inspected.activation->kind==session::Kind::native && inspected.activation->output.empty() && sessions(root)==0,
                    "Production activation parse is native-only and creates no controller/output");}
        {
            std::ifstream source(entry,std::ios::binary);const std::string original((std::istreambuf_iterator<char>(source)),{});
            std::vector<std::string> invalid;
            auto change=[&](const std::string& from,const std::string& to){auto changed=original;const auto at=changed.find(from);
                require(at!=std::string::npos,"Activation mutation exists");changed.replace(at,from.size(),to);invalid.push_back(std::move(changed));};
            change("SL3-ASIO-ACTIVATION-1","SL3-ASIO-ACTIVATION-2");change("startup_timeout_ms=15000","startup_timeout_ms=99");
            change("startup_failure_grace_ms=5000","startup_failure_grace_ms=15001");change("lifetime_ms=60000","lifetime_ms=600001");
            change("lifetime_ms=60000","lifetime_ms=060000");change("controller_sha256="+worker::Process::executable_sha256(controller),"controller_sha256="+std::string(64,'0'));
            invalid.push_back(original+"kind=simulated\n");invalid.push_back(original.substr(0,original.size()-1));
            unsigned index=0;
            for(const auto& bytes:invalid){const auto bad=root/(L"invalid-"+std::to_wstring(++index)+L".conf");write(bad,bytes);bool rejected=false;
                try{load_driver_entry_configuration(bad,TimingPolicy::unmeasured_diagnostic);}catch(const std::exception&){rejected=true;}
                require(rejected && sessions(root)==0,"Malformed activation record refuses without a process or output");}
        }
        {
            BrokerActivationSpec first,second;select_user_activation_output(first);select_user_activation_output(second);
            require(first.output.is_absolute() && first.output_root_lease && second.output_root_lease && first.output!=second.output &&
                    first.output.parent_path()==second.output.parent_path() && !std::filesystem::exists(first.output) && !std::filesystem::exists(second.output),
                    "Current-user private activation root supports fresh paths without starting a controller");
        }
        library=LoadLibraryExW(std::filesystem::absolute(argv[1]).c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);
        require(library!=nullptr,"Load unregistered activation fixture DLL");
        const auto configure=function<BOOL(*)(const wchar_t*,const wchar_t*)>(library,"sl3_test_activation_configure");
        require(configure(entry.c_str(),root.c_str())!=FALSE,"Configure explicit simulated provider");
        const auto get=function<HRESULT(WINAPI*)(REFCLSID,REFIID,void**)>(library,"DllGetClassObject");
        const auto unload=function<HRESULT(WINAPI*)()>(library,"DllCanUnloadNow");
        require(get(driver_clsid,IID_IClassFactory,reinterpret_cast<void**>(&factory))==S_OK,"Create ordinary ASIO factory");
        require(factory->CreateInstance(nullptr,driver_clsid,reinterpret_cast<void**>(&device))==S_OK && sessions(root)==0,"ASIO object creation does not acquire");
        play(device);device->Release();device=nullptr;
        require(sessions(root)==1 && std::filesystem::is_regular_file(root/L"session-1/result.json"),"Ordinary ASIO release retires its activated controller");
        factory->Release();factory=nullptr;
        require(get(driver_clsid,IID_IClassFactory,reinterpret_cast<void**>(&factory))==S_OK,"Create next ASIO factory");
        require(factory->CreateInstance(nullptr,driver_clsid,reinterpret_cast<void**>(&device))==S_OK && sessions(root)==1,"Reopening is lazy");
        play(device);device->Release();device=nullptr;factory->Release();factory=nullptr;
        require(std::filesystem::is_regular_file(root/L"session-2/result.json"),"Second normal ASIO release retires controller");
        require(get(driver_clsid,IID_IClassFactory,reinterpret_cast<void**>(&factory))==S_OK,"Create explicit scope factory");
        require(factory->QueryInterface(scope_iid,reinterpret_cast<void**>(&scope))==S_OK && scope->BeginScope()==S_OK && sessions(root)==2,
                "Explicit factory preparation does not acquire");
        require(factory->CreateInstance(nullptr,driver_clsid,reinterpret_cast<void**>(&device))==S_OK,"Create scoped ASIO object");
        play(device);device->Release();device=nullptr;
        require(scope->EndScope()==S_OK,"Explicit scope detaches ASIO client");scope->Release();scope=nullptr;factory->Release();factory=nullptr;
        require(std::filesystem::is_regular_file(root/L"session-3/result.json"),"Scope release retires its activation");
        require(unload()==S_OK,"Activation DLL is unloadable after normal retirement");
        const auto require_rate=function<BOOL(*)(unsigned)>(library,"sl3_test_activation_require_rate");
        require(require_rate(48000)!=FALSE,"Configure fixture-only rate mismatch");
        require(get(driver_clsid,IID_IClassFactory,reinterpret_cast<void**>(&factory))==S_OK &&
                factory->CreateInstance(nullptr,driver_clsid,reinterpret_cast<void**>(&device))==S_OK,"Create rate-mismatch ASIO object");
        factory->Release();factory=nullptr;const auto before_mismatch=callbacks.load();
        require(device->init(nullptr)==ASIOFalse,"Rate mismatch rejects initialization");
        const auto rejected_at=GetTickCount64();
        while(!std::filesystem::is_regular_file(root/L"session-4/result.json")){
            require(GetTickCount64()-rejected_at<2000,"Rejected ASIO initialization must retire activation while its object remains alive");Sleep(10);
        }
        require(device->init(nullptr)==ASIOFalse && sessions(root)==4 && callbacks.load()==before_mismatch,"Failed object cannot retry acquisition or stream");
        device->Release();device=nullptr;require(require_rate(0)!=FALSE,"Restore fixture rate requirement");
        entered=CreateEventW(nullptr,TRUE,FALSE,nullptr);release=CreateEventW(nullptr,TRUE,FALSE,nullptr);
        require(entered && release,"Blocked activation callback events");block=true;
        require(get(driver_clsid,IID_IClassFactory,reinterpret_cast<void**>(&factory))==S_OK,"Create blocked-callback factory");
        require(factory->CreateInstance(nullptr,driver_clsid,reinterpret_cast<void**>(&device))==S_OK,"Create blocked activation device");
        factory->Release();factory=nullptr;
        require(device->init(nullptr)==ASIOTrue,"Initialize blocked activation owner");
        for(unsigned channel=0;channel<12;++channel)planes[channel]={channel<6?ASIOTrue:ASIOFalse,long(channel%6),{}};
        ASIOCallbacks calls{};calls.bufferSwitch=callback;
        require(device->createBuffers(planes.data(),12,128,&calls)==ASE_OK && device->start()==ASE_OK && WaitForSingleObject(entered,5000)==WAIT_OBJECT_0,
                "Callback holds activated audio planes");
        device->Release();device=nullptr;
        const auto code=GetProcAddress(library,"DllGetClassObject");FreeLibrary(library);library=nullptr;HMODULE retained=nullptr;
        require(GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                                  reinterpret_cast<LPCWSTR>(code),&retained)!=FALSE,"Actual blocked callback retains the activation module");
        SetEvent(release);const auto began=GetTickCount64();
        while(GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                                reinterpret_cast<LPCWSTR>(code),&retained)){
            require(GetTickCount64()-began<5000,"Activation module retirement deadline");Sleep(5);
        }
        require(blocked_completed.load()==1,"Retained callback completes once on its original planes");
        CloseHandle(entered);CloseHandle(release);entered=nullptr;release=nullptr;CoUninitialize();
        std::cout<<"{\"schema\":\"sl3.activation-asio-tests.v1\",\"passed\":true,\"simulatedSessions\":5,\"normalSessions\":3,\"callbacks\":"<<callbacks.load()
                 <<",\"registrationChanged\":false,\"nativeDeviceAccess\":false,\"lazyCreationVerified\":true,\"normalReopenVerified\":true,"
                   "\"privateUserRootVerified\":true,\"blockedCallbackLeaseVerified\":true,\"rejectedInitRetiresWhileObjectHeld\":true}\n";return 0;
    }catch(const std::exception& error){
        if(release)SetEvent(release);
        if(device)device->Release();if(scope)scope->Release();if(factory)factory->Release();if(library)FreeLibrary(library);
        std::cerr<<error.what()<<'\n';return 1;
    }
}
