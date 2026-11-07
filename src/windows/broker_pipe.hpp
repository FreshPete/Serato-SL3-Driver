#pragma once
#include "windows/retained_broker.hpp"

namespace sl3::worker {
// Explicit, private ordinary-user endpoint. No service, registration, discovery
// file or device acquisition. Caller retains the listener and owner lifetimes.
class BrokerListener final {
public:
    BrokerListener();
    ~BrokerListener();
    BrokerListener(const BrokerListener&)=delete;
    BrokerListener& operator=(const BrokerListener&)=delete;
    const std::wstring& name() const noexcept;
private:
    struct State;std::unique_ptr<State> state_;
    friend class BrokerConnection;
};
enum class BrokerServeResult {no_client,detached,rejected,owner_failed,stopped};
enum class BrokerAccess {audio,metadata_only};
bool same_broker_user(HANDLE process);
// Single control thread. Stop event belongs to the explicit owner/controller.
// Accept is bounded; connected idle waits poll liveness/stop at 50 ms. Closing
// an active owner never certifies retirement of callbacks in the client process.
// If supplied, application is a retained live process object restricting admission.
BrokerServeResult serve_broker_client(BrokerListener&,RetainedBroker&,HANDLE stop_event,std::string* diagnostic=nullptr,
                                     BrokerAccess access=BrokerAccess::audio,HANDLE application=nullptr);

class BrokerClient final {
public:
    // Exact already-held server process object, not a PID supplied over IPC.
    // No retries or implicit process/device launch. Native/simulated kind is
    // verified explicitly before any stream can start.
    BrokerClient(const std::wstring& endpoint,HANDLE expected_server,session::Kind,std::string expected_worker_sha256={});
    ~BrokerClient();
    BrokerClient(const BrokerClient&)=delete;
    BrokerClient& operator=(const BrokerClient&)=delete;
    unsigned clock();
    device_session::Snapshot start(Mailbox& audio,StreamConfig);
    device_session::Snapshot stop(DWORD timeout_ms=7000);
    // Retire local callbacks separately before disposal. This acknowledges the
    // held-state reply and detaches only this client, not the physical worker.
    device_session::Snapshot detach(DWORD timeout_ms=7000);
    // Nonwaiting failure path: no stop/detach success is inferred. The server
    // owns subsequent worker containment; local callbacks keep their own leases.
    void disconnect() noexcept;
    const device_session::Snapshot& observation() const noexcept;
    HANDLE worker_process_handle() const noexcept; // Borrowed wait/query only.
private:
    struct State;std::unique_ptr<State> state_;
};
}
