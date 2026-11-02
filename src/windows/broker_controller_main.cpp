#include "asio/driver_configuration.hpp"
#include "windows/broker_pipe.hpp"
#include "windows/broker_record.hpp"
#include "windows/startup_journal.hpp"
#include <sddl.h>
#include <algorithm>
#include <atomic>
#include <charconv>
#include <iostream>
#include <map>
#include <sstream>
#include <thread>

namespace {
using namespace sl3;using namespace sl3::worker;
#ifdef SL3_BROKER_CONTROLLER_SIMULATED
constexpr auto kind=session::Kind::simulated;constexpr const char* kind_name="simulated";
#else
constexpr auto kind=session::Kind::native;constexpr const char* kind_name="native";
#endif
void require(bool good,const char* text){if(!good)throw std::runtime_error(text);}
struct Handle {HANDLE value=INVALID_HANDLE_VALUE;~Handle(){if(value && value!=INVALID_HANDLE_VALUE)CloseHandle(value);}};
struct Security {
    PSECURITY_DESCRIPTOR descriptor=nullptr;SECURITY_ATTRIBUTES attributes{sizeof(attributes),nullptr,FALSE};
    Security(){
        Handle token;require(OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token.value)!=FALSE,"Read controller owner token");
        DWORD bytes=0;GetTokenInformation(token.value,TokenUser,nullptr,0,&bytes);std::vector<std::uint8_t> storage(bytes);
        require(bytes && GetTokenInformation(token.value,TokenUser,storage.data(),bytes,&bytes),"Read controller owner SID");
        LPWSTR sid=nullptr;require(ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(storage.data())->User.Sid,&sid)!=FALSE,"Format controller owner SID");
        const auto dacl=L"D:P(A;OICI;GA;;;"+std::wstring(sid)+L")";LocalFree(sid);
        require(ConvertStringSecurityDescriptorToSecurityDescriptorW(dacl.c_str(),SDDL_REVISION_1,&descriptor,nullptr)!=FALSE,"Create owner-only controller DACL");attributes.lpSecurityDescriptor=descriptor;
    }
    ~Security(){if(descriptor)LocalFree(descriptor);}
};
void local(const std::filesystem::path& p){const auto drive=p.root_name().native();const auto& name=p.native();
    require(p.is_absolute() && drive.size()==2 && drive[1]==L':' && name.find(L'\0')==std::wstring::npos &&
        name.find(L':',2)==std::wstring::npos && name.find_first_of(L"\r\n\"")==std::wstring::npos && GetDriveTypeW(p.root_path().c_str())==DRIVE_FIXED,"Controller requires absolute local fixed-drive paths");}
void final_local(HANDLE file){std::vector<wchar_t> b(32768);const auto n=GetFinalPathNameByHandleW(file,b.data(),DWORD(b.size()),FILE_NAME_NORMALIZED|VOLUME_NAME_DOS);
    require(n>4 && n<b.size() && std::wstring(b.data(),4)==L"\\\\?\\","Resolve controller file path");local(std::filesystem::path(std::wstring(b.data()+4,n-4)));}
struct ReadFileLease {
    Handle file;LONGLONG bytes=0;
    explicit ReadFileLease(const std::filesystem::path& p,DWORD maximum=65536){local(p);file.value=CreateFileW(p.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        require(file.value!=INVALID_HANDLE_VALUE,"Pin controller file");LARGE_INTEGER size{};require(GetFileType(file.value)==FILE_TYPE_DISK && GetFileSizeEx(file.value,&size) && size.QuadPart>0 && size.QuadPart<=maximum,"Controller file size/type");bytes=size.QuadPart;final_local(file.value);}
    std::string text(){std::string s(std::size_t(bytes),'\0');DWORD n=0;require(ReadFile(file.value,s.data(),DWORD(s.size()),&n,nullptr) && n==s.size(),"Read pinned controller bytes");return s;}
};
std::shared_ptr<ReadFileLease> write_new(const std::filesystem::path& p,const std::string& text){
    local(p);const std::filesystem::path pending(p.native()+L".pending");
    require(pending.parent_path()==p.parent_path(),"Publication remains inside its owned directory");
    {Security security;Handle file;file.value=CreateFileW(pending.c_str(),GENERIC_WRITE,FILE_SHARE_READ,&security.attributes,CREATE_NEW,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_WRITE_THROUGH,nullptr);
        require(file.value!=INVALID_HANDLE_VALUE,"Create new controller evidence file");DWORD n=0;
        require(text.size()<=65536 && WriteFile(file.value,text.data(),DWORD(text.size()),&n,nullptr) && n==text.size() && FlushFileBuffers(file.value),"Write complete controller evidence");}
    require(MoveFileExW(pending.c_str(),p.c_str(),MOVEFILE_WRITE_THROUGH)!=FALSE,"Publish new controller evidence without replacement");
    auto pin=std::make_shared<ReadFileLease>(p);require(pin->text()==text,"Reopen exact published bytes");return pin;
}
std::string json_string(const std::string& s){std::string r="\"";constexpr char hex[]="0123456789abcdef";for(unsigned char c:s){
    if(c=='"' || c=='\\'){r+='\\';r+=char(c);}else if(c<32){r+="\\u00";r+=hex[c>>4];r+=hex[c&15];}else r+=char(c);}return r+'"';}
std::filesystem::path self(){std::vector<wchar_t> name(32768);const auto n=GetModuleFileNameW(nullptr,name.data(),DWORD(name.size()));require(n && n<name.size(),"Read controller image path");return std::filesystem::path(std::wstring(name.data(),n));}
std::wstring stop_name(const std::wstring& endpoint){require(endpoint.size()>=32,"Invalid bound controller endpoint");return L"Local\\SL3BrokerStop-"+endpoint.substr(endpoint.size()-32);}
bool helper_loaded(){return GetModuleHandleW(L"UsbDkHelper.dll") || GetModuleHandleW(L"UsbDkHelper.dll10");}
DWORD limit(const std::wstring& s){require(!s.empty() && s[0]!=L'0',"Noncanonical controller lifetime");std::string ascii;for(auto c:s){require(c>=L'0' && c<=L'9',"Invalid controller lifetime");ascii+=char(c);}DWORD n=0;
    const auto parsed=std::from_chars(ascii.data(),ascii.data()+ascii.size(),n);require(parsed.ec==std::errc{} && parsed.ptr==ascii.data()+ascii.size() && n>=1000 && n<=43200000,"Controller lifetime must be 1000..43200000 ms");return n;}
struct Timer {
    HANDLE stop;std::atomic<bool> expired{false};std::thread thread;
    Timer(HANDLE event,DWORD duration):stop(event),thread([this,duration]{if(WaitForSingleObject(stop,duration)==WAIT_TIMEOUT){expired=true;SetEvent(stop);}}){}
    ~Timer(){SetEvent(stop);thread.join();}
};
struct RunEvidence {bool acquired=false,published=false;std::string error,reason="failure";BrokerReport final;};
std::string result(const RunEvidence& e,bool expired){
    const auto& r=e.final;const bool retired=e.acquired && r.snapshot_valid && r.device.io_retired;
    const bool released=e.acquired && r.snapshot_valid && r.device.device_released;
    const bool successful=e.published && e.error.empty() && !r.failed && retired && released && r.process.process_exited && r.process.job_empty && !r.termination_requested;
    std::ostringstream o;o<<std::boolalpha<<"{\"schema\":\"sl3.broker-controller-result.v1\",\"kind\":"<<json_string(kind_name)<<",\"successful\":"<<successful
        <<",\"acquireAttempted\":"<<r.acquire_attempted<<",\"acquired\":"<<e.acquired<<",\"published\":"<<e.published<<",\"reason\":"<<json_string(e.reason)<<",\"error\":"<<json_string(e.error)
        <<",\"lifetimeExpired\":"<<expired<<",\"failed\":"<<r.failed<<",\"snapshotValid\":"<<r.snapshot_valid<<",\"ioRetiredVerified\":"<<retired<<",\"deviceReleasedVerified\":"<<released
        <<",\"processStarted\":"<<r.process.started<<",\"processExited\":"<<r.process.process_exited<<",\"jobEmpty\":"<<r.process.job_empty<<",\"terminationRequested\":"<<r.termination_requested
        <<",\"processExitCodeKnown\":"<<r.process.exit_code_known<<",\"processExitCode\":"<<r.process.exit_code
        <<",\"lastDevicePhase\":"<<unsigned(r.device.phase)<<",\"lastDeviceFailure\":"<<unsigned(r.device.failure)<<",\"lastStreamFault\":"<<unsigned(r.device.stream_fault)
        <<",\"lastNativeError\":"<<r.device.native_error<<",\"lastObservedRateHz\":"<<r.device.rate_hz<<",\"lastDiagnostic\":"<<json_string(r.device.diagnostic)
        <<",\"nativeDeviceAcquired\":"<<(kind==session::Kind::native && e.acquired)<<",\"helperLoadedInController\":"<<helper_loaded()<<",\"usbReadyForNextAcquire\":false,\"rateRestorationVerified\":false}\n";return o.str();
}
int run(const std::filesystem::path& input,const std::filesystem::path& output,DWORD duration){
    auto config=asio::load_driver_configuration(input);require(!config.broker,"Controller input must be reviewed private-worker format");
    ReadFileLease source(input);const auto source_text=source.text();const auto image=self();auto image_pin=std::make_shared<ReadFileLease>(image,256*1024*1024);const auto image_hash=Process::executable_sha256(image);
    BrokerListener listener; // Requires an ordinary user before files/device access.
    local(output);require(!std::filesystem::exists(output),"Controller output directory must be new");
    Security security;require(CreateDirectoryW(output.c_str(),&security.attributes)!=FALSE,"Create new owner-only controller directory");
    Handle directory;directory.value=CreateFileW(output.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS,nullptr);require(directory.value!=INVALID_HANDLE_VALUE,"Retain controller directory");final_local(directory.value);
    std::vector<std::shared_ptr<ReadFileLease>> published;
    diagnostic::StartupJournal journal(output/L"controller-startup.tsv");journal.mark("controller_intent");
    std::ostringstream intent;intent<<"{\"schema\":\"sl3.broker-controller-intent.v1\",\"kind\":"<<json_string(kind_name)<<",\"workerSha256\":"<<json_string(config.worker.sha256)
        <<",\"brokerSha256\":"<<json_string(image_hash)<<",\"limitMs\":"<<duration<<",\"controllerGeneratesAudio\":false,\"rateWritesAllowed\":false,\"automaticRestart\":false}\n";
    published.push_back(write_new(output/L"intent.json",intent.str()));
    Handle stop;stop.value=CreateEventW(&security.attributes,TRUE,FALSE,stop_name(listener.name()).c_str());require(stop.value && GetLastError()!=ERROR_ALREADY_EXISTS,"Create unique owner-only stop event");
    Timer timer(stop.value,duration);BrokerSpec spec;spec.executable=config.worker.executable;spec.sha256=config.worker.sha256;spec.helper=config.worker.helper;spec.kind=kind;
    if constexpr(kind==session::Kind::native)spec.startup_journal=output/L"worker-startup.tsv";else spec.fixture_mode=L"audit:"+(output/L"worker-audit.txt").native();
    RetainedBroker owner(spec);RunEvidence evidence;
    try{
        journal.mark("owner_open_begin");require(owner.open(),"Broker owner acquisition/handshake failed");evidence.acquired=true;journal.mark("owner_open_ready");
        require(owner.report().snapshot_valid && owner.report().device.rate_hz==config.latency.rate_hz,"Observed clock differs from reviewed timing profile");
        require(WaitForSingleObject(stop.value,0)==WAIT_TIMEOUT,"Controller stopped before publication");
        const auto record=output/L"broker-session.txt";published.push_back(write_new(record,broker_record_text(listener.name(),owner.worker_sha256())));journal.mark("session_record_published");
        auto native_config=source_text;const std::string header="SL3-ASIO-CONFIG-1";require(native_config.compare(0,header.size(),header)==0,"Controller input header changed");native_config.replace(0,header.size(),"SL3-ASIO-BROKER-CONFIG-1");
        native_config+="broker="+image.u8string()+"\nbroker_sha256="+image_hash+"\nsession_record="+record.u8string()+"\nsession_record_sha256="+Process::executable_sha256(record)+"\n";
        const auto consumer=output/L"sl3-asio.conf";published.push_back(write_new(consumer,native_config));
        auto binding=asio::load_driver_configuration(consumer);require(binding.broker && GetProcessId(binding.broker->server->handle())==GetCurrentProcessId(),"Verify published controller binding");journal.mark("consumer_config_published");
        const auto ready_state=owner.report();
        require(!ready_state.failed && ready_state.phase==BrokerPhase::idle && ready_state.snapshot_valid && ready_state.device.io_retired &&
            !ready_state.device.device_released && ready_state.process.started && ready_state.process.job_assigned && !ready_state.process.process_exited,
            "Owner became unavailable during publication");
        require(WaitForSingleObject(stop.value,0)==WAIT_TIMEOUT,"Controller stopped during publication");
        std::ostringstream ready;ready<<"{\"schema\":\"sl3.broker-controller-ready.v1\",\"kind\":"<<json_string(kind_name)<<",\"controllerPid\":"<<GetCurrentProcessId()<<",\"workerPid\":"<<GetProcessId(owner.worker_process_handle())
            <<",\"configFile\":"<<json_string(consumer.u8string())<<",\"configSha256\":"<<json_string(Process::executable_sha256(consumer))<<",\"recordSha256\":"<<json_string(Process::executable_sha256(record))
            <<",\"brokerSha256\":"<<json_string(image_hash)<<",\"workerSha256\":"<<json_string(config.worker.sha256)<<",\"rateHz\":"<<ready_state.device.rate_hz<<",\"limitMs\":"<<duration<<",\"readyIsSnapshot\":true}\n";
        published.push_back(write_new(output/L"ready.json",ready.str()));evidence.published=true;journal.mark("serve_begin");
        while(WaitForSingleObject(stop.value,0)==WAIT_TIMEOUT){
            const auto served=serve_broker_client(listener,owner,stop.value);
            if(served==BrokerServeResult::owner_failed || owner.report().failed){evidence.reason="owner_failure";break;}
            if(served==BrokerServeResult::stopped)break;
        }
        if(evidence.reason!="owner_failure")evidence.reason=timer.expired?"lifetime_limit":"stop_requested";
    }catch(const std::exception& e){evidence.error=e.what();journal.mark("controller_failure");}
    journal.mark("owner_close_begin");evidence.final=owner.close();journal.mark("owner_close_returned");
    const auto text=result(evidence,timer.expired);published.push_back(write_new(output/L"result.json",text));std::cout<<text;
    return evidence.published && evidence.error.empty() && !evidence.final.failed && evidence.final.snapshot_valid && evidence.final.device.io_retired &&
        evidence.final.device.device_released && evidence.final.process.process_exited && evidence.final.process.job_empty && !evidence.final.termination_requested?0:1;
}
int stop(const std::filesystem::path& file){
    const auto config=asio::load_driver_configuration(file);require(config.broker.has_value(),"Stop requires a live reviewed broker configuration");
    Handle event;event.value=OpenEventW(EVENT_MODIFY_STATE,FALSE,stop_name(config.broker->endpoint).c_str());require(event.value && SetEvent(event.value),"Request known controller stop");
    std::cout<<"{\"schema\":\"sl3.broker-controller-stop.v1\",\"stopRequested\":true,\"deviceReleasedVerified\":false}\n";return 0;
}
}
int wmain(int argc,wchar_t** argv){
    try{
        if(argc==1 || (argc==2 && std::wstring(argv[1])==L"--plan")){
            std::cout<<"{\"schema\":\"sl3.broker-controller-plan.v1\",\"kind\":"<<json_string(kind_name)<<",\"planOnly\":true,\"helperLoaded\":false,\"deviceAccess\":false,\"filesWritten\":false,\"explicitLifetimeRequired\":true,\"automaticRestart\":false}\n";return 0;
        }
        require(argc>=2,"Controller mode required");std::map<std::wstring,std::wstring> args;
        for(int n=2;n<argc;n+=2){require(n+1<argc && args.emplace(argv[n],argv[n+1]).second,"Duplicate/incomplete controller option");}
        if(std::wstring(argv[1])==L"--run"){require(args.size()==3 && args.count(L"--input") && args.count(L"--output") && args.count(L"--limit-ms"),"Run requires input/output/limit-ms only");return run(std::filesystem::path(args.at(L"--input")),std::filesystem::path(args.at(L"--output")),limit(args.at(L"--limit-ms")));}
        if(std::wstring(argv[1])==L"--stop"){require(args.size()==1 && args.count(L"--config"),"Stop requires config only");return stop(std::filesystem::path(args.at(L"--config")));}
        throw std::invalid_argument("Unknown controller mode");
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
