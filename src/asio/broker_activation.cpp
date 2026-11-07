#include "asio/broker_activation.hpp"
#include <algorithm>
#include <array>
#include <aclapi.h>
#include <bcrypt.h>
#include <sddl.h>
#include <shlobj.h>
#include <stdexcept>

namespace sl3::asio {
namespace {
void require(bool value,const char* message){if(!value)throw std::runtime_error(message);}
struct Handle {HANDLE value=nullptr;~Handle(){if(value && value!=INVALID_HANDLE_VALUE)CloseHandle(value);}};
void local_path(const std::filesystem::path& path,bool missing_leaf=false){
    const auto drive=path.root_name().native();const auto& name=path.native();
    require(path.is_absolute() && drive.size()==2 && drive[1]==L':' && name.find(L'\0')==std::wstring::npos &&
            name.find(L':',2)==std::wstring::npos && GetDriveTypeW(path.root_path().c_str())==DRIVE_FIXED,
            "Activation paths must use a local fixed drive");
    auto current=path.root_path();
    for(const auto& part:path.relative_path()){
        require(part!=L"." && part!=L"..","Activation paths cannot traverse components");current/=part;
        const auto attributes=GetFileAttributesW(current.c_str());
        if(attributes==INVALID_FILE_ATTRIBUTES){
            require(missing_leaf && current==path && GetLastError()==ERROR_FILE_NOT_FOUND,"Activation parent/input is unavailable");
        }else require(!(attributes&FILE_ATTRIBUTE_REPARSE_POINT),"Activation path redirects are not supported");
    }
}
void ordinary_user(){
    Handle token;require(OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token.value)!=FALSE,"Read activation token");
    TOKEN_ELEVATION elevation{};DWORD size=0;
    require(GetTokenInformation(token.value,TokenElevation,&elevation,sizeof(elevation),&size)!=FALSE && !elevation.TokenIsElevated,
            "Broker activation requires an ordinary user");
}
bool present(const std::filesystem::path& path){
    const auto attributes=GetFileAttributesW(path.c_str());
    if(attributes!=INVALID_FILE_ATTRIBUTES)return true;
    require(GetLastError()==ERROR_FILE_NOT_FOUND || GetLastError()==ERROR_PATH_NOT_FOUND,"Cannot inspect activation output");return false;
}
bool is_regular(const std::filesystem::path& path){
    const auto attributes=GetFileAttributesW(path.c_str());
    if(attributes==INVALID_FILE_ATTRIBUTES){
        require(GetLastError()==ERROR_FILE_NOT_FOUND || GetLastError()==ERROR_PATH_NOT_FOUND,"Cannot observe activation readiness");return false;
    }
    require(!(attributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT)),"Activation readiness must be a regular file");return true;
}
void request_stop(const BrokerAttachment& binding){
    const std::wstring prefix=L"\\\\.\\pipe\\SL3Broker-";
    require(binding.endpoint.size()==prefix.size()+32 && binding.endpoint.compare(0,prefix.size(),prefix)==0,
            "Unexpected activation endpoint");
    const auto name=L"Local\\SL3BrokerStop-"+binding.endpoint.substr(prefix.size());
    Handle event;event.value=OpenEventW(EVENT_MODIFY_STATE,FALSE,name.c_str());
    require(event.value && SetEvent(event.value),"Request owned activation stop");
}
std::wstring application_identity(wchar_t separator){
    FILETIME start{},exit{},kernel{},user{};
    require(GetProcessTimes(GetCurrentProcess(),&start,&exit,&kernel,&user)!=FALSE,"Read host creation time");
    const auto creation=(std::uint64_t(start.dwHighDateTime)<<32)|start.dwLowDateTime;
    return std::to_wstring(GetCurrentProcessId())+separator+std::to_wstring(creation);
}
void open_existing_claim(Handle& claim,const std::filesystem::path& path,DWORD timeout){
    const auto began=GetTickCount64();
    for(;;){
        claim.value=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
        if(claim.value!=INVALID_HANDLE_VALUE)break;
        require(GetLastError()==ERROR_SHARING_VIOLATION && GetTickCount64()-began<timeout,
                "Previous application activation is unavailable or still starting");
        Sleep(10);
    }
    BY_HANDLE_FILE_INFORMATION info{};
    require(GetFileType(claim.value)==FILE_TYPE_DISK && GetFileInformationByHandle(claim.value,&info) &&
            !(info.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT)) && info.nNumberOfLinks==1,
            "Application activation claim must be one regular file");
}
}
void select_user_activation_output(BrokerActivationSpec& spec){
    ordinary_user();
    require(spec.output.empty(),"Activation output was already assigned");
    PWSTR known=nullptr;const auto status=SHGetKnownFolderPath(FOLDERID_LocalAppData,0,nullptr,&known);
    require(SUCCEEDED(status) && known,"Resolve current-user activation state");
    const auto root=std::filesystem::path(known)/L"SL3RebuildActivated";CoTaskMemFree(known);
    local_path(root,true);
    Handle token;require(OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token.value)!=FALSE,"Read activation owner");
    DWORD size=0;GetTokenInformation(token.value,TokenUser,nullptr,0,&size);std::vector<BYTE> user(size);
    require(size && GetTokenInformation(token.value,TokenUser,user.data(),size,&size),"Read activation owner SID");
    const auto sid=reinterpret_cast<TOKEN_USER*>(user.data())->User.Sid;
    LPWSTR text=nullptr;require(ConvertSidToStringSidW(sid,&text)!=FALSE,"Format activation owner SID");
    const auto acl=L"D:P(A;OICI;GA;;;"+std::wstring(text)+L")";LocalFree(text);
    PSECURITY_DESCRIPTOR descriptor=nullptr;
    require(ConvertStringSecurityDescriptorToSecurityDescriptorW(acl.c_str(),SDDL_REVISION_1,&descriptor,nullptr)!=FALSE,"Create activation root policy");
    SECURITY_ATTRIBUTES security{sizeof(security),descriptor,FALSE};
    const bool created=CreateDirectoryW(root.c_str(),&security)!=FALSE;const auto error=GetLastError();LocalFree(descriptor);
    require(created || error==ERROR_ALREADY_EXISTS,"Create private activation state root");
    struct Root {
        HANDLE handle=INVALID_HANDLE_VALUE;
        ~Root(){if(handle!=INVALID_HANDLE_VALUE)CloseHandle(handle);}
    };
    auto retained=std::make_shared<Root>();retained->handle=CreateFileW(root.c_str(),READ_CONTROL|FILE_READ_ATTRIBUTES,
        FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
    require(retained->handle!=INVALID_HANDLE_VALUE,"Retain private activation root");
    FILE_ATTRIBUTE_TAG_INFO attributes{};
    require(GetFileInformationByHandleEx(retained->handle,FileAttributeTagInfo,&attributes,sizeof(attributes)) &&
            (attributes.FileAttributes&FILE_ATTRIBUTE_DIRECTORY) && !(attributes.FileAttributes&FILE_ATTRIBUTE_REPARSE_POINT),"Activation root cannot redirect");
    PSID owner=nullptr;PACL dacl=nullptr;PSECURITY_DESCRIPTOR actual=nullptr;
    require(GetSecurityInfo(retained->handle,SE_FILE_OBJECT,OWNER_SECURITY_INFORMATION|DACL_SECURITY_INFORMATION,
                           &owner,nullptr,&dacl,nullptr,&actual)==ERROR_SUCCESS,"Inspect activation root policy");
    SECURITY_DESCRIPTOR_CONTROL control=0;DWORD revision=0;void* raw=nullptr;
    const bool owner_only=actual && owner && EqualSid(owner,sid) && dacl && dacl->AceCount==1 &&
        GetSecurityDescriptorControl(actual,&control,&revision) && (control&SE_DACL_PROTECTED) && GetAce(dacl,0,&raw);
    bool allowed=false;
    if(owner_only){const auto ace=static_cast<ACCESS_ALLOWED_ACE*>(raw);
        constexpr BYTE inherited=OBJECT_INHERIT_ACE|CONTAINER_INHERIT_ACE;
        allowed=ace->Header.AceType==ACCESS_ALLOWED_ACE_TYPE && (ace->Mask==GENERIC_ALL || ace->Mask==FILE_ALL_ACCESS) &&
                (!spec.application_bound || (ace->Header.AceFlags&inherited)==inherited) &&
                EqualSid(&ace->SidStart,sid);}
    LocalFree(actual);require(allowed,"Existing activation root is not private to this user");
    if(spec.application_bound){
        spec.output=root/(L"application-"+application_identity(L'-'));
        spec.output_root_lease=std::move(retained);
        return;
    }
    std::array<UCHAR,16> random{};require(BCryptGenRandom(nullptr,random.data(),ULONG(random.size()),BCRYPT_USE_SYSTEM_PREFERRED_RNG)>=0,"Generate activation identity");
    std::wstring leaf=L"session-";constexpr wchar_t digits[]=L"0123456789abcdef";
    for(const auto byte:random){leaf+=digits[byte>>4];leaf+=digits[byte&15];}
    spec.output=root/leaf;spec.output_root_lease=std::move(retained);
}
struct BrokerActivation::Borrow {
    std::shared_ptr<BrokerActivation> owner;
    std::shared_ptr<const void> files;
    Borrow(std::shared_ptr<BrokerActivation> selected,std::shared_ptr<const void> retained):owner(std::move(selected)),files(std::move(retained)){
        owner->borrowed_.fetch_add(1);
    }
    ~Borrow(){if(owner->borrowed_.fetch_sub(1)==1 && owner->retirement_requested_.load())owner->request_retirement();}
};
std::shared_ptr<BrokerActivation> BrokerActivation::start(const BrokerActivationSpec& spec){
    auto result=std::shared_ptr<BrokerActivation>(new BrokerActivation);
    try{result->launch(spec);return result;}
    catch(const std::exception& error){
        const std::string reason=error.what();
        const auto cleanup=result->close(std::min<DWORD>(spec.startup_failure_grace_ms,15000));
        throw BrokerActivationError(reason,cleanup);
    }
}
DriverConfiguration BrokerActivation::application_configuration(BrokerActivationSpec spec){
    ordinary_user();
    require(spec.application_bound,"Application-bound activation is required");
    if(spec.output.empty())select_user_activation_output(spec);
    local_path(spec.output,true);
    const auto claim_path=std::filesystem::path(spec.output.native()+L".claim");
    const auto config_path=spec.output/L"sl3-asio.conf";
    const auto expected_prefix="SL3-ASIO-APPLICATION-1\n"+spec.controller.u8string()+"\n"+spec.controller_sha256+"\n"+
        spec.input.u8string()+"\n"+spec.input_sha256+"\n"+std::to_string(spec.startup_timeout_ms)+"\n"+
        std::to_string(spec.startup_failure_grace_ms)+"\n"+std::to_string(spec.lifetime_ms)+"\n";
    Handle claim;
    // This create-new file is both the exclusive startup claim and the receipt.
    // An empty or partial receipt preserves a failed attempt across DLL unloads.
    claim.value=CreateFileW(claim_path.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(claim.value!=INVALID_HANDLE_VALUE){
        auto owner=start(spec);
        const auto receipt=expected_prefix+worker::Process::executable_sha256(config_path)+"\n";
        DWORD written=0;
        require(WriteFile(claim.value,receipt.data(),DWORD(receipt.size()),&written,nullptr) &&
                written==receipt.size() && FlushFileBuffers(claim.value),"Publish application activation receipt");
        owner->handed_off_=true;
        return std::move(*owner->configuration_);
    }
    const auto error=GetLastError();
    require(error==ERROR_FILE_EXISTS || error==ERROR_ALREADY_EXISTS || error==ERROR_SHARING_VIOLATION,
            "Cannot claim application activation");
    open_existing_claim(claim,claim_path,spec.startup_timeout_ms);
    auto selected=load_driver_configuration(config_path,spec.timing);
    require(selected.broker.has_value(),"Application activation receipt requires a live broker");
    const auto expected=expected_prefix+worker::Process::executable_sha256(config_path)+"\n";
    std::string actual(expected.size()+1,'\0');DWORD count=0;
    require(ReadFile(claim.value,actual.data(),DWORD(actual.size()),&count,nullptr)!=FALSE,"Read application activation receipt");
    actual.resize(count);
    require(actual==expected,"Previous application activation differs or failed; restart only after checking recovery");
    selected.broker->kind=spec.kind;
    return selected;
}
void BrokerActivation::launch(const BrokerActivationSpec& spec){
    ordinary_user();
    local_path(spec.controller);local_path(spec.input);local_path(spec.output,true);
    output_root_lease_=spec.output_root_lease;
    require(spec.startup_timeout_ms>=100 && spec.startup_timeout_ms<=30000,"Bounded activation startup deadline required");
    require(spec.startup_failure_grace_ms<=15000,"Bounded activation failure cleanup required");
    require(spec.lifetime_ms>=1000 && spec.lifetime_ms<=43200000 &&
            (spec.timing!=TimingPolicy::unmeasured_diagnostic || spec.lifetime_ms<=600000),"Activation lifetime exceeds its timing policy");
    require(spec.kind==session::Kind::native || spec.kind==session::Kind::simulated,"Known activation worker kind required");
    require(spec.output.is_absolute() && std::filesystem::is_directory(spec.output.parent_path()) && !present(spec.output),
            "Fresh absolute activation output directory required");
    input_=load_driver_configuration(spec.input,spec.timing);
    require(!input_->broker,"Activation requires private-worker input, not another broker");
    // The loader already holds input and transitive dependency bytes read-only.
    require(worker::Process::executable_sha256(spec.input)==spec.input_sha256,"Activation input identity differs");
    report_.attempted=true;
    std::vector<std::wstring> arguments={L"--run",L"--input",spec.input.native(),L"--output",spec.output.native(),
                                         L"--limit-ms",std::to_wstring(spec.lifetime_ms)};
    if(!input_->keepalive_timing_sha256.empty()){
        arguments.push_back(L"--playback-keepalive");arguments.push_back(L"on");
    }
    if(spec.application_bound){
        arguments.push_back(L"--application-process");
        arguments.push_back(application_identity(L':'));
    }
    process_.launch(spec.controller,spec.controller_sha256,arguments,spec.application_bound?
                    worker::Process::JobLifetime::application_controller:worker::Process::JobLifetime::owner);
    const auto began=GetTickCount64();
    while(!is_regular(spec.output/L"ready.json")){
        require(!process_.observe().process_exited,"Activation controller exited before readiness");
        require(GetTickCount64()-began<spec.startup_timeout_ms,"Activation startup deadline");Sleep(10);
    }
    auto selected=load_driver_configuration(spec.output/L"sl3-asio.conf",spec.timing);
    require(selected.broker.has_value() && selected.broker->server &&
            GetProcessId(selected.broker->server->handle())==GetProcessId(process_.process_handle()),
            "Published activation must bind the exact owned controller");
    require(selected.worker.sha256==input_->worker.sha256 && selected.worker.executable==input_->worker.executable &&
            selected.worker.helper==input_->worker.helper && selected.keepalive_timing_sha256==input_->keepalive_timing_sha256,
            "Published activation worker/profile differs from the retained input");
    require(!process_.observe().process_exited,"Activation controller exited during binding");
    selected.broker->kind=spec.kind; // The client still checks the actual pipe greeting.
    configuration_=std::move(selected);report_.ready=true;
}
BrokerActivation::~BrokerActivation(){if(!handed_off_)(void)close();}
DriverConfiguration BrokerActivation::configuration(){
    std::lock_guard<std::mutex> lock(mutex_);
    require(report_.ready && configuration_ && !process_.observe().process_exited,"Activation is no longer ready");
    auto result=*configuration_;
    result.files=std::make_shared<Borrow>(shared_from_this(),result.files);
    result.broker->lifetime=result.files;return result;
}
BrokerActivationReport BrokerActivation::observe(){
    std::lock_guard<std::mutex> lock(mutex_);auto result=report_;result.controller=process_.observe();return result;
}
BrokerActivationReport BrokerActivation::request_retirement() noexcept {
    std::lock_guard<std::mutex> lock(mutex_);retirement_requested_=true;report_.ready=false;
    report_.retirement_deferred=borrowed_.load()!=0;
    if(report_.retirement_deferred)return report_;
    try{
        report_.controller=process_.observe();
        if(report_.controller.started && !report_.controller.process_exited && configuration_ && !report_.stop_requested){
            request_stop(*configuration_->broker);report_.stop_requested=true;
        }
    }catch(const std::exception& error){report_.cleanup_error=error.what();}
    return report_;
}
BrokerActivationReport BrokerActivation::close(DWORD grace) noexcept {
    std::lock_guard<std::mutex> lock(mutex_);
    report_.retirement_deferred=borrowed_.load()!=0;
    if(report_.retirement_deferred)return report_;
    if(grace>15000){report_.cleanup_error="Activation close grace exceeds fifteen seconds";return report_;}
    try{
        report_.controller=process_.observe();
        report_.ready=false;
        if(report_.controller.started && !report_.controller.process_exited && configuration_ && !report_.stop_requested){
            request_stop(*configuration_->broker);report_.stop_requested=true;
        }
        const auto began=GetTickCount64();
        while(report_.controller.started && (!report_.controller.process_exited || !report_.controller.job_empty)){
            if(GetTickCount64()-began>=grace)break;
            Sleep(10);report_.controller=process_.observe();
        }
        if(report_.controller.started && (!report_.controller.process_exited || !report_.controller.job_empty)){
            const auto stopped=process_.terminate_and_wait(2000);report_.termination_requested|=stopped.termination_requested;
            report_.controller=stopped.state;
        }
    }catch(const std::exception& error){
        report_.cleanup_error=error.what();
        // Process retains exact child/job handles; no PID/name lookup or retry.
        try{const auto stopped=process_.terminate_and_wait(2000);report_.termination_requested|=stopped.termination_requested;
            report_.controller=stopped.state;}catch(...){ }
    }
    return report_;
}
}
