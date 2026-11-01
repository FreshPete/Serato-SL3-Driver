#pragma once
#include "core/control_frames.hpp"

namespace sl3::control {
// Offline transaction engine only. The owner must exclusively hold an idle
// device, provide a total wall-clock deadline and retain all submitted I/O.
// No retries, rollback writes, transport calls or streaming transitions occur here.
enum class RatePhase {inspect_ready,inspect_wait,set_ready,set_wait,verify_ready,verify_wait,complete,failed};
enum class RateError {none,invalid_target,exchange,readback_mismatch,aborted};
class RateSelection final {
    unsigned target_=0,initial_=0,verified_=0;
    RatePhase phase_=RatePhase::inspect_ready;
    RateError error_=RateError::none;
    Error exchange_error_=Error::none;
    bool write_possible_=false;
    Exchange exchange_{rate_query()};
    void fail(RateError,Error=Error::none) noexcept;
public:
    explicit RateSelection(unsigned target_hz) noexcept;
    RateSelection(const RateSelection&)=delete;
    RateSelection& operator=(const RateSelection&)=delete;
    // Copies each request at most once and enters its waiting phase. Taking
    // the setter conservatively means the device may change, even if the
    // caller subsequently cannot prove whether submission reached hardware.
    bool take_request(Frame&) noexcept;
    Event accept(const std::uint8_t*,std::size_t) noexcept;
    // Call on timeout, transfer failure or owner cancellation. Terminal states
    // are immutable; abort never manufactures a compensating write.
    void abort() noexcept;
    RatePhase phase() const noexcept{return phase_;}
    RateError error() const noexcept{return error_;}
    Error exchange_error() const noexcept{return exchange_error_;}
    unsigned initial_rate_hz() const noexcept{return initial_;}
    unsigned verified_rate_hz() const noexcept{return verified_;}
    bool device_may_have_changed() const noexcept{return write_possible_;}
};
}
