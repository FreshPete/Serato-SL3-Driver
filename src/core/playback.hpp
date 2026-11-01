#pragma once
#include "core/capture.hpp"

namespace sl3 {
struct PlaybackLayout {
    std::vector<Packet> packets;
    std::vector<std::uint8_t> packed_pcm;
    // A necessary shape check only, not proof of WinUSB API acceptance.
    bool winusb_maximum_packet_shape = false;
};
// Pure, bounded layout construction: no device access or nominal-rate pacing.
// Every supplied frame is consumed once, preserving the observed IN lengths.
// Zero/error packets require a separate recovery policy and are rejected here.
PlaybackLayout make_playback_layout(const std::vector<std::uint32_t>& lengths,
                                    const std::vector<Frame>& frames);
}
