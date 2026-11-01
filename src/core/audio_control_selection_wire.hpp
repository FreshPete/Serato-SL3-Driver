#pragma once
#include "core/audio_control_selection_io.hpp"
#include <algorithm>
#include <stdexcept>

namespace sl3::control::selection_wire {
// Serialization only. Not a worker command, ownership proof or write permission.
constexpr std::uint32_t magic=0x53334c53,version=1;
constexpr std::size_t request_bytes=24,reply_bytes=132;
struct Target {AudioControlSetting setting;unsigned group,value;};
struct Reply {Target target;SelectionIoResult selection;std::uint32_t native_error=0;};
using RequestBytes=std::array<std::uint8_t,request_bytes>;
using ReplyBytes=std::array<std::uint8_t,reply_bytes>;
namespace detail {
inline void require(bool ok){if(!ok)throw std::invalid_argument("Invalid control-selection evidence");}
inline bool same(Target a,Target b) noexcept{return a.setting==b.setting && a.group==b.group && a.value==b.value;}
inline std::size_t index(Target t){
    require(t.group<input_control_indexes.size() &&
        ((t.setting==AudioControlSetting::sensitivity && t.value<=15) || (t.setting==AudioControlSetting::through && t.value<=1)));
    const auto fields=input_control_indexes[t.group];return t.setting==AudioControlSetting::sensitivity?fields.sensitivity:fields.through;
}
inline std::uint32_t get(const std::uint8_t* b,std::size_t word) noexcept {
    std::uint32_t v=0;for(unsigned n=0;n<4;++n)v|=std::uint32_t(b[4*word+n])<<(8*n);return v;
}
template<std::size_t N> void put(std::array<std::uint8_t,N>& b,std::size_t word,std::uint32_t v) noexcept {
    for(unsigned n=0;n<4;++n)b[4*word+n]=std::uint8_t(v>>(8*n));
}
inline void validate(const Reply& r){
    const auto field=index(r.target);const auto& s=r.selection;
    require(unsigned(s.error)<=unsigned(SelectionIoError::readback_mismatch) && s.error!=SelectionIoError::invalid_target &&
        unsigned(s.selection_error)<=unsigned(AudioControlError::aborted) && unsigned(s.exchange_error)<=unsigned(Error::terminal_state));
    require(s.write_attempts<=3 && s.read_attempts<=12 && s.setter_attempts<=1 && s.read_attempts<=4*s.write_attempts);
    require(s.device_may_have_changed==(s.setter_attempts==1));
    require(bool(s.initial)==bool(s.observed));
    require(s.write_attempts<2 || (s.setter_attempts==1 && s.initial));
    require(!s.setter_attempts || (s.write_attempts>=2 && s.initial && s.initial->raw[field]!=r.target.value));
    require(s.write_attempts!=3 || bool(s.acknowledgement));
    require(!s.acknowledgement || (s.setter_attempts==1 && s.write_attempts>=2 && s.read_attempts>=2));
    require(!s.initial || (s.write_attempts>=1 && s.read_attempts>=1));
    require(!s.initial || (s.acknowledgement && s.write_attempts==3) || s.initial->raw==s.observed->raw);
    if(s.error==SelectionIoError::none){
        require(s.phase==AudioControlPhase::complete && s.selection_error==AudioControlError::none && s.exchange_error==Error::none &&
            s.initial && s.observed && s.verified && s.verified->raw==s.observed->raw && s.verified->raw[field]==r.target.value);
        if(s.setter_attempts)require(s.write_attempts==3 && s.read_attempts>=3 && s.acknowledgement);
        else require(s.write_attempts==1 && s.read_attempts>=1 && !s.acknowledgement && s.initial->raw==s.verified->raw);
    }else{
        require(s.phase==AudioControlPhase::failed && !s.verified && s.selection_error!=AudioControlError::none);
        require(!s.initial || s.initial->raw[field]!=r.target.value);
        if(s.error==SelectionIoError::readback_mismatch){
            require(s.selection_error==AudioControlError::readback_mismatch && s.exchange_error==Error::none &&
                s.write_attempts==3 && s.read_attempts>=3 && s.acknowledgement && s.observed && s.observed->raw[field]!=r.target.value);
        }else if(s.error==SelectionIoError::protocol){
            require((s.selection_error==AudioControlError::exchange && s.exchange_error!=Error::none) ||
                (s.selection_error==AudioControlError::aborted && s.exchange_error==Error::none));
        }else require(s.selection_error==AudioControlError::aborted && s.exchange_error==Error::none);
        if(s.error==SelectionIoError::invalid_budget)require(!s.write_attempts && !s.read_attempts && !s.setter_attempts && !s.initial);
    }
}
}
inline RequestBytes encode_request(Target t){
    detail::index(t);RequestBytes b{};
    detail::put(b,0,magic);detail::put(b,1,version);detail::put(b,2,unsigned(t.setting));
    detail::put(b,3,t.group);detail::put(b,4,t.value);return b;
}
inline Target decode_request(const std::uint8_t* b,std::size_t size){
    detail::require(b && size==request_bytes && detail::get(b,0)==magic && detail::get(b,1)==version && !detail::get(b,5));
    detail::require(detail::get(b,2)<=unsigned(AudioControlSetting::through));
    Target t{AudioControlSetting(detail::get(b,2)),detail::get(b,3),detail::get(b,4)};detail::index(t);return t;
}
inline ReplyBytes encode_reply(const Reply& r){
    detail::validate(r);ReplyBytes b{};const auto& s=r.selection;
    detail::put(b,0,magic);detail::put(b,1,version);detail::put(b,2,unsigned(r.target.setting));
    detail::put(b,3,r.target.group);detail::put(b,4,r.target.value);
    detail::put(b,5,unsigned(s.error));detail::put(b,6,unsigned(s.selection_error));detail::put(b,7,unsigned(s.exchange_error));
    detail::put(b,8,unsigned(s.phase));detail::put(b,9,s.write_attempts);detail::put(b,10,s.read_attempts);detail::put(b,11,s.setter_attempts);
    const auto flags=(s.device_may_have_changed?1u:0u)|(s.initial?2u:0u)|(s.observed?4u:0u)|(s.verified?8u:0u)|(s.acknowledgement?16u:0u);
    detail::put(b,12,flags);detail::put(b,15,r.native_error);
    std::size_t at=64;
    for(const auto* snapshot:{&s.initial,&s.observed,&s.verified}){
        if(*snapshot)std::copy((*snapshot)->raw.begin(),(*snapshot)->raw.end(),b.begin()+at);at+=22;
    }
    if(s.acknowledgement)std::copy(s.acknowledgement->begin(),s.acknowledgement->end(),b.begin()+at);
    return b;
}
inline Reply decode_reply(const std::uint8_t* b,std::size_t size,Target expected){
    detail::index(expected);
    detail::require(b && size==reply_bytes && detail::get(b,0)==magic && detail::get(b,1)==version &&
        !detail::get(b,13) && !detail::get(b,14) && !(detail::get(b,12)&~31u));
    detail::require(detail::get(b,2)<=unsigned(AudioControlSetting::through) &&
        detail::get(b,5)<=unsigned(SelectionIoError::readback_mismatch) &&
        detail::get(b,6)<=unsigned(AudioControlError::aborted) && detail::get(b,7)<=unsigned(Error::terminal_state) &&
        detail::get(b,8)<=unsigned(AudioControlPhase::failed));
    Reply r{{AudioControlSetting(detail::get(b,2)),detail::get(b,3),detail::get(b,4)},{},detail::get(b,15)};
    detail::require(detail::same(r.target,expected));auto& s=r.selection;
    s.error=SelectionIoError(detail::get(b,5));s.selection_error=AudioControlError(detail::get(b,6));s.exchange_error=Error(detail::get(b,7));
    s.phase=AudioControlPhase(detail::get(b,8));s.write_attempts=detail::get(b,9);s.read_attempts=detail::get(b,10);s.setter_attempts=detail::get(b,11);
    const auto flags=detail::get(b,12);s.device_may_have_changed=(flags&1)!=0;
    std::size_t at=64;unsigned present=2;
    for(auto* snapshot:{&s.initial,&s.observed,&s.verified}){
        if(flags&present){snapshot->emplace();std::copy_n(b+at,22,(*snapshot)->raw.begin());}
        at+=22;present<<=1;
    }
    if(flags&16)s.acknowledgement=std::array<std::uint8_t,2>{{b[130],b[131]}};
    // Re-encoding also rejects nonzero bytes in absent optional fields.
    const auto canonical=encode_reply(r);detail::require(std::equal(canonical.begin(),canonical.end(),b));return r;
}
}
