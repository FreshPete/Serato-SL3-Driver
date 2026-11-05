// Test DLL only. Never compiled into the production ASIO DLL.
#include "asio/driver_facade.hpp"
#include "asio/driver_configuration.hpp"
#include <mutex>

namespace {std::mutex configuration_mutex;std::filesystem::path executable,audit_path;std::string expected_hash;bool retained=false, report_latency=true;
std::shared_ptr<sl3::asio::DriverOwner> shared_owner;std::optional<sl3::asio::BrokerAttachment> broker;}
static BOOL configure(const wchar_t* path,const char* hash,bool held,bool latency=true) noexcept {
    try{
        if(!path || !hash)return FALSE;
        const std::filesystem::path candidate(path);const std::string expected(hash);
        if(!candidate.is_absolute() || sl3::worker::Process::executable_sha256(candidate)!=expected)return FALSE;
        std::lock_guard<std::mutex> guard(configuration_mutex);if(shared_owner)return FALSE;
        executable=candidate;expected_hash=expected;retained=held;report_latency=latency;audit_path.clear();broker.reset();return TRUE;
    }catch(...){return FALSE;}
}
extern "C" __declspec(dllexport) BOOL sl3_test_configure(const wchar_t* path,const char* hash) noexcept {return configure(path,hash,false);}
extern "C" __declspec(dllexport) BOOL sl3_test_configure_retained(const wchar_t* path,const char* hash) noexcept {return configure(path,hash,true);}
extern "C" __declspec(dllexport) BOOL sl3_test_configure_unmeasured(const wchar_t* path,const char* hash) noexcept {
    return configure(path,hash,false,false);
}
// Test-only audit records the actual simulated worker lifecycle across distinct
// COM objects. This export/provider is absent from the production DLL.
extern "C" __declspec(dllexport) BOOL sl3_test_configure_retained_audit(const wchar_t* path,const char* hash,const wchar_t* audit) noexcept {
    try{
        if(!audit || !*audit)return FALSE;
        const std::filesystem::path candidate(audit);
        if(!candidate.is_absolute() || std::filesystem::exists(candidate))return FALSE;
        if(!configure(path,hash,true))return FALSE;
        std::lock_guard<std::mutex> guard(configuration_mutex);audit_path=candidate;return TRUE;
    }catch(...){return FALSE;}
}
std::unique_ptr<sl3::asio::DriverFacade> make_test_asio_facade(){
    std::lock_guard<std::mutex> guard(configuration_mutex);
    if(broker){
        const auto timing=report_latency?sl3::asio::LatencyProfile{7,11,48000,128}:sl3::asio::LatencyProfile{0,0,44100,128,false};
        return std::make_unique<sl3::asio::DriverFacade>(*broker,timing);
    }
    if(executable.empty())return {};
    if(shared_owner)return std::make_unique<sl3::asio::DriverFacade>(shared_owner,sl3::asio::LatencyProfile{7,11});
    sl3::asio::WorkerSpec spec;spec.executable=executable;spec.sha256=expected_hash;spec.kind=sl3::session::Kind::simulated;
    spec.lifetime=retained?sl3::asio::DeviceLifetime::retained:sl3::asio::DeviceLifetime::temporary;
    if(!audit_path.empty())spec.fixture_mode=L"audit:"+audit_path.native();
    const auto timing=report_latency?sl3::asio::LatencyProfile{7,11}:sl3::asio::LatencyProfile{0,0,48000,128,false};
    return std::make_unique<sl3::asio::DriverFacade>(spec,timing);
}
static BOOL configure_broker(const wchar_t* endpoint,HANDLE server,const char* worker_hash,bool latency) noexcept {
    try{
        if(!endpoint || !*endpoint)return FALSE;
        sl3::asio::BrokerAttachment candidate{endpoint,sl3::worker::ProcessWait::duplicate(server),sl3::session::Kind::simulated};
        if(worker_hash){
            if(std::string(worker_hash).size()!=64)return FALSE;
            candidate.worker_sha256=worker_hash;
        }
        std::lock_guard<std::mutex> guard(configuration_mutex);if(shared_owner)return FALSE;
        broker=std::move(candidate);executable.clear();expected_hash.clear();audit_path.clear();retained=false;report_latency=latency;return TRUE;
    }catch(...){return FALSE;}
}
extern "C" __declspec(dllexport) BOOL sl3_test_configure_broker(const wchar_t* endpoint,HANDLE server) noexcept {
    return configure_broker(endpoint,server,nullptr,true);
}
extern "C" __declspec(dllexport) BOOL sl3_test_configure_bound_broker(const wchar_t* endpoint,HANDLE server,const char* worker_hash) noexcept {
    return worker_hash?configure_broker(endpoint,server,worker_hash,true):FALSE;
}
extern "C" __declspec(dllexport) BOOL sl3_test_configure_unmeasured_broker(const wchar_t* endpoint,HANDLE server,const char* worker_hash) noexcept {
    return worker_hash?configure_broker(endpoint,server,worker_hash,false):FALSE;
}
extern "C" __declspec(dllexport) BOOL sl3_test_configure_shared_owner_audit(const wchar_t* path,const char* hash,const wchar_t* audit) noexcept {
    try{
        if(!sl3_test_configure_retained_audit(path,hash,audit))return FALSE;
        std::lock_guard<std::mutex> guard(configuration_mutex);
        sl3::asio::WorkerSpec spec;spec.executable=executable;spec.sha256=expected_hash;spec.kind=sl3::session::Kind::simulated;
        spec.lifetime=sl3::asio::DeviceLifetime::retained;spec.fixture_mode=L"audit:"+audit_path.native();
        shared_owner=std::make_shared<sl3::asio::DriverOwner>(spec);return TRUE;
    }catch(...){return FALSE;}
}
extern "C" __declspec(dllexport) BOOL sl3_test_close_shared_owner() noexcept {
    std::lock_guard<std::mutex> guard(configuration_mutex);if(!shared_owner)return FALSE;
    const auto value=shared_owner->close();
    if(!value || !value->audio.retired || !value->io_retired || !value->device_released ||
       !value->process.process_exited || !value->process.job_empty || value->failure!=sl3::asio::HostFailure::none)return FALSE;
    shared_owner.reset();return TRUE;
}
bool test_asio_owner_held() noexcept {
    std::lock_guard<std::mutex> guard(configuration_mutex);return bool(shared_owner);
}
std::shared_ptr<sl3::asio::DriverScope> make_test_asio_scope(){
    std::lock_guard<std::mutex> guard(configuration_mutex);if(executable.empty() || !retained || shared_owner)return {};
    sl3::asio::WorkerSpec spec;spec.executable=executable;spec.sha256=expected_hash;spec.kind=sl3::session::Kind::simulated;
    spec.lifetime=sl3::asio::DeviceLifetime::retained;
    if(!audit_path.empty())spec.fixture_mode=L"audit:"+audit_path.native();
    return std::make_shared<sl3::asio::DriverScope>(sl3::asio::DriverScope{
        std::make_shared<sl3::asio::DriverOwner>(spec),sl3::asio::LatencyProfile{7,11}});
}
