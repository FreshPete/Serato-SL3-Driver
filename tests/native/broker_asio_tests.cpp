#include "asio/driver_facade.hpp"
#include "asio/driver_configuration.hpp"
#include "asio/com_identity.hpp"
#include "com_activation_fixture.hpp"
#include "windows/broker_pipe.hpp"
#include "iasiodrv.h"
#include <algorithm>
#include <condition_variable>
#include <cstring>
#include <cwchar>
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
    IASIO* device=nullptr;std::array<ASIOBufferInfo,12> planes{};bool block=false;unsigned rate=48000;
    Handle entered,release;std::atomic<unsigned> calls{0};std::atomic<bool> bad{false};
    Host(){entered.value=CreateEventW(nullptr,TRUE,FALSE,nullptr);release.value=CreateEventW(nullptr,TRUE,FALSE,nullptr);require(entered.value && release.value,"Callback events");
        for(long c=0;c<6;++c){planes[std::size_t(c)]={ASIOTrue,c,{}};planes[std::size_t(c+6)]={ASIOFalse,c,{}};}}
    ~Host(){SetEvent(release.value);if(device){device->stop();device->disposeBuffers();device->Release();}}
};
static Host* host=nullptr;
static void callback(long bank,ASIOBool direct){
    auto& h=*host;const auto call=h.calls.load();ASIOSamples position{};ASIOTimeStamp timestamp{};ASIOSampleRate rate=0;
    if(bank!=long(call%2) || direct!=ASIOTrue || h.device->getSamplePosition(&position,&timestamp)!=ASE_OK ||
       ((std::uint64_t(position.hi)<<32)|position.lo)!=std::uint64_t(call)*128 || h.device->getSampleRate(&rate)!=ASE_OK || rate!=h.rate ||
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
    if(h.rate==44100){
        long input=71,output=72;
        require(h.device->getLatencies(&input,&output)==ASE_InvalidMode && input==0 && output==0,
                "Unmeasured broker publishes no directional latency");
    }
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
static constexpr wchar_t close_window_class[]=L"SL3SimulatedAsioCloseFixture";
static LRESULT CALLBACK close_window_proc(HWND window,UINT message,WPARAM wparam,LPARAM lparam){
    if(message==WM_DESTROY){PostQuitMessage(0);return 0;}
    return DefWindowProcW(window,message,wparam,lparam);
}
static void window_shutdown(Host& h){
    buffers(h);require(h.device->start()==ASE_OK,"Start window-owned simulated ASIO session");
    const auto ready=GetTickCount64()+2000;
    while(h.block?WaitForSingleObject(h.entered.value,0)!=WAIT_OBJECT_0:h.calls.load()<12){
        require(GetTickCount64()<ready,"Window host has executing/completed callbacks before close");Sleep(1);
    }
    WNDCLASSW klass{};klass.lpfnWndProc=close_window_proc;klass.hInstance=GetModuleHandleW(nullptr);klass.lpszClassName=close_window_class;
    require(RegisterClassW(&klass)!=0,"Register owned close-message test window");
    struct Window {
        HWND value=nullptr;
        ~Window(){if(value && IsWindow(value))DestroyWindow(value);UnregisterClassW(close_window_class,GetModuleHandleW(nullptr));}
    } window;
    window.value=CreateWindowExW(0,close_window_class,L"Simulated ASIO close test",WS_OVERLAPPEDWINDOW,
        0,0,320,160,nullptr,nullptr,klass.hInstance,nullptr);
    require(window.value!=nullptr,"Create hidden ordinary host window");
    MSG message{};int received=0;
    while((received=GetMessageW(&message,nullptr,0,0))>0){TranslateMessage(&message);DispatchMessageW(&message);}
    require(received==0 && !IsWindow(window.value),"Parent-posted WM_CLOSE destroyed owned window and ended UI loop");
    const auto before=GetTickCount64();const auto stopped=h.device->stop();const auto elapsed=GetTickCount64()-before;
    if(h.block){
        require(stopped==ASE_HWMalfunction && elapsed>=4000 && elapsed<7500,
            "Blocked callback returns a bounded failed stop instead of claiming retirement");
        require(h.device->disposeBuffers()==ASE_InvalidMode,"Executing callback keeps its planes after stop timeout");
        SetEvent(h.release.value);const auto retired=GetTickCount64()+3000;
        ASIOError disposed=ASE_InvalidMode;
        while((disposed=h.device->disposeBuffers())==ASE_InvalidMode){require(GetTickCount64()<retired,"Released callback retires before plane disposal");Sleep(1);}
        require(disposed==ASE_OK && h.calls==1 && !h.bad,"Late callback returns once on retained planes");
    }else{
        require(stopped==ASE_OK && elapsed<7500 && h.calls>=12 && !h.bad,"Window close stops active callbacks successfully");
        require(h.device->disposeBuffers()==ASE_OK,"Window close disposes retired planes");
    }
    require(h.device->Release()==0,"Window owner releases its final ASIO interface");h.device=nullptr;
}
static void ordinary(const std::filesystem::path& library,const std::wstring& endpoint,HANDLE server,bool blocked,const std::string& worker_hash={},bool activate_com=false,const std::filesystem::path& pause={},bool unmeasured=false,bool window_close=false){
    HMODULE module=LoadLibraryExW(library.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);require(module!=nullptr,"Load actual unregistered ASIO test DLL");
    using Configure=BOOL(*)(const wchar_t*,HANDLE);using GetClass=HRESULT(__stdcall*)(REFCLSID,REFIID,void**);using Unload=HRESULT(__stdcall*)();
    const auto configure=symbol<Configure>(module,"sl3_test_configure_broker");const auto get=symbol<GetClass>(module,"DllGetClassObject");const auto unload=symbol<Unload>(module,"DllCanUnloadNow");
    if(worker_hash.empty())require(configure(endpoint.c_str(),server),"Explicit simulated broker test configuration");
    else {using ConfigureBound=BOOL(*)(const wchar_t*,HANDLE,const char*);require(symbol<ConfigureBound>(module,unmeasured?"sl3_test_configure_unmeasured_broker":"sl3_test_configure_bound_broker")(endpoint.c_str(),server,worker_hash.c_str()),"Explicit simulated provider with pinned record worker contract");}
    auto create=[&](Host& h){
        HRESULT result=E_FAIL;
        if(activate_com)result=CoCreateInstance(driver_clsid,nullptr,CLSCTX_INPROC_SERVER,driver_clsid,reinterpret_cast<void**>(&h.device));
        else {IClassFactory* factory=nullptr;require(get(driver_clsid,IID_IClassFactory,reinterpret_cast<void**>(&factory))==S_OK,"Fresh ordinary factory");
            result=factory->CreateInstance(nullptr,driver_clsid,reinterpret_cast<void**>(&h.device));factory->Release();}
        if(result!=S_OK)std::cerr<<"Create IASIO HRESULT 0x"<<std::hex<<static_cast<unsigned long>(result)<<std::dec<<"\n";
        require(result==S_OK && h.device->init(nullptr)==ASIOTrue,"Ordinary IASIO object initialized without custom scope");
    };
    if(window_close){
        Host h;host=&h;h.block=blocked;create(h);window_shutdown(h);
        const auto deadline=GetTickCount64()+3000;
        while(unload()!=S_OK){require(GetTickCount64()<deadline,"Window host releases COM/module ownership");Sleep(1);}
        FreeLibrary(module);return;
    }
    if(!blocked){
        for(unsigned object=0;object<3;++object){
            Host h;h.rate=unmeasured?44100u:48000u;host=&h;create(h);long in=0,out=0;
            require(h.device->getChannels(&in,&out)==ASE_OK && in==6 && out==6,"Broker metadata on ordinary object");
            require(h.device->setSampleRate(unmeasured?48000:44100)==ASE_NoClock &&
                    h.device->setSampleRate(h.rate)==ASE_OK,"ASIO remains observed-rate-only");
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
    const bool window_close=mode==L"window-close" || mode==L"window-close-blocked";
    struct CloseTarget {DWORD pid;unsigned posted=0;bool failed=false;};
    CloseTarget target{GetProcessId(child.process_handle())};require(target.pid!=0,"Exact owned child PID");
    const auto deadline=GetTickCount64()+15000;
    while(!child.observe().process_exited){
        const auto now=GetTickCount64();if(now>=deadline){child.terminate_and_wait(2000);throw std::runtime_error("ASIO child deadline");}
        if(window_close && !target.posted){
            require(EnumWindows([](HWND window,LPARAM raw)->BOOL{
                auto& selected=*reinterpret_cast<CloseTarget*>(raw);DWORD pid=0;GetWindowThreadProcessId(window,&pid);
                wchar_t klass[64]{};
                if(pid==selected.pid && GetClassNameW(window,klass,64) && std::wcscmp(klass,close_window_class)==0){
                    if(PostMessageW(window,WM_CLOSE,0,0))++selected.posted;else selected.failed=true;
                }
                return TRUE;
            },reinterpret_cast<LPARAM>(&target))!=FALSE && !target.failed,"Post WM_CLOSE only to exact owned child/class");
        }
        child.wait_for_exit(window_close?10:DWORD((std::min)(ULONGLONG(5000),deadline-now)));
    }
    if(window_close)require(target.posted==1,"One cross-process close message accepted");
    server.finish();std::string error;{std::ifstream in{std::filesystem::path(result_path)};std::getline(in,error);}std::error_code ec;std::filesystem::remove(result_path,ec);
    if(!error.empty())std::cerr<<error<<'\n';require(child.observe().exit_code==0,"ASIO broker child succeeds");if(server.error)std::rethrow_exception(server.error);
    const auto rows=server.lines();require(std::count(rows.begin(),rows.end(),"acquire")==1 && std::count(rows.begin(),rows.end(),"release")==1,"One worker acquisition/final release across actual ASIO client lifetimes");
    if(mode==L"ordinary")require(!server.final.failed && std::count(rows.begin(),rows.end(),"rate")==8 && std::count(rows.begin(),rows.end(),"begin")==4 && std::count(rows.begin(),rows.end(),"end")==4,"Three ordinary COM objects/four ASIO starts share one acquired worker");
    else if(mode==L"reports")require(!server.final.failed && std::count(rows.begin(),rows.end(),"begin")==0 && std::count(rows.begin(),rows.end(),"rate")==3,"Client report path refreshes reused owner clock and sends no audio");
    else if(window_close)require(!server.final.failed && std::count(rows.begin(),rows.end(),"begin")==1 && std::count(rows.begin(),rows.end(),"end")==1,
        "Posted UI close retires one simulated stream and detaches after actual callback retirement");
    else require(server.final.failed && server.final.process.process_exited && server.final.process.job_empty,"Blocked client destruction seals broker without assuming callback retirement");
}
int wmain(int argc,wchar_t** argv){
    try{
        if(argc==5 && std::wstring(argv[1])==L"--published"){
            if(std::wstring(argv[4])==L"unmeasured"){
                const auto config=load_driver_entry_configuration(std::filesystem::absolute(argv[2]),TimingPolicy::unmeasured_diagnostic);
                require(config.broker && !config.latency.report_latency && config.latency.rate_hz==44100 &&
                        config.latency.buffer_frames==128,"Published unmeasured configuration");
                ordinary(std::filesystem::absolute(argv[3]),config.broker->endpoint,config.broker->server->handle(),
                         false,config.broker->worker_sha256,false,{},true);
                return 0;
            }
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
            const std::wstring mode=argv[5];const bool window_close=mode==L"window-close" || mode==L"window-close-blocked";
            std::unique_ptr<sl3::test::ComApartment> apartment;
            if(window_close)apartment=std::make_unique<sl3::test::ComApartment>(COINIT_APARTMENTTHREADED);
            if(mode==L"reports")reports(argv[2],server.value);
            else ordinary(std::filesystem::absolute(argv[4]),argv[2],server.value,mode==L"blocked" || mode==L"window-close-blocked",{},false,{},false,window_close);
            return 0;
        }
        require(argc==3,"Fixture and test DLL paths required");const auto self=std::filesystem::absolute(argv[0]);
        for(const auto mode:{L"ordinary",L"reports",L"blocked",L"window-close",L"window-close-blocked"})run(self,argv[1],argv[2],mode);
        std::cout<<"Broker-backed IASIO lifecycle and cross-process window close (normal/blocked callback) passed; simulation only, no USB or Serato\n";return 0;
    }catch(const std::exception& e){if(argc==7){std::ofstream out{std::filesystem::path(argv[6])};out<<e.what()<<'\n';}std::cerr<<e.what()<<'\n';return 1;}
}
