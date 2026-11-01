#pragma once
#include "core/rate_diagnostic.hpp"
#include <algorithm>
#include <stdexcept>

namespace sl3::control::rate_wire {
// Serialization only: no worker command, capability grant or device ownership.
constexpr std::uint32_t magic=0x52334c53,version=1;
constexpr std::size_t request_bytes=16,reply_bytes=64;
using RequestBytes=std::array<std::uint8_t,request_bytes>;
using ReplyBytes=std::array<std::uint8_t,reply_bytes>;
struct Reply {unsigned target_hz;RateDiagnosticResult observation;std::uint32_t native_error=0;};
namespace detail {
inline void require(bool value){if(!value)throw std::invalid_argument("Invalid rate-selection evidence");}
inline bool rate(unsigned value) noexcept{return value==44100 || value==48000;}
inline std::uint32_t get(const std::uint8_t* b,std::size_t word) noexcept {
    std::uint32_t value=0;for(unsigned n=0;n<4;++n)value|=std::uint32_t(b[4*word+n])<<(8*n);return value;
}
template<std::size_t N> void put(std::array<std::uint8_t,N>& b,std::size_t word,std::uint32_t value) noexcept {
    for(unsigned n=0;n<4;++n)b[4*word+n]=std::uint8_t(value>>(8*n));
}
inline void validate(const Reply& reply){
    const auto& s=reply.observation;const auto target=reply.target_hz;
    require(rate(target) && (!s.initial_rate_hz || rate(s.initial_rate_hz)) &&
        (!s.verified_rate_hz || rate(s.verified_rate_hz)) && (!s.readback_rate_hz || rate(s.readback_rate_hz)));
    require(unsigned(s.error)<=unsigned(DiagnosticError::transaction) && s.error!=DiagnosticError::invalid_target &&
        unsigned(s.transaction_error)<=unsigned(RateError::aborted) && s.transaction_error!=RateError::invalid_target &&
        unsigned(s.exchange_error)<=unsigned(Error::terminal_state));
    require(s.write_attempts<=3 && s.read_attempts<=12 && s.read_attempts<=4*s.write_attempts && s.setter_attempts<=1);
    require(s.device_may_have_changed==bool(s.setter_attempts) && (s.write_attempts<2 || s.setter_attempts==1));
    require(!s.setter_attempts || (s.write_attempts>=2 && s.initial_rate_hz && s.initial_rate_hz!=target));
    require(!s.initial_rate_hz || (s.write_attempts>=1 && s.read_attempts>=1));
    require(!s.acknowledgement_received || (s.setter_attempts==1 && s.write_attempts>=2 && s.read_attempts>=2));
    require(s.write_attempts!=3 || s.acknowledgement_received);
    require(!s.readback_rate_hz || (s.acknowledgement_received && s.write_attempts==3 && s.read_attempts>=3));
    if(s.error==DiagnosticError::none){
        require(s.transaction_error==RateError::none && s.exchange_error==Error::none && s.initial_rate_hz && s.verified_rate_hz==target);
        if(s.setter_attempts)require(s.acknowledgement_received && s.readback_rate_hz==target && s.write_attempts==3 && s.read_attempts>=3);
        else require(!s.acknowledgement_received && !s.readback_rate_hz && s.initial_rate_hz==target && s.write_attempts==1 && s.read_attempts>=1);
    }else{
        require(!s.verified_rate_hz && s.initial_rate_hz!=target);
        if(s.transaction_error==RateError::readback_mismatch){
            require(s.error==DiagnosticError::transaction && s.exchange_error==Error::none && s.readback_rate_hz && s.readback_rate_hz!=target);
        }else{
            require(!s.readback_rate_hz);
            require((s.error==DiagnosticError::transaction && s.transaction_error==RateError::exchange && s.exchange_error!=Error::none) ||
                (s.transaction_error==RateError::aborted && s.exchange_error==Error::none));
            if(s.transaction_error==RateError::exchange)require((!s.initial_rate_hz || s.write_attempts>=2) && (!s.acknowledgement_received || s.write_attempts==3));
        }
    }
}
}
inline RequestBytes encode_request(unsigned target){
    detail::require(detail::rate(target));RequestBytes b{};
    detail::put(b,0,magic);detail::put(b,1,version);detail::put(b,2,target);return b;
}
inline unsigned decode_request(const std::uint8_t* b,std::size_t size){
    detail::require(b && size==request_bytes && detail::get(b,0)==magic && detail::get(b,1)==version && !detail::get(b,3));
    const auto target=detail::get(b,2);detail::require(detail::rate(target));return target;
}
inline ReplyBytes encode_reply(const Reply& reply){
    detail::validate(reply);ReplyBytes b{};const auto& s=reply.observation;
    detail::put(b,0,magic);detail::put(b,1,version);detail::put(b,2,reply.target_hz);
    detail::put(b,3,unsigned(s.error));detail::put(b,4,unsigned(s.transaction_error));detail::put(b,5,unsigned(s.exchange_error));
    detail::put(b,6,s.initial_rate_hz);detail::put(b,7,s.verified_rate_hz);detail::put(b,8,s.readback_rate_hz);
    detail::put(b,9,s.write_attempts);detail::put(b,10,s.read_attempts);detail::put(b,11,s.setter_attempts);
    detail::put(b,12,(s.device_may_have_changed?1u:0u)|(s.acknowledgement_received?2u:0u));
    detail::put(b,13,reply.native_error);return b;
}
inline Reply decode_reply(const std::uint8_t* b,std::size_t size,unsigned expected_target){
    detail::require(detail::rate(expected_target));
    detail::require(b && size==reply_bytes && detail::get(b,0)==magic && detail::get(b,1)==version &&
        detail::get(b,2)==expected_target && !(detail::get(b,12)&~3u) && !detail::get(b,14) && !detail::get(b,15));
    detail::require(detail::get(b,3)<=unsigned(DiagnosticError::transaction) && detail::get(b,4)<=unsigned(RateError::aborted) &&
        detail::get(b,5)<=unsigned(Error::terminal_state));
    Reply reply{expected_target,{ },detail::get(b,13)};auto& s=reply.observation;
    s.error=DiagnosticError(detail::get(b,3));s.transaction_error=RateError(detail::get(b,4));s.exchange_error=Error(detail::get(b,5));
    s.initial_rate_hz=detail::get(b,6);s.verified_rate_hz=detail::get(b,7);s.readback_rate_hz=detail::get(b,8);
    s.write_attempts=detail::get(b,9);s.read_attempts=detail::get(b,10);s.setter_attempts=detail::get(b,11);
    s.device_may_have_changed=(detail::get(b,12)&1)!=0;s.acknowledgement_received=(detail::get(b,12)&2)!=0;
    const auto canonical=encode_reply(reply);detail::require(std::equal(canonical.begin(),canonical.end(),b));return reply;
}
}
