#pragma once
#include "core/audio_control_selection.hpp"
#include "core/audio_controls_query.hpp"

namespace sl3::control {
// Transport-independent execution policy. A caller must own an exclusive idle
// device and retire each transfer before returning (AudioControlsIo contract).
// There is no Windows adapter, IPC command or automatic setting selection here.
enum class SelectionIoError {none,invalid_budget,invalid_target,cancelled,deadline,transfer,protocol,readback_mismatch};
struct SelectionIoResult {
    SelectionIoError error=SelectionIoError::none;
    AudioControlError selection_error=AudioControlError::none;
    Error exchange_error=Error::none;
    AudioControlPhase phase=AudioControlPhase::failed;
    unsigned write_attempts=0,read_attempts=0,setter_attempts=0;
    bool device_may_have_changed=false;
    std::optional<AudioControlsSnapshot> initial,observed,verified;
    std::optional<std::array<std::uint8_t,2>> acknowledgement;
};
constexpr unsigned control_selection_budget_ms=4500;
inline SelectionIoResult select_audio_control(AudioControlsIo& io,AudioControlSetting setting,
                                             std::size_t group,unsigned value,
                                             unsigned budget_ms=control_selection_budget_ms) noexcept {
    SelectionIoResult result;
    AudioControlSelection selection(setting,group,value);
    const auto finish=[&](SelectionIoError error) noexcept {
        if(error!=SelectionIoError::none)selection.abort();
        result.error=error;result.selection_error=selection.error();result.exchange_error=selection.exchange_error();
        result.phase=selection.phase();result.device_may_have_changed=selection.device_may_have_changed();
        result.initial=selection.initial_controls();result.observed=selection.observed_controls();
        result.verified=selection.verified_controls();result.acknowledgement=selection.acknowledgement();
        return result;
    };
    if(!budget_ms || budget_ms>control_selection_budget_ms)return finish(SelectionIoError::invalid_budget);
    if(selection.phase()==AudioControlPhase::failed)return finish(SelectionIoError::invalid_target);
    const auto entered=io.now_ms();auto previous=entered;
    // Three requests and at most four received frames per request; no retry.
    for(unsigned operation=0;operation<3*(1+maximum_received_frames);++operation){
        if(io.cancelled())return finish(SelectionIoError::cancelled);
        const auto now=io.now_ms();
        if(now<previous || now-entered>=budget_ms)return finish(SelectionIoError::deadline);
        const auto phase=selection.phase();
        const bool output=phase==AudioControlPhase::inspect_ready || phase==AudioControlPhase::set_ready ||
                          phase==AudioControlPhase::verify_ready;
        Frame frame{};
        if(output){
            if(!selection.take_request(frame))return finish(SelectionIoError::protocol);
            ++result.write_attempts;
            if(frame[0]==0x33)++result.setter_attempts;
        }else ++result.read_attempts;
        const auto timeout=std::min(output?100u:300u,budget_ms-unsigned(now-entered));
        std::size_t bytes=0;const auto transferred=io.transfer(output,frame,timeout,bytes);
        const auto completed=io.now_ms();
        if(io.cancelled())return finish(SelectionIoError::cancelled);
        if(completed<now || completed-entered>=budget_ms)return finish(SelectionIoError::deadline);
        previous=completed;
        if(!transferred || bytes!=frame_bytes)return finish(SelectionIoError::transfer);
        if(!output){
            selection.accept(frame.data(),bytes);
            if(selection.phase()==AudioControlPhase::failed)
                return finish(selection.error()==AudioControlError::readback_mismatch?
                              SelectionIoError::readback_mismatch:SelectionIoError::protocol);
            if(selection.phase()==AudioControlPhase::complete)return finish(SelectionIoError::none);
        }
    }
    return finish(SelectionIoError::protocol);
}
}
