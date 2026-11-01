#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace sl3::control {
constexpr std::size_t frame_bytes=64, maximum_received_frames=4, maximum_reply_bytes=22;
using Frame=std::array<std::uint8_t,frame_bytes>;
using Challenge=std::array<std::uint8_t,8>;
enum class Kind {rate,audio_controls,overloads,driver_timer,rate_ack,audio_control_ack};
enum class Outcome {notification,reply,failed};
enum class Error {none,invalid_size,invalid_tag,unexpected_command,unsupported_rate,frame_limit,terminal_state};

class Query final {
    Kind kind_;
    Frame frame_{};
    std::size_t reply_bytes_;
    Query(Kind,std::uint8_t,std::size_t) noexcept;
    friend Query rate_query() noexcept;
    friend Query audio_controls_query() noexcept;
    friend Query overloads_query() noexcept;
    friend Query driver_timer_query(const Challenge&) noexcept;
    friend class RateSelection;
    friend class AudioControlSelection;
public:
    Kind kind() const noexcept{return kind_;}
    const Frame& frame() const noexcept{return frame_;}
    std::size_t reply_bytes() const noexcept{return reply_bytes_;}
};
Query rate_query() noexcept;
Query audio_controls_query() noexcept;
Query overloads_query() noexcept;
// Original IOCTL selector 0x44 maps to interrupt command 0x37. This only
// constructs a request for the real device; it neither verifies nor invents
// the device's response and does not implement an application handshake.
Query driver_timer_query(const Challenge&) noexcept;

struct Event {
    Outcome outcome=Outcome::failed;
    Error error=Error::none;
    std::uint8_t command=0;
    std::array<std::uint8_t,maximum_reply_bytes> payload{};
    std::size_t payload_bytes=0;
};

class Exchange final {
    Query query_;
    std::size_t received_=0;
    bool finished_=false;
    Error error_=Error::none;
    unsigned rate_=0;
    Event fail(Error) noexcept;
public:
    explicit Exchange(Query query) noexcept:query_(query){}
    const Query& query() const noexcept{return query_;}
    Event accept(const std::uint8_t*,std::size_t) noexcept;
    bool finished() const noexcept{return finished_;}
    Error error() const noexcept{return error_;}
    std::size_t received_frames() const noexcept{return received_;}
    // Nonzero only after a valid rate reply. This is device readback, not a
    // measured oscillator rate, stream validation or authentication result.
    unsigned rate_hz() const noexcept{return rate_;}
};
const char* error_message(Error) noexcept;
}
