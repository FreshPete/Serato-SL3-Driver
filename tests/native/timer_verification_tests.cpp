#include "core/timer_verification.hpp"
#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <string_view>

namespace {
using namespace sl3::control;
void require(bool value,const char* message){if(!value)throw std::runtime_error(message);}
template<std::size_t N> std::array<std::uint8_t,N> hex(std::string_view value){
    require(value.size()==2*N,"Fixture width");
    const auto nibble=[](char c)->unsigned {
        if(c>='0' && c<='9')return unsigned(c-'0');
        if(c>='a' && c<='f')return unsigned(c-'a'+10);
        throw std::runtime_error("Invalid fixture hex");
    };
    std::array<std::uint8_t,N> result{};
    for(std::size_t i=0;i<N;++i)result[i]=std::uint8_t(nibble(value[2*i])*16+nibble(value[2*i+1]));
    return result;
}
Event parsed_reply(const Challenge& challenge,const Challenge& response){
    Frame input{};input.fill(0xa7);input[0]=0x37;input[1]=0x1c;input[2]=0xc5;input[3]=0;input[4]=1;
    std::copy(response.begin(),response.end(),input.begin()+5);
    Exchange exchange(driver_timer_query(challenge));
    const auto event=exchange.accept(input.data(),input.size());
    require(event.outcome==Outcome::reply && event.payload_bytes==8,"Actual codec reply boundary");
    return event;
}
void vectors(){
    // Synthetic public test keys only. Expected values come from a separate
    // variable-word reference calculation, not from this two-word verifier.
    struct Vector {const char* challenge;const char* key;const char* response;};
    const Vector cases[]{
        {"0000000000000000","00000000000000000000000000000000","053704ab575d8c80"},
        {"0001020304050607","000102030405060708090a0b0c0d0e0f","121a0f715f2550ed"},
        {"0123456789abcdef","00112233445566778899aabbccddeeff","34354989dd7d1a7a"},
        {"ffffffffffffffff","ffffffffffffffffffffffffffffffff","09b03d2ab3560cb2"},
    };
    for(const auto& item:cases){
        const auto challenge=hex<8>(item.challenge);
        const auto key=hex<16>(item.key);
        const auto response=hex<8>(item.response);
        const auto event=parsed_reply(challenge,response);
        require(matches_driver_timer_reply(challenge,key,event),"Big-endian two-word known answer");
        const auto saved=event.payload;
        for(std::size_t byte=0;byte<8;++byte)for(unsigned bit=0;bit<8;++bit){
            auto changed=event;changed.payload[byte]^=std::uint8_t(1u<<bit);
            require(!matches_driver_timer_reply(challenge,key,changed),"Every received response bit matters");
            auto other=challenge;other[byte]^=std::uint8_t(1u<<bit);
            require(!matches_driver_timer_reply(other,key,event),"A reply for a different challenge is rejected");
        }
        for(std::size_t byte=0;byte<key.size();++byte)for(unsigned bit=0;bit<8;++bit){
            auto changed=key;changed[byte]^=std::uint8_t(1u<<bit);
            require(!matches_driver_timer_reply(challenge,changed,event),"Synthetic key bit mismatch");
        }
        require(saved==event.payload,"Verification does not mutate received data");
        auto reversed=response;std::reverse(reversed.begin(),reversed.end());
        require(!matches_driver_timer_reply(challenge,key,parsed_reply(challenge,reversed)),"Response byte order matters");
    }
}
void event_gate(){
    const Challenge challenge{};const TimerKey key{};
    const auto event=parsed_reply(challenge,hex<8>("053704ab575d8c80"));
    for(unsigned command=0;command<256;++command){
        if(command==0x37)continue;
        auto changed=event;changed.command=std::uint8_t(command);
        require(!matches_driver_timer_reply(challenge,key,changed),"Another command cannot verify");
    }
    for(std::size_t width=0;width<=maximum_reply_bytes;++width){
        if(width==8)continue;
        auto changed=event;changed.payload_bytes=width;
        require(!matches_driver_timer_reply(challenge,key,changed),"Exact reply width required");
    }
    for(const auto outcome:{Outcome::notification,Outcome::failed}){
        auto changed=event;changed.outcome=outcome;
        require(!matches_driver_timer_reply(challenge,key,changed),"Only reply events compare");
    }
    auto changed=event;changed.error=Error::invalid_tag;
    require(!matches_driver_timer_reply(challenge,key,changed),"Framing errors cannot verify");
    require(!matches_driver_timer_reply(challenge,key,Event{}),"Default event cannot verify");
}
}
int main(){try{vectors();event_gate();std::cout<<"Synthetic device-timer verification checks passed; no device I/O or embedded vendor key\n";return 0;}
catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}}
