#pragma once
#include "asio/activation_report.hpp"
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
    std::shared_ptr<const void> output_root_lease;
};
// Resolves the current user's LocalAppData, creates/verifies one private root,
// and assigns a fresh random child path. Called only during explicit activation.
void select_user_activation_output(BrokerActivationSpec&);
class BrokerActivationError final : public std::runtime_error {
public:
    BrokerActivationReport cleanup;
    BrokerActivationError(const std::string& message,BrokerActivationReport observation):
        std::runtime_error(message),cleanup(std::move(observation)){}
};
// Control-thread ordinary-user activation only. No service, registry, locator
// publication, elevation, firmware operations or automatic acquisition retry.
// The activation entry format uses a lazy DriverSession around this component.
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
    // Seal new borrows and post stop when the final configuration/callback
    // lease retires. Never waits for or terminates a process.
    BrokerActivationReport request_retirement() noexcept;
    BrokerActivationReport close(DWORD grace_ms=15000) noexcept;
private:
    BrokerActivation()=default;
    void launch(const BrokerActivationSpec&);
    struct Borrow;
    std::mutex mutex_;
    std::atomic<unsigned> borrowed_{0};
    std::atomic<bool> retirement_requested_{false};
    worker::Process process_;
    std::optional<DriverConfiguration> configuration_,input_;
    std::shared_ptr<const void> output_root_lease_;
    BrokerActivationReport report_;
};
}
