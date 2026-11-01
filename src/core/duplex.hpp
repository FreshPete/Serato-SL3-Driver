#pragma once
#include "core/capture.hpp"

namespace sl3 {
struct PacketResult64 {std::uint64_t length{},status{};};
enum class SilentStageStatus {ok,invalid_arguments,invalid_input_packet,insufficient_capacity};
struct SilentStageResult {SilentStageStatus status=SilentStageStatus::invalid_arguments;std::size_t bytes=0;};
// Validate full-width results before narrowing or modifying caller-owned OUT
// arrays. On success every byte of the bounded output storage is set to zero.
// Input, lengths and output storage must remain valid and disjoint for the call.
SilentStageResult stage_silent_output(const PacketResult64*,std::size_t packets,
                                      std::uint64_t* lengths,std::size_t lengths_capacity,
                                      std::uint8_t* output,std::size_t output_capacity) noexcept;
// Even slots are IN; the following odd slot is its corresponding OUT request.
class DuplexBackend:public CaptureBackend {
public:
    // Called only after terminal successful IN. Must reject packet errors and
    // construct/validate the OUT layout before any OUT submission occurs.
    virtual void stage_output(std::size_t input_slot,std::size_t output_slot)=0;
};
// Finite diagnostic pipeline, not a continuous ASIO session. Preparation of all
// resources precedes I/O. On any failure, cancel all pending directions first,
// drain under one deadline, and retain every unproven lease.
CaptureResult duplex_transaction(DuplexBackend&,std::size_t pairs=4,
                                 std::uint32_t deadline_ms=5000,std::uint32_t drain_ms=2000);
}
