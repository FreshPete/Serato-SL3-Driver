#include "windows/broker_pipe.hpp"
#include "windows/broker_record.hpp"
#include "windows/diagnostic.hpp"
#include <sddl.h>
#include <array>
#include <map>
#include <sstream>

namespace {
using namespace sl3;using namespace sl3::worker;
#ifdef SL3_BROKER_SCOPE_SIMULATED
constexpr auto kind=session::Kind::simulated;constexpr bool simulated=true;
#else
constexpr auto kind=session::Kind::native;constexpr bool simulated=false;
#endif
constexpr char helper_hash[]="66bbfe6f99b417f97c7a9e97816e24af7dde0e01b8e535c41e91e1c6c19cfeda";
void require(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
struct Handle {HANDLE value=INVALID_HANDLE_VALUE;~Handle(){if(value && value!=INVALID_HANDLE_VALUE)CloseHandle(value);}};
struct Security {
    PSECURITY_DESCRIPTOR value=nullptr;SECURITY_ATTRIBUTES attributes{sizeof(attributes),nullptr,FALSE};
    Security(){
        Handle token;require(OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token.value)!=FALSE,"Read diagnostic token");
        TOKEN_ELEVATION elevation{};DWORD count=0;
        require(GetTokenInformation(token.value,TokenElevation,&elevation,sizeof(elevation),&count) && !elevation.TokenIsElevated,"Ordinary non-elevated diagnostic token required");
        GetTokenInformation(token.value,TokenUser,nullptr,0,&count);require(count && count<=65536,"Bounded diagnostic SID");
        std::vector<std::uint8_t> bytes(count);require(GetTokenInformation(token.value,TokenUser,bytes.data(),count,&count)!=FALSE,"Read diagnostic SID");
        LPWSTR sid=nullptr;require(ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(bytes.data())->User.Sid,&sid)!=FALSE,"Format diagnostic SID");
        const auto sddl=L"D:P(A;OICI;GA;;;"+std::wstring(sid)+L")";LocalFree(sid);
        require(ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl.c_str(),SDDL_REVISION_1,&value,nullptr)!=FALSE,"Owner-only diagnostic DACL");attributes.lpSecurityDescriptor=value;
    }
    ~Security(){if(value)LocalFree(value);}
};
void local(const std::filesystem::path& p){const auto drive=p.root_name().native();const auto& s=p.native();
    require(p.is_absolute() && drive.size()==2 && drive[1]==L':' && s.find(L'\0')==std::wstring::npos &&
            s.find(L':',2)==std::wstring::npos && p.lexically_normal()==p && GetDriveTypeW(p.root_path().c_str())==DRIVE_FIXED,"Canonical absolute fixed-drive path required");}
struct Pin {
    Handle file;
    explicit Pin(const std::filesystem::path& path,bool directory=false){
        local(path);file.value=CreateFileW(path.c_str(),GENERIC_READ,directory?FILE_SHARE_READ|FILE_SHARE_WRITE:FILE_SHARE_READ,nullptr,OPEN_EXISTING,
                                         FILE_FLAG_OPEN_REPARSE_POINT|(directory?FILE_FLAG_BACKUP_SEMANTICS:0),nullptr);
        require(file.value!=INVALID_HANDLE_VALUE,"Pin diagnostic file/directory");BY_HANDLE_FILE_INFORMATION info{};
        require(GetFileInformationByHandle(file.value,&info) && !(info.dwFileAttributes&FILE_ATTRIBUTE_REPARSE_POINT) &&
                bool(info.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY)==directory && (directory || info.nNumberOfLinks==1),"Diagnostic object type/link mismatch");
        std::array<wchar_t,32768> name{};const auto n=GetFinalPathNameByHandleW(file.value,name.data(),DWORD(name.size()),FILE_NAME_NORMALIZED|VOLUME_NAME_DOS);
        require(n>4 && n<name.size() && std::wstring(name.data(),4)==L"\\\\?\\" && std::filesystem::path(std::wstring(name.data()+4,n-4))==path,"Diagnostic final path differs");
    }
    std::string text(){LARGE_INTEGER size{};require(GetFileSizeEx(file.value,&size) && size.QuadPart>0 && size.QuadPart<=65536,"Bounded diagnostic record");
        std::string result(std::size_t(size.QuadPart),'\0');DWORD n=0;require(ReadFile(file.value,result.data(),DWORD(result.size()),&n,nullptr) && n==result.size(),"Read complete diagnostic record");return result;}
};
std::shared_ptr<Pin> write_new(const std::filesystem::path& path,const std::string& text){
    Security security;{Handle file;file.value=CreateFileW(path.c_str(),GENERIC_WRITE,FILE_SHARE_READ,&security.attributes,CREATE_NEW,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_WRITE_THROUGH,nullptr);
        require(file.value!=INVALID_HANDLE_VALUE && text.size()<=65536,"Create new diagnostic record");DWORD n=0;
        require(WriteFile(file.value,text.data(),DWORD(text.size()),&n,nullptr) && n==text.size() && FlushFileBuffers(file.value),"Flush diagnostic record");}
    auto pin=std::make_shared<Pin>(path);require(pin->text()==text,"Published diagnostic bytes differ");return pin;
}
std::filesystem::path self(){std::array<wchar_t,32768> name{};const auto n=GetModuleFileNameW(nullptr,name.data(),DWORD(name.size()));require(n && n<name.size(),"Read diagnostic image");return std::filesystem::path(std::wstring(name.data(),n));}
std::string ascii(const std::wstring& s){std::string out;for(auto c:s){require(c>0 && c<128,"ASCII argument required");out+=char(c);}return out;}
bool hash(const std::string& s){return s.size()==64 && s.find_first_not_of("0123456789abcdef")==std::string::npos;}
bool helper_loaded(){return GetModuleHandleW(L"UsbDkHelper.dll") || GetModuleHandleW(L"UsbDkHelper.dll10");}
std::uint64_t created(HANDLE process){FILETIME start{},end{},kernel{},user{};require(GetProcessTimes(process,&start,&end,&kernel,&user)!=FALSE,"Read client creation identity");return (std::uint64_t(start.dwHighDateTime)<<32)|start.dwLowDateTime;}
std::string client_text(unsigned index,DWORD pid,DWORD worker,unsigned rate,std::uint64_t creation){std::ostringstream s;
    s<<"{\"schema\":\"sl3.broker-scope-client.v1\",\"index\":"<<index<<",\"pid\":"<<pid<<",\"workerPid\":"<<worker
     <<",\"rateHz\":"<<rate<<",\"created100ns\":"<<creation<<",\"simulated\":"<<(simulated?"true":"false")<<",\"detached\":true,\"audioStarted\":false,\"deviceReleased\":false}\n";return s.str();}
int client(const std::map<std::wstring,std::wstring>& args){
    require(args.size()==4 && args.count(L"--record") && args.count(L"--record-sha256") && args.count(L"--worker-sha256") && args.count(L"--index"),"Exact client arguments required");
    Security security;const std::filesystem::path record(args.at(L"--record"));local(record);
    require(record.filename()==L"broker-session.txt","Typed diagnostic record required");const auto ordinal=args.at(L"--index");
    require(ordinal==L"0" || ordinal==L"1" || ordinal==L"2","Client index must be 0..2");const auto index=unsigned(ordinal[0]-L'0');
    auto binding=bind_broker_record(record,ascii(args.at(L"--record-sha256")),self(),Process::executable_sha256(self()),ascii(args.at(L"--worker-sha256")));
    BrokerClient remote(binding.endpoint,binding.server->handle(),kind,ascii(args.at(L"--worker-sha256")));
    const auto rate=remote.clock();require(rate==44100 || rate==48000,"Supported diagnostic clock required");
    const auto worker=GetProcessId(remote.worker_process_handle());require(worker!=0,"Exact worker wait/query reference");
    const auto detached=remote.detach();require(detached.phase==device_session::Phase::ready && detached.io_retired && !detached.device_released &&
        !detached.stats.input_submissions && !detached.stats.output_submissions && WaitForSingleObject(remote.worker_process_handle(),0)==WAIT_TIMEOUT,"Detach must retain an idle worker");
    require(!helper_loaded(),"Client unexpectedly loaded helper");
    auto record_pin=write_new(record.parent_path()/(L"client-"+ordinal+L".json"),client_text(index,GetCurrentProcessId(),worker,rate,created(GetCurrentProcess())));return 0;
}
struct ClientResult {DWORD pid=0;unsigned rate=0;std::uint64_t creation=0;bool retired=false,terminated=false;};
int run(const std::map<std::wstring,std::wstring>& args){
    require(args.count(L"--worker") && args.count(L"--worker-sha256") && args.count(L"--output"),"Worker/hash/output required");
    for(const auto& arg:args)require(arg.first==L"--worker" || arg.first==L"--worker-sha256" || arg.first==L"--output" ||
        (simulated?arg.first==L"--fixture-mode":arg.first==L"--helper"),"Unknown diagnostic run option");
    require(simulated || args.count(L"--helper"),"Native diagnostic requires reviewed helper");
    Security security;const std::filesystem::path worker(args.at(L"--worker")),output(args.at(L"--output"));
    local(worker);local(output);require(!std::filesystem::exists(output) && std::filesystem::is_directory(output.parent_path()),"Fresh output in existing directory required");
    const auto worker_hash=ascii(args.at(L"--worker-sha256"));require(hash(worker_hash),"Lowercase worker SHA256 required");
    auto image_pin=std::make_shared<Pin>(self()),worker_pin=std::make_shared<Pin>(worker);
    require(Process::executable_sha256(worker)==worker_hash,"Worker hash differs");
    std::filesystem::path helper;std::shared_ptr<Pin> helper_pin;
    if(!simulated){helper=args.at(L"--helper");local(helper);helper_pin=std::make_shared<Pin>(helper);
        require(Process::executable_sha256(helper)==helper_hash,"Reviewed helper hash differs");}
    std::vector<std::shared_ptr<Pin>> pins{image_pin,worker_pin};if(helper_pin)pins.push_back(helper_pin);
    std::vector<std::filesystem::path> parents;for(auto p=output.parent_path();!p.empty();){parents.push_back(p);const auto next=p.parent_path();if(next==p)break;p=next;}
    for(auto it=parents.rbegin();it!=parents.rend();++it)pins.push_back(std::make_shared<Pin>(*it,true));
    require(CreateDirectoryW(output.c_str(),&security.attributes)!=FALSE,"Create new owner-only diagnostic directory");
    pins.push_back(std::make_shared<Pin>(output,true));
    auto mark=[&](const std::wstring& name){pins.push_back(write_new(output/(name+L".json"),"{\"phase\":"+diagnostic::quote(ascii(name))+"}\n"));};
    mark(L"phase-prepared");diagnostic::Watchdog watchdog;
    BrokerListener listener;Handle stop;stop.value=CreateEventW(nullptr,TRUE,FALSE,nullptr);require(stop.value!=nullptr,"Create diagnostic stop event");
    BrokerSpec spec;spec.executable=worker;spec.sha256=worker_hash;spec.kind=kind;spec.helper=helper;
    if(simulated)spec.fixture_mode=args.count(L"--fixture-mode")?args.at(L"--fixture-mode"):L"audit:"+(output/L"worker-audit.txt").native();
    else spec.startup_journal=output/L"worker-startup.tsv";
    RetainedBroker owner(spec);bool acquired=false,published=false,successful=false;unsigned attempted=0,completed=0;DWORD worker_pid=0;
    std::array<ClientResult,3> clients{};std::string error;BrokerReport final;
    try{
        mark(L"phase-acquire");require(owner.open(),"Broker acquisition failed");acquired=true;
        const auto initial=owner.report();const auto initial_rate=initial.device.rate_hz;
        require(initial.snapshot_valid && (initial_rate==44100 || initial_rate==48000),"Supported acquired clock required");
        worker_pid=GetProcessId(owner.worker_process_handle());require(worker_pid!=0,"Observed worker identity required");
        const auto record=output/L"broker-session.txt";pins.push_back(write_new(record,broker_record_text(listener.name(),worker_hash)));published=true;
        const auto record_hash=Process::executable_sha256(record),image_hash=Process::executable_sha256(self());
        for(unsigned index=0;index<3;++index){
            const auto ordinal=std::to_wstring(index);mark(L"phase-client-"+ordinal);++attempted;
            Process child;auto& row=clients[index];
            try{
                child.launch(self(),image_hash,{L"--client",L"--record",record.native(),L"--record-sha256",std::wstring(record_hash.begin(),record_hash.end()),
                    L"--worker-sha256",std::wstring(worker_hash.begin(),worker_hash.end()),L"--index",ordinal});
                row.pid=GetProcessId(child.process_handle());row.creation=created(child.process_handle());const auto deadline=GetTickCount64()+15000;bool detached=false;
                while(!detached){
                    require(GetTickCount64()<deadline && !child.observe().process_exited,"Client exited or connection deadline expired");
                    std::string why;const auto served=serve_broker_client(listener,owner,stop.value,&why,BrokerAccess::metadata_only);
                    require(served==BrokerServeResult::no_client || served==BrokerServeResult::detached,why.empty()?"Read-only broker connection failed":why.c_str());
                    detached=served==BrokerServeResult::detached;
                }
                while(true){const auto state=child.observe();if(state.process_exited && state.job_empty){row.retired=true;require(state.exit_code_known && state.exit_code==0,"Diagnostic client failed");break;}
                    require(GetTickCount64()<deadline,"Client retirement deadline");Sleep(1);}
                const auto state=owner.report();row.rate=state.device.rate_hz;
                require(!state.failed && state.phase==BrokerPhase::idle && !state.client_attached && state.snapshot_valid &&
                    row.rate==initial_rate && GetProcessId(owner.worker_process_handle())==worker_pid &&
                    !state.device.stats.input_submissions && !state.device.stats.output_submissions,"Client must preserve one idle physical lease");
                auto evidence=std::make_shared<Pin>(output/(L"client-"+ordinal+L".json"));
                require(evidence->text()==client_text(index,row.pid,worker_pid,row.rate,row.creation),"Exact client result differs");pins.push_back(evidence);++completed;
            }catch(...){
                const auto state=child.observe();if(state.started && (!state.process_exited || !state.job_empty)){
                    const auto stopped=child.terminate_and_wait(2000);row.terminated=stopped.termination_requested;row.retired=stopped.state.process_exited && stopped.state.job_empty;}
                throw;
            }
        }
        successful=true;
    }catch(const std::exception& e){error=e.what();}
    mark(L"phase-close");final=owner.close();
    const bool released=acquired && final.snapshot_valid && final.device.device_released;
    successful=successful && released && !final.failed && final.device.io_retired && final.phase==BrokerPhase::closed &&
        final.process.process_exited && final.process.job_empty && !final.termination_requested && !helper_loaded();
    std::ostringstream report;report<<"{\"schema\":\"sl3.broker-scope-probe.v1\",\"simulated\":"<<(simulated?"true":"false")
        <<",\"successful\":"<<(successful?"true":"false")<<",\"acquireAttempted\":"<<(final.acquire_attempted?"true":"false")
        <<",\"acquired\":"<<(acquired?"true":"false")<<",\"nativeDeviceAcquired\":"<<(!simulated && acquired?"true":"false")
        <<",\"recordPublished\":"<<(published?"true":"false")<<",\"workerPid\":"<<worker_pid<<",\"workerSha256\":"<<diagnostic::quote(worker_hash)
        <<",\"clientAttempts\":"<<attempted<<",\"completedClients\":"<<completed<<",\"clients\":[";
    for(unsigned i=0;i<attempted;++i){if(i)report<<',';report<<"{\"index\":"<<i<<",\"pid\":"<<clients[i].pid<<",\"created100ns\":"<<clients[i].creation<<",\"rateHz\":"<<clients[i].rate
        <<",\"retired\":"<<(clients[i].retired?"true":"false")<<",\"terminationRequested\":"<<(clients[i].terminated?"true":"false")<<'}';}
    report<<"],\"deviceReleasedVerified\":"<<(released?"true":"false")<<",\"ioRetiredVerified\":"<<(acquired && final.snapshot_valid && final.device.io_retired?"true":"false")
        <<",\"workerProcessExited\":"<<(final.process.process_exited?"true":"false")<<",\"workerJobEmpty\":"<<(final.process.job_empty?"true":"false")
        <<",\"workerTerminationRequested\":"<<(final.termination_requested?"true":"false")<<",\"error\":"<<diagnostic::quote(error)
        <<",\"audioAllowed\":false,\"audioStarts\":0,\"rateSetters\":0,\"timingProfileReadOrWritten\":false,\"asioConfigurationPublished\":false"
        <<",\"helperLoadedInProbe\":"<<(helper_loaded()?"true":"false")<<",\"kernelQuiescenceVerified\":false,\"usbReadyForNextAcquire\":false,\"physicalAudioVerified\":false,\"seratoAdmissionVerified\":false}\n";
    pins.push_back(write_new(output/L"result.json",report.str()));std::cout<<report.str();return successful?0:1;
}
}
int wmain(int argc,wchar_t** argv){
    try{
        if(argc==1 || (argc==2 && std::wstring(argv[1])==L"--plan")){
            std::cout<<"{\"planOnly\":true,\"simulated\":"<<(simulated?"true":"false")<<",\"deviceAccess\":false,\"requiresTimingProfile\":false,\"clients\":3,\"acquisitions\":1,\"audioAllowed\":false,\"watchdogMs\":20000}\n";return 0;}
        const std::wstring action=argv[1];require(action==L"--run" || action==L"--client","Explicit run/client mode required");
        std::map<std::wstring,std::wstring> args;for(int i=2;i<argc;i+=2){require(i+1<argc,"Missing diagnostic argument");require(args.emplace(argv[i],argv[i+1]).second,"Duplicate diagnostic argument");}
        return action==L"--client"?client(args):run(args);
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}
}
