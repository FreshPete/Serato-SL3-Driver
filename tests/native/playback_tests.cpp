#include "core/playback.hpp"
#include <iostream>
#include <stdexcept>

static void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
template<class F> static void rejects(F call) {
    bool caught = false;
    try { call(); } catch (const std::runtime_error&) { caught = true; }
    require(caught, "Invalid playback accepted");
}
static void round_trip(const std::vector<std::uint32_t>& lengths, bool maximum_shape) {
    std::size_t frame_count = 0;
    for (auto length : lengths) frame_count += length / sl3::frame_bytes;
    std::vector<sl3::Frame> frames(frame_count);
    const sl3::Frame extremes{-8388608, -1, 0, 1, 0x123456, 8388607};
    for (std::size_t i = 0; i < frames.size(); ++i) {
        frames[i] = extremes;
        // Distinct packet/frame ordering; no repeating silence-only assertion.
        frames[i][2] = static_cast<std::int32_t>(i);
    }
    const auto layout = sl3::make_playback_layout(lengths, frames);
    require(layout.winusb_maximum_packet_shape == maximum_shape, "Wrong WinUSB shape classification");
    std::uint32_t offset = 0;
    for (std::size_t i = 0; i < lengths.size(); ++i) {
        require(layout.packets[i].offset == offset && layout.packets[i].length == lengths[i], "Packet boundary changed");
        offset += lengths[i];
    }
    require(layout.packed_pcm.size() == offset, "Playback padding was inserted");
    require(sl3::decode_capture(layout.packed_pcm, layout.packets).frames == frames, "PCM/layout round trip changed frame/channel order");
}
int main() {
    try {
        // Synthetic arithmetic fixtures, not measured SL3 packet sequences.
        for (const std::uint32_t rate : {44100u, 48000u}) {
            std::uint32_t phase = 0, total_frames = 0;
            std::vector<std::uint32_t> lengths;
            for (unsigned interval = 0; interval < 80; ++interval) {
                phase += rate;
                const auto count = phase / 8000;
                phase %= 8000;
                total_frames += count;
                lengths.push_back(count * static_cast<std::uint32_t>(sl3::frame_bytes));
            }
            require(total_frames == rate / 100, "Synthetic rate fixture error");
            round_trip(lengths, false);
        }
        round_trip({18,36,54,72,90,108,126,18}, false);
        round_trip(std::vector<std::uint32_t>(8,126), true);
        round_trip({126,126,126,126,126,126,126,18}, true);
        const std::vector<sl3::Frame> six(6);
        rejects([&] { sl3::make_playback_layout({}, {}); });
        rejects([&] { sl3::make_playback_layout(std::vector<std::uint32_t>(7,18), six); });
        rejects([&] { sl3::make_playback_layout(std::vector<std::uint32_t>(1032,18), {}); });
        for (auto invalid : {0u,17u,127u,0xffffffffu}) {
            auto lengths = std::vector<std::uint32_t>(8,18); lengths[3] = invalid;
            rejects([&] { sl3::make_playback_layout(lengths, {}); });
        }
        rejects([&] { sl3::make_playback_layout(std::vector<std::uint32_t>(8,18), six); });
        rejects([&] { sl3::make_playback_layout(std::vector<std::uint32_t>(8,18), std::vector<sl3::Frame>(9)); });
        for (auto invalid : {-8388609,8388608}) {
            std::vector<sl3::Frame> frames(8); frames[7][5] = invalid;
            rejects([&] { sl3::make_playback_layout(std::vector<std::uint32_t>(8,18), frames); });
        }
        std::cout << "Playback boundaries, rate fixtures, signed samples and rejection cases passed\n";
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
