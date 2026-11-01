#pragma once
#include "core/audio_controls.hpp"
#include <algorithm>

namespace sl3::control {
class AudioControlsIo {
public:
    virtual ~AudioControlsIo()=default;
    virtual std::uint64_t now_ms() noexcept=0;
    virtual bool cancelled() noexcept=0;
    // Both success and failure require retired transfer/storage ownership.
    // Unproved retirement must retain storage and contain the isolated worker.
    virtual bool transfer(bool output,Frame&,unsigned timeout_ms,std::size_t& bytes) noexcept=0;
};
enum class ControlsError {none,invalid_budget,cancelled,deadline,transfer,exchange};
struct ControlsResult {
    ControlsError error=ControlsError::none;
    Error exchange_error=Error::none;
    unsigned write_attempts=0,read_attempts=0;
    std::optional<AudioControlsSnapshot> controls;
};
constexpr unsigned controls_budget_ms=1500;
// Exactly one 0x32 getter and at most four complete received frames. No retry,
// setter, alternate change, audio request or device open occurs in this engine.
inline ControlsResult inspect_audio_controls(AudioControlsIo& io,unsigned budget_ms=controls_budget_ms) noexcept {
    ControlsResult result;
    if(!budget_ms || budget_ms>controls_budget_ms){result.error=ControlsError::invalid_budget;return result;}
    Exchange exchange(audio_controls_query());const auto entered=io.now_ms();
    for(unsigned operation=0;operation<=maximum_received_frames;++operation){
        if(io.cancelled()){result.error=ControlsError::cancelled;return result;}
        const auto now=io.now_ms();
        if(now<entered || now-entered>=budget_ms){result.error=ControlsError::deadline;return result;}
        const bool output=operation==0;Frame frame=output?exchange.query().frame():Frame{};
        const auto timeout=std::min(output?100u:300u,budget_ms-unsigned(now-entered));
        if(output)++result.write_attempts;else ++result.read_attempts;
        std::size_t bytes=0;const auto transferred=io.transfer(output,frame,timeout,bytes);
        const auto completed=io.now_ms();
        if(io.cancelled()){result.error=ControlsError::cancelled;return result;}
        if(completed<now || completed-entered>=budget_ms){result.error=ControlsError::deadline;return result;}
        if(!transferred || bytes!=frame_bytes){result.error=ControlsError::transfer;return result;}
        if(output)continue;
        const auto event=exchange.accept(frame.data(),bytes);
        if(event.outcome==Outcome::failed){result.error=ControlsError::exchange;result.exchange_error=event.error;return result;}
        if(event.outcome==Outcome::reply){
            result.controls=audio_controls_snapshot(event);
            if(!result.controls)result.error=ControlsError::exchange;
            return result;
        }
    }
    result.error=ControlsError::exchange;result.exchange_error=Error::frame_limit;return result;
}
}
