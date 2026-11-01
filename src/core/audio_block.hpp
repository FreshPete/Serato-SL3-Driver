#pragma once
#include <array>
#include <cstdint>

namespace sl3 {
struct AudioBlock {
    std::uint64_t first_frame=0,host_observation_ns=0;
    std::uint32_t reported_rate_hz=0;
    // Active high-speed intervals: 8..64 in complete USB frames. All inactive
    // packet counts must be zero; PCM remains tightly packed actual frames.
    std::uint32_t packet_count=64;
    std::array<std::uint8_t,64> frames_per_packet{};
    std::array<std::uint8_t,8064> pcm{};
};
}
