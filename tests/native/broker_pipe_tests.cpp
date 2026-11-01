#include "windows/broker_pipe.hpp"
#include <algorithm>
#include <condition_variable>
#include <fstream>
#include <iostream>
#include <mutex>
#include <thread>
#include <stdexcept>

using namespace sl3;using namespace sl3::worker;namespace ds=device_session;
static void require(bool good,const char* text){if(!good)throw std::runtime_error(text);}
template<class F>static void rejects(F f){bool bad=false;try{f();}catch(const std::exception&){bad=true;}require(bad,"Invalid broker operation accepted");}
struct Handle {HANDLE value=nullptr;~Handle(){if(value && value!=INVALID_HANDLE_VALUE)CloseHandle(value);}};
static void pump(Mailbox& audio){
    const auto deadline=GetTickCount64()+2000;unsigned blocks=0;std::uint64_t next=0;
    while(blocks<24 && GetTickCount64()<deadline){
        AudioBlock b;const auto got=audio.try_pop_audio(AudioDirection::input,b);
        if(got==AudioResult::empty){SwitchToThread();continue;}
        require(got==AudioResult::ok && b.first_frame==next && b.packet_count==8,"Pipe client fresh ordered input");
        for(unsigned n=0;n<b.packet_count;++n)next+=b.frames_per_packet[n];b.pcm.fill(0);
        for(;;){const auto sent=audio.try_push_audio(AudioDirection::output,b);
            if(sent==AudioResult::full){require(GetTickCount64()<deadline,"Pipe client output deadline");SwitchToThread();continue;}
            require(sent==AudioResult::ok,"Pipe client publishes silent PCM directly");break;}
        ++blocks;
    }
    require(blocks==24,"Pipe client audio progress");
}
static void word(std::vector<std::uint8_t>& b,unsigned v){for(unsigned n=0;n<4;++n)b.push_back(std::uint8_t(v>>(8*n)));}
static void handle(std::vector<std::uint8_t>& b,HANDLE h){const auto v=reinterpret_cast<std::uintptr_t>(h);for(unsigned n=0;n<8;++n)b.push_back(std::uint8_t(std::uint64_t(v)>>(8*n)));}
static HANDLE handle(const std::vector<std::uint8_t>& b){std::uint64_t v=0;for(unsigned n=0;n<8;++n)v|=std::uint64_t(b.at(24+n))<<(8*n);return reinterpret_cast<HANDLE>(std::uintptr_t(v));}
static std::vector<std::uint8_t> frame(unsigned sequence,unsigned op,const std::vector<std::uint8_t>& payload={}){
    std::vector<std::uint8_t> out;for(auto v:{0x42334c53u,1u,sequence,op,0u,unsigned(payload.size())})word(out,v);out.insert(out.end(),payload.begin(),payload.end());return out;
}
static bool send(HANDLE pipe,const std::vector<std::uint8_t>& b){DWORD bytes=0;return WriteFile(pipe,b.data(),DWORD(b.size()),&bytes,nullptr) && bytes==b.size();}
static std::vector<std::uint8_t> receive(HANDLE pipe){std::vector<std::uint8_t> b(4096);DWORD count=0;require(ReadFile(pipe,b.data(),DWORD(b.size()),&count,nullptr)!=FALSE,"Read raw fixture reply");b.resize(count);return b;}
static void malformed_client(const std::wstring& endpoint,const std::wstring& mode){
    std::unique_ptr<Mailbox> mapping_a,mapping_b;
    Handle pipe;pipe.value=CreateFileW(endpoint.c_str(),GENERIC_READ|GENERIC_WRITE,0,nullptr,OPEN_EXISTING,SECURITY_SQOS_PRESENT|SECURITY_IDENTIFICATION,nullptr);
    require(pipe.value!=INVALID_HANDLE_VALUE,"Raw fixture pipe connection");DWORD read_mode=PIPE_READMODE_MESSAGE;require(SetNamedPipeHandleState(pipe.value,&read_mode,nullptr,nullptr)!=FALSE,"Raw fixture message mode");
    if(mode==L"bad-magic"){auto bad=frame(1,1);bad[0]^=1;require(send(pipe.value,bad),"Bad greeting sent");}
    else if(mode==L"oversized"){(void)send(pipe.value,frame(1,1,std::vector<std::uint8_t>(2049,0)));}
    else{
        require(send(pipe.value,frame(1,1,ds::encode_hello(session::Kind::simulated))),"Raw greeting");Handle challenge;challenge.value=handle(receive(pipe.value));
        if(mode!=L"bad-proof")require(SetEvent(challenge.value)!=FALSE,"Raw process proof");
        require(send(pipe.value,frame(2,2)),"Raw proof reply");
        if(mode!=L"bad-proof"){
            Handle worker;worker.value=handle(receive(pipe.value));
            if(mode==L"bad-sequence")require(send(pipe.value,frame(99,3)),"Stale request sent");
            else if(mode==L"worker-op")require(send(pipe.value,frame(3,0x308)),"Unsupported worker opcode sent");
            else if(mode==L"wrong-mapping"){
                mapping_a=Mailbox::create();mapping_b=Mailbox::create();std::vector<std::uint8_t> bytes;handle(bytes,mapping_b->mapping_handle());
                const auto start=ds::encode_start({{48000,8,1000,200},mapping_a->name()});bytes.insert(bytes.end(),start.begin(),start.end());
                require(send(pipe.value,frame(3,4,bytes)),"Mismatched process mapping reference sent");
            }else if(mode==L"disconnect-idle"){CloseHandle(pipe.value);pipe.value=nullptr;Sleep(1500);return;}
            else if(mode==L"delayed-detach"){
                require(send(pipe.value,frame(3,6)),"Raw detach request");Sleep(100);
                const auto reply=receive(pipe.value);const auto state=ds::decode_snapshot({reply.begin()+24,reply.end()});
                require(state.phase==ds::Phase::ready && !state.device_released,"Delayed reader receives retained-state reply before disconnect");
                require(send(pipe.value,frame(4,6)),"Terminal detach acknowledgement");return;
            }
            else throw std::runtime_error("Unknown malformed fixture mode");
        }
    }
    std::array<std::uint8_t,4096> ignored{};DWORD bytes=0;
    require(!ReadFile(pipe.value,ignored.data(),DWORD(ignored.size()),&bytes,nullptr),"Malformed connection is closed rather than receiving success");
}
static int client(int argc,wchar_t** argv){
    require(argc==7,"Client fixture arguments");const std::wstring endpoint=argv[2],mode=argv[4];
    Handle server;server.value=OpenProcess(SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,DWORD(std::stoul(argv[3])));require(server.value!=nullptr,"Fixture parent process reference");
    std::string worker_hash;for(wchar_t c:std::wstring(argv[6])){require(c<=127,"ASCII worker hash");worker_hash+=static_cast<char>(c);}
    if(mode==L"wrong-server"){rejects([&]{BrokerClient wrong(endpoint,GetCurrentProcess(),session::Kind::simulated);});return 0;}
    if(mode==L"bad-magic" || mode==L"oversized" || mode==L"bad-proof" || mode==L"bad-sequence" || mode==L"worker-op" || mode==L"wrong-mapping" || mode==L"disconnect-idle" || mode==L"delayed-detach"){
        malformed_client(endpoint,mode);return 0;
    }
    if(mode==L"wrong-kind"){rejects([&]{BrokerClient wrong(endpoint,server.value,session::Kind::native,worker_hash);});return 0;}
    if(mode==L"wrong-worker"){rejects([&]{BrokerClient wrong(endpoint,server.value,session::Kind::simulated,std::string(64,'0'));});return 0;}
    BrokerClient broker(endpoint,server.value,session::Kind::simulated,worker_hash);
    if(mode==L"die-idle")ExitProcess(0);
    require(broker.clock()==48000,"Pipe fresh clock");auto audio=Mailbox::create();const auto name=audio->name();
    require(broker.start(*audio,{48000,8,1000,200}).phase==ds::Phase::running,"Pipe starts stream");
    if(mode==L"die-running")ExitProcess(0);
    pump(*audio);const auto stopped=broker.stop();
    require(stopped.phase==ds::Phase::ready && stopped.io_retired && !stopped.device_released && stopped.stats.output_completions>0,"Pipe stops audio while retaining device");audio.reset();
    const auto worker_pid=GetProcessId(broker.worker_process_handle());require(worker_pid!=0,"Granted worker query handle");
    require(!TerminateProcess(broker.worker_process_handle(),75) && GetLastError()==ERROR_ACCESS_DENIED,"Client has no worker termination authority");
    const auto detached=broker.detach();require(detached.phase==ds::Phase::ready && !detached.device_released,"Client detach is not physical release");
    require(WaitForSingleObject(broker.worker_process_handle(),0)==WAIT_TIMEOUT,"Worker survives ordinary client detach");rejects([&]{broker.clock();});
    std::string ascii;for(auto c:name){require(c<=127,"ASCII fixture mapping name");ascii+=static_cast<char>(c);}
    std::ofstream out{std::filesystem::path(argv[5])};out<<ascii<<'\n'<<worker_pid<<'\n';require(bool(out),"Record fixture client identity");return 0;
}
struct Harness {
    BrokerListener listener;Handle stop;std::thread thread;std::mutex mutex;std::condition_variable condition;
    bool ready=false;unsigned completed=0;std::exception_ptr failure;BrokerReport final;
    std::vector<std::string> diagnostics;
    std::string worker_hash;
    std::filesystem::path audit=std::filesystem::temp_directory_path()/(listener.name().substr(listener.name().size()-32)+L"-pipe-audit.txt");
    explicit Harness(const std::filesystem::path& worker):worker_hash(Process::executable_sha256(worker)){
        require(!std::filesystem::exists(audit),"Fresh pipe audit");stop.value=CreateEventW(nullptr,TRUE,FALSE,nullptr);require(stop.value!=nullptr,"Controller stop event");
        thread=std::thread([this,worker]{
            try{
                BrokerSpec spec;spec.executable=worker;spec.sha256=Process::executable_sha256(worker);spec.kind=session::Kind::simulated;spec.fixture_mode=L"audit:"+audit.native();
                RetainedBroker owner(spec);require(owner.open(),"Fixture broker owner opened");
                {std::lock_guard<std::mutex> lock(mutex);ready=true;condition.notify_all();}
                while(WaitForSingleObject(stop.value,0)==WAIT_TIMEOUT){
                    std::string diagnostic;const auto result=serve_broker_client(listener,owner,stop.value,&diagnostic);
                    if(!diagnostic.empty()){
                        std::cerr<<"Fixture broker connection: "<<diagnostic<<'\n';
                        std::lock_guard<std::mutex> lock(mutex);diagnostics.push_back(diagnostic);
                    }
                    if(result!=BrokerServeResult::no_client){std::lock_guard<std::mutex> lock(mutex);++completed;condition.notify_all();}
                    if(result==BrokerServeResult::owner_failed || result==BrokerServeResult::stopped)break;
                }
                final=owner.close();
            }catch(...){std::lock_guard<std::mutex> lock(mutex);failure=std::current_exception();condition.notify_all();}
        });
        std::unique_lock<std::mutex> lock(mutex);
        if(!condition.wait_for(lock,std::chrono::seconds(8),[&]{return ready || failure;})){lock.unlock();finish();throw std::runtime_error("Broker fixture ready deadline");}
        if(failure){lock.unlock();finish();std::rethrow_exception(failure);}
    }
    void served(unsigned count){std::unique_lock<std::mutex> lock(mutex);require(condition.wait_for(lock,std::chrono::seconds(8),[&]{return completed>=count || failure;}),"Broker connection retirement deadline");if(failure)std::rethrow_exception(failure);}
    void finish(){SetEvent(stop.value);if(thread.joinable())thread.join();}
    ~Harness(){finish();std::error_code ec;std::filesystem::remove(audit,ec);}
    std::vector<std::string> lines(){std::ifstream in(audit);std::vector<std::string> rows;for(std::string s;std::getline(in,s);)rows.push_back(s);return rows;}
};
static std::vector<std::string> run_client(Harness& h,const std::filesystem::path& self,const std::wstring& mode,unsigned ordinal){
    const auto out=h.audit.native()+L"-"+std::to_wstring(ordinal);require(!std::filesystem::exists(out),"Fresh client report");
    Process process;process.launch(self,Process::executable_sha256(self),{L"--client",h.listener.name(),std::to_wstring(GetCurrentProcessId()),mode,out,std::wstring(h.worker_hash.begin(),h.worker_hash.end())});
    const auto deadline=GetTickCount64()+12000;
    while(!process.observe().process_exited){
        const auto now=GetTickCount64();if(now>=deadline){process.terminate_and_wait(2000);throw std::runtime_error("Pipe child deadline");}
        process.wait_for_exit(DWORD((std::min)(ULONGLONG(5000),deadline-now)));
    }
    std::vector<std::string> lines;{std::ifstream in{std::filesystem::path(out)};for(std::string s;std::getline(in,s);)lines.push_back(s);}
    std::error_code ec;std::filesystem::remove(out,ec);
    if(process.observe().exit_code!=0){std::wcerr<<L"Fixture client mode: "<<mode<<L'\n';for(const auto& line:lines)std::cerr<<line<<'\n';throw std::runtime_error("Pipe client exits successfully");}return lines;
}
static void positive(const std::filesystem::path& worker,const std::filesystem::path& self){
    Harness h(worker);const auto one=run_client(h,self,L"normal",1);h.served(1);const auto two=run_client(h,self,L"normal",2);h.served(2);h.finish();
    require(one.size()==2 && two.size()==2 && one[0]!=two[0] && one[1]==two[1],"Independent client mappings and same worker process");
    require(!h.final.failed && h.final.phase==BrokerPhase::closed && h.final.process.process_exited && h.final.process.job_empty && h.final.device.device_released,"Explicit final owner release");
    const auto rows=h.lines();require(std::count(rows.begin(),rows.end(),"acquire")==1 && std::count(rows.begin(),rows.end(),"release")==1 &&
        std::count(rows.begin(),rows.end(),"rate")==7 && std::count(rows.begin(),rows.end(),"begin")==2 && std::count(rows.begin(),rows.end(),"end")==2,"Real pipe/process lifetime and audio audit");
}
static void negatives(const std::filesystem::path& worker,const std::filesystem::path& self){
    {Harness h(worker);run_client(h,self,L"delayed-detach",1);h.served(1);run_client(h,self,L"normal",2);h.served(2);h.finish();require(!h.final.failed,"Delayed detach reply/ack retires connection before replacement");}
    for(const auto mode:{L"bad-magic",L"oversized",L"bad-proof",L"wrong-kind",L"wrong-worker"}){
        Harness h(worker);run_client(h,self,mode,1);h.served(1);h.finish();const auto rows=h.lines();
        require(!h.final.failed && std::count(rows.begin(),rows.end(),"rate")==1 && std::count(rows.begin(),rows.end(),"begin")==0,"Unauthenticated request reaches no client/device operation");
    }
    {Harness h(worker);run_client(h,self,L"wrong-server",1);h.finish();require(!h.final.failed,"Wrong server refused before admission");}
    for(const auto mode:{L"bad-sequence",L"worker-op",L"wrong-mapping",L"disconnect-idle",L"die-running"}){
        Harness h(worker);run_client(h,self,mode,1);h.served(1);h.finish();
        require(h.final.failed && h.final.process.process_exited && h.final.process.job_empty,"Unknown/malformed active client seals and retires owner");
        if(std::wstring(mode)==L"wrong-mapping")require(std::any_of(h.diagnostics.begin(),h.diagnostics.end(),[](const std::string& s){return s.find("Client mapping reference does not match audio channel")!=std::string::npos;}),"Wrong mapping is refused by exact kernel-object comparison");
        if(std::wstring(mode)!=L"die-running"){const auto rows=h.lines();require(std::count(rows.begin(),rows.end(),"begin")==0,"Rejected operation starts no audio");}
    }
    {Harness h(worker);run_client(h,self,L"die-idle",1);h.served(1);run_client(h,self,L"normal",2);h.served(2);h.finish();require(!h.final.failed,"Idle process death releases claim without reacquisition");const auto rows=h.lines();require(std::count(rows.begin(),rows.end(),"acquire")==1,"Idle death reuses same acquired worker");}
}
static void references(){
    auto a=Mailbox::create(),b=Mailbox::create();auto proof=Mailbox::hold_audio_reference(GetCurrentProcess(),a->mapping_handle(),a->name());require(bool(proof),"Exact mapping reference proof");
    rejects([&]{Mailbox::hold_audio_reference(GetCurrentProcess(),b->mapping_handle(),a->name());});
    rejects([&]{Mailbox::hold_audio_reference(GetCurrentProcess(),INVALID_HANDLE_VALUE,a->name());});
}
static void preclosed(const std::filesystem::path& worker){
    BrokerListener listener;Handle stop;stop.value=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    {Handle early;early.value=CreateFileW(listener.name().c_str(),GENERIC_READ|GENERIC_WRITE,0,nullptr,OPEN_EXISTING,0,nullptr);require(early.value!=INVALID_HANDLE_VALUE,"Early pipe connection");}
    BrokerSpec spec;spec.executable=worker;spec.sha256=Process::executable_sha256(worker);spec.kind=session::Kind::simulated;
    RetainedBroker owner(spec);require(owner.open(),"Owner for early disconnect");
    require(serve_broker_client(listener,owner,stop.value)==BrokerServeResult::rejected && !owner.report().failed,"Disconnect before accept is refused without ending owner");
    require(owner.close().phase==BrokerPhase::closed,"Early disconnect final cleanup");
}
int wmain(int argc,wchar_t** argv){
    try{
        if(argc>1 && std::wstring(argv[1])==L"--client")return client(argc,argv);
        require(argc==2,"Device fixture required");const auto self=std::filesystem::absolute(argv[0]);
        references();preclosed(argv[1]);positive(argv[1],self);negatives(argv[1],self);
        std::cout<<"Broker pipe/process authentication, direct audio, malformed requests and death tests passed (simulation only)\n";return 0;
    }catch(const std::exception& e){
        if(argc==7 && std::wstring(argv[1])==L"--client"){std::ofstream out{std::filesystem::path(argv[5])};out<<"ERROR: "<<e.what()<<'\n';}
        std::cerr<<e.what()<<'\n';return 1;
    }
}
