#include "core/session_protocol.hpp"
#include <array>
#include <stdexcept>

namespace sl3::session {
namespace {
void require(bool value){if(!value)throw std::invalid_argument("Invalid continuous-session payload");}
void put(std::vector<std::uint8_t>& bytes,std::uint32_t value){for(unsigned i=0;i<4;++i)bytes.push_back(std::uint8_t(value>>(8*i)));}
std::uint32_t get(const std::vector<std::uint8_t>& bytes,std::size_t word){
    require(word<=bytes.size()/4 && bytes.size()-word*4>=4);std::uint32_t value=0;
    for(unsigned i=0;i<4;++i)value|=std::uint32_t(bytes[word*4+i])<<(8*i);return value;
}
void put64(std::vector<std::uint8_t>& bytes,std::uint64_t value){put(bytes,std::uint32_t(value));put(bytes,std::uint32_t(value>>32));}
std::uint64_t get64(const std::vector<std::uint8_t>& bytes,std::size_t word){return get(bytes,word)|(std::uint64_t(get(bytes,word+1))<<32);}
void config(StreamConfig c){require((c.rate_hz==44100 || c.rate_hz==48000) && c.intervals>=8 && c.intervals<=64 &&
    c.intervals%8==0 && c.stall_ms && c.stall_ms<=1000 && c.drain_ms && c.drain_ms<=5000);}
void snapshot(const Snapshot& s){
    require(std::uint32_t(s.phase)<=std::uint32_t(Phase::retained) && std::uint32_t(s.failure)<=std::uint32_t(Failure::cleanup) &&
        unsigned(s.stream_fault)<=unsigned(StreamFault::release) && s.diagnostic.size()<=512);
    require((!s.rate_hz && !s.intervals) || ((s.rate_hz==44100 || s.rate_hz==48000) && s.intervals>=8 && s.intervals<=64 && s.intervals%8==0));
    require(s.stats.pending_mask<=255 && s.stats.retained_mask<=255 && s.stats.expected_outputs<=16);
    require(!s.device_released || s.io_retired);
    require(!s.io_retired || (!s.stats.pending_mask && !s.stats.retained_mask));
    require(s.phase!=Phase::idle || (!s.rate_hz && s.io_retired && s.device_released));
    require(s.phase!=Phase::running || (s.rate_hz && !s.io_retired && !s.device_released));
    require(s.phase!=Phase::stopped || (s.io_retired && s.device_released));
    require(s.stats.input_submissions>=s.stats.input_blocks && s.stats.output_submissions<=s.stats.input_blocks &&
        s.stats.output_completions<=s.stats.output_submissions && s.stats.output_frames_submitted<=s.stats.input_frames);
}
}
std::vector<std::uint8_t> encode_hello(Kind kind){
    require(kind==Kind::native || kind==Kind::simulated);std::vector<std::uint8_t> bytes;bytes.reserve(32);
    for(auto value:std::array<std::uint32_t,8>{{version,std::uint32_t(kind),queue_version,6,3,18,8,64}})put(bytes,value);return bytes;
}
Kind decode_hello(const std::vector<std::uint8_t>& bytes){
    require(bytes.size()==32 && get(bytes,0)==version);const auto kind=Kind(get(bytes,1));
    require(kind==Kind::native || kind==Kind::simulated);require(bytes==encode_hello(kind));return kind;
}
std::vector<std::uint8_t> encode_clock(unsigned rate){
    require(rate==44100 || rate==48000);std::vector<std::uint8_t> bytes;bytes.reserve(32);
    for(auto value:std::array<std::uint32_t,8>{{version,rate,6,3,18,3,0,0}})put(bytes,value);return bytes;
}
unsigned decode_clock(const std::vector<std::uint8_t>& bytes){
    require(bytes.size()==32);const auto rate=get(bytes,1);require(bytes==encode_clock(rate));return rate;
}
std::vector<std::uint8_t> encode_start(StreamConfig c){
    config(c);std::vector<std::uint8_t> bytes;bytes.reserve(32);
    for(auto value:std::array<std::uint32_t,8>{{version,c.rate_hz,c.intervals,c.stall_ms,c.drain_ms,0,0,0}})put(bytes,value);return bytes;
}
StreamConfig decode_start(const std::vector<std::uint8_t>& bytes){
    require(bytes.size()==32 && get(bytes,0)==version && !get(bytes,5) && !get(bytes,6) && !get(bytes,7));
    StreamConfig c{get(bytes,1),get(bytes,2),get(bytes,3),get(bytes,4)};config(c);return c;
}
std::vector<std::uint8_t> encode_snapshot(const Snapshot& s){
    snapshot(s);std::vector<std::uint8_t> bytes;bytes.reserve(128+s.diagnostic.size());
    for(auto value:std::array<std::uint32_t,12>{{version,std::uint32_t(s.phase),std::uint32_t(s.failure),std::uint32_t(s.stream_fault),
        s.rate_hz,s.intervals,(s.io_retired?1u:0u)|(s.device_released?2u:0u),s.stats.pending_mask,s.stats.retained_mask,
        s.stats.expected_outputs,s.native_error,std::uint32_t(s.diagnostic.size())}})put(bytes,value);
    put64(bytes,s.stats.input_submissions);put64(bytes,s.stats.output_submissions);put64(bytes,s.stats.input_blocks);
    put64(bytes,s.stats.input_frames);put64(bytes,s.stats.output_frames_submitted);put64(bytes,s.stats.output_completions);
    for(unsigned i=0;i<8;++i)put(bytes,0);bytes.insert(bytes.end(),s.diagnostic.begin(),s.diagnostic.end());return bytes;
}
Snapshot decode_snapshot(const std::vector<std::uint8_t>& bytes){
    require(bytes.size()>=128 && bytes.size()<=640 && get(bytes,0)==version && get(bytes,11)==bytes.size()-128 && (get(bytes,6)&~3u)==0);
    for(unsigned i=24;i<32;++i)require(!get(bytes,i));Snapshot s;
    s.phase=Phase(get(bytes,1));s.failure=Failure(get(bytes,2));s.stream_fault=StreamFault(get(bytes,3));
    s.rate_hz=get(bytes,4);s.intervals=get(bytes,5);s.io_retired=(get(bytes,6)&1)!=0;s.device_released=(get(bytes,6)&2)!=0;
    s.stats.pending_mask=get(bytes,7);s.stats.retained_mask=get(bytes,8);s.stats.expected_outputs=get(bytes,9);s.native_error=get(bytes,10);
    s.stats.input_submissions=get64(bytes,12);s.stats.output_submissions=get64(bytes,14);s.stats.input_blocks=get64(bytes,16);
    s.stats.input_frames=get64(bytes,18);s.stats.output_frames_submitted=get64(bytes,20);s.stats.output_completions=get64(bytes,22);
    s.diagnostic.assign(bytes.begin()+128,bytes.end());snapshot(s);return s;
}
}
