#include "core/worker_protocol.hpp"
#include <array>
#include <numeric>
#include <stdexcept>

namespace sl3::protocol {
namespace {
void require(bool value){if(!value)throw std::invalid_argument("Invalid typed worker payload");}
void put(std::vector<std::uint8_t>& bytes,std::uint32_t value){
    for(unsigned i=0;i<4;++i)bytes.push_back(std::uint8_t(value>>(i*8)));
}
std::uint32_t get(const std::vector<std::uint8_t>& bytes,std::size_t index){
    require(index<=bytes.size()/4 && bytes.size()-index*4>=4);
    std::uint32_t value=0;
    for(unsigned i=0;i<4;++i)value|=std::uint32_t(bytes[index*4+i])<<(i*8);
    return value;
}
std::size_t frames(const CaptureBatch& batch){
    require(batch.reported_rate_hz==44100 || batch.reported_rate_hz==48000);
    require(batch.frames_per_packet.size()==intervals);
    std::size_t count=0;
    for(const auto length:batch.frames_per_packet){require(length>=1 && length<=7);count+=length;}
    require(batch.pcm.size()==count*18);return count;
}
}
std::vector<std::uint8_t> encode_hello(){
    std::vector<std::uint8_t> bytes;bytes.reserve(32);
    for(const auto value:std::array<std::uint32_t,8>{{version,descriptor_probe|finite_input,6,3,18,126,256,32000}})put(bytes,value);
    return bytes;
}
Hello decode_hello(const std::vector<std::uint8_t>& bytes){
    require(bytes.size()==32 && get(bytes,0)==version);
    const auto features=get(bytes,1);
    require(features==(descriptor_probe|finite_input));
    const std::array<std::uint32_t,6> format{{6,3,18,126,256,32000}};
    for(std::size_t i=0;i<format.size();++i)require(get(bytes,i+2)==format[i]);
    return {features};
}
std::vector<std::uint8_t> encode_probe(){
    std::vector<std::uint8_t> bytes;bytes.reserve(32);
    // Descriptor match only. No redirection, rate measurement or audio result.
    for(const auto value:std::array<std::uint32_t,8>{{version,0x1cc5,1,3,235,1,0,0}})put(bytes,value);
    return bytes;
}
void validate_probe(const std::vector<std::uint8_t>& bytes){require(bytes==encode_probe());}
std::vector<std::uint8_t> encode_capture(const CaptureBatch& batch){
    const auto count=frames(batch);
    std::vector<std::uint8_t> bytes;bytes.reserve(32+intervals+batch.pcm.size());
    // Flag 1 means native transfer/alternate/redirection cleanup completed.
    // No continuous-clock, analogue, latency or sample-timestamp flag exists.
    for(const auto value:std::array<std::uint32_t,8>{{version,batch.reported_rate_hz,256,std::uint32_t(count),
        std::uint32_t(batch.pcm.size()),1,0,0}})put(bytes,value);
    bytes.insert(bytes.end(),batch.frames_per_packet.begin(),batch.frames_per_packet.end());
    bytes.insert(bytes.end(),batch.pcm.begin(),batch.pcm.end());return bytes;
}
CaptureBatch decode_capture(const std::vector<std::uint8_t>& bytes){
    require(bytes.size()>=32+intervals && bytes.size()<=maximum_reply);
    require(get(bytes,0)==version && get(bytes,2)==intervals && get(bytes,5)==1 && get(bytes,6)==0 && get(bytes,7)==0);
    CaptureBatch batch;batch.reported_rate_hz=get(bytes,1);
    batch.frames_per_packet.assign(bytes.begin()+32,bytes.begin()+32+intervals);
    batch.pcm.assign(bytes.begin()+32+intervals,bytes.end());
    require(get(bytes,3)==frames(batch) && get(bytes,4)==batch.pcm.size());return batch;
}
}
