#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace sl3 {
constexpr std::size_t channels = 6, sample_bytes = 3, frame_bytes = 18, max_packet = 126;
using Frame = std::array<std::int32_t, channels>;
struct Packet { std::uint32_t offset{}, length{}, status{}; };
struct Decoded {
    std::vector<Frame> frames;
    std::vector<std::uint8_t> packed_pcm;
    std::size_t zero_packets{};
};
// Decode only successful returned packet slices. Unused slot bytes are ignored.
Decoded decode_capture(const std::vector<std::uint8_t>& buffer, const std::vector<Packet>& packets);

enum class Completion { success, failure, pending };
class CaptureBackend {
public:
    virtual ~CaptureBackend() = default;
    virtual void prepare(std::size_t slot) = 0;
    // Throw means no request was queued. Accepted requests retain their leases
    // until wait() confirms a terminal completion, including cancellation.
    virtual void submit(std::size_t slot, bool continue_stream) = 0;
    virtual Completion wait(std::size_t slot, std::uint32_t timeout_ms) = 0;
    virtual void cancel(std::size_t slot) = 0;
    virtual void release(std::size_t slot) = 0;
    virtual std::uint64_t now_ms() const = 0;
};
struct CaptureResult {
    bool transfers_succeeded = false;
    bool cleanup_complete = true;
    std::string error;
    std::vector<std::size_t> retained_slots;
};
// Fixed, finite transaction. Cancellation is a request, never completion proof.
// If cleanup_complete is false, the backend still owns pending native memory;
// callers must fail-stop the isolated process rather than unwind/free it.
CaptureResult capture_transaction(CaptureBackend&, std::size_t slots = 4,
                                  std::uint32_t deadline_ms = 3000, std::uint32_t drain_ms = 2000);
}
