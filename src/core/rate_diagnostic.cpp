#include "core/rate_diagnostic.hpp"
#include <algorithm>

namespace sl3::control {
RateDiagnosticResult diagnose_rate(unsigned target_hz,RateIo& io,unsigned budget_ms) noexcept{
    RateDiagnosticResult result;RateSelection selection(target_hz);
    if(selection.phase()==RatePhase::failed){result.error=DiagnosticError::invalid_target;result.transaction_error=selection.error();return result;}
    const auto start=io.now_ms();
    io.transaction_started(start,budget_ms);
    for(unsigned operation=0;operation<15;++operation){
        if(io.cancelled()){result.error=DiagnosticError::cancelled;break;}
        const auto now=io.now_ms();
        if(now<start || now-start>=budget_ms){result.error=DiagnosticError::deadline;break;}
        Frame frame{};const auto output=selection.take_request(frame);
        const auto timeout=std::min(output?100u:300u,budget_ms-unsigned(now-start));
        std::size_t bytes=0;
        if(output){++result.write_attempts;if(frame[0]==0x31)++result.setter_attempts;}
        else ++result.read_attempts;
        const auto transferred=io.transfer(output,frame,timeout,bytes);
        const auto completed=io.now_ms();
        const auto observe=[&](RateIoDecision decision){
            io.observed({operation,output,timeout,now,completed,transferred,bytes,frame,decision});
        };
        if(io.cancelled()){result.error=DiagnosticError::cancelled;observe(RateIoDecision::cancelled);break;}
        if(completed<now || completed-start>=budget_ms){result.error=DiagnosticError::deadline;observe(RateIoDecision::deadline);break;}
        if(!transferred || bytes!=frame_bytes){result.error=DiagnosticError::transfer;observe(RateIoDecision::transfer_failure);break;}
        if(output)observe(RateIoDecision::write_retired);
        else{
            const auto event=selection.accept(frame.data(),bytes);
            observe(event.outcome==Outcome::notification?RateIoDecision::notification:
                event.outcome==Outcome::reply?RateIoDecision::reply:RateIoDecision::exchange_failure);
        }
        if(selection.phase()==RatePhase::complete)break;
        if(selection.phase()==RatePhase::failed){result.error=DiagnosticError::transaction;break;}
    }
    if(selection.phase()!=RatePhase::complete && selection.phase()!=RatePhase::failed){
        selection.abort();if(result.error==DiagnosticError::none)result.error=DiagnosticError::transaction;
    }
    result.transaction_error=selection.error();result.exchange_error=selection.exchange_error();
    result.initial_rate_hz=selection.initial_rate_hz();result.verified_rate_hz=selection.verified_rate_hz();
    result.readback_rate_hz=selection.readback_rate_hz();result.acknowledgement_received=selection.acknowledgement_received();
    result.device_may_have_changed=selection.device_may_have_changed();
    io.transaction_finished(io.now_ms(),result.error);return result;
}
}
