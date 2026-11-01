#pragma once
#include "asio/audio_owner.hpp"
#include "core/session_protocol.hpp"
#include "core/device_session_protocol.hpp"

namespace sl3::asio {
// Reviewed absolute executable and expected hash are supplied by the control
// owner. Simulated kind is explicit and must never advertise hardware readiness.
enum class DeviceLifetime {temporary,retained};
struct WorkerSpec {
    std::filesystem::path executable,helper;
    std::string sha256;
    session::Kind kind=session::Kind::native;
    std::wstring fixture_mode=L"normal";
    // Explicit diagnostic host only. Production configuration leaves this empty.
    std::filesystem::path diagnostic_directory;
    DeviceLifetime lifetime=DeviceLifetime::temporary;
    // Explicit native diagnostic only; production configuration leaves empty.
    std::optional<control::selection_wire::Target> diagnostic_control_target;
};
enum class HostFailure {none,launch,handshake,inspection,rate_changed,audio_start,worker_start,worker,control,audio,containment};
struct HostReport {
    HostFailure failure=HostFailure::none;
    bool running=false,reentrant=false,io_retired=true,device_released=true,termination_requested=false;
    // Confirmed live retained control session, not proof of I/O retirement.
    bool device_held=false;
    unsigned observed_rate_hz=0;
    AudioReport audio{};
    worker::ProcessState process{};
    // Last decoded control reply, not a continuously refreshed worker view.
    session::Snapshot worker_snapshot{};
    device_session::Snapshot device_snapshot{};
};
struct ControlSelectionReport {
    bool command_attempted=false,outcome_unknown=false,device_may_have_changed=false;
    std::optional<control::selection_wire::Reply> outcome;
};
// One control owner. No COM registration or helper loading inside the host.
// Temporary mode preserves the diagnostic inspect/reopen contract. Retained
// mode acquires once during inspection and uses a fresh data channel per start.
// Only observation() and rejected callback reentry are audio-thread operations.
class HostSession final {
public:
    explicit HostSession(WorkerSpec);
    ~HostSession();
    HostSession(const HostSession&)=delete;
    HostSession& operator=(const HostSession&)=delete;
    bool inspect() noexcept;
    // One fresh getter on an already held, idle device, before buffer creation.
    // No acquisition, setter or cached fallback. Failure seals/closes the owner.
    std::optional<unsigned> inspect_rate() noexcept;
    // Explicit control-owner operation on an already held, idle retained device.
    // No acquisition, audio start, setter or automatic refresh is performed.
    std::optional<device_session::ControlSample> inspect_controls() noexcept;
    // No acquisition or retry. Outcome and subsequent cleanup are independent;
    // use report()/close() for process/device ownership, including on failure.
    ControlSelectionReport select_control(control::selection_wire::Target) noexcept;
    ASIOError create_buffers(ASIOBufferInfo*,long channels,long frames,const ASIOCallbacks*) noexcept;
    ASIOError dispose_buffers() noexcept;
    bool start(unsigned intervals=8) noexcept;
    // Explicit one-open diagnostic entry: the native factory must verify this
    // expected rate on its acquired handle before activation or submissions.
    // Does not turn a supplied rate into a successful inspect() result.
    bool start_checked(unsigned expected_rate_hz,unsigned intervals=8) noexcept;
    HostReport stop(DWORD total_timeout_ms=5000) noexcept;
    // Final release. In retained mode this seals the owner against reacquisition.
    HostReport close(DWORD total_timeout_ms=5000) noexcept;
    // Nonwaiting fail-stop retirement request. Seals this owner; never certifies
    // USB recovery or waits for an executing host callback.
    void request_shutdown() noexcept;
    HostReport report() noexcept; // Control thread; may observe the owned process.
    bool on_audio_thread() const noexcept {return reentrant();}
    Observation observation() const noexcept;
private:
    WorkerSpec spec_;
    std::shared_ptr<BufferLease> buffers_=std::make_shared<BufferLease>();
    std::shared_ptr<worker::Mailbox> channel_;
    std::shared_ptr<worker::Mailbox> data_channel_;
    std::shared_ptr<worker::Process> process_;
    std::unique_ptr<AudioOwner> audio_;
    HostReport state_{};
    bool usable_=false,prepared_=false,control_ok_=false;
    bool device_closed_=false;
    unsigned launch_number_=0;
    bool reentrant() const noexcept;
    void failure(HostFailure) noexcept;
    void launch();
    unsigned query_clock();
    worker::Message call(session::Command,const std::vector<std::uint8_t>&,DWORD);
    worker::Message exchange(std::uint32_t,const std::vector<std::uint8_t>&,DWORD);
    worker::Message device_call(device_session::Command,const std::vector<std::uint8_t>&,DWORD);
    void accept_cleanup(const worker::Message&);
    void accept_device(const worker::Message&);
    void accept_device_value(const device_session::Snapshot&);
    bool retired() noexcept;
    bool quiescent() noexcept;
    bool acquire_retained() noexcept;
    bool start_retained(unsigned) noexcept;
    HostReport stop_retained(DWORD,bool final) noexcept;
    bool start_impl(unsigned expected_rate_hz,unsigned intervals,bool inspect_first) noexcept;
};
}
