#pragma once
#include <algorithm>
#include <cstdint>

namespace sl3 {
// Enumeration readiness only: never authorizes retrying a USB operation.
class DevicePresence {
public:
    enum class State { waiting, ready, absent, ambiguous, expired, invalid };
    DevicePresence(std::uint64_t now, unsigned budget_ms) noexcept
        : started_(now), previous_(now), budget_(budget_ms),
          state_(budget_ms <= 2000 ? State::waiting : State::invalid) {}
    State observe(unsigned matches, std::uint64_t now) noexcept {
        if(state_ != State::waiting) return state_;
        if(now < previous_) return state_ = State::invalid;
        previous_ = now;
        if(matches > 1) return state_ = State::ambiguous;
        if(budget_ && now - started_ >= budget_) return state_ = State::expired;
        if(matches == 1) return state_ = State::ready;
        if(!budget_) return state_ = State::absent;
        return state_;
    }
    unsigned sleep_ms() const noexcept {
        if(state_ != State::waiting) return 0;
        return static_cast<unsigned>(std::min<std::uint64_t>(25, budget_ - (previous_ - started_)));
    }
private:
    std::uint64_t started_, previous_;
    unsigned budget_;
    State state_;
};
}
