#pragma once
#include "core/session_protocol.hpp"
#include "windows/mailbox.hpp"
#include <functional>

namespace sl3::worker {
class SessionTarget {
public:
    virtual ~SessionTarget()=default;
    virtual ContinuousBackend& backend() noexcept=0;
    // Called only after the stream object has retired all its leases and been
    // destroyed. False requires worker containment, not ordinary unwinding.
    virtual bool close() noexcept=0;
    virtual DWORD native_error() const noexcept=0;
    virtual bool control_failed() const noexcept{return false;}
    virtual bool wait_for_work(Mailbox&,unsigned pending_mask,DWORD timeout_ms) noexcept=0;
};
using SessionFactory=std::function<std::unique_ptr<SessionTarget>(StreamConfig)>;
// Inspector must leave no native lease/device handle on return or exception;
// otherwise it must contain the isolated worker. It never activates audio.
using SessionInspector=std::function<unsigned()>;
struct SessionTimeouts {DWORD startup_ms=8000,live_ms=1000,cleanup_ms=8000,idle_ms=5000;};
// Isolated worker only. A throwing factory must roll back its own partial open
// or fail-stop. No factory/hardware access occurs until a valid greeted start or inspection.
int serve_stream_session(Mailbox&,session::Kind,SessionFactory,SessionInspector,SessionTimeouts={});
}
