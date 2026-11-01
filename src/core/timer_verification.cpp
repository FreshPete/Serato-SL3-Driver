#include "timer_verification.hpp"

namespace sl3::control {
namespace {
std::uint32_t big_endian_word(const std::uint8_t* bytes) noexcept {
    return (std::uint32_t{bytes[0]}<<24)|(std::uint32_t{bytes[1]}<<16)|
           (std::uint32_t{bytes[2]}<<8)|std::uint32_t{bytes[3]};
}
std::uint32_t mix(std::uint32_t previous,std::uint32_t next,std::uint32_t sum,
                  std::uint32_t key) noexcept {
    return (((previous>>5)^(next<<2))+((next>>3)^(previous<<4))) ^
           ((sum^next)+(key^previous));
}
}
bool matches_driver_timer_reply(const Challenge& challenge,const TimerKey& key,const Event& reply) noexcept {
    if(reply.outcome!=Outcome::reply || reply.error!=Error::none || reply.command!=0x37 || reply.payload_bytes!=8)
        return false;
    std::array<std::uint32_t,4> words{};
    for(std::size_t i=0;i<words.size();++i)words[i]=big_endian_word(key.data()+i*4);
    std::uint32_t first=big_endian_word(challenge.data());
    std::uint32_t second=big_endian_word(challenge.data()+4);
    std::uint32_t sum=0;
    for(unsigned round=0;round<32;++round){
        sum+=0x9e3779b9u;
        const auto selection=(sum>>2)&3u;
        first+=mix(second,second,sum,words[selection]);
        second+=mix(first,first,sum,words[selection^1u]);
    }
    const auto difference=(first^big_endian_word(reply.payload.data()))|
                          (second^big_endian_word(reply.payload.data()+4));
    return difference==0;
}
}
