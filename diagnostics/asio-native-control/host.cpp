// One production COM initialization. No buffers, start, audio, rate writes or firmware.
#include "asio/com_identity.hpp"
#include "iasiodrv.h"
#include <array>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
namespace fs=std::filesystem;
namespace {
void need(bool condition,const char* message){if(!condition)throw std::runtime_error(message);}
void publish(const fs::path& file,const std::string& body){
    need(!fs::exists(file),"Fresh diagnostic marker required");
    const auto temporary=fs::path(file.wstring()+L".tmp");
    {std::ofstream stream(temporary,std::ios::binary);stream<<body;stream.flush();need(bool(stream),"Write diagnostic marker");}
    fs::rename(temporary,file);
}
}
int wmain(int argc,wchar_t** argv){
    if(argc==1 || (argc==2 && std::wstring(argv[1])==L"--plan")){
        std::cout<<"{\"schema\":\"sl3.native-control-plan.v1\",\"initializationAttempted\":false,\"audioStarted\":false}\n";return 0;
    }
    IASIO* device=nullptr;HANDLE context=INVALID_HANDLE_VALUE;ULONG_PTR cookie=0;bool com=false;
    try{
        need(argc==4 && std::wstring(argv[1])==L"--run-native-control","Explicit native control arguments required");
        const auto dll=fs::absolute(argv[2]),markers=fs::absolute(argv[3]);
        need(dll.filename()==L"sl3_asio.dll" && fs::is_directory(markers) && fs::is_empty(markers),"Fresh private diagnostic paths required");
        ACTCTXW specification{};specification.cbSize=sizeof(specification);
        const auto manifest=dll.parent_path()/L"fixture.manifest";specification.lpSource=manifest.c_str();
        context=CreateActCtxW(&specification);need(context!=INVALID_HANDLE_VALUE && ActivateActCtx(context,&cookie),"Activate private COM manifest");
        need(SUCCEEDED(CoInitializeEx(nullptr,COINIT_MULTITHREADED)),"Initialize COM");com=true;
        need(CoCreateInstance(sl3::asio::driver_clsid,nullptr,CLSCTX_INPROC_SERVER,sl3::asio::driver_clsid,reinterpret_cast<void**>(&device))==S_OK && device,"Create production ASIO object");
        const auto module=GetModuleHandleW(L"sl3_asio.dll");need(module!=nullptr,"COM-loaded module required");
        std::array<wchar_t,32768> image{};const auto size=GetModuleFileNameW(module,image.data(),DWORD(image.size()));
        need(size && size<image.size() && fs::equivalent(dll,fs::path(image.data())),"Exact production module required");
        need(GetProcAddress(module,"sl3_test_activation_configure")==nullptr,"Production image must exclude fixture seam");
        const bool initialized=device->init(nullptr)==ASIOTrue;
        std::array<char,124> error{};device->getErrorMessage(error.data());
        // Error text stays in stdout, never interpolated into JSON.
        std::cout<<"ASIO initialization: "<<(initialized?"true":"false")<<"; error: "<<error.data()<<'\n';std::cout.flush();
        long inputs=-1,outputs=-1;ASIOSampleRate rate=-1;
        const bool channels=initialized && device->getChannels(&inputs,&outputs)==ASE_OK;
        const bool clock=initialized && device->getSampleRate(&rate)==ASE_OK;
        const bool accepted=initialized && channels && clock && inputs==6 && outputs==6 && rate==44100;
        publish(markers/L"host-ready.json","{\"schema\":\"sl3.native-control-ready.v1\",\"pid\":"+std::to_string(GetCurrentProcessId())+
            ",\"initialized\":"+(initialized?"true":"false")+",\"accepted\":"+(accepted?"true":"false")+
            ",\"inputs\":"+std::to_string(inputs)+",\"outputs\":"+std::to_string(outputs)+",\"rateHz\":"+std::to_string(rate)+",\"audioStarted\":false}\n");
        const auto began=GetTickCount64();
        while(!fs::exists(markers/L"release")){need(GetTickCount64()-began<15000,"Observer release deadline");Sleep(10);}
        device->Release();device=nullptr;
        const auto address=GetProcAddress(module,"DllCanUnloadNow");need(address!=nullptr,"Production unload export required");
        HRESULT(WINAPI* unload)();static_assert(sizeof(unload)==sizeof(address));std::memcpy(&unload,&address,sizeof(unload));
        const bool unloadable=unload()==S_OK;
        publish(markers/L"host-result.json","{\"schema\":\"sl3.native-control-result.v1\",\"successful\":"+std::string(accepted && unloadable?"true":"false")+
            ",\"released\":true,\"unloadable\":"+(unloadable?"true":"false")+",\"audioStarted\":false}\n");
        CoUninitialize();com=false;need(DeactivateActCtx(0,cookie)!=FALSE,"Deactivate private context");cookie=0;ReleaseActCtx(context);context=INVALID_HANDLE_VALUE;
        return accepted && unloadable?0:1;
    }catch(const std::exception& error){
        if(device)device->Release();if(com)CoUninitialize();if(cookie)DeactivateActCtx(0,cookie);if(context!=INVALID_HANDLE_VALUE)ReleaseActCtx(context);
        std::cerr<<error.what()<<'\n';return 1;
    }
}
