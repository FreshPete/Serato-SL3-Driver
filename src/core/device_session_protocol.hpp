#pragma once
#include "core/session_protocol.hpp"
#include "core/audio_controls.hpp"
#include "core/audio_control_selection_wire.hpp"
#include "core/rate_selection_wire.hpp"

namespace sl3::device_session {
// Separate handshake/entry point from the temporary-device session protocol.
constexpr std::uint32_t version=3,magic=0x44334c53;
constexpr unsigned selection_watchdog_ms=7500,selection_reply_ms=8000;
constexpr unsigned rate_watchdog_ms=5500,rate_reply_ms=6000;
static_assert(3000+2000<rate_watchdog_ms && rate_watchdog_ms<rate_reply_ms,
              "Rate transaction, cancellation drain, watchdog and host reply have distinct budgets");
static_assert(control::control_selection_budget_ms+2000<selection_watchdog_ms && selection_watchdog_ms<selection_reply_ms,
              "Selection I/O, one cancellation drain, watchdog and host reply need distinct budgets");
// clock is an optional read-only extension using the existing Snapshot reply.
// Older workers reject unknown commands; the host must fail/close, never fall
// back to a cached clock after requesting a refresh. Wire layouts stay v3.
// select_rate is another optional extension. It requires explicit adapter opt-in;
// older/default adapters refuse it without issuing a control transfer.
enum class Command:std::uint32_t {hello=0x300,acquire=0x301,start=0x302,state=0x303,stop=0x304,controls=0x305,select_control=0x306,clock=0x307,select_rate=0x308,quit=0x3ff};
enum class Phase:std::uint32_t {empty,ready,running,draining,failed,retained,closed};
struct Start {StreamConfig config;std::wstring audio_channel;};
struct Snapshot {
    Phase phase=Phase::empty;
    session::Failure failure=session::Failure::none;
    StreamFault stream_fault=StreamFault::none;
    unsigned rate_hz=0,intervals=0;
    bool io_retired=true,device_released=true;
    bool selection_supported=false; // Explicit device capability; native adapter currently false.
    std::uint32_t native_error=0;
    StreamStats stats{};
    std::string diagnostic;
};
struct ControlSample {control::AudioControlsSnapshot audio;unsigned received_frames=0;};
struct ControlsReply {Snapshot device;ControlSample sample;};
struct SelectionReply {Snapshot device;control::selection_wire::Reply outcome;};
struct RateReply {Snapshot device;control::rate_wire::Reply outcome;};
std::vector<std::uint8_t> encode_hello(session::Kind);
session::Kind decode_hello(const std::vector<std::uint8_t>&);
std::vector<std::uint8_t> encode_start(const Start&);
Start decode_start(const std::vector<std::uint8_t>&);
std::vector<std::uint8_t> encode_snapshot(const Snapshot&);
Snapshot decode_snapshot(const std::vector<std::uint8_t>&);
std::vector<std::uint8_t> encode_controls(const ControlsReply&);
ControlsReply decode_controls(const std::vector<std::uint8_t>&);
std::vector<std::uint8_t> encode_selection(const SelectionReply&);
SelectionReply decode_selection(const std::vector<std::uint8_t>&,control::selection_wire::Target expected);
std::vector<std::uint8_t> encode_rate_selection(const RateReply&);
RateReply decode_rate_selection(const std::vector<std::uint8_t>&,unsigned expected_target);
}
