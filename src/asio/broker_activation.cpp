#include "asio/broker_activation.hpp"
#include <algorithm>
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
}
struct BrokerActivation::Borrow {
    std::shared_ptr<BrokerActivation> owner;
    std::shared_ptr<const void> files;
    Borrow(std::shared_ptr<BrokerActivation> selected,std::shared_ptr<const void> retained):owner(std::move(selected)),files(std::move(retained)){
        owner->borrowed_.fetch_add(1);
    }
    ~Borrow(){owner->borrowed_.fetch_sub(1);}
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
void BrokerActivation::launch(const BrokerActivationSpec& spec){
    ordinary_user();
    local_path(spec.controller);local_path(spec.input);local_path(spec.output,true);
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
    process_.launch(spec.controller,spec.controller_sha256,arguments);
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
BrokerActivation::~BrokerActivation(){(void)close();}
DriverConfiguration BrokerActivation::configuration(){
    std::lock_guard<std::mutex> lock(mutex_);
    require(report_.ready && configuration_ && !process_.observe().process_exited,"Activation is no longer ready");
    auto result=*configuration_;
    result.files=std::make_shared<Borrow>(shared_from_this(),result.files);return result;
}
BrokerActivationReport BrokerActivation::observe(){
    std::lock_guard<std::mutex> lock(mutex_);auto result=report_;result.controller=process_.observe();return result;
}
BrokerActivationReport BrokerActivation::close(DWORD grace) noexcept {
    std::lock_guard<std::mutex> lock(mutex_);
    report_.retirement_deferred=borrowed_.load()!=0;
    if(report_.retirement_deferred)return report_;
    if(grace>15000){report_.cleanup_error="Activation close grace exceeds fifteen seconds";return report_;}
    try{
        report_.controller=process_.observe();
        report_.ready=false;
        if(report_.controller.started && !report_.controller.process_exited && configuration_){
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
