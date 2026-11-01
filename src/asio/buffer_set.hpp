#pragma once
#include "asiosys.h"
#include "asio.h"
#include "core/audio_bridge.hpp"
#include <memory>

namespace sl3::asio {
struct Observation {
    bool valid=false;
    unsigned bank=0;
    std::uint64_t first_frame=0,host_observation_ns=0;
};
// SDK-facing buffer component, not an IASIO device or transport-availability
// assertion. Its owner must quiesce/serialize the stream before disposal.
class BufferSet final:private BlockCallbacks {
public:
    ASIOError create(ASIOBufferInfo*,long channels,long frames,const ASIOCallbacks*) noexcept;
    ASIOError dispose() noexcept;
    ASIOError start_buffer_flow(unsigned rate_hz) noexcept;
    ASIOError stop_buffer_flow() noexcept;
    ASIOError channel_info(ASIOChannelInfo*) const noexcept;
    BridgeStatus accept_capture(const Frame*,std::size_t,std::uint64_t first_frame,
                                std::uint64_t host_observation_ns) noexcept;
    BridgeStatus render_output(const std::uint32_t*,std::size_t,std::uint8_t*,std::size_t,
                               Packet*,std::size_t) noexcept;
    bool prepared() const noexcept {return bool(bridge_);}
    BridgeState state() const noexcept {return bridge_?bridge_->state():BridgeState::ready;}
    Observation observation() const noexcept {return observation_;}
    BridgeStats stats() const noexcept {return bridge_?bridge_->stats():BridgeStats{};}
private:
    std::unique_ptr<AudioBridge> bridge_;
    ASIOCallbacks callbacks_{};
    Observation observation_{};
    bool in_callback_=false;
    void buffer_switch(unsigned,std::uint64_t,std::uint64_t) override;
};
}
