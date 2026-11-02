#include "asio/com_identity.hpp"
#include "asio/scope_interface.hpp"
#include "iasiodrv.h"
#include <array>
#include <atomic>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <vector>
#if defined(_MSC_VER) && defined(_DEBUG)
#include <crtdbg.h>
#endif

static void require(bool value,const char* text){if(!value)throw std::runtime_error(text);}
using GetClass=HRESULT(__stdcall*)(REFCLSID,REFIID,void**);
using CanUnload=HRESULT(__stdcall*)();
int wmain(int argc,wchar_t** argv){
#if defined(_MSC_VER) && defined(_DEBUG)
    _CrtSetReportMode(_CRT_ASSERT,_CRTDBG_MODE_FILE);_CrtSetReportFile(_CRT_ASSERT,_CRTDBG_FILE_STDERR);
#endif
    try{
        require(argc==2,"DLL path required");
        require(!std::filesystem::exists(std::filesystem::path(argv[1]).parent_path()/L"sl3-asio.conf"),"Unavailable-state COM test requires absent adjacent configuration; refusing possible hardware access");
        const auto module=LoadLibraryExW(argv[1],nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);
        require(module!=nullptr,"Load reviewed local ASIO DLL");
        const auto get=reinterpret_cast<GetClass>(GetProcAddress(module,"DllGetClassObject"));
        const auto unload=reinterpret_cast<CanUnload>(GetProcAddress(module,"DllCanUnloadNow"));
        require(get && unload,"COM exports");
        require(!GetProcAddress(module,"DllRegisterServer") && !GetProcAddress(module,"DllUnregisterServer"),"No registration entrypoints yet");
        require(!GetProcAddress(module,"sl3_test_configure") && !GetProcAddress(module,"sl3_test_configure_retained") &&
                !GetProcAddress(module,"sl3_test_configure_broker") && !GetProcAddress(module,"sl3_test_configure_bound_broker"),"Production DLL exports no simulated-provider configuration");
        require(unload()==S_OK,"Initially unloadable");
        sl3::asio::DeviceScope* missing_scope=nullptr;
        require(get(sl3::asio::driver_clsid,sl3::asio::scope_iid,reinterpret_cast<void**>(&missing_scope))==S_OK &&
                missing_scope->EndScope()==S_FALSE && missing_scope->BeginScope()==E_FAIL && missing_scope->BeginScope()==E_UNEXPECTED,
                "Production factory scope rejects missing reviewed configuration without a worker");
        IClassFactory* failed_scope_factory=nullptr;
        require(missing_scope->QueryInterface(IID_IClassFactory,reinterpret_cast<void**>(&failed_scope_factory))==S_OK,
                "Scope queries its canonical factory");
        void* failed_scope_device=reinterpret_cast<void*>(1);
        require(failed_scope_factory->CreateInstance(nullptr,sl3::asio::driver_clsid,&failed_scope_device)==E_UNEXPECTED && !failed_scope_device,
                "Failed scope cannot fall back to a private driver");
        failed_scope_factory->Release();require(missing_scope->Release()==0 && unload()==S_OK,"Failed controller fully unloads");
        void* pointer=reinterpret_cast<void*>(1);
        require(get(CLSID_NULL,IID_IClassFactory,&pointer)==CLASS_E_CLASSNOTAVAILABLE && !pointer,"Unknown class clears result");
        require(get(sl3::asio::driver_clsid,IID_NULL,&pointer)==E_NOINTERFACE && !pointer && unload()==S_OK,"Failed factory QI leaves no object");
        require(get(sl3::asio::driver_clsid,IID_IClassFactory,nullptr)==E_POINTER,"Null export result");
        IClassFactory* factory=nullptr;
        require(get(sl3::asio::driver_clsid,IID_IClassFactory,reinterpret_cast<void**>(&factory))==S_OK,"Get factory");
        require(unload()==S_FALSE,"Factory retains module");
        IUnknown* factory_identity=nullptr;
        require(factory->QueryInterface(IID_IUnknown,reinterpret_cast<void**>(&factory_identity))==S_OK &&
            factory_identity==static_cast<IUnknown*>(factory),"Factory canonical identity");
        require(factory_identity->Release()==1,"Factory QI balances refcount");
        require(factory->QueryInterface(IID_NULL,&pointer)==E_NOINTERFACE && !pointer,"Unknown factory IID clears result");
        require(factory->QueryInterface(IID_IUnknown,nullptr)==E_POINTER,"Null factory QI");
        require(factory->LockServer(FALSE)==E_UNEXPECTED,"Unbalanced unlock rejected");
        require(factory->CreateInstance(factory,sl3::asio::driver_clsid,&pointer)==CLASS_E_NOAGGREGATION && !pointer,"Aggregation rejected");
        require(factory->CreateInstance(nullptr,IID_NULL,&pointer)==E_NOINTERFACE && !pointer,"Unknown device IID");
        require(factory->CreateInstance(nullptr,sl3::asio::driver_clsid,nullptr)==E_POINTER,"Null create result");
        IASIO* device=nullptr;
        require(factory->CreateInstance(nullptr,sl3::asio::driver_clsid,reinterpret_cast<void**>(&device))==S_OK,"Create IASIO using class IID");
        IUnknown* identity=nullptr;
        require(device->QueryInterface(IID_IUnknown,reinterpret_cast<void**>(&identity))==S_OK,"Device IUnknown");
        require(identity==static_cast<IUnknown*>(device),"Canonical identity");
        require(identity->Release()==1,"QI balances refcount");
        require(device->QueryInterface(IID_NULL,&pointer)==E_NOINTERFACE && !pointer,"Device unknown IID clears result");
        require(device->QueryInterface(IID_IUnknown,nullptr)==E_POINTER,"Null device QI");
        require(device->init(nullptr)==ASIOFalse && device->init(reinterpret_cast<void*>(1))==ASIOFalse,"Never claim a live device");
        std::array<char,32> name{};std::array<char,124> error{};
        device->getDriverName(name.data());device->getErrorMessage(error.data());
        require(std::strcmp(name.data(),"SL3 Rebuild Development")==0 && std::strstr(error.data(),"unavailable"),"Development identity and reason");
        require(device->getDriverVersion()==1,"Version");
        device->getDriverName(nullptr);device->getErrorMessage(nullptr);
        long a=73,b=74,c=75,d=76;ASIOSampleRate rate=12345;
        ASIOClockSource clock{};clock.index=77;
        ASIOSamples samples{};samples.hi=78;samples.lo=79;
        ASIOTimeStamp time{};time.hi=80;time.lo=81;
        ASIOChannelInfo channel{};channel.channel=82;
        ASIOBufferInfo buffer{};buffer.buffers[0]=reinterpret_cast<void*>(83);
        ASIOCallbacks callbacks{};
        // Calls through the real SDK vtable cover every IASIO slot, including
        // the initial host probe. No callback or sample-rate operation runs.
        for(const auto status:{device->start(),device->stop(),device->getChannels(&a,&b),device->getLatencies(&a,&b),
            device->getBufferSize(&a,&b,&c,&d),device->canSampleRate(44100),device->canSampleRate(48000),
            device->getSampleRate(&rate),device->setSampleRate(48000),device->getClockSources(&clock,&a),
            device->setClockSource(0),device->getSamplePosition(&samples,&time),device->getChannelInfo(&channel),
            device->createBuffers(&buffer,1,64,&callbacks),device->disposeBuffers(),device->controlPanel(),
            device->future(kAsioCanTimeInfo,nullptr),device->outputReady()})require(status==ASE_NotPresent,"Unavailable IASIO method must fail");
        require(a==73 && b==74 && c==75 && d==76 && rate==12345 && clock.index==77 &&
            samples.hi==78 && samples.lo==79 && time.hi==80 && time.lo==81 && channel.channel==82 &&
            buffer.buffers[0]==reinterpret_cast<void*>(83),"Unavailable calls preserve caller outputs");
        require(factory->Release()==0 && unload()==S_FALSE,"Device alone retains module");
        require(device->Release()==0 && unload()==S_OK,"Last device release permits unload");
        require(get(sl3::asio::driver_clsid,IID_IClassFactory,reinterpret_cast<void**>(&factory))==S_OK,"Second factory");
        require(factory->LockServer(TRUE)==S_OK && factory->LockServer(TRUE)==S_OK,"Count both server locks");
        require(factory->Release()==0 && unload()==S_FALSE,"Locks survive factory release");
        require(get(sl3::asio::driver_clsid,IID_IClassFactory,reinterpret_cast<void**>(&factory))==S_OK,"New factory unlocks global server");
        require(factory->LockServer(FALSE)==S_OK && factory->Release()==0 && unload()==S_FALSE,"One lock still retains module");
        require(get(sl3::asio::driver_clsid,IID_IClassFactory,reinterpret_cast<void**>(&factory))==S_OK,"Factory for concurrency");
        require(factory->LockServer(FALSE)==S_OK,"Final balanced unlock");
        std::atomic<bool> failed{false};std::vector<std::thread> threads;
        for(unsigned t=0;t<8;++t)threads.emplace_back([&]{
            for(unsigned i=0;i<200;++i){
                IASIO* item=nullptr;
                factory->AddRef();
                if(factory->LockServer(TRUE)!=S_OK)failed=true;
                if(factory->CreateInstance(nullptr,sl3::asio::driver_clsid,reinterpret_cast<void**>(&item))!=S_OK)failed=true;
                if(item){if(item->init(nullptr)!=ASIOFalse)failed=true;item->AddRef();item->Release();item->Release();}
                if(factory->LockServer(FALSE)!=S_OK)failed=true;
                factory->Release();
            }
        });
        for(auto& thread:threads)thread.join();
        require(!failed && factory->Release()==0 && unload()==S_OK,"Concurrent factory/device/ref/lock retirement");
        require(FreeLibrary(module)!=FALSE,"Unload DLL");
        std::cout<<"ASIO COM ABI and unavailable-state lifetime tests passed; no registration or USB access\n";
        return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
