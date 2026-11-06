#pragma once
#include "asio/driver_facade.hpp"

namespace sl3::asio {
inline constexpr char reviewed_helper_sha256[]="66bbfe6f99b417f97c7a9e97816e24af7dde0e01b8e535c41e91e1c6c19cfeda";
struct DriverConfiguration {
    WorkerSpec worker;
    std::optional<BrokerAttachment> broker;
    std::shared_ptr<const BrokerActivationSpec> activation;
    LatencyProfile latency;
    std::shared_ptr<const void> files;
    std::string keepalive_timing_sha256;
};
struct DriverScope {
    std::shared_ptr<DriverOwner> owner;
    LatencyProfile latency;
};
struct SessionPointer {
    std::filesystem::path configuration;
    std::string sha256;
};
enum class TimingPolicy { reviewed, unmeasured_diagnostic };
// Bounded syntax only; resolving a target applies the file/process policy.
SessionPointer parse_session_pointer(const std::string&);
std::string session_pointer_text(const std::filesystem::path&,const std::string& sha256);
// Strict UTF-8 records, absolute paths, locked bytes and SHA256 bindings only.
// This verifies consistency, not the truth/quality of a timing measurement.
DriverConfiguration load_driver_configuration(const std::filesystem::path&,TimingPolicy=TimingPolicy::reviewed);
// Direct configuration, one fixed locator -> mutable pointer -> immutable
// broker configuration, or a validated lazy activation plan. Activation parsing
// starts no process and creates no state directory. No recursive fallback.
DriverConfiguration load_driver_entry_configuration(const std::filesystem::path&,TimingPolicy=TimingPolicy::reviewed);
std::filesystem::path production_configuration_path();
// Selects the same production backend from an already validated configuration.
// Construction and explicit scope preparation do not acquire hardware.
std::unique_ptr<DriverFacade> make_configured_asio_facade(DriverConfiguration,TimingPolicy=TimingPolicy::reviewed);
std::shared_ptr<DriverScope> make_configured_asio_scope(DriverConfiguration,TimingPolicy=TimingPolicy::reviewed);
std::unique_ptr<DriverFacade> make_native_asio_facade(TimingPolicy=TimingPolicy::reviewed);
std::shared_ptr<DriverScope> make_native_asio_scope(TimingPolicy=TimingPolicy::reviewed);
}
