// Process-local HKCR override only. Loads the explicitly simulated DLL via COM.
#include "asio/com_identity.hpp"
#include "iasiodrv.h"
#include <array>
#include <atomic>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>

namespace fs=std::filesystem;
namespace {
void need(bool value,const char* text){if(!value)throw std::runtime_error(text);}
template<class T>T symbol(HMODULE module,const char* name){
    const auto address=GetProcAddress(module,name);need(address!=nullptr,"Simulated fixture export required");
    T result;static_assert(sizeof(result)==sizeof(address));std::memcpy(&result,&address,sizeof(result));return result;
}
std::atomic<unsigned> completed{0};std::array<ASIOBufferInfo,12> planes{};
void callback(long bank,ASIOBool){
    for(unsigned channel=6;channel<12;++channel)std::memset(planes[channel].buffers[bank],0,128*3);
    completed.fetch_add(1);
}
}
int wmain(int argc,wchar_t** argv){
    if(argc==1 || (argc==2 && std::wstring(argv[1])==L"--plan")){
        std::cout<<"{\"schema\":\"sl3.com-registration-plan.v1\",\"registryOverrideApplied\":false,\"fixtureLoaded\":false,\"nativeDeviceAccess\":false}\n";return 0;
    }
    HKEY classes=nullptr;IClassFactory* factory=nullptr;IASIO* device=nullptr;bool initialized=false,overridden=false;
    HANDLE context=INVALID_HANDLE_VALUE;ULONG_PTR cookie=0;
    try{
        need(argc==7 && std::wstring(argv[1])==L"--run","Explicit private registry fixture arguments required");
        const std::wstring mode=argv[2],key=argv[3],prefix=L"Software\\SL3RebuildComActivationTests\\",suffix=L"\\SOFTWARE\\Classes";
        need(mode==L"absent" || mode==L"registry-probe" || mode==L"manifest" || mode==L"production-enumeration","Known COM diagnostic mode required");
        need(key.size()==prefix.size()+32+suffix.size() && key.compare(0,prefix.size(),prefix)==0 && key.substr(prefix.size()+32)==suffix,
             "Exact private registry namespace required");
        for(const auto c:key.substr(prefix.size(),32))need((c>=L'0' && c<=L'9') || (c>=L'a' && c<=L'f'),"Fresh namespace identity required");
        const auto dll=fs::absolute(argv[4]),entry=fs::absolute(argv[5]),owners=fs::absolute(argv[6]);
        need(dll.filename()==L"sl3_asio.dll" && fs::is_directory(owners),"Explicit copied simulated fixture required");
        need(GetModuleHandleW(L"sl3_asio.dll")==nullptr,"Fixture must not be preloaded");
        need(RegOpenKeyExW(HKEY_CURRENT_USER,key.c_str(),0,KEY_READ|KEY_WOW64_64KEY,&classes)==ERROR_SUCCESS,"Open existing private classes root");
        need(RegOverridePredefKey(HKEY_CLASSES_ROOT,classes)==ERROR_SUCCESS,"Apply process-only private HKCR override");overridden=true;
        if(mode!=L"absent"){
            std::array<wchar_t,32768> value{};DWORD bytes=DWORD(value.size()*sizeof(wchar_t));
            need(RegGetValueW(HKEY_CLASSES_ROOT,L"CLSID\\{5A551CD0-F83E-48EB-8B9D-8614E07852FE}\\InprocServer32",nullptr,RRF_RT_REG_SZ,nullptr,value.data(),&bytes)==ERROR_SUCCESS && fs::equivalent(fs::path(value.data()),dll),"Mapped registry read must resolve exact fixture path");
        }
        if(mode==L"manifest" || mode==L"production-enumeration"){
            const auto manifest=dll.parent_path()/L"fixture.manifest";ACTCTXW specification{};specification.cbSize=sizeof(specification);specification.lpSource=manifest.c_str();
            context=CreateActCtxW(&specification);need(context!=INVALID_HANDLE_VALUE && ActivateActCtx(context,&cookie),"Activate explicit registration-free diagnostic context");
        }
        need(SUCCEEDED(CoInitializeEx(nullptr,COINIT_MULTITHREADED)),"Initialize ordinary COM host");initialized=true;
        const auto result=CoGetClassObject(sl3::asio::driver_clsid,CLSCTX_INPROC_SERVER,nullptr,IID_IClassFactory,reinterpret_cast<void**>(&factory));
        if(mode==L"absent" || mode==L"registry-probe"){
            need(result==REGDB_E_CLASSNOTREG && factory==nullptr && GetModuleHandleW(L"sl3_asio.dll")==nullptr,"Absent private registration must not fall back to live class roots");
            std::cout<<"{\"schema\":\"sl3.com-registration-result.v1\",\"registryAliasContainsClass\":"<<(mode==L"registry-probe"?"true":"false")<<",\"classNotRegistered\":true,\"fixtureLoaded\":false,\"nativeDeviceAccess\":false}\n";
        }else{
            if(result!=S_OK || !factory){std::cerr<<"CoGetClassObject HRESULT=0x"<<std::hex<<static_cast<unsigned long>(result)<<'\n';throw std::runtime_error("Resolve factory through actual COM registration");}
            const auto module=GetModuleHandleW(L"sl3_asio.dll");need(module!=nullptr,"COM must load the fixture");
            std::array<wchar_t,32768> loaded{};const auto length=GetModuleFileNameW(module,loaded.data(),DWORD(loaded.size()));
            need(length>0 && length<loaded.size() && fs::equivalent(dll,fs::path(loaded.data())),"Exact COM-loaded DLL path required");
            need(fs::is_empty(owners),"Class factory enumeration must not activate controller");
            const bool production=mode==L"production-enumeration";
            if(production)need(GetProcAddress(module,"sl3_test_activation_configure")==nullptr,"Production DLL must exclude simulated-provider seam");
            else{
                // Only the simulated test DLL has this seam. Production DLL has no fallback.
                need(symbol<BOOL(*)(const wchar_t*,const wchar_t*)>(module,"sl3_test_activation_configure")(entry.c_str(),owners.c_str())!=FALSE,"Configure explicitly simulated provider after COM factory resolution");
            }
            factory->Release();factory=nullptr;
            for(unsigned run=0;run<2;++run){
                need(CoCreateInstance(sl3::asio::driver_clsid,nullptr,CLSCTX_INPROC_SERVER,sl3::asio::driver_clsid,reinterpret_cast<void**>(&device))==S_OK && device,"CoCreateInstance must resolve registered ASIO object");
                const auto session=owners/(L"session-"+std::to_wstring(run+1));need(!fs::exists(session),"Object construction must remain idle");
                if(production){
                    // No init, scope creation, configuration resolution or transport operation.
                    std::array<char,64> name{};device->getDriverName(name.data());need(std::string(name.data())=="SL3 Rebuild Development" && device->getDriverVersion()==1,"Production metadata contract");
                    long inputs=-11,outputs=-12;need(device->getChannels(&inputs,&outputs)==ASE_NotPresent && inputs==-11 && outputs==-12,"Production enumeration must preserve unavailable channel outputs");
                    device->Release();device=nullptr;
                    need(symbol<HRESULT(WINAPI*)()>(module,"DllCanUnloadNow")()==S_OK && fs::is_empty(owners),"Idle production COM object retirement");continue;
                }
                need(device->init(nullptr)==ASIOTrue,"Registered simulated ASIO initialization");
                long inputs=0,outputs=0;need(device->getChannels(&inputs,&outputs)==ASE_OK && inputs==6 && outputs==6,"Registered six-channel contract");
                for(unsigned channel=0;channel<12;++channel)planes[channel]={channel<6?ASIOTrue:ASIOFalse,long(channel%6),{}};
                ASIOCallbacks callbacks{};callbacks.bufferSwitch=callback;
                need(device->createBuffers(planes.data(),12,128,&callbacks)==ASE_OK,"Registered simulated buffers");
                const auto before=completed.load();need(device->start()==ASE_OK,"Registered simulated start");const auto began=GetTickCount64();
                while(completed.load()<before+8){need(GetTickCount64()-began<5000,"Registered callback progress deadline");Sleep(1);}
                need(device->stop()==ASE_OK && device->disposeBuffers()==ASE_OK,"Registered stop/dispose");device->Release();device=nullptr;
                need(symbol<HRESULT(WINAPI*)()>(module,"DllCanUnloadNow")()==S_OK,"Registered object retirement must release module leases");
            }
            std::cout<<"{\"schema\":\"sl3.com-registration-result.v1\",\"registrationFreeContext\":true,\"comFactoryResolved\":true,\"coCreateInstances\":2,\"callbacksCompleted\":"<<completed.load()<<",\"productionEnumerationOnly\":"<<(production?"true":"false")<<",\"simulatedOnly\":"<<(production?"false":"true")<<",\"nativeDeviceAccess\":false}\n";
        }
        CoUninitialize();initialized=false;need(RegOverridePredefKey(HKEY_CLASSES_ROOT,nullptr)==ERROR_SUCCESS,"Restore process-local HKCR mapping");overridden=false;
        if(cookie)need(DeactivateActCtx(0,cookie)!=FALSE,"Deactivate diagnostic context");if(context!=INVALID_HANDLE_VALUE)ReleaseActCtx(context);
        RegCloseKey(classes);return 0;
    }catch(const std::exception& error){
        if(device)device->Release();if(factory)factory->Release();if(initialized)CoUninitialize();
        if(overridden)RegOverridePredefKey(HKEY_CLASSES_ROOT,nullptr);if(classes)RegCloseKey(classes);
        if(cookie)DeactivateActCtx(0,cookie);if(context!=INVALID_HANDLE_VALUE)ReleaseActCtx(context);
        std::cerr<<error.what()<<'\n';return 1;
    }
}
