#pragma once
#include "core/rate_selection.hpp"

namespace sl3::control {
class RateIo {
public:
    virtual ~RateIo()=default;
    virtual std::uint64_t now_ms() noexcept=0;
    virtual bool cancelled() noexcept=0;
    // Returns only after the request's I/O/storage has retired, on success or
    // failure. An adapter unable to prove retirement must contain its process
    // while retaining storage; returning and freeing it is forbidden.
    virtual bool transfer(bool output,Frame&,unsigned timeout_ms,std::size_t& bytes) noexcept=0;
};
enum class DiagnosticError {none,invalid_target,deadline,cancelled,transfer,transaction};
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
