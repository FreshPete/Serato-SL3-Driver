// Standalone offline host: only the test DLL's simulated provider is admitted.
#include "asio/com_identity.hpp"
#include "windows/worker_process.hpp"
#include "iasiodrv.h"
#include <array>
#include <atomic>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>

static void require(bool value,const char* text){if(!value)throw std::runtime_error(text);}
using GetClass=HRESULT(__stdcall*)(REFCLSID,REFIID,void**);
using Configure=BOOL(*)(const wchar_t*,const char*,const wchar_t*);
struct Host {
    IASIO* device=nullptr;
    std::array<ASIOBufferInfo,12> buffers{};
    std::atomic<unsigned> calls{0};
    std::atomic<bool> bad{false};
    unsigned frames=128;
    Host(){for(long c=0;c<6;++c){buffers[std::size_t(c)]={ASIOTrue,c,{}};buffers[std::size_t(c+6)]={ASIOFalse,c,{}};}}
    ~Host(){if(device){device->stop();device->disposeBuffers();device->Release();}}
};
static Host* current=nullptr;
static void callback(long bank,ASIOBool direct){
    auto& h=*current;const auto count=h.calls.load();ASIOSamples position{};ASIOTimeStamp timestamp{};
    if(bank!=long(count%2) || direct!=ASIOTrue || h.device->getSamplePosition(&position,&timestamp)!=ASE_OK ||
       ((std::uint64_t(position.hi)<<32)|position.lo)!=std::uint64_t(count)*h.frames)h.bad=true;
    if(bank==0 || bank==1){
        for(unsigned channel=0;channel<6;++channel)
            std::memcpy(h.buffers[channel+6].buffers[bank],h.buffers[channel].buffers[bank],h.frames*3);
    }
    h.calls.fetch_add(1);
}
int wmain(int argc,wchar_t** argv){
    try{
        require(argc==4,"Test-only ASIO DLL, simulated worker and fresh audit path required");
        const std::filesystem::path dll=argv[1],worker=argv[2],audit=argv[3];
        require(dll.filename()==L"sl3_asio_session_fixture.dll" && worker.filename()==L"sl3_device_session_fixture.exe" &&
                !std::filesystem::exists(audit),"Only fresh test fixtures admitted");
        const auto module=LoadLibraryExW(dll.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);
        require(module!=nullptr,"Load test-only unregistered DLL");
        const auto get=reinterpret_cast<GetClass>(GetProcAddress(module,"DllGetClassObject"));
        const auto configure=reinterpret_cast<Configure>(GetProcAddress(module,"sl3_test_configure_retained_audit"));
        require(get && configure && !GetProcAddress(module,"DllRegisterServer"),"Production DLL cannot enter endurance host");
        const auto hash=sl3::worker::Process::executable_sha256(worker);
        require(configure(worker.c_str(),hash.c_str(),audit.c_str()),"Configure pinned simulated worker");
        IClassFactory* factory=nullptr;
        require(get(sl3::asio::driver_clsid,IID_IClassFactory,reinterpret_cast<void**>(&factory))==S_OK,"Create test factory");
        DWORD before=0,after=0;require(GetProcessHandleCount(GetCurrentProcess(),&before)!=0,"Initial handle sample");
        unsigned total=0;
        constexpr unsigned objects=16,cycles=4;
        for(unsigned object=0;object<objects;++object){
            Host host;current=&host;
            require(factory->CreateInstance(nullptr,sl3::asio::driver_clsid,reinterpret_cast<void**>(&host.device))==S_OK &&
                    host.device->init(nullptr)==ASIOTrue,"Recreated ASIO object initializes");
            for(unsigned cycle=0;cycle<cycles;++cycle){
                host.frames=64u<<(cycle%3);host.calls=0;host.bad=false;
                ASIOCallbacks callbacks{};callbacks.bufferSwitch=callback;
                require(host.device->createBuffers(host.buffers.data(),12,long(host.frames),&callbacks)==ASE_OK &&
                        host.device->start()==ASE_OK,"Restart ASIO with changing bank sizes");
                const auto deadline=GetTickCount64()+3000;
                while(host.calls<32){require(GetTickCount64()<deadline,"Callback progress deadline");Sleep(1);}
                require(host.device->stop()==ASE_OK && !host.bad,"Stop and verify banks/sample positions");
                const auto stopped=host.calls.load();Sleep(5);
                require(host.calls==stopped && host.device->stop()==ASE_OK && host.device->disposeBuffers()==ASE_OK,
                        "No callbacks after stop; idempotent stop and buffer retirement");
                total+=stopped;
                for(auto& buffer:host.buffers)buffer.buffers[0]=buffer.buffers[1]=nullptr;
            }
        }
        current=nullptr;
        require(factory->Release()==0 && FreeLibrary(module)!=0,"Release host COM and module references");
        require(GetProcessHandleCount(GetCurrentProcess(),&after)!=0,"Final handle sample");
        std::ifstream input(audit);std::vector<std::string> actual,expected;
        for(std::string line;std::getline(input,line);)actual.push_back(line);
        for(unsigned object=0;object<objects;++object){
            expected.insert(expected.end(),{"acquire","rate"});
            for(unsigned cycle=0;cycle<cycles;++cycle)expected.insert(expected.end(),{"rate","begin","end"});
            expected.push_back("release");
        }
        require(input.eof() && actual==expected,"Exact balanced simulated acquire/start/stop/release sequence");
        require(after<=before+4,"Handle growth exceeds bounded warm-up allowance");
        std::cout<<"{\"schema\":\"sl3.asio-restart-endurance.v1\",\"objects\":"<<objects
                 <<",\"startStopCycles\":"<<objects*cycles<<",\"callbacks\":"<<total
                 <<",\"handlesBefore\":"<<before<<",\"handlesAfter\":"<<after
                 <<",\"exactLifecycleAudit\":true,\"simulatedTransport\":true,\"physicalUsbTested\":false}\n";
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
