#pragma once
#include "core/device_session_protocol.hpp"
#include "windows/stream_session.hpp"

namespace sl3::worker {
// Isolated process only. One redirect survives successful stream stop/start.
// begin() must roll back partial activation on exception. Target::close retires
// its backend/alternates, but never releases this device's redirect.
class SessionDevice {
public:
    virtual ~SessionDevice()=default;
    // Idle getter: every interrupt request must retire before return/throw.
    // Otherwise contain the isolated worker while retaining its native storage.
    virtual unsigned read_rate()=0;
    // Idle held device only. On return or exception every interrupt request
    // must be retired; otherwise contain this process without freeing storage.
    virtual device_session::ControlSample read_controls()=0;
    // Default refusal keeps the native getter-only adapter read-only. A device
    // implementation must explicitly opt in and retire I/O before returning or
    // throwing; unproved retirement must contain the isolated worker.
    virtual bool supports_selection() const noexcept{return false;}
    virtual control::selection_wire::Reply select_control(control::selection_wire::Target){throw std::logic_error("Control selection unsupported");}
    // Separate opt-in: supporting audio controls never authorizes a rate write.
    // Same retired-I/O/containment contract as select_control, on this idle lease.
    virtual bool supports_rate_selection() const noexcept{return false;}
    virtual control::rate_wire::Reply select_rate(unsigned){throw std::logic_error("Rate selection unsupported");}
    virtual std::unique_ptr<SessionTarget> begin(StreamConfig)=0;
    virtual bool close() noexcept=0;
    virtual DWORD native_error() const noexcept=0;
};
// A throwing acquire must release its partial open or contain the process.
using DeviceFactory=std::function<std::unique_ptr<SessionDevice>()>;
int serve_device_session(Mailbox&,session::Kind,DeviceFactory,SessionTimeouts={});
}
