#include "asio/driver_facade.hpp"
#include "asio/driver_configuration.hpp"
#include "asio/com_identity.hpp"
#include "com_activation_fixture.hpp"
#include "windows/broker_pipe.hpp"
#include "iasiodrv.h"
#include <algorithm>
#include <condition_variable>
#include <cstring>
#include <fstream>
#include <iostream>
#include <mutex>
#include <thread>

using namespace sl3;using namespace sl3::asio;using namespace sl3::worker;
static void require(bool good,const char* text){if(!good)throw std::runtime_error(text);}
struct Handle {HANDLE value=nullptr;~Handle(){if(value)CloseHandle(value);}};
template<class F>static F symbol(HMODULE module,const char* name){
    const auto address=GetProcAddress(module,name);require(address!=nullptr,"Test DLL export");F result;static_assert(sizeof(result)==sizeof(address));std::memcpy(&result,&address,sizeof(result));return result;
}
struct Host {
    IASIO* device=nullptr;std::array<ASIOBufferInfo,12> planes{};bool block=false;
    Handle entered,release;std::atomic<unsigned> calls{0};std::atomic<bool> bad{false};
    Host(){entered.value=CreateEventW(nullptr,TRUE,FALSE,nullptr);release.value=CreateEventW(nullptr,TRUE,FALSE,nullptr);require(entered.value && release.value,"Callback events");
        for(long c=0;c<6;++c){planes[std::size_t(c)]={ASIOTrue,c,{}};planes[std::size_t(c+6)]={ASIOFalse,c,{}};}}
    ~Host(){SetEvent(release.value);if(device){device->stop();device->disposeBuffers();device->Release();}}
};
static Host* host=nullptr;
static void callback(long bank,ASIOBool direct){
    auto& h=*host;const auto call=h.calls.load();ASIOSamples position{};ASIOTimeStamp timestamp{};ASIOSampleRate rate=0;
    if(bank!=long(call%2) || direct!=ASIOTrue || h.device->getSamplePosition(&position,&timestamp)!=ASE_OK ||
       ((std::uint64_t(position.hi)<<32)|position.lo)!=std::uint64_t(call)*128 || h.device->getSampleRate(&rate)!=ASE_OK || rate!=48000 ||
       h.device->stop()!=ASE_InvalidMode || h.device->disposeBuffers()!=ASE_InvalidMode)h.bad=true;
    SetEvent(h.entered.value);if(h.block)WaitForSingleObject(h.release.value,INFINITE);
    for(unsigned c=0;c<6;++c)std::memset(h.planes[c+6].buffers[bank],0,128*3);
    h.calls.fetch_add(1);
}
static void buffers(Host& h){ASIOCallbacks callbacks{};callbacks.bufferSwitch=callback;
    require(h.device->createBuffers(h.planes.data(),12,64,&callbacks)==ASE_InvalidMode,"Synthetic fixed profile refuses another buffer size");
    require(h.device->createBuffers(h.planes.data(),12,128,&callbacks)==ASE_OK,"Official SDK planes prepared");}
static void cycles(Host& h,const std::filesystem::path& pause={}){
    buffers(h);const auto stable=h.planes[0].buffers[0];
    for(unsigned cycle=0;cycle<2;++cycle){
        h.calls=0;ResetEvent(h.entered.value);require(h.device->start()==ASE_OK,"Actual IASIO start over broker");
        if(cycle==0 && !pause.empty()){
            const auto first=GetTickCount64()+2000;while(h.calls==0){require(GetTickCount64()<first,"First callback before pointer withdrawal barrier");Sleep(1);}
            {std::ofstream marker(pause/L"client-running.txt");marker<<"actual simulated callback observed\n";require(bool(marker),"Write control-thread running marker");}
            const auto resume=GetTickCount64()+5000;
            while(!std::filesystem::exists(pause/L"client-resume.txt")){require(GetTickCount64()<resume,"Explicit pointer withdrawal/publication barrier");Sleep(1);}
        }
        const auto deadline=GetTickCount64()+2000;
        while(h.calls<12){require(GetTickCount64()<deadline,"Several SDK callbacks completed over direct broker mapping");Sleep(1);}
        require(h.device->stop()==ASE_OK && !h.bad && h.calls>=12 && h.planes[0].buffers[0]==stable,"ASIO callback positions/reentry/stable planes and retained stop");
    }
    require(h.device->disposeBuffers()==ASE_OK,"Retired callback planes disposed");
}
static void ordinary(const std::filesystem::path& library,const std::wstring& endpoint,HANDLE server,bool blocked,const std::string& worker_hash={},bool activate_com=false,const std::filesystem::path& pause={}){
    HMODULE module=LoadLibraryExW(library.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);require(module!=nullptr,"Load actual unregistered ASIO test DLL");
    using Configure=BOOL(*)(const wchar_t*,HANDLE);using GetClass=HRESULT(__stdcall*)(REFCLSID,REFIID,void**);using Unload=HRESULT(__stdcall*)();
    const auto configure=symbol<Configure>(module,"sl3_test_configure_broker");const auto get=symbol<GetClass>(module,"DllGetClassObject");const auto unload=symbol<Unload>(module,"DllCanUnloadNow");
    if(worker_hash.empty())require(configure(endpoint.c_str(),server),"Explicit simulated broker test configuration");
    else {using ConfigureBound=BOOL(*)(const wchar_t*,HANDLE,const char*);require(symbol<ConfigureBound>(module,"sl3_test_configure_bound_broker")(endpoint.c_str(),server,worker_hash.c_str()),"Explicit simulated provider with reviewed record worker contract");}
    auto create=[&](Host& h){
        HRESULT result=E_FAIL;
        if(activate_com)result=CoCreateInstance(driver_clsid,nullptr,CLSCTX_INPROC_SERVER,driver_clsid,reinterpret_cast<void**>(&h.device));
        else {IClassFactory* factory=nullptr;require(get(driver_clsid,IID_IClassFactory,reinterpret_cast<void**>(&factory))==S_OK,"Fresh ordinary factory");
            result=factory->CreateInstance(nullptr,driver_clsid,reinterpret_cast<void**>(&h.device));factory->Release();}
        if(result!=S_OK)std::cerr<<"Create IASIO HRESULT 0x"<<std::hex<<static_cast<unsigned long>(result)<<std::dec<<"\n";
        require(result==S_OK && h.device->init(nullptr)==ASIOTrue,"Ordinary IASIO object initialized without custom scope");
    };
    if(!blocked){
        for(unsigned object=0;object<3;++object){
            Host h;host=&h;create(h);long in=0,out=0;
            require(h.device->getChannels(&in,&out)==ASE_OK && in==6 && out==6,"Broker metadata on ordinary object");
            require(h.device->setSampleRate(44100)==ASE_NoClock && h.device->setSampleRate(48000)==ASE_OK,"ASIO remains observed-rate-only");
            if(object)cycles(h,object==1?pause:std::filesystem::path{}); // Enumeration object followed by two audio objects.
            require(h.device->Release()==0,"Ordinary object releases final reference");h.device=nullptr;
            require(unload()==S_OK,"No lingering COM object/scope after successful detach");
            // No parent-side served barrier or USB retry between these objects.
        }
        FreeLibrary(module);if(activate_com)CoFreeUnusedLibrariesEx(0,0);return;
    }
    Host h;host=&h;h.block=true;create(h);buffers(h);require(h.device->start()==ASE_OK,"Start deliberately blocked callback");
    require(WaitForSingleObject(h.entered.value,2000)==WAIT_OBJECT_0,"Callback is executing before destruction");
    h.device->Release();h.device=nullptr;FreeLibrary(module);module=nullptr;
    require(GetModuleHandleW(library.c_str())!=nullptr,"Callback retains ASIO module after object destruction/caller unload");
    SetEvent(h.release.value);const auto deadline=GetTickCount64()+3000;
    while(GetModuleHandleW(library.c_str())){require(GetTickCount64()<deadline,"ASIO module unload after actual callback/thread retirement");Sleep(1);}
    require(h.calls==1 && !h.bad,"Blocked callback safely finishes on retained planes with no additional lease");
}
static void reports(const std::wstring& endpoint,HANDLE server){
    BrokerAttachment spec{endpoint,ProcessWait::duplicate(server),session::Kind::simulated};
    auto owner=std::make_shared<DriverOwner>(spec);
    {DriverFacade facade(owner,{7,11,48000,128});require(facade.init()==ASIOTrue,"Broker facade for domain report");}
    {DriverFacade next(owner,{7,11,48000,128});require(next.init()==ASIOTrue,"Recreated facade on same client obtains fresh idle clock");}
    const auto report=owner->close();require(report && driver_session_closed(*report),"Client-domain final retirement helper");
    require(report->domain==HostDomain::broker_client && report->broker.ever_attached && report->broker.detached && !report->broker.attached &&
        report->broker.worker_alive && !report->process.started && !report->process.job_assigned && !report->device_released && !report->device_held,
        "Acknowledged client detach is neither an owned process job nor physical USB release");
}
struct Server {
    BrokerListener listener;Handle stop;std::thread thread;std::mutex mutex;std::condition_variable condition;
    bool ready=false;std::exception_ptr error;BrokerReport final;
    std::filesystem::path audit=std::filesystem::temp_directory_path()/(listener.name().substr(listener.name().size()-32)+L"-asio-broker.txt");
    explicit Server(const std::filesystem::path& fixture){
        require(!std::filesystem::exists(audit),"Fresh ASIO broker audit");stop.value=CreateEventW(nullptr,TRUE,FALSE,nullptr);require(stop.value!=nullptr,"Broker stop event");
        thread=std::thread([this,fixture]{try{
            BrokerSpec spec;spec.executable=fixture;spec.sha256=Process::executable_sha256(fixture);spec.kind=session::Kind::simulated;spec.fixture_mode=L"audit:"+audit.native();
            RetainedBroker owner(spec);require(owner.open(),"ASIO test server opens simulated worker once");
            {std::lock_guard<std::mutex> lock(mutex);ready=true;condition.notify_all();}
            while(WaitForSingleObject(stop.value,0)==WAIT_TIMEOUT){
                std::string diagnostic;const auto result=serve_broker_client(listener,owner,stop.value,&diagnostic);
                if(!diagnostic.empty())std::cerr<<"Broker ASIO server: "<<diagnostic<<'\n';
                if(result==BrokerServeResult::owner_failed || result==BrokerServeResult::stopped)break;
            }
            final=owner.close();
        }catch(...){std::lock_guard<std::mutex> lock(mutex);error=std::current_exception();condition.notify_all();}});
        std::unique_lock<std::mutex> lock(mutex);
        if(!condition.wait_for(lock,std::chrono::seconds(8),[&]{return ready || error;})){lock.unlock();finish();throw std::runtime_error("Server ready deadline");}
        if(error){lock.unlock();finish();std::rethrow_exception(error);}
    }
    void finish(){SetEvent(stop.value);if(thread.joinable())thread.join();}
    ~Server(){finish();std::error_code ec;std::filesystem::remove(audit,ec);}
    std::vector<std::string> lines(){std::ifstream in(audit);std::vector<std::string> rows;for(std::string s;std::getline(in,s);)rows.push_back(s);return rows;}
};
static void run(const std::filesystem::path& self,const std::filesystem::path& fixture,const std::filesystem::path& library,const std::wstring& mode){
    Server server(fixture);Process child;const auto result_path=server.audit.native()+L"-child.txt";
    child.launch(self,Process::executable_sha256(self),{L"--client",server.listener.name(),std::to_wstring(GetCurrentProcessId()),library.native(),mode,result_path});
    const auto deadline=GetTickCount64()+15000;
    while(!child.observe().process_exited){const auto now=GetTickCount64();if(now>=deadline){child.terminate_and_wait(2000);throw std::runtime_error("ASIO child deadline");}child.wait_for_exit(DWORD((std::min)(ULONGLONG(5000),deadline-now)));}
    server.finish();std::string error;{std::ifstream in{std::filesystem::path(result_path)};std::getline(in,error);}std::error_code ec;std::filesystem::remove(result_path,ec);
    if(!error.empty())std::cerr<<error<<'\n';require(child.observe().exit_code==0,"ASIO broker child succeeds");if(server.error)std::rethrow_exception(server.error);
    const auto rows=server.lines();require(std::count(rows.begin(),rows.end(),"acquire")==1 && std::count(rows.begin(),rows.end(),"release")==1,"One worker acquisition/final release across actual ASIO client lifetimes");
    if(mode==L"ordinary")require(!server.final.failed && std::count(rows.begin(),rows.end(),"rate")==8 && std::count(rows.begin(),rows.end(),"begin")==4 && std::count(rows.begin(),rows.end(),"end")==4,"Three ordinary COM objects/four ASIO starts share one acquired worker");
    else if(mode==L"reports")require(!server.final.failed && std::count(rows.begin(),rows.end(),"begin")==0 && std::count(rows.begin(),rows.end(),"rate")==3,"Client report path refreshes reused owner clock and sends no audio");
    else require(server.final.failed && server.final.process.process_exited && server.final.process.job_empty,"Blocked client destruction seals broker without assuming callback retirement");
}
int wmain(int argc,wchar_t** argv){
    try{
        if(argc==5 && std::wstring(argv[1])==L"--published"){
            const auto config=load_driver_entry_configuration(std::filesystem::absolute(argv[2]));
            require(config.broker && config.broker->kind==session::Kind::native && config.latency.rate_hz==48000 && config.latency.buffer_frames==128 &&
                config.latency.input_extra_frames==7 && config.latency.output_extra_frames==11,"Published native-only record with synthetic test profile");
            const std::wstring mode=argv[4];require(mode==L"ordinary" || mode==L"ordinary-sta" || mode==L"ordinary-mta" || mode==L"ordinary-sta-withdrawal" || mode==L"blocked","Published fixture mode");
            const bool activate_com=mode==L"ordinary-sta" || mode==L"ordinary-mta" || mode==L"ordinary-sta-withdrawal";
            std::unique_ptr<sl3::test::ComApartment> apartment;std::unique_ptr<sl3::test::ComActivation> activation;
            if(activate_com){apartment=std::make_unique<sl3::test::ComApartment>(mode==L"ordinary-mta"?COINIT_MULTITHREADED:COINIT_APARTMENTTHREADED);
                activation=std::make_unique<sl3::test::ComActivation>(std::filesystem::absolute(argv[3]));}
            ordinary(std::filesystem::absolute(argv[3]),config.broker->endpoint,config.broker->server->handle(),mode==L"blocked",config.broker->worker_sha256,activate_com,mode==L"ordinary-sta-withdrawal"?std::filesystem::absolute(argv[2]).parent_path():std::filesystem::path{});
            if(activate_com)std::wcout<<L"CoCreateInstance "<<mode<<L": three objects/four simulated streams; one retained owner; no registration or USB\n";
            return 0;
        }
        if(argc==7 && std::wstring(argv[1])==L"--client"){
            Handle server;server.value=OpenProcess(SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,DWORD(std::stoul(argv[3])));require(server.value!=nullptr,"Fixture-only parent reference");
            if(std::wstring(argv[5])==L"reports")reports(argv[2],server.value);else ordinary(std::filesystem::absolute(argv[4]),argv[2],server.value,std::wstring(argv[5])==L"blocked");return 0;
        }
        require(argc==3,"Fixture and test DLL paths required");const auto self=std::filesystem::absolute(argv[0]);
        for(const auto mode:{L"ordinary",L"reports",L"blocked"})run(self,argv[1],argv[2],mode);
        std::cout<<"Broker-backed ordinary IASIO objects, callbacks, domain reports and blocked-module lifetime passed (simulation only)\n";return 0;
    }catch(const std::exception& e){if(argc==7){std::ofstream out{std::filesystem::path(argv[6])};out<<e.what()<<'\n';}std::cerr<<e.what()<<'\n';return 1;}
}
