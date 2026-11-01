#pragma once
#include "core/rate_selection.hpp"

namespace sl3::control {
enum class DiagnosticError {none,invalid_target,deadline,cancelled,transfer,transaction};
// A reply decision is acceptance by the bounded exchange, not verification of
// the requested clock. A mismatching supported getter is still a reply.
enum class RateIoDecision {write_retired,notification,reply,exchange_failure,cancelled,deadline,transfer_failure};
struct RateIoObservation {
    unsigned sequence=0;bool output=false;unsigned timeout_ms=0;
    std::uint64_t started_ms=0,completed_ms=0;
    bool transferred=false;std::size_t bytes=0;Frame frame{};
    RateIoDecision decision=RateIoDecision::transfer_failure;
};
class RateIo {
public:
    virtual ~RateIo()=default;
    virtual std::uint64_t now_ms() noexcept=0;
    virtual bool cancelled() noexcept=0;
    // Returns only after the request's I/O/storage has retired, on success or
    // failure. An adapter unable to prove retirement must contain its process
    // while retaining storage; returning and freeing it is forbidden.
    virtual bool transfer(bool output,Frame&,unsigned timeout_ms,std::size_t& bytes) noexcept=0;
    // Optional telemetry after the runner decides whether to consume the frame.
    // Must be bounded, nonblocking and perform no I/O. A native adapter buffers
    // these decisions and persists them after the bounded transaction returns.
    // Observing a frame cannot promote late/cancelled data to accepted evidence.
    virtual void observed(const RateIoObservation&) noexcept{}
    virtual void transaction_started(std::uint64_t,unsigned) noexcept{}
    virtual void transaction_finished(std::uint64_t,DiagnosticError) noexcept{}
};
struct RateDiagnosticResult {
    DiagnosticError error=DiagnosticError::none;
    RateError transaction_error=RateError::none;
    Error exchange_error=Error::none;
    unsigned initial_rate_hz=0,verified_rate_hz=0,readback_rate_hz=0,write_attempts=0,read_attempts=0,setter_attempts=0;
    bool device_may_have_changed=false,acknowledgement_received=false;
};
// Owner must hold an idle redirect exclusively, with no outstanding I/O. The
// transaction starts with a fresh getter on that same lease. The deadline covers the
// whole control sequence, not adapter cancellation/drain time. No audio,
// alternate activation, automatic retry or restoration write is performed.
RateDiagnosticResult diagnose_rate(unsigned target_hz,RateIo&,unsigned budget_ms=3000) noexcept;
}
