#pragma once
#include "core/continuous.hpp"
#include <string>
#include <vector>

namespace sl3::session {
constexpr std::uint32_t version=2,queue_version=3;
enum class Command:std::uint32_t {hello=0x200,start=0x201,state=0x202,stop=0x203,inspect=0x204,quit=0x2ff};
enum class Status:std::uint32_t {ok,bad_request,bad_state,operation_failed};
enum class Kind:std::uint32_t {native=1,simulated=2};
enum class Phase:std::uint32_t {idle,starting,running,draining,stopped,failed,retained};
enum class Failure:std::uint32_t {none,startup,stream,control,wait,cleanup};
struct Snapshot {
    Phase phase=Phase::idle;
    Failure failure=Failure::none;
    StreamFault stream_fault=StreamFault::none;
    unsigned rate_hz=0,intervals=0;
    bool io_retired=true,device_released=true;
    std::uint32_t native_error=0;
    StreamStats stats{};
    std::string diagnostic;
};
// A successful inspection confirms this observed rate and release of its temporary
// device handle. It certifies neither streaming readiness nor hardware timing.
std::vector<std::uint8_t> encode_clock(unsigned rate_hz);
unsigned decode_clock(const std::vector<std::uint8_t>&);
// Hello is compiled protocol/kind/format only; no device, audio or clock readiness.
std::vector<std::uint8_t> encode_hello(Kind);
Kind decode_hello(const std::vector<std::uint8_t>&);
std::vector<std::uint8_t> encode_start(StreamConfig);
StreamConfig decode_start(const std::vector<std::uint8_t>&);
std::vector<std::uint8_t> encode_snapshot(const Snapshot&);
Snapshot decode_snapshot(const std::vector<std::uint8_t>&);
}
