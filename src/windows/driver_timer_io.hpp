#pragma once
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include "core/driver_timer_query.hpp"
#include <functional>
#include <utility>

namespace sl3::worker {
struct DriverTimerClock {static std::uint64_t now_ms() noexcept{return GetTickCount64();}};
// Explicit isolated diagnostic only. Never used by startup, ASIO or IPC.
template<class Device,class Transfer,class Clock=DriverTimerClock>
class NativeDriverTimerIo final:public control::DriverTimerIo {
    Device& device_;
    const control::Frame expected_;
    control::Exchange exchange_;
    std::function<void(const char*)> progress_;
    const std::uint64_t entered_=Clock::now_ms();
    std::uint64_t previous_=entered_;
    bool sent_=false,sealed_=false;
    bool reject(DWORD reason) noexcept {sealed_=true;if(!error)error=reason;return false;}
public:
    DWORD error=0;
    unsigned writes=0,reads=0;
    NativeDriverTimerIo(Device& device,const control::Challenge& challenge,std::function<void(const char*)> progress={})
        :device_(device),expected_(control::driver_timer_query(challenge).frame()),
         exchange_(control::driver_timer_query(challenge)),progress_(std::move(progress)){}
    std::uint64_t now_ms() noexcept override{return Clock::now_ms();}
    bool cancelled() noexcept override{return false;} // Private process watchdog owns containment.
    bool transfer(bool output,control::Frame& frame,unsigned timeout,std::size_t& bytes) noexcept override{
        bytes=0;
        if(sealed_)return reject(ERROR_INVALID_STATE);
        if(!timeout || timeout>(output?100u:300u))return reject(ERROR_INVALID_PARAMETER);
        const auto entered=Clock::now_ms();
        if(entered<previous_ || entered-entered_>=control::driver_timer_budget_ms)return reject(ERROR_TIMEOUT);
        if(output){if(sent_ || frame!=expected_)return reject(ERROR_INVALID_PARAMETER);sent_=true;++writes;}
        else {if(!sent_ || reads>=control::maximum_received_frames)return reject(ERROR_INVALID_STATE);++reads;}
        try{
            if(progress_)progress_(output?"before timer request":"before timer reply read");
            Transfer request(device_);request.prepare(output?0x01:0x81,control::frame_bytes,false);
            if(output)std::copy(frame.begin(),frame.end(),request.buffer.begin());
            const auto prepared=Clock::now_ms();
            if(prepared<entered || prepared-entered>=timeout || prepared-entered_>=control::driver_timer_budget_ms)
                return reject(ERROR_TIMEOUT);
            const auto remaining=std::min<std::uint64_t>(timeout-(prepared-entered),control::driver_timer_budget_ms-(prepared-entered_));
            SetLastError(ERROR_SUCCESS);
            try{request.bounded(output,DWORD(remaining));}
            catch(...){const auto native=request.completion_error?request.completion_error:GetLastError();return reject(native?native:ERROR_GEN_FAILURE);}
            bytes=std::size_t(request.request.Result.GenResult.BytesTransferred);
            const auto completed=Clock::now_ms();previous_=completed;
            if(completed<prepared || completed-entered_>=control::driver_timer_budget_ms)return reject(ERROR_TIMEOUT);
            if(bytes!=control::frame_bytes)return reject(ERROR_BAD_LENGTH);
            if(!output){
                std::copy(request.buffer.begin(),request.buffer.end(),frame.begin());
                const auto event=exchange_.accept(frame.data(),bytes);
                if(event.outcome!=control::Outcome::notification)sealed_=true;
                if(event.outcome==control::Outcome::failed)error=ERROR_INVALID_DATA;
            }
            if(progress_)progress_("timer transfer retired");
            return true;
        }catch(...){return reject(ERROR_GEN_FAILURE);}
    }
};
}
