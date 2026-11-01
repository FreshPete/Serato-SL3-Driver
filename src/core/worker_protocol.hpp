#pragma once
#include <cstddef>
#include <cstdint>
#include <vector>

namespace sl3::protocol {
enum class Command:std::uint32_t {hello=0x100,probe=0x101,capture_input=0x102,quit=0x1ff};
enum class Status:std::uint32_t {ok=0,bad_request=1,bad_state=2,operation_failed=3};
constexpr std::uint32_t version=1,descriptor_probe=1,finite_input=2;
constexpr std::size_t intervals=256,maximum_reply=32+intervals+126*intervals;
static_assert(maximum_reply<=32768,"Worst-case capture reply fits the bounded mailbox");
struct Hello {
    std::uint32_t features=0;
    // These are a compiled finite diagnostic format, not device availability,
    // measured clock/latency, channel mapping or physical audio validation.
};
struct CaptureBatch {
    unsigned reported_rate_hz=0;
    std::vector<std::uint8_t> frames_per_packet,pcm;
};
std::vector<std::uint8_t> encode_hello();
Hello decode_hello(const std::vector<std::uint8_t>&);
std::vector<std::uint8_t> encode_probe();
void validate_probe(const std::vector<std::uint8_t>&);
std::vector<std::uint8_t> encode_capture(const CaptureBatch&);
CaptureBatch decode_capture(const std::vector<std::uint8_t>&);
}
