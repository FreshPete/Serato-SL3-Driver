#pragma once
#include "asio/host_session.hpp"

namespace sl3::asio {
struct BrokerAttachment {
    std::wstring endpoint;
    std::shared_ptr<worker::ProcessWait> server;
    session::Kind kind=session::Kind::native;
    std::string worker_sha256{}; // Required by reviewed broker configuration.
};
// Common ASIO control surface; ownership domain stays explicit in every report.
class DriverSession {
public:
    virtual ~DriverSession()=default;
    virtual bool inspect() noexcept=0;
    virtual std::optional<unsigned> inspect_rate() noexcept=0;
    virtual ASIOError create_buffers(ASIOBufferInfo*,long,long,const ASIOCallbacks*) noexcept=0;
    virtual ASIOError dispose_buffers() noexcept=0;
    virtual bool start(unsigned) noexcept=0;
    virtual HostReport stop(DWORD=5000) noexcept=0;
    virtual HostReport close(DWORD=5000) noexcept=0;
    virtual void request_shutdown() noexcept=0;
    virtual HostReport report() noexcept=0;
    virtual bool on_audio_thread() const noexcept=0;
    virtual Observation observation() const noexcept=0;
};
std::unique_ptr<DriverSession> make_owned_driver_session(WorkerSpec);
std::unique_ptr<DriverSession> make_broker_driver_session(BrokerAttachment);
// Successful client retirement does not imply device release or worker exit.
inline bool driver_session_closed(const HostReport& r) noexcept {
    if(r.failure!=HostFailure::none || r.reentrant || !r.audio.retired || !r.io_retired || r.device_held)return false;
    if(r.domain==HostDomain::broker_client)return (!r.broker.ever_attached || r.broker.detached) && !r.broker.attached && !r.process.started && !r.device_released;
    return r.device_released && (!r.process.started || (r.process.process_exited && r.process.job_empty));
}
}
