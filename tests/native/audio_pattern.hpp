#pragma once
#include "windows/audio_ring.hpp"

// Synthetic test contract only. No USB timing, analogue mapping or clock claim.
namespace pattern {
constexpr unsigned process_blocks=400;
inline std::int32_t value(std::uint64_t frame,unsigned channel) noexcept {
    switch((frame+channel)%7){
    case 0:return -8388608;
    case 1:return 8388607;
    case 2:return -1;
    case 3:return 0;
    case 4:return 1;
    default:return static_cast<std::int32_t>((frame*7919+channel*104729)%0x1000000)-8388608;
    }
}
inline void pack(std::int32_t sample,std::uint8_t* out) noexcept {
    const auto bits=static_cast<std::uint32_t>(sample);
    out[0]=static_cast<std::uint8_t>(bits);out[1]=static_cast<std::uint8_t>(bits>>8);out[2]=static_cast<std::uint8_t>(bits>>16);
}
inline std::size_t frames(const sl3::worker::AudioBlock& block) noexcept {
    std::size_t result=0;for(auto count:block.frames_per_packet)result+=count;return result;
}
inline sl3::worker::AudioBlock input(unsigned number,std::uint64_t position,unsigned rate,unsigned packets=0) noexcept {
    sl3::worker::AudioBlock result;result.first_frame=position;result.host_observation_ns=1000+number;result.reported_rate_hz=rate;
    result.packet_count=packets?packets:8*(1+number%8);
    for(std::size_t i=0;i<result.packet_count;++i)result.frames_per_packet[i]=number%11==0?7:(number%11==1?1:std::uint8_t(1+(number+i)%7));
    const auto frame_count=frames(result);
    for(std::size_t f=0;f<frame_count;++f)for(unsigned c=0;c<6;++c)pack(value(position+f,c),result.pcm.data()+f*18+c*3);
    return result;
}
inline bool output_matches(const sl3::worker::AudioBlock& block,unsigned number,std::uint64_t position,unsigned rate,unsigned bank_frames,unsigned packets=0) noexcept {
    const auto schedule=input(number,position,rate,packets);
    if(block.first_frame!=position || block.host_observation_ns!=schedule.host_observation_ns ||
       block.reported_rate_hz!=rate || block.packet_count!=schedule.packet_count || block.frames_per_packet!=schedule.frames_per_packet)return false;
    for(std::size_t f=0;f<frames(block);++f)for(unsigned c=0;c<6;++c){
        std::uint8_t packed[3]{};
        pack(position+f>=2*bank_frames?value(position+f-2*bank_frames,5-c):0,packed);
        for(unsigned byte=0;byte<3;++byte)if(block.pcm[f*18+c*3+byte]!=packed[byte])return false;
    }
    return true;
}
}
