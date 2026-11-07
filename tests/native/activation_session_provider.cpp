// Explicit simulated provider for this unregistered test DLL only.
#include "asio/broker_activation.hpp"
#include <mutex>

namespace {
std::mutex mutex;
std::filesystem::path entry,output;
unsigned ordinal=0;
unsigned required_rate=0;
sl3::asio::DriverConfiguration selected(){
    std::lock_guard<std::mutex> lock(mutex);
    if(entry.empty())throw std::runtime_error("Activation fixture is not configured");
    auto config=sl3::asio::load_driver_entry_configuration(entry,sl3::asio::TimingPolicy::unmeasured_diagnostic);
    if(!config.activation)throw std::runtime_error("Activation fixture requires an activation record");
    auto spec=std::make_shared<sl3::asio::BrokerActivationSpec>(*config.activation);
    spec->kind=sl3::session::Kind::simulated;
    spec->output=output/(spec->application_bound?L"application-owner":L"session-"+std::to_wstring(++ordinal));
    config.activation=std::move(spec);if(required_rate)config.latency.rate_hz=required_rate;return config;
}
}
extern "C" __declspec(dllexport) BOOL sl3_test_activation_configure(const wchar_t* record,const wchar_t* directory) noexcept {
    try{
        if(!record || !directory)return FALSE;std::lock_guard<std::mutex> lock(mutex);
        if(!entry.empty() || !std::filesystem::path(record).is_absolute() || !std::filesystem::path(directory).is_absolute() ||
           !std::filesystem::is_directory(directory))return FALSE;
        entry=record;output=directory;return TRUE;
    }catch(...){return FALSE;}
}
extern "C" __declspec(dllexport) BOOL sl3_test_activation_require_rate(unsigned rate) noexcept {
    if(rate!=0 && rate!=48000)return FALSE;std::lock_guard<std::mutex> lock(mutex);required_rate=rate;return TRUE;
}
std::unique_ptr<sl3::asio::DriverFacade> make_test_asio_facade(){
    return sl3::asio::make_configured_asio_facade(selected(),sl3::asio::TimingPolicy::unmeasured_diagnostic);
}
std::shared_ptr<sl3::asio::DriverScope> make_test_asio_scope(){
    return sl3::asio::make_configured_asio_scope(selected(),sl3::asio::TimingPolicy::unmeasured_diagnostic);
}
bool test_asio_owner_held() noexcept {return false;}
