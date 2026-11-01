#pragma once
#include "core/device_session_protocol.hpp"
#include "windows/mailbox.hpp"
#include "windows/worker_process.hpp"

namespace sl3::worker {
// Single-control-thread backend for an explicitly started ordinary-user broker. It
// owns the worker/job, never client callbacks or client audio mappings. A later
// authenticated IPC frontend must supply the actual client's process handle;
// a PID or token alone is not an admission credential.
struct BrokerSpec {
    std::filesystem::path executable,helper;
    std::string sha256;
    session::Kind kind=session::Kind::native;
    std::wstring fixture_mode=L"normal";
};
enum class BrokerPhase {dormant,idle,leased,running,sealed,closed};
struct BrokerReport {
    BrokerPhase phase=BrokerPhase::dormant;
    bool client_attached=false,client_alive=false,termination_requested=false;
    bool failed=false; // Sticky operation/ownership failure, including after clean final release.
    DWORD client_pid=0;
    ProcessState process{};
    device_session::Snapshot device{}; // Last typed worker observation only.
};
class RetainedBroker final {
public:
    explicit RetainedBroker(BrokerSpec);
    ~RetainedBroker();
    RetainedBroker(const RetainedBroker&)=delete;
    RetainedBroker& operator=(const RetainedBroker&)=delete;
    // Explicit acquisition once. Failure seals; neither attach nor stream start
    // launches a worker. No retry, reconnect, rate/control writes or elevation.
    bool open() noexcept;
    session::Kind kind() const noexcept {return spec_.kind;}
    const std::string& worker_sha256() const noexcept {return spec_.sha256;}
    // One exclusive live client, bound to a duplicated process object. Fresh
    // clock query precedes admission. Lease numbers are local stale-call guards.
    std::uint64_t attach(HANDLE client_process);
    unsigned clock(std::uint64_t);
    device_session::Snapshot start(std::uint64_t,const device_session::Start&);
    device_session::Snapshot stop(std::uint64_t);
    // Client must retire its own callbacks first. A successful running detach
    // drains worker I/O, then retains the redirect. Never claims client retirement.
    bool detach(std::uint64_t) noexcept;
    // Must be serviced by frontend even without client requests. Idle client
    // death releases its claim. Running death seals and closes the owner: no
    // unproved callback/queue recovery and no subsequent acquisition.
    void poll_client() noexcept;
    BrokerReport report() noexcept;
    BrokerReport close() noexcept;
    BrokerReport abandon() noexcept {seal();return close();} // Unknown client/control outcome; never reusable.
    // Borrowed local wait handle; never close it or use it beyond owner life.
    // An IPC frontend must duplicate an appropriate wait-only handle to clients.
    HANDLE worker_process_handle() const noexcept {return process_.process_handle();}
private:
    BrokerSpec spec_;
    std::unique_ptr<Mailbox> control_;
    Process process_;
    BrokerReport state_{};
    HANDLE client_=nullptr;
    std::uint64_t next_lease_=1,lease_=0;
    bool control_ok_=false;
    Message call(device_session::Command,const std::vector<std::uint8_t>& body={});
    device_session::Snapshot snapshot(device_session::Command,const std::vector<std::uint8_t>& body={});
    void check(std::uint64_t);
    void clear_client() noexcept;
    void seal() noexcept;
};
}
