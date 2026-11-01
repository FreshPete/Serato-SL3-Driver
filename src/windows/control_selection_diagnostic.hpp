#pragma once
#include "windows/control_transfer_io.hpp"
#include "core/audio_control_selection_wire.hpp"

namespace sl3::worker {
// Control-thread-only, exclusive idle Device. No acquire/retry/audio/rollback.
// The default has no setting grant. An explicit diagnostic target allows one
// attempt, following a successful same-owner getter; it is never a panel API.
template<class Device,class Transfer,class Clock=ControlClock>
class ControlSelectionDiagnostic final {
    using Io=NativeControlsIo<Device,Transfer,Clock>;
    Device& device_;
    std::optional<control::selection_wire::Target> allowed_;
    std::optional<typename Io::Baseline> baseline_;
    bool attempted_=false;
    DWORD error_=0;
public:
    explicit ControlSelectionDiagnostic(Device& device,std::optional<control::selection_wire::Target> allowed=std::nullopt)
        :device_(device),allowed_(allowed){if(allowed_)control::selection_wire::encode_request(*allowed_);}
    bool enabled() const noexcept{return allowed_.has_value();}
    bool supported() const noexcept{return enabled() && !attempted_ && baseline_ && Io::baseline_current(device_,*baseline_);}
    void invalidate() noexcept {baseline_.reset();device_.control_baseline.invalidate();}
    DWORD native_error() const noexcept{return error_;}
    control::ControlsResult inspect(){
        invalidate();Io io(device_);const auto result=control::inspect_audio_controls(io);error_=io.error;
        if(result.error==control::ControlsError::none && result.controls)baseline_=io.take_baseline();
        return result;
    }
    control::selection_wire::Reply select(control::selection_wire::Target target){
        control::selection_wire::encode_request(target); // No native I/O for invalid target.
        const bool ready=supported();attempted_=true;
        const bool matched=allowed_ && target.setting==allowed_->setting && target.group==allowed_->group && target.value==allowed_->value;
        if(!ready || !matched){
            invalidate();error_=matched?ERROR_INVALID_STATE:ERROR_ACCESS_DENIED;
            control::SelectionIoResult result;result.error=control::SelectionIoError::transfer;
            result.selection_error=control::AudioControlError::aborted;result.phase=control::AudioControlPhase::failed;
            return {target,result,error_};
        }
        auto baseline=std::move(*baseline_);baseline_.reset();
        device_.api.mark("audio_control_selection.enter");
        Io io(device_,std::move(baseline),target.setting,target.group,target.value);
        const auto result=control::select_audio_control(io,target.setting,target.group,target.value);error_=io.error;
        device_.api.mark(result.device_may_have_changed?"audio_control_selection_possible_write.return":"audio_control_selection_no_write.return");
        device_.api.mark(result.error==control::SelectionIoError::none?"audio_control_selection_verified.return":"audio_control_selection_failed.return");
        device_.api.mark("audio_control_selection.return");
        invalidate();return {target,result,error_};
    }
};
}
