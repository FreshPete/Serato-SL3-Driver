#include "core/rate_selection.hpp"

namespace sl3::control {
RateSelection::RateSelection(unsigned target_hz) noexcept:target_(target_hz){
    if(target_!=44100 && target_!=48000)fail(RateError::invalid_target);
}
void RateSelection::fail(RateError error,Error detail) noexcept{
    phase_=RatePhase::failed;error_=error;exchange_error_=detail;
}
bool RateSelection::take_request(Frame& frame) noexcept{
    switch(phase_){
    case RatePhase::inspect_ready:phase_=RatePhase::inspect_wait;break;
    case RatePhase::set_ready:phase_=RatePhase::set_wait;write_possible_=true;break;
    case RatePhase::verify_ready:phase_=RatePhase::verify_wait;break;
    default:return false;
    }
    frame=exchange_.query().frame();return true;
}
Event RateSelection::accept(const std::uint8_t* data,std::size_t bytes) noexcept{
    if(phase_!=RatePhase::inspect_wait && phase_!=RatePhase::set_wait && phase_!=RatePhase::verify_wait){
        if(phase_!=RatePhase::complete && phase_!=RatePhase::failed)fail(RateError::exchange,Error::terminal_state);
        Event event;event.error=Error::terminal_state;return event;
    }
    const auto event=exchange_.accept(data,bytes);
    if(event.outcome==Outcome::failed){fail(RateError::exchange,event.error);return event;}
    if(event.outcome==Outcome::notification)return event;
    switch(phase_){
    case RatePhase::inspect_wait:
        initial_=exchange_.rate_hz();
        if(initial_==target_){verified_=initial_;phase_=RatePhase::complete;}
        else{
            // Original acknowledgement bytes are opaque; only the getter
            // establishes a selected rate. No public setter factory exists.
            Query setter(Kind::rate_ack,0x31,2);
            setter.frame_[5]=std::uint8_t(target_>>8);
            setter.frame_[6]=std::uint8_t(target_);
            exchange_=Exchange(setter);phase_=RatePhase::set_ready;
        }
        break;
    case RatePhase::set_wait:exchange_=Exchange(rate_query());phase_=RatePhase::verify_ready;break;
    case RatePhase::verify_wait:
        if(exchange_.rate_hz()!=target_)fail(RateError::readback_mismatch);
        else{verified_=target_;phase_=RatePhase::complete;}
        break;
    default:break;
    }
    return event;
}
void RateSelection::abort() noexcept{
    if(phase_!=RatePhase::complete && phase_!=RatePhase::failed)fail(RateError::aborted);
}
}
