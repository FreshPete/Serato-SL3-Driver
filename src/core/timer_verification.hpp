#pragma once
#include "control_frames.hpp"

namespace sl3::control {
using TimerKey=std::array<std::uint8_t,16>;

// Compare a parsed 0x37 reply with the original two-word calculation.
// No key is embedded, no response is returned, and no I/O is performed.
// A match alone does not prove that Event came from a physical device or
// satisfy any current application's product/account/handshake requirements.
bool matches_driver_timer_reply(const Challenge&,const TimerKey&,const Event&) noexcept;
}
