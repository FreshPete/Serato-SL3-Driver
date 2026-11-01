#pragma once
#include "core/audio_controls.hpp"

namespace sl3::control {
// Offline engine only: no transport, IPC command, UI or automatic setter.
// Any future I/O owner must exclusively hold an idle device, enforce a total
// deadline/cancellation policy and retain submitted I/O through retirement.
enum class AudioControlSetting {sensitivity,through};
enum class AudioControlPhase {inspect_ready,inspect_wait,set_ready,set_wait,verify_ready,verify_wait,complete,failed};
enum class AudioControlError {none,invalid_target,exchange,readback_mismatch,aborted};
class AudioControlSelection final {
    std::optional<std::size_t> index_;
    std::uint8_t target_=0;
    AudioControlPhase phase_=AudioControlPhase::inspect_ready;
    AudioControlError error_=AudioControlError::none;
    Error exchange_error_=Error::none;
    bool write_possible_=false;
    std::size_t received_=0;
    Exchange exchange_{audio_controls_query()};
    std::optional<AudioControlsSnapshot> initial_,observed_,verified_;
    std::optional<std::array<std::uint8_t,2>> acknowledgement_;
    void fail(AudioControlError error,Error detail=Error::none) noexcept {
        phase_=AudioControlPhase::failed;error_=error;exchange_error_=detail;
    }
public:
    // Groups follow the original UI's table, not physical jack/deck order.
    // Only original UI sensitivity codes 0..15 and through values 0/1.
    AudioControlSelection(AudioControlSetting setting,std::size_t group,unsigned value) noexcept {
        if(group>=input_control_indexes.size() ||
           !((setting==AudioControlSetting::sensitivity && value<=15) ||
             (setting==AudioControlSetting::through && value<=1))){fail(AudioControlError::invalid_target);return;}
        const auto fields=input_control_indexes[group];
        index_=setting==AudioControlSetting::sensitivity?fields.sensitivity:fields.through;
        target_=std::uint8_t(value);
    }
    AudioControlSelection(const AudioControlSelection&)=delete;
    AudioControlSelection& operator=(const AudioControlSelection&)=delete;
    // Each request can be taken once. Taking a setter conservatively means
    // the device may change even when later submission/completion is unknown.
    bool take_request(Frame& output) noexcept {
        switch(phase_){
        case AudioControlPhase::inspect_ready:phase_=AudioControlPhase::inspect_wait;break;
        case AudioControlPhase::set_ready:phase_=AudioControlPhase::set_wait;write_possible_=true;break;
        case AudioControlPhase::verify_ready:phase_=AudioControlPhase::verify_wait;break;
        default:return false;
        }
        output=exchange_.query().frame();return true;
    }
    Event accept(const std::uint8_t* data,std::size_t bytes) noexcept {
        if(phase_!=AudioControlPhase::inspect_wait && phase_!=AudioControlPhase::set_wait && phase_!=AudioControlPhase::verify_wait){
            if(phase_!=AudioControlPhase::complete && phase_!=AudioControlPhase::failed)
                fail(AudioControlError::exchange,Error::terminal_state);
            Event event;event.error=Error::terminal_state;return event;
        }
        ++received_;
        const auto event=exchange_.accept(data,bytes);
        if(event.outcome==Outcome::failed){fail(AudioControlError::exchange,event.error);return event;}
        if(event.outcome==Outcome::notification)return event;
        if(phase_==AudioControlPhase::set_wait){
            // Original driver requests two acknowledgement bytes. Their
            // values are opaque; a receipt is not verified control state.
            acknowledgement_=std::array<std::uint8_t,2>{{event.payload[0],event.payload[1]}};
            exchange_=Exchange(audio_controls_query());phase_=AudioControlPhase::verify_ready;return event;
        }
        const auto snapshot=audio_controls_snapshot(event);
        if(!snapshot){fail(AudioControlError::exchange,Error::invalid_size);Event bad;bad.error=Error::invalid_size;return bad;}
        observed_=snapshot;
        if(phase_==AudioControlPhase::inspect_wait){
            initial_=snapshot;
            if(snapshot->raw[*index_]==target_){verified_=snapshot;phase_=AudioControlPhase::complete;}
            else{
                Query setter(Kind::audio_control_ack,0x33,2);
                setter.frame_[5]=std::uint8_t(*index_);setter.frame_[6]=1;setter.frame_[7]=target_;
                exchange_=Exchange(setter);phase_=AudioControlPhase::set_ready;
            }
        }else if(snapshot->raw[*index_]!=target_)fail(AudioControlError::readback_mismatch);
        else{verified_=snapshot;phase_=AudioControlPhase::complete;}
        return event;
    }
    // Terminal evidence is immutable. No retries or compensating writes.
    void abort() noexcept {
        if(phase_!=AudioControlPhase::complete && phase_!=AudioControlPhase::failed)fail(AudioControlError::aborted);
    }
    AudioControlPhase phase() const noexcept{return phase_;}
    AudioControlError error() const noexcept{return error_;}
    Error exchange_error() const noexcept{return exchange_error_;}
    bool device_may_have_changed() const noexcept{return write_possible_;}
    std::size_t received_frames() const noexcept{return received_;}
    const std::optional<AudioControlsSnapshot>& initial_controls() const noexcept{return initial_;}
    const std::optional<AudioControlsSnapshot>& observed_controls() const noexcept{return observed_;}
    const std::optional<AudioControlsSnapshot>& verified_controls() const noexcept{return verified_;}
    const std::optional<std::array<std::uint8_t,2>>& acknowledgement() const noexcept{return acknowledgement_;}
};
}
