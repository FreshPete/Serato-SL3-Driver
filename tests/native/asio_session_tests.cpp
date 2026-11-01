#include "asio/com_identity.hpp"
#include "asio/scope_interface.hpp"
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
using CanUnload=HRESULT(__stdcall*)();
using Configure=BOOL(*)(const wchar_t*,const char*);
using ConfigureAudit=BOOL(*)(const wchar_t*,const char*,const wchar_t*);
using CloseOwner=BOOL(*)();
struct Host {
    IASIO* device=nullptr;
    std::array<ASIOBufferInfo,12> buffers{};
    unsigned frames=64;
    HANDLE entered=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    HANDLE release=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    std::atomic<unsigned> calls{0};std::atomic<bool> bad{false};
    bool block=false;
    Host(){require(entered && release,"Host callback events");for(long c=0;c<6;++c){buffers[std::size_t(c)]={ASIOTrue,c,{}};buffers[std::size_t(c+6)]={ASIOFalse,c,{}};}}
    ~Host(){SetEvent(release);if(device){device->stop();device->disposeBuffers();device->Release();}CloseHandle(entered);CloseHandle(release);}
};
static Host* host=nullptr;
static void callback(long bank,ASIOBool direct){
    auto& h=*host;ASIOSamples position{};ASIOTimeStamp time{};ASIOSampleRate rate=0;const auto call=h.calls.load();
    if(bank!=long(call%2) || direct!=ASIOTrue || h.device->getSamplePosition(&position,&time)!=ASE_OK ||
       ((std::uint64_t(position.hi)<<32)|position.lo)!=std::uint64_t(call)*h.frames || h.device->getSampleRate(&rate)!=ASE_OK || rate!=48000 ||
       h.device->stop()!=ASE_InvalidMode || h.device->disposeBuffers()!=ASE_InvalidMode)h.bad=true;
    if(h.block){SetEvent(h.entered);WaitForSingleObject(h.release,INFINITE);}
    for(unsigned c=0;c<6;++c)std::memcpy(h.buffers[c+6].buffers[bank],h.buffers[c].buffers[bank],h.frames*3);
    h.calls.fetch_add(1);SetEvent(h.entered);
}
static void recreated_objects(IClassFactory& factory,ConfigureAudit configure,CanUnload unload,
                              const std::filesystem::path& fixture,const std::string& hash,CloseOwner close_owner=nullptr,
                              sl3::asio::DeviceScope* scope=nullptr){
    GUID id{};require(CoCreateGuid(&id)==S_OK,"Unique object-recreation audit identity");
    wchar_t text[40]{};require(StringFromGUID2(id,text,40)!=0,"Format audit identity");
    const auto path=std::filesystem::temp_directory_path()/(std::wstring(L"sl3-asio-recreate-")+text+L".txt");
    struct Remove {std::filesystem::path path;~Remove(){std::error_code error;std::filesystem::remove(path,error);}} remove{path};
    require(configure(fixture.c_str(),hash.c_str(),path.c_str()),"Configure audited retained simulated provider");
    if(scope){
        require(scope->BeginScope()==S_OK && scope->BeginScope()==E_UNEXPECTED && !std::filesystem::exists(path),
                "Actual factory prepares one scope before creating any worker");
    }
    const bool persistent=close_owner || scope;
    std::vector<std::string> expected;
    auto verify_audit=[&]{
        std::ifstream input(path);std::vector<std::string> actual;std::string line;
        while(std::getline(input,line))actual.push_back(line);
        require(input.eof() && actual==expected,"Exact per-object worker acquisition/rate/start/stop/final-release audit");
    };
    // Enumeration consumes metadata and drops its interface without starting I/O.
    {
        Host h;host=&h;
        require(factory.CreateInstance(nullptr,sl3::asio::driver_clsid,reinterpret_cast<void**>(&h.device))==S_OK &&
                h.device->init(nullptr)==ASIOTrue,"Separate enumeration IASIO object initializes");
        long in=0,out=0;ASIOSampleRate rate=0;
        require(h.device->getChannels(&in,&out)==ASE_OK && in==6 && out==6 &&
                h.device->getSampleRate(&rate)==ASE_OK && rate==48000,"Enumeration object metadata");
        require(h.device->Release()==0,"Enumeration releases its last interface");h.device=nullptr;
    }
    expected={"acquire","rate"};if(!persistent)expected.push_back("release");verify_audit();
    for(unsigned object=0;object<2;++object){
        {
            Host h;host=&h;h.frames=128;
            require(factory.CreateInstance(nullptr,sl3::asio::driver_clsid,reinterpret_cast<void**>(&h.device))==S_OK &&
                    h.device->init(nullptr)==ASIOTrue,"Fresh recreated IASIO object initializes after predecessor release");
            if(!persistent)expected.insert(expected.end(),{"acquire","rate"});else expected.push_back("rate");verify_audit();
            if(persistent){
                require(scope?scope->EndScope()==S_FALSE:!close_owner(),"Explicit close refused while an ASIO object borrows the owner");
                IASIO* competing=nullptr;
                require(factory.CreateInstance(nullptr,sl3::asio::driver_clsid,reinterpret_cast<void**>(&competing))==S_OK,
                        "Construct competing ASIO identity without acquiring transport");
                require(competing->init(nullptr)==ASIOFalse,"Concurrent facade borrow rejected before worker operation");
                competing->Release();verify_audit();
            }
            ASIOCallbacks callbacks{};callbacks.bufferSwitch=callback;
            for(unsigned stream=0;stream<2;++stream){
                h.calls=0;ResetEvent(h.entered);
                require(h.device->createBuffers(h.buffers.data(),12,128,&callbacks)==ASE_OK && h.device->start()==ASE_OK &&
                        WaitForSingleObject(h.entered,2000)==WAIT_OBJECT_0,"Recreated object creates buffers and delivers setup/stream callbacks");
                // Match the observed setup I/O hold only as an application call
                // shape. This elapsed delay is not a USB-readiness condition.
                if(stream==0)Sleep(80);
                require(h.device->stop()==ASE_OK && h.calls>0 && !h.bad && h.device->disposeBuffers()==ASE_OK,
                        "Recreated object retires setup/stream callbacks and buffers");
                expected.insert(expected.end(),{"rate","begin","end"});verify_audit();
                for(auto& buffer:h.buffers)buffer.buffers[0]=buffer.buffers[1]=nullptr;
            }
            require(h.device->Release()==0,"Recreated object releases its last interface");h.device=nullptr;
        }
        if(!persistent)expected.push_back("release");verify_audit();
        require(unload()==S_FALSE,"Only surviving factory still prevents COM unload between objects");
    }
    if(close_owner){require(close_owner(),"Explicit scope close releases the one retained worker");expected.push_back("release");verify_audit();}
    if(scope){
        require(scope->EndScope()==S_OK && scope->EndScope()==S_FALSE && scope->BeginScope()==E_UNEXPECTED,
                "Actual factory scope closes once and cannot reopen");expected.push_back("release");verify_audit();
        void* after=reinterpret_cast<void*>(1);
        require(factory.CreateInstance(nullptr,sl3::asio::driver_clsid,&after)==E_UNEXPECTED && !after,
                "Closed scoped factory cannot fall back to a private acquisition");
    }
}
static void factory_scope_lifetime(GetClass get,ConfigureAudit configure,const std::filesystem::path& fixture,const std::string& hash){
    GUID id{};require(CoCreateGuid(&id)==S_OK,"Factory scope audit identity");wchar_t name[40]{};
    require(StringFromGUID2(id,name,40)!=0,"Format factory scope audit identity");
    const auto path=std::filesystem::temp_directory_path()/(std::wstring(L"sl3-factory-scope-")+name+L".txt");
    struct Remove {std::filesystem::path path;~Remove(){std::error_code error;std::filesystem::remove(path,error);}} remove{path};
    auto audit=[&]{std::ifstream input(path);std::vector<std::string> rows;for(std::string line;std::getline(input,line);)rows.push_back(line);return rows;};
    auto make=[&](IClassFactory*& factory,sl3::asio::DeviceScope*& scope){
        require(get(sl3::asio::driver_clsid,IID_IClassFactory,reinterpret_cast<void**>(&factory))==S_OK &&
                factory->QueryInterface(sl3::asio::scope_iid,reinterpret_cast<void**>(&scope))==S_OK,"Create explicit scope controller");
    };
    require(configure(fixture.c_str(),hash.c_str(),path.c_str()),"Configure scope lifetime fixture");
    {
        IClassFactory* factory=nullptr;sl3::asio::DeviceScope* scope=nullptr;make(factory,scope);
        require(scope->BeginScope()==S_OK && scope->EndScope()==S_OK && !std::filesystem::exists(path),
                "Begin/end without ASIO init performs no worker acquisition");scope->Release();factory->Release();
    }
    {
        IClassFactory* factory=nullptr;sl3::asio::DeviceScope* scope=nullptr;make(factory,scope);IASIO* device=nullptr;
        require(scope->BeginScope()==S_OK && factory->CreateInstance(nullptr,sl3::asio::driver_clsid,reinterpret_cast<void**>(&device))==S_OK &&
                device->init(nullptr)==ASIOTrue,"Scoped device acquires before controller release");
        require(scope->Release()==1 && factory->Release()==0 && audit()==std::vector<std::string>({"acquire","rate"}),
                "Live device retains owner after final factory/controller release");
        ASIOSampleRate rate=0;require(device->getSampleRate(&rate)==ASE_OK && rate==48000 && device->Release()==0 &&
                audit()==std::vector<std::string>({"acquire","rate","release"}),"Last device releases the orphaned scope exactly once");
    }
    require(std::filesystem::remove(path),"Retired audit removed before unopened-device case");
    {
        IClassFactory* factory=nullptr;sl3::asio::DeviceScope* scope=nullptr;make(factory,scope);IASIO* device=nullptr;
        require(scope->BeginScope()==S_OK && factory->CreateInstance(nullptr,sl3::asio::driver_clsid,reinterpret_cast<void**>(&device))==S_OK &&
                scope->EndScope()==S_OK && device->init(nullptr)==ASIOFalse && !std::filesystem::exists(path),
                "Uninitialized device cannot acquire after scope close");device->Release();scope->Release();factory->Release();
    }
    {
        IClassFactory* factory=nullptr;sl3::asio::DeviceScope* scope=nullptr;make(factory,scope);IASIO* device=nullptr;
        require(factory->CreateInstance(nullptr,sl3::asio::driver_clsid,reinterpret_cast<void**>(&device))==S_OK &&
                scope->BeginScope()==E_UNEXPECTED && !std::filesystem::exists(path),"Cannot switch an already-used default factory into scoped ownership");
        device->Release();scope->Release();factory->Release();
    }
}
static void factory_scope_fault(GetClass get,Configure configure,const std::filesystem::path& fixture,const std::string& hash){
    require(configure(fixture.c_str(),hash.c_str()),"Configure scope fault fixture");
    IClassFactory* factory=nullptr;sl3::asio::DeviceScope* scope=nullptr;
    require(get(sl3::asio::driver_clsid,IID_IClassFactory,reinterpret_cast<void**>(&factory))==S_OK &&
            factory->QueryInterface(sl3::asio::scope_iid,reinterpret_cast<void**>(&scope))==S_OK && scope->BeginScope()==S_OK,
            "Create faulted-lifetime scope controller");
    Host h;host=&h;h.block=true;
    require(factory->CreateInstance(nullptr,sl3::asio::driver_clsid,reinterpret_cast<void**>(&h.device))==S_OK &&
            h.device->init(nullptr)==ASIOTrue,"Initialize scoped callback owner");
    ASIOCallbacks callbacks{};callbacks.bufferSwitch=callback;
    require(h.device->createBuffers(h.buffers.data(),12,64,&callbacks)==ASE_OK && h.device->start()==ASE_OK &&
            WaitForSingleObject(h.entered,2000)==WAIT_OBJECT_0,"Block callback before destroying scoped ASIO object");
    const auto start=GetTickCount64();require(h.device->Release()==0,"Release scoped object with blocked callback");h.device=nullptr;
    require(GetTickCount64()-start<1000 && !h.calls,"Controller does not make blocked-object destruction wait");
    SetEvent(h.release);const auto deadline=GetTickCount64()+2000;
    while(!h.calls){require(GetTickCount64()<deadline,"Scoped callback returns through retained planes");Sleep(1);}
    require(h.calls==1 && !h.bad && scope->EndScope()==E_FAIL,"Forced shutdown is not a healthy scope end");
    void* next=reinterpret_cast<void*>(1);
    require(factory->CreateInstance(nullptr,sl3::asio::driver_clsid,&next)==E_UNEXPECTED && !next && scope->BeginScope()==E_UNEXPECTED,
            "Failed scope end cannot fall back or reacquire");
    scope->Release();factory->Release();
}
int wmain(int argc,wchar_t** argv){
    try{
        require(argc==3 || (argc==4 && std::wstring(argv[3])==L"--retained"),"Session ASIO test DLL and simulated worker required");
        const auto module=LoadLibraryExW(argv[1],nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);
        require(module!=nullptr,"Load unregistered session ASIO test DLL");
        const auto get=reinterpret_cast<GetClass>(GetProcAddress(module,"DllGetClassObject"));
        const auto unload=reinterpret_cast<CanUnload>(GetProcAddress(module,"DllCanUnloadNow"));
        const auto configure=reinterpret_cast<Configure>(GetProcAddress(module,argc==4?"sl3_test_configure_retained":"sl3_test_configure"));
        require(get && unload && configure && !GetProcAddress(module,"DllRegisterServer"),"Test-only provider and ordinary COM ABI without registration");
        const std::filesystem::path fixture=argv[2];const auto hash=sl3::worker::Process::executable_sha256(fixture);
        require(!configure(fixture.c_str(),std::string(64,'0').c_str()) && configure(fixture.c_str(),hash.c_str()),"Configure only pinned simulated executable");
        IClassFactory* factory=nullptr;require(get(sl3::asio::driver_clsid,IID_IClassFactory,reinterpret_cast<void**>(&factory))==S_OK,"Create actual COM factory");
        {
            Host h;host=&h;require(factory->CreateInstance(nullptr,sl3::asio::driver_clsid,reinterpret_cast<void**>(&h.device))==S_OK,"Create actual IASIO interface");
            require(h.device->init(nullptr)==ASIOTrue && unload()==S_FALSE,"Actual ASIO init uses isolated clock inspection; live object blocks COM unload");
            long input=0,output=0,minimum=0,maximum=0,preferred=0,granularity=0;
            require(h.device->getChannels(&input,&output)==ASE_OK && input==6 && output==6 &&
                    h.device->getBufferSize(&minimum,&maximum,&preferred,&granularity)==ASE_OK && minimum==64 && maximum==1024 && preferred==128 && granularity==-1,"ASIO vtable metadata");
            ASIOCallbacks callbacks{};callbacks.bufferSwitch=callback;
            require(h.device->createBuffers(h.buffers.data(),12,64,&callbacks)==ASE_OK && h.device->getLatencies(&input,&output)==ASE_OK && input==71 && output==75,"Actual buffers plus explicit synthetic latency profile");
            for(unsigned cycle=0;cycle<2;++cycle){h.calls=0;ResetEvent(h.entered);
                require(h.device->start()==ASE_OK && WaitForSingleObject(h.entered,2000)==WAIT_OBJECT_0 && h.device->stop()==ASE_OK && h.calls>0 && !h.bad,"ASIO ABI reaches callbacks, position and orderly retirement across fresh sessions");}
            require(h.device->disposeBuffers()==ASE_OK,"Actual ASIO buffer disposal");
            // Current Serato's legacy ASIO backend first tries the aligned
            // application size, then retries the driver's preferred bank.
            // This tests our real vtable/lifecycle, without running Serato.
            for(auto& buffer:h.buffers)buffer.buffers[0]=buffer.buffers[1]=nullptr;
            h.calls=0;ResetEvent(h.entered);
            require(h.device->createBuffers(h.buffers.data(),12,240,&callbacks)==ASE_InvalidMode && h.calls==0,"Aligned application bank rejected without starting callbacks");
            for(const auto& buffer:h.buffers)require(!buffer.buffers[0] && !buffer.buffers[1],"Rejected creation publishes no planes");
            require(h.device->getBufferSize(&minimum,&maximum,&preferred,&granularity)==ASE_OK && preferred==128,"Preferred bank remains available after rejection");
            h.frames=unsigned(preferred);
            require(h.device->createBuffers(h.buffers.data(),12,preferred,&callbacks)==ASE_OK &&
                    h.device->getLatencies(&input,&output)==ASE_OK && input==135 && output==139,"Retry preferred bank with unchanged synthetic timing");
            for(unsigned cycle=0;cycle<2;++cycle){h.calls=0;ResetEvent(h.entered);
                require(h.device->start()==ASE_OK && WaitForSingleObject(h.entered,2000)==WAIT_OBJECT_0 && h.device->stop()==ASE_OK && h.calls>0 && !h.bad,"Preferred-bank retry supports callbacks and repeated fresh sessions");}
            require(h.device->disposeBuffers()==ASE_OK,"Retire preferred-bank retry buffers");
            // Prevent Host's redundant dispose; its stop is safely idempotent.
        }
        std::unique_ptr<Host> blocked;
        if(argc==4){
            const auto audited=reinterpret_cast<ConfigureAudit>(GetProcAddress(module,"sl3_test_configure_retained_audit"));
            require(audited!=nullptr,"Test-only object-recreation audit provider exists");
            recreated_objects(*factory,audited,unload,fixture,hash);
            const auto shared=reinterpret_cast<ConfigureAudit>(GetProcAddress(module,"sl3_test_configure_shared_owner_audit"));
            const auto close_owner=reinterpret_cast<CloseOwner>(GetProcAddress(module,"sl3_test_close_shared_owner"));
            require(shared && close_owner,"Test-only explicit owner scope exists");
            recreated_objects(*factory,shared,unload,fixture,hash,close_owner);
            IClassFactory* scoped_factory=nullptr;sl3::asio::DeviceScope* scope=nullptr;
            require(get(sl3::asio::driver_clsid,IID_IClassFactory,reinterpret_cast<void**>(&scoped_factory))==S_OK &&
                    scoped_factory->QueryInterface(sl3::asio::scope_iid,reinterpret_cast<void**>(&scope))==S_OK,
                    "Actual factory exposes project scope capability");
            IUnknown* scope_identity=nullptr;
            require(scope->QueryInterface(IID_IUnknown,reinterpret_cast<void**>(&scope_identity))==S_OK &&
                    scope_identity==static_cast<IUnknown*>(scoped_factory),"Scope and factory have one COM identity");
            scope_identity->Release();
            recreated_objects(*scoped_factory,audited,unload,fixture,hash,nullptr,scope);
            require(scope->Release()==1 && scoped_factory->Release()==0,"Release both factory controller interfaces");
            factory_scope_lifetime(get,audited,fixture,hash);
            factory_scope_fault(get,configure,fixture,hash);
            require(configure(fixture.c_str(),hash.c_str()),"Restore unaudited retained fixture for blocked-callback destruction");
            blocked=std::make_unique<Host>();host=blocked.get();blocked->block=true;
            require(factory->CreateInstance(nullptr,sl3::asio::driver_clsid,reinterpret_cast<void**>(&blocked->device))==S_OK && blocked->device->init(nullptr)==ASIOTrue,
                    "Create retained actual IASIO object for blocked destruction");
            ASIOCallbacks callbacks{};callbacks.bufferSwitch=callback;
            require(blocked->device->createBuffers(blocked->buffers.data(),12,64,&callbacks)==ASE_OK && blocked->device->start()==ASE_OK &&
                    WaitForSingleObject(blocked->entered,2000)==WAIT_OBJECT_0,"Actual DLL callback blocked before COM owner destruction");
            const auto begin=GetTickCount64();require(blocked->device->Release()==0,"Release last IASIO object while its callback executes");blocked->device=nullptr;
            require(GetTickCount64()-begin<1000 && blocked->calls==0,"Actual COM destruction does not wait on blocked user code");
        }
        require(factory->Release()==0 && unload()==S_OK,"All COM references released; executing audio has its independent module lease");
        require(FreeLibrary(module)!=0,"Release caller DLL reference");
        if(blocked){
            require(GetModuleHandleW(L"sl3_asio_session_fixture.dll")!=nullptr,"Executing retained callback keeps DLL loaded after COM/caller references are gone");
            SetEvent(blocked->release);const auto deadline=GetTickCount64()+2000;
            while(!blocked->calls){require(GetTickCount64()<deadline,"Actual retained callback returns through preserved planes/code");Sleep(1);}
            require(blocked->calls==1 && !blocked->bad,"Actual retained callback accesses original planes after COM destruction");
        }
        const auto begin=GetTickCount64();while(GetModuleHandleW(L"sl3_asio_session_fixture.dll")){require(GetTickCount64()-begin<2000,"Deferred audio-code reference releases after thread retirement");Sleep(1);}
        std::cout<<"Actual unregistered ASIO DLL vtable initialized, delivered repeat sessions, rejected 240 frames and retried preferred 128-frame banks; retained mode also audited enumeration release and two recreated objects with setup/stream I/O; synthetic timing only, no physical USB or Serato execution\n";
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
