#include "asio/driver_configuration.hpp"
#include "windows/broker_pipe.hpp"
#include "windows/broker_record.hpp"
#include "windows/startup_journal.hpp"
#include <sddl.h>
#include <aclapi.h>
#include <bcrypt.h>
#include <array>
#include <algorithm>
#include <atomic>
#include <charconv>
#include <iostream>
#include <map>
#include <sstream>
#include <thread>

namespace {
using namespace sl3;using namespace sl3::worker;
#ifdef SL3_ASIO_UNMEASURED_DIAGNOSTIC
constexpr auto timing_policy=asio::TimingPolicy::unmeasured_diagnostic;
#else
constexpr auto timing_policy=asio::TimingPolicy::reviewed;
#endif
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
template<class T> T process_number(const std::wstring& text){
    require(!text.empty() && text.size()<=20 && text.front()!=L'0',"Invalid application process identity");
    std::string ascii;
    for(const auto digit:text){
        require(digit>=L'0' && digit<=L'9',"Invalid application process identity");ascii+=char(digit);
    }
    T value=0;const auto end=ascii.data()+ascii.size();
    const auto parsed=std::from_chars(ascii.data(),end,value);
    require(parsed.ec==std::errc{} && parsed.ptr==end,"Invalid application process identity");
    return value;
}
void bind_application(Handle& application,const std::wstring& identity){
    const auto separator=identity.find(L':');
    require(separator!=std::wstring::npos,"Application identity requires PID and creation FILETIME");
    const auto pid=process_number<DWORD>(identity.substr(0,separator));
    const auto expected=process_number<std::uint64_t>(identity.substr(separator+1));
    require(pid!=GetCurrentProcessId(),"Application must be separate from the controller");
    application.value=OpenProcess(SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid);
    require(application.value && WaitForSingleObject(application.value,0)==WAIT_TIMEOUT,"Bound application process is unavailable");
    FILETIME start{},end{},kernel{},user{};
    require(GetProcessTimes(application.value,&start,&end,&kernel,&user)!=FALSE,"Read application creation time");
    require(((std::uint64_t(start.dwHighDateTime)<<32)|start.dwLowDateTime)==expected &&
            same_broker_user(application.value),"Bound application creation identity or user differs");
}
struct Timer {
    HANDLE stop;std::atomic<bool> expired{false};std::thread thread;
    Timer(HANDLE event,DWORD duration,HANDLE application):stop(event),thread([this,duration,application]{
        const HANDLE waits[]={stop,application};
        const auto wait=WaitForMultipleObjects(application?2:1,waits,FALSE,duration);
        if(wait==WAIT_TIMEOUT)expired=true;
        if(wait!=WAIT_OBJECT_0)SetEvent(stop);
    }){}
    ~Timer(){SetEvent(stop);thread.join();}
};
struct RunEvidence {
    bool acquired=false,published=false,application_exited=false;
    std::string error,reason="failure",connection_diagnostic;
    BrokerReport final;
    std::array<BrokerClientObservation,16> clients{};
    std::size_t client_count=0;
    bool client_observations_truncated=false;
};
std::string result(const RunEvidence& e,bool expired){
    const auto& r=e.final;const bool retired=e.acquired && r.snapshot_valid && r.device.io_retired;
    const bool released=e.acquired && r.snapshot_valid && r.device.device_released;
    const bool successful=e.published && e.error.empty() && !r.failed && retired && released && r.process.process_exited && r.process.job_empty && !r.termination_requested;
    std::ostringstream o;o<<std::boolalpha<<"{\"schema\":\"sl3.broker-controller-result.v1\",\"kind\":"<<json_string(kind_name)<<",\"successful\":"<<successful
        <<",\"acquireAttempted\":"<<r.acquire_attempted<<",\"acquired\":"<<e.acquired<<",\"published\":"<<e.published<<",\"reason\":"<<json_string(e.reason)<<",\"error\":"<<json_string(e.error)
        <<",\"lifetimeExpired\":"<<expired<<",\"applicationExitObserved\":"<<e.application_exited
        <<",\"failed\":"<<r.failed<<",\"snapshotValid\":"<<r.snapshot_valid<<",\"ioRetiredVerified\":"<<retired<<",\"deviceReleasedVerified\":"<<released
        <<",\"processStarted\":"<<r.process.started<<",\"processExited\":"<<r.process.process_exited<<",\"jobEmpty\":"<<r.process.job_empty<<",\"terminationRequested\":"<<r.termination_requested
        <<",\"processExitCodeKnown\":"<<r.process.exit_code_known<<",\"processExitCode\":"<<r.process.exit_code
        <<",\"lastDevicePhase\":"<<unsigned(r.device.phase)<<",\"lastDeviceFailure\":"<<unsigned(r.device.failure)<<",\"lastStreamFault\":"<<unsigned(r.device.stream_fault)
        <<",\"lastNativeError\":"<<r.device.native_error<<",\"lastObservedRateHz\":"<<r.device.rate_hz<<",\"lastDiagnostic\":"<<json_string(r.device.diagnostic)
        <<",\"ownerFailureCode\":"<<json_string(broker_failure_name(r.first_failure))<<",\"ownerFailurePhase\":"<<unsigned(r.first_failure_phase)
        <<",\"connectionDiagnostic\":"<<json_string(e.connection_diagnostic)
        <<",\"clientObservationsTruncated\":"<<e.client_observations_truncated<<",\"clientObservations\":[";
    for(std::size_t i=0;i<e.client_count;++i){
        const auto& client=e.clients[i];
        if(i)o<<',';
        o<<"{\"pid\":"<<client.pid<<",\"creationFileTimeUtc\":\""<<client.creation_filetime
            <<"\",\"admissionReplySent\":"<<client.admission_reply_sent
            <<",\"streamStartReplies\":"<<client.stream_start_replies
            <<",\"detachAcknowledged\":"<<client.detach_acknowledged<<'}';
    }
    o<<']'
        <<",\"nativeDeviceAcquired\":"<<(kind==session::Kind::native && e.acquired)<<",\"helperLoadedInController\":"<<helper_loaded()<<",\"usbReadyForNextAcquire\":false,\"rateRestorationVerified\":false}\n";return o.str();
}
int run(const std::filesystem::path& input,const std::filesystem::path& output,DWORD duration,bool keepalive,HANDLE application){
    require(!keepalive || kind==session::Kind::native,"Playback keepalive requires the native controller");
    if constexpr(timing_policy==asio::TimingPolicy::unmeasured_diagnostic)
        require(duration<=600000,"Unmeasured diagnostic lifetime must not exceed ten minutes");
    auto config=asio::load_driver_configuration(input,timing_policy);require(!config.broker,"Controller input must be private-worker format");
    require(keepalive==!config.keepalive_timing_sha256.empty(),"Controller playback mode differs from reviewed timing profile");
    ReadFileLease source(input);const auto source_text=source.text();const auto image=self();auto image_pin=std::make_shared<ReadFileLease>(image,256*1024*1024);const auto image_hash=Process::executable_sha256(image);
    BrokerListener listener; // Requires an ordinary user before files/device access.
    local(output);require(!std::filesystem::exists(output),"Controller output directory must be new");
    Security security;require(CreateDirectoryW(output.c_str(),&security.attributes)!=FALSE,"Create new owner-only controller directory");
    Handle directory;directory.value=CreateFileW(output.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS,nullptr);require(directory.value!=INVALID_HANDLE_VALUE,"Retain controller directory");final_local(directory.value);
    std::vector<std::shared_ptr<ReadFileLease>> published;
    diagnostic::StartupJournal journal(output/L"controller-startup.tsv");journal.mark("controller_intent");
    std::ostringstream intent;intent<<"{\"schema\":\"sl3.broker-controller-intent.v1\",\"kind\":"<<json_string(kind_name)<<",\"workerSha256\":"<<json_string(config.worker.sha256)
        <<",\"brokerSha256\":"<<json_string(image_hash)<<",\"limitMs\":"<<duration<<",\"controllerGeneratesAudio\":false,\"rateWritesAllowed\":false,\"automaticRestart\":false"
        <<",\"playbackKeepalive\":"<<(keepalive?"true":"false")<<",\"applicationBound\":"<<(application?"true":"false")<<"}\n";
    published.push_back(write_new(output/L"intent.json",intent.str()));
    Handle stop;stop.value=CreateEventW(&security.attributes,TRUE,FALSE,stop_name(listener.name()).c_str());require(stop.value && GetLastError()!=ERROR_ALREADY_EXISTS,"Create unique owner-only stop event");
    Timer timer(stop.value,duration,application);BrokerSpec spec;spec.executable=config.worker.executable;spec.sha256=config.worker.sha256;spec.helper=config.worker.helper;spec.kind=kind;
    spec.playback_keepalive=keepalive;
    if constexpr(kind==session::Kind::native)spec.startup_journal=output/L"worker-startup.tsv";
    else if constexpr(timing_policy==asio::TimingPolicy::unmeasured_diagnostic){
        const auto clock=output/L"simulated-clock.txt";
        published.push_back(write_new(clock,"44100\n"));
        spec.fixture_mode=L"clock:"+clock.native();
    }else spec.fixture_mode=L"audit:"+(output/L"worker-audit.txt").native();
    RetainedBroker owner(spec);RunEvidence evidence;
    try{
        journal.mark("owner_open_begin");
        if(!owner.open(stop.value,application))
            throw std::runtime_error(owner.report().first_failure==BrokerFailure::acquisition_cancelled?
                "Broker stopped before device acquisition":"Broker owner acquisition/handshake failed");
        evidence.acquired=true;journal.mark("owner_open_ready");
        require(owner.report().snapshot_valid && owner.report().device.rate_hz==config.latency.rate_hz,"Observed clock differs from reviewed timing profile");
        require(WaitForSingleObject(stop.value,0)==WAIT_TIMEOUT &&
                (!application || WaitForSingleObject(application,0)==WAIT_TIMEOUT),"Controller stopped before publication");
        const auto record=output/L"broker-session.txt";published.push_back(write_new(record,broker_record_text(listener.name(),owner.worker_sha256(),config.keepalive_timing_sha256)));journal.mark("session_record_published");
        auto native_config=source_text;const std::string header="SL3-ASIO-CONFIG-1";require(native_config.compare(0,header.size(),header)==0,"Controller input header changed");native_config.replace(0,header.size(),"SL3-ASIO-BROKER-CONFIG-1");
        native_config+="broker="+image.u8string()+"\nbroker_sha256="+image_hash+"\nsession_record="+record.u8string()+"\nsession_record_sha256="+Process::executable_sha256(record)+"\n";
        const auto consumer=output/L"sl3-asio.conf";published.push_back(write_new(consumer,native_config));
        auto binding=asio::load_driver_configuration(consumer,timing_policy);require(binding.broker && GetProcessId(binding.broker->server->handle())==GetCurrentProcessId(),"Verify published controller binding");journal.mark("consumer_config_published");
        const auto ready_state=owner.report();
        require(!ready_state.failed && ready_state.phase==BrokerPhase::idle && ready_state.snapshot_valid && ready_state.device.io_retired &&
            !ready_state.device.device_released && ready_state.process.started && ready_state.process.job_assigned && !ready_state.process.process_exited,
            "Owner became unavailable during publication");
        require(WaitForSingleObject(stop.value,0)==WAIT_TIMEOUT &&
                (!application || WaitForSingleObject(application,0)==WAIT_TIMEOUT),"Controller stopped during publication");
        std::ostringstream ready;ready<<"{\"schema\":\"sl3.broker-controller-ready.v1\",\"kind\":"<<json_string(kind_name)<<",\"controllerPid\":"<<GetCurrentProcessId()<<",\"workerPid\":"<<GetProcessId(owner.worker_process_handle())
            <<",\"configFile\":"<<json_string(consumer.u8string())<<",\"configSha256\":"<<json_string(Process::executable_sha256(consumer))<<",\"recordSha256\":"<<json_string(Process::executable_sha256(record))
            <<",\"brokerSha256\":"<<json_string(image_hash)<<",\"workerSha256\":"<<json_string(config.worker.sha256)<<",\"rateHz\":"<<ready_state.device.rate_hz<<",\"limitMs\":"<<duration<<",\"readyIsSnapshot\":true}\n";
        published.push_back(write_new(output/L"ready.json",ready.str()));evidence.published=true;journal.mark("serve_begin");
        while(WaitForSingleObject(stop.value,0)==WAIT_TIMEOUT){
            std::string connection_diagnostic;
            BrokerClientObservation client;
            const auto served=serve_broker_client(listener,owner,stop.value,&connection_diagnostic,BrokerAccess::audio,application,&client);
            if(client.pid){
                if(evidence.client_count<evidence.clients.size())evidence.clients[evidence.client_count++]=client;
                else evidence.client_observations_truncated=true;
            }
            if(served==BrokerServeResult::owner_failed || owner.report().failed){
                evidence.reason="owner_failure";evidence.connection_diagnostic=connection_diagnostic.substr(0,512);break;
            }
            if(served==BrokerServeResult::stopped)break;
        }
    }catch(const std::exception& e){evidence.error=e.what();journal.mark("controller_failure");}
    SetEvent(stop.value);
    evidence.application_exited=application && WaitForSingleObject(application,0)==WAIT_OBJECT_0;
    if(evidence.error.empty() && evidence.reason!="owner_failure")
        evidence.reason=timer.expired?"lifetime_limit":evidence.application_exited?"application_exit":"stop_requested";
    journal.mark("owner_close_begin");evidence.final=owner.close();journal.mark("owner_close_returned");
    const auto text=result(evidence,timer.expired);published.push_back(write_new(output/L"result.json",text));std::cout<<text;
    return evidence.published && evidence.error.empty() && !evidence.final.failed && evidence.final.snapshot_valid && evidence.final.device.io_retired &&
        evidence.final.device.device_released && evidence.final.process.process_exited && evidence.final.process.job_empty && !evidence.final.termination_requested?0:1;
}
int stop(const std::filesystem::path& file){
    const auto config=asio::load_driver_configuration(file,timing_policy);require(config.broker.has_value(),"Stop requires a live broker configuration");
    Handle event;event.value=OpenEventW(EVENT_MODIFY_STATE,FALSE,stop_name(config.broker->endpoint).c_str());require(event.value && SetEvent(event.value),"Request known controller stop");
    std::cout<<"{\"schema\":\"sl3.broker-controller-stop.v1\",\"stopRequested\":true,\"deviceReleasedVerified\":false}\n";return 0;
}
void ordinary_user(){
    Handle token;require(OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token.value)!=FALSE,"Read publisher token");
    TOKEN_ELEVATION elevation{};DWORD bytes=0;
    require(GetTokenInformation(token.value,TokenElevation,&elevation,sizeof(elevation),&bytes) && !elevation.TokenIsElevated,"Pointer commands require an ordinary non-elevated user");
}
int publish_pointer(const std::filesystem::path& source,const std::filesystem::path& destination){
    auto config=asio::load_driver_configuration(source,timing_policy);require(config.broker.has_value(),"Pointer publication requires an immutable broker configuration");
    ReadFileLease source_pin(source);const auto digest=Process::executable_sha256(source);ordinary_user();
    local(destination);Handle parent;
    parent.value=CreateFileW(destination.parent_path().c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS,nullptr);
    require(parent.value!=INVALID_HANDLE_VALUE,"Pin existing session pointer directory");final_local(parent.value);
    require(!std::filesystem::exists(destination) && !std::filesystem::exists(std::filesystem::path(destination.native()+L".pending")),"Session pointer and pending path must be new; existing bytes are preserved");
    require(WaitForSingleObject(config.broker->server->handle(),0)==WAIT_TIMEOUT,"Session pointer requires a still-live bound broker");
    const auto text=asio::session_pointer_text(source,digest);
    const auto published=write_new(destination,text);
    std::cout<<"{\"schema\":\"sl3.broker-session-pointer-publication.v1\",\"pointerPublished\":true,\"configurationSha256\":"<<json_string(digest)
        <<",\"replaced\":false,\"deviceAccess\":false,\"deviceReadinessVerified\":false}\n";return 0;
}
int withdraw_pointer(const std::filesystem::path& destination,const std::wstring& expected){
    ordinary_user();local(destination);
    require(expected.size()==64 && std::all_of(expected.begin(),expected.end(),[](wchar_t c){return (c>=L'0' && c<=L'9') || (c>=L'a' && c<=L'f');}),"Withdrawal requires exact lowercase pointer SHA256");
    Handle parent;parent.value=CreateFileW(destination.parent_path().c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS,nullptr);
    require(parent.value!=INVALID_HANDLE_VALUE,"Pin pointer withdrawal directory");final_local(parent.value);
    Handle file;file.value=CreateFileW(destination.c_str(),GENERIC_READ|DELETE,0,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
    require(file.value!=INVALID_HANDLE_VALUE,"Open pointer exclusively for reviewed withdrawal");final_local(file.value);
    BY_HANDLE_FILE_INFORMATION info{};LARGE_INTEGER size{};
    require(GetFileType(file.value)==FILE_TYPE_DISK && GetFileInformationByHandle(file.value,&info) &&
        !(info.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT)) && info.nNumberOfLinks==1 &&
        GetFileSizeEx(file.value,&size) && size.QuadPart>0 && size.QuadPart<=65536,"Withdrawal requires one bounded regular pointer file, no reparse/hard links");
    struct Owner {PSECURITY_DESCRIPTOR descriptor=nullptr;~Owner(){if(descriptor)LocalFree(descriptor);}} owner;
    PSID sid=nullptr;require(GetSecurityInfo(file.value,SE_FILE_OBJECT,OWNER_SECURITY_INFORMATION,&sid,nullptr,nullptr,nullptr,&owner.descriptor)==ERROR_SUCCESS,"Read pointer file owner");
    require(sid && IsValidSid(sid),"Pointer file must have a valid owner SID");
    Handle token;require(OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token.value)!=FALSE,"Read pointer withdrawal owner token");
    DWORD needed=0;GetTokenInformation(token.value,TokenUser,nullptr,0,&needed);std::vector<std::uint8_t> user(needed);
    require(needed && GetTokenInformation(token.value,TokenUser,user.data(),needed,&needed) && EqualSid(sid,reinterpret_cast<TOKEN_USER*>(user.data())->User.Sid),"Pointer must be owned by current user");
    std::string text(std::size_t(size.QuadPart),'\0');DWORD received=0;
    require(ReadFile(file.value,text.data(),DWORD(text.size()),&received,nullptr) && received==text.size(),"Read exact held pointer bytes");
    asio::parse_session_pointer(text); // No target resolution: stale pointers can be withdrawn.
    struct Hash {BCRYPT_ALG_HANDLE algorithm{};BCRYPT_HASH_HANDLE value{};std::vector<UCHAR> storage;
        ~Hash(){if(value)BCryptDestroyHash(value);if(algorithm)BCryptCloseAlgorithmProvider(algorithm,0);}} hash;
    require(BCryptOpenAlgorithmProvider(&hash.algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0,"Open pointer SHA256 provider");
    DWORD object_bytes=0,returned=0;
    require(BCryptGetProperty(hash.algorithm,BCRYPT_OBJECT_LENGTH,reinterpret_cast<PUCHAR>(&object_bytes),sizeof(object_bytes),&returned,0)>=0,"Pointer hash object size");
    hash.storage.resize(object_bytes);
    require(BCryptCreateHash(hash.algorithm,&hash.value,hash.storage.data(),object_bytes,nullptr,0,0)>=0 &&
        BCryptHashData(hash.value,reinterpret_cast<PUCHAR>(text.data()),ULONG(text.size()),0)>=0,"Hash exact held pointer bytes");
    std::array<UCHAR,32> digest{};require(BCryptFinishHash(hash.value,digest.data(),ULONG(digest.size()),0)>=0,"Finish pointer SHA256");
    constexpr char hex[]="0123456789abcdef";std::wstring actual;for(const auto byte:digest){actual+=wchar_t(hex[byte>>4]);actual+=wchar_t(hex[byte&15]);}
    require(actual==expected,"Pointer bytes differ from explicitly reviewed withdrawal hash");
    FILE_DISPOSITION_INFO disposition{};disposition.DeleteFile=TRUE;
    require(SetFileInformationByHandle(file.value,FileDispositionInfo,&disposition,sizeof(disposition))!=FALSE,"Mark exact opened pointer for deletion");
    const HANDLE retired=file.value;file.value=INVALID_HANDLE_VALUE;require(CloseHandle(retired)!=FALSE,"Close withdrawn pointer");
    const auto attributes=GetFileAttributesW(destination.c_str());const auto error=GetLastError();
    const bool absent=attributes==INVALID_FILE_ATTRIBUTES && (error==ERROR_FILE_NOT_FOUND || error==ERROR_PATH_NOT_FOUND);
    std::cout<<"{\"schema\":\"sl3.broker-session-pointer-withdrawal.v1\",\"pointerDeletionMarked\":true,\"pointerAbsentObserved\":"<<std::boolalpha<<absent
        <<",\"deviceAccess\":false,\"brokerStopped\":false,\"automaticPublication\":false}\n";return 0;
}
}
int wmain(int argc,wchar_t** argv){
    try{
        if(argc==1 || (argc==2 && std::wstring(argv[1])==L"--plan")){
            std::cout<<"{\"schema\":\"sl3.broker-controller-plan.v1\",\"kind\":"<<json_string(kind_name)<<",\"planOnly\":true,\"helperLoaded\":false,\"deviceAccess\":false,\"filesWritten\":false,\"explicitLifetimeRequired\":true,\"automaticRestart\":false}\n";return 0;
        }
        require(argc>=2,"Controller mode required");std::map<std::wstring,std::wstring> args;
        for(int n=2;n<argc;n+=2){require(n+1<argc && args.emplace(argv[n],argv[n+1]).second,"Duplicate/incomplete controller option");}
        if constexpr(timing_policy==asio::TimingPolicy::unmeasured_diagnostic){
            if(std::wstring(argv[1])==L"--inspect-input"){
                require(args.size()==1 && args.count(L"--input"),"Inspection requires input only");
                const auto config=asio::load_driver_configuration(std::filesystem::path(args.at(L"--input")),timing_policy);
                require(!config.broker,"Inspection requires private-worker input");
                std::cout<<"{\"schema\":\"sl3.unmeasured-input-inspection.v1\",\"kind\":"<<json_string(kind_name)
                    <<",\"rateHz\":"<<config.latency.rate_hz<<",\"bufferFrames\":"<<config.latency.buffer_frames
                    <<",\"workerSha256\":"<<json_string(config.worker.sha256)
                    <<",\"latencyAvailable\":false,\"deviceAccess\":false,\"filesWritten\":false}\n";
                return 0;
            }
        }
        if(std::wstring(argv[1])==L"--run"){
            const auto option=args.find(L"--playback-keepalive");
            const bool keepalive=option!=args.end();
            require(!keepalive || option->second==L"on","Playback keepalive value must be on");
            const auto bound=args.find(L"--application-process");
            require(args.size()==3u+keepalive+(bound!=args.end()) && args.count(L"--input") && args.count(L"--output") &&
                    args.count(L"--limit-ms"),"Run requires input, output and limit-ms");
            Handle application;
            if(bound!=args.end())bind_application(application,bound->second);
            return run(std::filesystem::path(args.at(L"--input")),std::filesystem::path(args.at(L"--output")),
                       limit(args.at(L"--limit-ms")),keepalive,bound!=args.end()?application.value:nullptr);
        }
        if(std::wstring(argv[1])==L"--publish-pointer"){require(args.size()==2 && args.count(L"--config") && args.count(L"--pointer"),"Pointer publication requires config/pointer only");return publish_pointer(std::filesystem::path(args.at(L"--config")),std::filesystem::path(args.at(L"--pointer")));}
        if(std::wstring(argv[1])==L"--withdraw-pointer"){require(args.size()==2 && args.count(L"--pointer") && args.count(L"--sha256"),"Pointer withdrawal requires pointer/sha256 only");return withdraw_pointer(std::filesystem::path(args.at(L"--pointer")),args.at(L"--sha256"));}
        if(std::wstring(argv[1])==L"--stop"){require(args.size()==1 && args.count(L"--config"),"Stop requires config only");return stop(std::filesystem::path(args.at(L"--config")));}
        throw std::invalid_argument("Unknown controller mode");
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
