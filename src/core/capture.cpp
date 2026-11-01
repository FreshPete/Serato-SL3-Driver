#include "core/capture.hpp"
#include <algorithm>
#include <exception>
#include <stdexcept>

namespace sl3 {
Decoded decode_capture(const std::vector<std::uint8_t>& buffer, const std::vector<Packet>& packets) {
    Decoded out;
    std::uint64_t previous_end = 0;
    for (const auto& p : packets) {
        if (p.status != 0) throw std::runtime_error("USB packet status is not success");
        if (p.length > max_packet || p.length % frame_bytes) throw std::runtime_error("Invalid six-channel packet length");
        const std::uint64_t end = std::uint64_t(p.offset) + p.length;
        if (end > buffer.size() || p.offset < previous_end) throw std::runtime_error("Packet slice is out of bounds or overlapping");
        previous_end = end;
        if (!p.length) { ++out.zero_packets; continue; }
        out.packed_pcm.insert(out.packed_pcm.end(), buffer.begin() + p.offset, buffer.begin() + static_cast<std::ptrdiff_t>(end));
        for (std::size_t at = p.offset; at < end; at += frame_bytes) {
            Frame frame{};
            for (std::size_t c = 0; c < channels; ++c) {
                const auto pos = at + c * sample_bytes;
                const std::uint32_t raw = buffer[pos] | (std::uint32_t(buffer[pos + 1]) << 8) | (std::uint32_t(buffer[pos + 2]) << 16);
                frame[c] = (raw & 0x800000) ? static_cast<std::int32_t>(raw) - 0x1000000 : static_cast<std::int32_t>(raw);
            }
            out.frames.push_back(frame);
        }
    }
    return out;
}

CaptureResult capture_transaction(CaptureBackend& backend, std::size_t slots, std::uint32_t deadline_ms, std::uint32_t drain_ms) {
    CaptureResult result;
    if (!slots || slots > 4 || !deadline_ms || deadline_ms > 5000 || !drain_ms || drain_ms > 5000) {
        result.error = "Invalid bounded capture parameters"; return result;
    }
    std::vector<bool> prepared(slots), pending(slots);
    const auto deadline = backend.now_ms() + deadline_ms;
    auto remaining = [&](std::uint64_t end) -> std::uint32_t {
        const auto now = backend.now_ms(); return now < end ? static_cast<std::uint32_t>(end - now) : 0;
    };
    try {
        for (std::size_t i = 0; i < slots; ++i) { backend.prepare(i); prepared[i] = true; }
        for (std::size_t i = 0; i < slots; ++i) { backend.submit(i, i != 0); pending[i] = true; }
        for (std::size_t i = 0; i < slots; ++i) {
            const auto status = backend.wait(i, remaining(deadline));
            if (status == Completion::pending) throw std::runtime_error("Capture deadline elapsed");
            pending[i] = false;
            if (status == Completion::failure) throw std::runtime_error("Capture request failed");
        }
        result.transfers_succeeded = true;
    } catch (const std::exception& e) { result.error = e.what(); }
    catch (...) { result.error = "Unknown capture failure"; }

    // Request cancellation for all pending transfers before waiting for any one.
    for (std::size_t i = 0; i < slots; ++i) if (pending[i]) {
        try { backend.cancel(i); } catch (...) { /* still must drain */ }
    }
    const auto drain_deadline = backend.now_ms() + drain_ms;
    for (std::size_t i = 0; i < slots; ++i) if (pending[i]) {
        try { pending[i] = backend.wait(i, remaining(drain_deadline)) == Completion::pending; }
        catch (...) { /* completion unproven: retain ownership */ }
    }
    for (std::size_t i = 0; i < slots; ++i) if (prepared[i]) {
        if (pending[i]) { result.cleanup_complete = false; result.retained_slots.push_back(i); }
        else {
            try { backend.release(i); }
            catch (...) {
                result.cleanup_complete = false; result.retained_slots.push_back(i);
                if (result.error.empty()) result.error = "Registered-buffer release failed";
            }
        }
    }
    return result;
}
}
