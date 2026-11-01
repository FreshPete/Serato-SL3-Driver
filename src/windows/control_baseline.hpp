#pragma once
#include "core/audio_controls.hpp"
#include <limits>
#include <memory>
#include <optional>

namespace sl3::worker {
template<class Device,class Transfer,class Clock> class NativeControlsIo;

// Process-local observation lifetime, not a persisted permit or authorization.
// The containing device and its control owner must remain exclusive and idle.
class ControlBaselineOwner final {
    struct State {std::uint64_t generation=0;};
    std::shared_ptr<State> state_=std::make_shared<State>();
    bool advance() noexcept {
        if(!state_)return false;
        if(state_->generation==std::numeric_limits<std::uint64_t>::max()){state_.reset();return false;}
        ++state_->generation;return true;
    }
public:
    class Token {
        std::weak_ptr<State> owner_;
        std::uint64_t generation_=0,observed_ms_=0;
        control::AudioControlsSnapshot controls_{};
        friend class ControlBaselineOwner;
    public:
        Token()=default;
        Token(const Token&)=delete;
        Token& operator=(const Token&)=delete;
        Token(Token&&)=default;
        Token& operator=(Token&&)=default;
    };
    ControlBaselineOwner()=default;
    ControlBaselineOwner(const ControlBaselineOwner&)=delete;
    ControlBaselineOwner& operator=(const ControlBaselineOwner&)=delete;
    void invalidate() noexcept {advance();}
private:
    struct Reservation {
        std::weak_ptr<State> owner;
        std::uint64_t generation=0,observed_ms=0;
        control::AudioControlsSnapshot controls{};
    };
    template<class Device,class Transfer,class Clock> friend class NativeControlsIo;
    Token observe(control::AudioControlsSnapshot controls,std::uint64_t now) noexcept {
        Token token;
        if(advance()){
            token.owner_=state_;token.generation_=state_->generation;
            token.observed_ms_=now;token.controls_=controls;
        }
        return token;
    }
    std::optional<Reservation> consume(Token&& token,std::uint64_t now,unsigned age) noexcept {
        auto owner=token.owner_.lock();token.owner_.reset(); // Every attempt consumes the token.
        if(!owner || owner!=state_ || owner->generation!=token.generation_ || now<token.observed_ms_ ||
           now-token.observed_ms_>=age || !advance())return std::nullopt;
        return Reservation{state_,state_->generation,token.observed_ms_,token.controls_};
    }
    bool available(const Token& token,std::uint64_t now,unsigned age) const noexcept {
        const auto owner=token.owner_.lock();
        return owner && owner==state_ && owner->generation==token.generation_ && now>=token.observed_ms_ &&
               now-token.observed_ms_<age;
    }
    bool matches(const Reservation& reservation) const noexcept {
        const auto owner=reservation.owner.lock();
        return owner && owner==state_ && owner->generation==reservation.generation;
    }
    bool current(const Reservation& reservation,std::uint64_t now,unsigned age) const noexcept {
        return matches(reservation) && now>=reservation.observed_ms && now-reservation.observed_ms<age;
    }
};
}
