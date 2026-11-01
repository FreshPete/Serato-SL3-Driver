#pragma once
#include "asio/driver_facade.hpp"

namespace sl3::asio {
inline constexpr char reviewed_helper_sha256[]="66bbfe6f99b417f97c7a9e97816e24af7dde0e01b8e535c41e91e1c6c19cfeda";
struct DriverConfiguration {
    WorkerSpec worker;
    std::optional<BrokerAttachment> broker;
    LatencyProfile latency;
    std::shared_ptr<const void> files;
};
struct DriverScope {
    std::shared_ptr<DriverOwner> owner;
    LatencyProfile latency;
};
// Strict UTF-8 records, absolute paths, locked bytes and SHA256 bindings only.
// This verifies consistency, not the truth/quality of a timing measurement.
DriverConfiguration load_driver_configuration(const std::filesystem::path&);
std::filesystem::path production_configuration_path();
std::unique_ptr<DriverFacade> make_native_asio_facade();
std::shared_ptr<DriverScope> make_native_asio_scope();
}
