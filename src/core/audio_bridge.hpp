#pragma once
#include "core/capture.hpp"

namespace sl3 {
enum class Direction { input, output };
enum class BridgeState { ready, running, faulted };
enum class BridgeStatus {
    ok, invalid_argument, invalid_state, reentrant_call, input_discontinuity,
    clock_regression, invalid_sample, output_overflow, output_underrun, callback_failure
};
class BlockCallbacks {
public:
    virtual ~BlockCallbacks() = default;
    // The host may fill this output bank until the next switch; return from
    // this callback does not prove output completion. The other bank is consumed.
    // Position identifies the input block's first logical frame. The timestamp
    // is a host observation of the completing batch, not a measured sample time.
    virtual void buffer_switch(unsigned bank, std::uint64_t first_frame,
                               std::uint64_t observation_ns) = 0;
};
struct BridgeStats {
    std::uint64_t input_frames{}, output_frames{}, completed_blocks{};
    std::size_t queued_output_frames{};
};
// Single-owner stream core. The session owner must serialize configuration,
// start/stop/disposal with its worker. This class owns no I/O, timer or thread.
// Construction allocates; start/process/render/stop use only fixed storage.
class AudioBridge {
public:
    AudioBridge(std::size_t block_frames, const std::vector<unsigned>& inputs,
                const std::vector<unsigned>& outputs);
    AudioBridge(const AudioBridge&) = delete;
    AudioBridge& operator=(const AudioBridge&) = delete;
    std::uint8_t* plane(Direction, unsigned channel, unsigned bank) noexcept;
    std::size_t block_frames() const noexcept { return block_frames_; }
    std::size_t startup_silence_frames() const noexcept { return 2 * block_frames_; }
    BridgeState state() const noexcept { return state_; }
    BridgeStatus fault() const noexcept { return fault_; }
    BridgeStats stats() const noexcept;
    BridgeStatus start(unsigned rate_hz, BlockCallbacks&) noexcept;
    BridgeStatus stop() noexcept;
    BridgeStatus process(const Frame* frames, std::size_t count,
                         std::uint64_t first_frame, std::uint64_t observation_ns) noexcept;
    // All-or-nothing validation/consumption. Packet boundaries are the observed
    // input schedule, supplied by the caller; no nominal-rate generator is used.
    // Caller storage must be valid, stable and disjoint for the entire call.
    BridgeStatus render(const std::uint32_t* lengths, std::size_t packets,
                        std::uint8_t* pcm, std::size_t capacity,
                        Packet* layout, std::size_t layout_capacity) noexcept;
private:
    using Planes = std::array<std::vector<std::uint8_t>, channels>;
    const std::size_t block_frames_;
    std::array<bool,channels> active_input_{},active_output_{};
    std::array<Planes,2> input_,output_;
    std::vector<Frame> output_ring_;
    std::size_t read_{},write_{},queued_{},fill_{};
    unsigned bank_{};
    BridgeState state_=BridgeState::ready;
    BridgeStatus fault_=BridgeStatus::ok;
    BlockCallbacks* callback_=nullptr;
    bool inside_=false,have_observation_=false;
    std::uint64_t input_frames_{},output_frames_{},blocks_{},last_observation_{};
    BridgeStatus fail(BridgeStatus) noexcept;
    void push(const Frame&) noexcept;
};
}
