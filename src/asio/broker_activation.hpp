#pragma once
#include "asio/driver_configuration.hpp"
#include "windows/worker_process.hpp"
#include <atomic>
#include <mutex>

namespace sl3::asio {
struct BrokerActivationSpec {
    std::filesystem::path controller,input,output;
    std::string controller_sha256,input_sha256;
    DWORD startup_timeout_ms=15000,startup_failure_grace_ms=5000,lifetime_ms=60000;
    TimingPolicy timing=TimingPolicy::reviewed;
    session::Kind kind=session::Kind::native;
};
struct BrokerActivationReport {
    bool attempted=false,ready=false,stop_requested=false,retirement_deferred=false;
    bool termination_requested=false;
    worker::ProcessState controller;
    std::string cleanup_error;
};
class BrokerActivationError final : public std::runtime_error {
public:
    BrokerActivationReport cleanup;
    BrokerActivationError(const std::string& message,BrokerActivationReport observation):
        std::runtime_error(message),cleanup(std::move(observation)){}
};
// Control-thread ordinary-user activation only. No service, registry, locator
// publication, elevation, firmware operations or automatic acquisition retry.
// Not yet connected to the production ASIO entry/configuration format.
class BrokerActivation final : public std::enable_shared_from_this<BrokerActivation> {
public:
    static std::shared_ptr<BrokerActivation> start(const BrokerActivationSpec&);
    ~BrokerActivation();
    BrokerActivation(const BrokerActivation&)=delete;
    BrokerActivation& operator=(const BrokerActivation&)=delete;
    // A returned configuration retains this activation. Explicit close refuses
    // to stop its controller while any returned configuration lease survives.
    DriverConfiguration configuration();
    BrokerActivationReport observe();
    BrokerActivationReport close(DWORD grace_ms=15000) noexcept;
private:
    BrokerActivation()=default;
    void launch(const BrokerActivationSpec&);
    struct Borrow;
    std::mutex mutex_;
    std::atomic<unsigned> borrowed_{0};
    worker::Process process_;
    std::optional<DriverConfiguration> configuration_,input_;
    BrokerActivationReport report_;
};
}
