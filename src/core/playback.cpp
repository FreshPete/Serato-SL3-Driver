#include "core/playback.hpp"
#include <stdexcept>

namespace sl3 {
PlaybackLayout make_playback_layout(const std::vector<std::uint32_t>& lengths,
                                    const std::vector<Frame>& frames) {
    if (lengths.empty() || lengths.size() > 1024 || lengths.size() % 8)
        throw std::runtime_error("Playback layout requires 8..1024 intervals in groups of eight");
    std::size_t bytes = 0;
    for (const auto length : lengths) {
        if (!length || length > max_packet || length % frame_bytes)
            throw std::runtime_error("Playback requires nonempty whole-frame packet lengths");
        bytes += length;
    }
    if (frames.size() != bytes / frame_bytes)
        throw std::runtime_error("Playback frame count must exactly match the observed packet schedule");
    PlaybackLayout out;
    out.winusb_maximum_packet_shape = true;
    std::uint32_t offset = 0;
    for (std::size_t i = 0; i < lengths.size(); ++i) {
        const auto length = lengths[i];
        out.packets.push_back({offset, length, 0});
        offset += length;
        if (i + 1 < lengths.size() && length != max_packet)
            out.winusb_maximum_packet_shape = false;
    }
    out.packed_pcm.reserve(bytes);
    for (const auto& frame : frames) for (const auto value : frame) {
        if (value < -8388608 || value > 8388607)
            throw std::runtime_error("Playback sample exceeds signed 24-bit range");
        const auto bits = static_cast<std::uint32_t>(value);
        for (unsigned byte = 0; byte < sample_bytes; ++byte)
            out.packed_pcm.push_back(static_cast<std::uint8_t>(bits >> (byte * 8)));
    }
    return out;
}
}
