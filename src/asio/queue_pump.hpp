#pragma once
#include "asio/buffer_set.hpp"
#include "windows/mailbox.hpp"

namespace sl3::asio {
enum class PumpState {ready,flowing,faulted,ended};
enum class PumpResult {ok,idle,backpressure,ended,faulted,invalid_state,invalid_rate,reentrant_call};
enum class PumpFault {none,queue,rate,bridge};
struct PumpFailure {
    PumpFault cause=PumpFault::none;
    worker::AudioResult queue=worker::AudioResult::ok;
    BridgeStatus bridge=BridgeStatus::ok;
};
struct PumpStats {
    std::uint64_t received_blocks=0,received_frames=0,published_blocks=0,published_frames=0;
    std::uint64_t discarded_pending_frames=0;
    bool pending_output=false;
};
// Single audio-owner-thread adapter. No thread, device I/O, clock negotiation or
// readiness assertion. Mailbox/BufferSet must outlive it; begin requires a fresh
// host-side channel and exclusively owned prepared buffers. Retire this owner
// before end/disposal; calling end from another thread is not synchronization.
class QueuePump final {
public:
    QueuePump(worker::Mailbox&,BufferSet&) noexcept;
    ~QueuePump();
    QueuePump(const QueuePump&)=delete;
    QueuePump& operator=(const QueuePump&)=delete;
    PumpResult begin(unsigned metadata_rate_hz) noexcept;
    // At most one input block, its callbacks and one output publication per
    // call. Full output retains the exact block; no more input is consumed
    // until it is published. Empty input never fabricates a host callback.
    PumpResult step() noexcept;
    PumpResult end() noexcept;
    PumpState state() const noexcept {return state_;}
    PumpFailure failure() const noexcept {return failure_;}
    PumpStats stats() const noexcept {return stats_;}
private:
    worker::Mailbox& channel_;
    BufferSet& buffers_;
    PumpState state_=PumpState::ready;
    PumpFailure failure_{};
    PumpStats stats_{};
    unsigned rate_=0;
    bool inside_=false,owns_flow_=false;
    std::size_t pending_frames_=0;
    worker::AudioBlock input_{},output_{};
    std::array<Frame,448> decoded_{};
    std::array<std::uint32_t,64> lengths_{};
    std::array<Packet,64> layout_{};
    PumpResult fail(PumpFailure) noexcept;
    PumpResult publish() noexcept;
};
}
