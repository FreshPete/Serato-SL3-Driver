#pragma once
#include <optional>
#include <stdexcept>
#include <string_view>

namespace sl3::control {
inline unsigned parse_rate_test_target(std::wstring_view text){
    if(text==L"44100")return 44100;
    if(text==L"48000")return 48000;
    throw std::invalid_argument("Rate-test target must be exactly 44100 or 48000");
}
// Process-local diagnostic configuration, never a persisted permission token or
// proof of device ownership. An attempt consumes this target before any I/O.
class RateTestGrant final {
    unsigned target_=0;bool consumed_=false;
public:
    explicit RateTestGrant(std::optional<unsigned> target={}){
        if(target){
            if(*target!=44100 && *target!=48000)throw std::invalid_argument("Invalid rate-test target");
            target_=*target;
        }
    }
    RateTestGrant(const RateTestGrant&)=delete;
    RateTestGrant& operator=(const RateTestGrant&)=delete;
    bool enabled() const noexcept{return target_!=0;}
    bool available() const noexcept{return enabled() && !consumed_;}
    bool consume(unsigned target) noexcept{
        if(!available())return false;
        consumed_=true;return target==target_;
    }
};
}
