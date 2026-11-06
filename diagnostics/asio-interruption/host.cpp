// Owned simulated-fixture host only; no COM registration or production-provider fallback.
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
    const auto address=GetProcAddress(module,name);need(address!=nullptr,"Explicit simulated fixture export required");
    T result;static_assert(sizeof(result)==sizeof(address));std::memcpy(&result,&address,sizeof(result));return result;
}
void write_new(const fs::path& path,const std::string& text){
    const auto file=CreateFileW(path.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
    need(file!=INVALID_HANDLE_VALUE,"Fresh diagnostic marker required");DWORD written=0;
    const bool ok=WriteFile(file,text.data(),DWORD(text.size()),&written,nullptr) && written==text.size() && FlushFileBuffers(file);
    CloseHandle(file);need(ok,"Complete diagnostic marker write required");
}
std::atomic<unsigned> entered{0},completed{0};
std::array<ASIOBufferInfo,12> planes{};
HANDLE callback_entered=nullptr,callback_release=nullptr;
bool block_callback=false;
void callback(long bank,ASIOBool){
    entered.fetch_add(1);
    if(block_callback){SetEvent(callback_entered);WaitForSingleObject(callback_release,INFINITE);}
    for(unsigned channel=6;channel<12;++channel)std::memset(planes[channel].buffers[bank],0,128*3);
    completed.fetch_add(1);
}
}
int wmain(int argc,wchar_t** argv){
    if(argc==1 || (argc==2 && std::wstring(argv[1])==L"--plan")){
        std::cout<<"{\"schema\":\"sl3.activation-interruption-host-plan.v1\",\"fixtureLoaded\":false,\"deviceAccess\":false,\"seratoExecuted\":false}\n";return 0;
    }
    HMODULE module=nullptr;IClassFactory* factory=nullptr;IASIO* device=nullptr;bool initialized=false;
    try{
        need(argc==7 && std::wstring(argv[1])==L"--run","Explicit owned-fixture arguments required");
        const std::wstring mode=argv[2];need(mode==L"stream" || mode==L"blocked","Known simulated host mode required");
        block_callback=mode==L"blocked";
        const auto dll=fs::absolute(argv[3]),entry=fs::absolute(argv[4]),owner=fs::absolute(argv[5]),output=fs::absolute(argv[6]);
        need(dll.filename()==L"sl3_activation_session_fixture.dll" && fs::is_directory(owner) && fs::is_directory(output),"Explicit fixture and owned output required");
        need(SUCCEEDED(CoInitializeEx(nullptr,COINIT_MULTITHREADED)),"Initialize owned COM host");initialized=true;
        callback_entered=CreateEventW(nullptr,TRUE,FALSE,nullptr);callback_release=CreateEventW(nullptr,TRUE,FALSE,nullptr);
        need(callback_entered && callback_release,"Owned diagnostic callback events required");
        module=LoadLibraryExW(dll.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);need(module!=nullptr,"Load explicit unregistered fixture");
        const auto configure=symbol<BOOL(*)(const wchar_t*,const wchar_t*)>(module,"sl3_test_activation_configure");
        need(configure(entry.c_str(),owner.c_str())!=FALSE,"Configure simulated fixture provider");
        const auto get=symbol<HRESULT(WINAPI*)(REFCLSID,REFIID,void**)>(module,"DllGetClassObject");
        need(get(sl3::asio::driver_clsid,IID_IClassFactory,reinterpret_cast<void**>(&factory))==S_OK,"Create fixture class factory");
        need(factory->CreateInstance(nullptr,sl3::asio::driver_clsid,reinterpret_cast<void**>(&device))==S_OK,"Create fixture IASIO device");
        factory->Release();factory=nullptr;
        need(device->init(nullptr)==ASIOTrue,"Initialize simulated activation owner");
        long inputs=0,outputs=0;need(device->getChannels(&inputs,&outputs)==ASE_OK && inputs==6 && outputs==6,"Expected simulated channel contract");
        ASIOChannelInfo format{};format.channel=0;format.isInput=ASIOFalse;
        need(device->getChannelInfo(&format)==ASE_OK && format.type==ASIOSTInt24LSB,"Reviewed packed sample format required");
        for(unsigned channel=0;channel<12;++channel)planes[channel]={channel<6?ASIOTrue:ASIOFalse,long(channel%6),{}};
        ASIOCallbacks callbacks{};callbacks.bufferSwitch=callback;
        need(device->createBuffers(planes.data(),12,128,&callbacks)==ASE_OK,"Create simulated audio buffers");
        for(unsigned channel=6;channel<12;++channel)for(unsigned bank=0;bank<2;++bank)std::memset(planes[channel].buffers[bank],0,128*3);
        need(device->start()==ASE_OK,"Start simulated stream");
        const auto began=GetTickCount64();
        if(block_callback)need(WaitForSingleObject(callback_entered,5000)==WAIT_OBJECT_0,"Enter explicit blocked diagnostic callback");
        else while(completed.load()<8){need(GetTickCount64()-began<5000,"Observe simulated callback progress");Sleep(1);}
        write_new(output/L"host-ready.json","{\"schema\":\"sl3.activation-interruption-host-ready.v1\",\"pid\":"+std::to_string(GetCurrentProcessId())+
            ",\"callbackBlocked\":"+(block_callback?"true":"false")+",\"callbacksEntered\":"+std::to_string(entered.load())+
            ",\"callbacksCompleted\":"+std::to_string(completed.load())+",\"simulatedOnly\":true,\"nativeDeviceAccess\":false}\n");
        const auto ready_at=GetTickCount64();
        while(!fs::exists(output/L"stop")){need(GetTickCount64()-ready_at<30000,"Bounded host diagnostic hold expired");Sleep(2);}
        SetEvent(callback_release);
        need(device->stop()==ASE_OK && device->disposeBuffers()==ASE_OK,"Normal simulated stop/dispose");
        device->Release();device=nullptr;
        const auto unload=symbol<HRESULT(WINAPI*)()>(module,"DllCanUnloadNow");need(unload()==S_OK,"Fixture module is unloadable after normal retirement");
        FreeLibrary(module);module=nullptr;
        write_new(output/L"host-result.json","{\"schema\":\"sl3.activation-interruption-host-result.v1\",\"successful\":true,\"callbacksCompleted\":"+
            std::to_string(completed.load())+",\"nativeDeviceAccess\":false}\n");
        CloseHandle(callback_entered);CloseHandle(callback_release);CoUninitialize();return 0;
    }catch(const std::exception& error){
        if(callback_release)SetEvent(callback_release);
        if(device)device->Release();if(factory)factory->Release();if(module)FreeLibrary(module);
        if(callback_entered)CloseHandle(callback_entered);if(callback_release)CloseHandle(callback_release);
        if(initialized)CoUninitialize();std::cerr<<error.what()<<'\n';return 1;
    }
}
