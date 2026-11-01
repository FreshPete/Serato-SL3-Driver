#pragma once
#include "core/control_frames.hpp"
#include <algorithm>
#include <optional>
#include <stdexcept>
#include <string_view>

namespace sl3::control {
inline Challenge parse_driver_timer_challenge(std::wstring_view text){
    if(text.size()!=16)throw std::invalid_argument("Timer challenge must be exactly sixteen hexadecimal digits");
    auto digit=[](wchar_t value)->unsigned{
        if(value>=L'0' && value<=L'9')return unsigned(value-L'0');
        if(value>=L'a' && value<=L'f')return unsigned(value-L'a')+10;
        if(value>=L'A' && value<=L'F')return unsigned(value-L'A')+10;
        throw std::invalid_argument("Invalid timer challenge digit");
    };
    Challenge result{};
    for(std::size_t i=0;i<result.size();++i)result[i]=std::uint8_t((digit(text[2*i])<<4)|digit(text[2*i+1]));
    return result;
}
class DriverTimerIo {
public:
    virtual ~DriverTimerIo()=default;
    virtual std::uint64_t now_ms() noexcept=0;
    virtual bool cancelled() noexcept=0;
    // Every return requires retired I/O/storage, including failure. Otherwise
    // retain storage and contain the isolated worker instead of returning.
    virtual bool transfer(bool output,Frame&,unsigned timeout_ms,std::size_t& bytes) noexcept=0;
};
enum class DriverTimerError {none,invalid_budget,cancelled,deadline,transfer,exchange};
struct DriverTimerResult {
    DriverTimerError error=DriverTimerError::none;
    Error exchange_error=Error::none;
    unsigned write_attempts=0,read_attempts=0;
    std::optional<Challenge> response;
};
constexpr unsigned driver_timer_budget_ms=1500;
// One real 0x37 request, at most four complete received frames, no retry.
// Response parsing is not device authentication, key verification or readiness.
inline DriverTimerResult inspect_driver_timer(const Challenge& challenge,DriverTimerIo& io,
                                              unsigned budget_ms=driver_timer_budget_ms) noexcept {
    DriverTimerResult result;
    if(!budget_ms || budget_ms>driver_timer_budget_ms){result.error=DriverTimerError::invalid_budget;return result;}
    Exchange exchange(driver_timer_query(challenge));const auto entered=io.now_ms();
    for(unsigned operation=0;operation<=maximum_received_frames;++operation){
        if(io.cancelled()){result.error=DriverTimerError::cancelled;return result;}
        const auto now=io.now_ms();
        if(now<entered || now-entered>=budget_ms){result.error=DriverTimerError::deadline;return result;}
        const bool output=operation==0;Frame frame=output?exchange.query().frame():Frame{};
        const auto timeout=std::min(output?100u:300u,budget_ms-unsigned(now-entered));
        if(output)++result.write_attempts;else ++result.read_attempts;
        std::size_t bytes=0;const bool transferred=io.transfer(output,frame,timeout,bytes);
        const auto completed=io.now_ms();
        if(io.cancelled()){result.error=DriverTimerError::cancelled;return result;}
        if(completed<now || completed-entered>=budget_ms){result.error=DriverTimerError::deadline;return result;}
        if(!transferred || bytes!=frame_bytes){result.error=DriverTimerError::transfer;return result;}
        if(output)continue;
        const auto event=exchange.accept(frame.data(),bytes);
        if(event.outcome==Outcome::failed){result.error=DriverTimerError::exchange;result.exchange_error=event.error;return result;}
        if(event.outcome==Outcome::reply){
            if(event.payload_bytes!=Challenge{}.size()){result.error=DriverTimerError::exchange;result.exchange_error=Error::invalid_size;return result;}
            Challenge response{};std::copy_n(event.payload.begin(),response.size(),response.begin());result.response=response;return result;
        }
    }
    result.error=DriverTimerError::exchange;result.exchange_error=Error::frame_limit;return result;
}
}
