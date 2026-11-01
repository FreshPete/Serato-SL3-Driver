#pragma once
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include "core/audio_controls_query.hpp"
#include "core/audio_control_selection_io.hpp"
#include "windows/control_baseline.hpp"
#include <algorithm>
#include <optional>

namespace sl3::worker {
struct ControlClock {static std::uint64_t now_ms() noexcept{return GetTickCount64();}};

// Transfer must retire its request/storage on every return or exception, or
// fail-stop the isolated worker. The production Transfer enforces this contract.
// The selected constructor is not used by NativeHeldDevice until its separate
// physical baseline/admission gate is met. Default construction is getter-only.
template<class Device,class Transfer,class Clock=ControlClock>
class NativeControlsIo final:public control::AudioControlsIo {
    Device& device_;
    std::optional<control::AudioControlSelection> selection_;
    std::optional<ControlBaselineOwner::Token> baseline_;
    std::optional<ControlBaselineOwner::Reservation> reservation_;
    control::Exchange getter_{control::audio_controls_query()};
    bool getter_sent_=false,sealed_=false;
    const std::uint64_t entered_=Clock::now_ms();
    std::uint64_t previous_=entered_;
    unsigned budget_=control::controls_budget_ms;
    bool reject(DWORD reason) noexcept {sealed_=true;error=reason;return false;}
public:
    using Baseline=ControlBaselineOwner::Token;
    static constexpr unsigned baseline_max_age_ms=control::controls_budget_ms;
    static bool baseline_current(Device& device,const Baseline& baseline) noexcept {
        return device.control_baseline.available(baseline,Clock::now_ms(),baseline_max_age_ms);
    }
    DWORD error=0;
    explicit NativeControlsIo(Device& device):device_(device){}
    NativeControlsIo(Device& device,Baseline&& baseline,control::AudioControlSetting setting,std::size_t group,unsigned value):device_(device){
        budget_=control::control_selection_budget_ms;
        reservation_=device_.control_baseline.consume(std::move(baseline),entered_,baseline_max_age_ms);
        selection_.emplace(setting,group,value);
        if(!reservation_ || selection_->phase()==control::AudioControlPhase::failed){sealed_=true;error=ERROR_INVALID_STATE;}
    }
    std::optional<Baseline> take_baseline() noexcept {auto result=std::move(baseline_);baseline_.reset();return result;}
    std::uint64_t now_ms() noexcept override{return Clock::now_ms();}
    bool cancelled() noexcept override{return false;} // Private worker watchdog owns containment.
    bool transfer(bool output,control::Frame& frame,unsigned timeout,std::size_t& bytes) noexcept override {
        bytes=0;
        if(sealed_){if(!error)error=ERROR_INVALID_PARAMETER;return false;}
        if(!timeout || timeout>(output?100u:300u))return reject(ERROR_INVALID_PARAMETER);
        const auto entered=Clock::now_ms();
        if(entered<previous_ || entered-entered_>=budget_)return reject(ERROR_TIMEOUT);
        try{
            if(output){
                if(selection_){
                    if(!device_.control_baseline.matches(*reservation_))return reject(ERROR_INVALID_STATE);
                    if(selection_->phase()==control::AudioControlPhase::set_ready){
                        if(!device_.control_baseline.current(*reservation_,entered,baseline_max_age_ms))return reject(ERROR_INVALID_STATE);
                        if(!selection_->initial_controls() || selection_->initial_controls()->raw!=reservation_->controls.raw)
                            return reject(ERROR_REVISION_MISMATCH);
                    }
                    control::Frame expected{};
                    if(!selection_->take_request(expected) || frame!=expected)return reject(ERROR_INVALID_PARAMETER);
                }else{
                    if(getter_sent_ || frame!=control::audio_controls_query().frame())return reject(ERROR_INVALID_PARAMETER);
                    getter_sent_=true;
                }
            }else if(selection_){
                const auto phase=selection_->phase();
                if(phase!=control::AudioControlPhase::inspect_wait && phase!=control::AudioControlPhase::set_wait &&
                   phase!=control::AudioControlPhase::verify_wait)return reject(ERROR_INVALID_PARAMETER);
            }else if(!getter_sent_)return reject(ERROR_INVALID_PARAMETER);
            const bool setter=output && frame[0]==0x33;
            device_.api.mark(setter?"audio_control_selection_set.enter":output?"audio_controls_write.enter":"audio_controls_read.enter");
            SetLastError(ERROR_SUCCESS);
            Transfer request(device_);request.prepare(output?0x01:0x81,control::frame_bytes,false);
            if(output)std::copy(frame.begin(),frame.end(),request.buffer.begin());
            const auto prepared=Clock::now_ms();
            if(prepared<entered || prepared-entered>=timeout || prepared-entered_>=budget_)return reject(ERROR_TIMEOUT);
            if(setter && !device_.control_baseline.current(*reservation_,prepared,baseline_max_age_ms))return reject(ERROR_INVALID_STATE);
            const auto remaining=std::min<std::uint64_t>(timeout-(prepared-entered),budget_-(prepared-entered_));
            SetLastError(ERROR_SUCCESS);
            try{request.bounded(output,DWORD(remaining));}
            catch(...){
                const auto native=request.completion_error?request.completion_error:GetLastError();
                return reject(native?native:ERROR_GEN_FAILURE);
            }
            bytes=std::size_t(request.request.Result.GenResult.BytesTransferred);
            if(!output && bytes==frame.size())std::copy(request.buffer.begin(),request.buffer.end(),frame.begin());
            device_.api.mark(setter?"audio_control_selection_set.return":output?"audio_controls_write.return":"audio_controls_read.return");
            const auto completed=Clock::now_ms();
            if(completed<prepared || completed-entered_>=budget_)return reject(ERROR_TIMEOUT);
            if(bytes!=frame.size()){sealed_=true;error=ERROR_BAD_LENGTH;}
            else if(!output){
                // Preserve successful raw transfer delivery, even when the
                // protocol rejects it. The outer engine owns detailed evidence.
                if(selection_){
                    selection_->accept(frame.data(),bytes);
                    sealed_=selection_->phase()==control::AudioControlPhase::failed || selection_->phase()==control::AudioControlPhase::complete;
                }else{
                    const auto event=getter_.accept(frame.data(),bytes);
                    sealed_=event.outcome!=control::Outcome::notification;
                    if(event.outcome==control::Outcome::reply){
                        const auto controls=control::audio_controls_snapshot(event);
                        if(controls)baseline_=device_.control_baseline.observe(*controls,completed);
                    }
                }
            }
            previous_=completed;
            return true;
        }catch(...){
            // Production Transfer::bounded drains or fail-stops; its destructor
            // forbids freeing pending storage. Never catch uncertain retirement.
            const auto native=GetLastError();return reject(native?native:ERROR_GEN_FAILURE);
        }
    }
};
}
