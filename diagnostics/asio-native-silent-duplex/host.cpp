// Explicit three-second production duplex probe. All output planes contain zero.
#include "asio/com_identity.hpp"
#include "iasiodrv.h"
#include <array>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
namespace fs=std::filesystem;
namespace {
constexpr unsigned frames=128;
std::array<ASIOBufferInfo,12> planes{};
std::array<std::atomic<unsigned>,6> peaks{};
std::atomic<unsigned> callbacks{0};
std::atomic<bool> invalid_bank{false};
void need(bool condition,const char* message){if(!condition)throw std::runtime_error(message);}
void publish(const fs::path& file,const std::string& body){
    need(!fs::exists(file),"Fresh diagnostic marker required");
    const auto temporary=fs::path(file.wstring()+L".tmp");
    {std::ofstream stream(temporary,std::ios::binary);stream<<body;stream.flush();need(bool(stream),"Write diagnostic marker");}
    fs::rename(temporary,file);
}
void callback(long bank,ASIOBool){
    if(bank<0 || bank>1){invalid_bank=true;return;}
    for(unsigned channel=6;channel<12;++channel)std::memset(planes[channel].buffers[bank],0,frames*3);
    for(unsigned channel=0;channel<6;++channel){
        const auto* input=static_cast<const unsigned char*>(planes[channel].buffers[bank]);
        unsigned peak=peaks[channel].load(std::memory_order_relaxed);
        for(unsigned sample=0;sample<frames;++sample){
            const auto* p=input+sample*3;
            const auto bits=std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16);
            const auto value=std::int32_t(bits&0x800000?bits|0xff000000:bits);
            const auto magnitude=unsigned(value<0?-value:value);if(magnitude>peak)peak=magnitude;
        }
        peaks[channel].store(peak,std::memory_order_relaxed);
    }
    callbacks.fetch_add(1,std::memory_order_relaxed);
}
void await_marker(const fs::path& marker,const fs::path& abort){
    const auto began=GetTickCount64();
    while(!fs::exists(marker)){
        need(!fs::exists(abort),"Observer canceled the diagnostic");
        need(GetTickCount64()-began<15000,"Observer release deadline");Sleep(10);
    }
    need(!fs::exists(abort),"Observer canceled the diagnostic");
}
}
int wmain(int argc,wchar_t** argv){
    if(argc==1 || (argc==2 && std::wstring(argv[1])==L"--plan")){
        std::cout<<"{\"schema\":\"sl3.native-silent-plan.v1\",\"initializationAttempted\":false,\"audioStarted\":false}\n";return 0;
    }
    IASIO* device=nullptr;HANDLE context=INVALID_HANDLE_VALUE;ULONG_PTR cookie=0;
    bool com=false,buffers=false,started=false;
    try{
        const bool reopen=argc==4 && std::wstring(argv[1])==L"--run-native-application-reopen";
        need(reopen || (argc==4 && std::wstring(argv[1])==L"--run-native-silent-duplex"),"Explicit native silent-duplex arguments required");
        const auto dll=fs::absolute(argv[2]),markers=fs::absolute(argv[3]);
        need(dll.filename()==L"sl3_asio.dll" && fs::is_directory(markers) && fs::is_empty(markers),"Fresh private diagnostic paths required");
        if(reopen){
            std::ifstream config(dll.parent_path()/L"sl3-asio.conf",std::ios::binary);
            std::array<char,64> header{};config.getline(header.data(),header.size());
            need(config && (std::string(header.data())=="SL3-ASIO-ACTIVATION-2" ||
                            std::string(header.data())=="SL3-ASIO-ACTIVATION-2\r"),
                 "Application-bound ASIO configuration required");
        }
        ACTCTXW specification{};specification.cbSize=sizeof(specification);
        const auto manifest=dll.parent_path()/L"fixture.manifest";specification.lpSource=manifest.c_str();
        context=CreateActCtxW(&specification);need(context!=INVALID_HANDLE_VALUE && ActivateActCtx(context,&cookie),"Activate private COM manifest");
        need(SUCCEEDED(CoInitializeEx(nullptr,COINIT_MULTITHREADED)),"Initialize COM");com=true;
        const auto stream=[&](const fs::path& output){
            need(!fs::exists(markers/L"abort"),"Observer canceled the diagnostic");
            callbacks=0;invalid_bank=false;for(auto& peak:peaks)peak=0;
            need(CoCreateInstance(sl3::asio::driver_clsid,nullptr,CLSCTX_INPROC_SERVER,sl3::asio::driver_clsid,reinterpret_cast<void**>(&device))==S_OK && device,"Create production ASIO object");
            const auto module=GetModuleHandleW(L"sl3_asio.dll");need(module!=nullptr,"COM-loaded module required");
            std::array<wchar_t,32768> image{};const auto size=GetModuleFileNameW(module,image.data(),DWORD(image.size()));
            need(size && size<image.size() && fs::equivalent(dll,fs::path(image.data())),"Exact production module required");
            need(GetProcAddress(module,"sl3_test_activation_configure")==nullptr,"Production image must exclude fixture seam");
            need(device->init(nullptr)==ASIOTrue,"Production silent-duplex init failed");
            long inputs=-1,outputs=-1;ASIOSampleRate rate=-1;
            need(device->getChannels(&inputs,&outputs)==ASE_OK && inputs==6 && outputs==6 && device->getSampleRate(&rate)==ASE_OK && rate==44100,"Six-channel 44.1 kHz profile required");
            publish(output/L"host-ready.json","{\"schema\":\"sl3.native-silent-ready.v1\",\"pid\":"+std::to_string(GetCurrentProcessId())+
                ",\"initialized\":true,\"accepted\":true,\"inputs\":6,\"outputs\":6,\"rateHz\":44100,\"audioStarted\":false}\n");
            await_marker(output/L"release",markers/L"abort");
            for(unsigned channel=0;channel<12;++channel){
                ASIOChannelInfo info{};info.channel=long(channel%6);info.isInput=channel<6?ASIOTrue:ASIOFalse;
                need(device->getChannelInfo(&info)==ASE_OK && info.type==ASIOSTInt24LSB,"Packed 24-bit little-endian channel required");
                planes[channel]={channel<6?ASIOTrue:ASIOFalse,long(channel%6),{}};
            }
            ASIOCallbacks calls{};calls.bufferSwitch=callback;
            need(device->createBuffers(planes.data(),12,frames,&calls)==ASE_OK,"Silent-duplex buffers failed");buffers=true;
            for(unsigned channel=0;channel<12;++channel)for(unsigned bank=0;bank<2;++bank){
                need(planes[channel].buffers[bank]!=nullptr,"Returned audio plane required");
                if(channel>=6)std::memset(planes[channel].buffers[bank],0,frames*3);
            }
            need(device->start()==ASE_OK,"Silent-duplex start failed");started=true;
            const auto stream_began=GetTickCount64();
            while(GetTickCount64()-stream_began<3000){need(!invalid_bank.load(),"Invalid callback bank");Sleep(5);}
            need(device->stop()==ASE_OK,"Silent-duplex stop failed");started=false;
            need(device->disposeBuffers()==ASE_OK,"Silent-duplex dispose failed");buffers=false;
            need(callbacks.load()>=500,"Insufficient callback progress over three seconds");
            device->Release();device=nullptr;
            const auto address=GetProcAddress(module,"DllCanUnloadNow");need(address!=nullptr,"Production unload export required");
            HRESULT(WINAPI* unload)();static_assert(sizeof(unload)==sizeof(address));std::memcpy(&unload,&address,sizeof(unload));
            need(unload()==S_OK,"Production object not unloadable after release");
            std::string values="[";for(unsigned channel=0;channel<6;++channel){if(channel)values+=",";values+=std::to_string(peaks[channel].load());}values+="]";
            publish(output/L"host-result.json","{\"schema\":\"sl3.native-silent-result.v1\",\"successful\":true,\"released\":true,\"unloadable\":true,\"audioStarted\":true,\"buffersCreated\":true,\"silentOutputOnly\":true,\"callbacksCompleted\":"+
                std::to_string(callbacks.load())+",\"durationMs\":3000,\"inputPeaks24\":"+values+"}\n");
        };
        if(reopen){
            for(const auto name:{L"open-1",L"open-2"}){
                const auto output=markers/name;need(fs::create_directory(output),"Fresh reopen marker directory required");
                stream(output);
            }
            await_marker(markers/L"finish",markers/L"abort");
        }else stream(markers);
        CoUninitialize();com=false;need(DeactivateActCtx(0,cookie)!=FALSE,"Deactivate private context");cookie=0;ReleaseActCtx(context);context=INVALID_HANDLE_VALUE;return 0;
    }catch(const std::exception& error){
        if(device){if(started)device->stop();if(buffers)device->disposeBuffers();device->Release();}
        if(com)CoUninitialize();if(cookie)DeactivateActCtx(0,cookie);if(context!=INVALID_HANDLE_VALUE)ReleaseActCtx(context);
        std::cerr<<error.what()<<'\n';return 1;
    }
}
