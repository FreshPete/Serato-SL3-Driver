#include "core/device_session_protocol.hpp"
#include <algorithm>
#include <array>
#include <stdexcept>

namespace sl3::device_session {
namespace {
void require(bool value){if(!value)throw std::invalid_argument("Invalid retained-device payload");}
void put(std::vector<std::uint8_t>& b,std::uint32_t v){for(unsigned i=0;i<4;++i)b.push_back(std::uint8_t(v>>(8*i)));}
std::uint32_t get(const std::vector<std::uint8_t>& b,std::size_t w){
    require(w<b.size()/4);std::uint32_t v=0;for(unsigned i=0;i<4;++i)v|=std::uint32_t(b[w*4+i])<<(8*i);return v;
}
void put64(std::vector<std::uint8_t>& b,std::uint64_t v){put(b,std::uint32_t(v));put(b,std::uint32_t(v>>32));}
std::uint64_t get64(const std::vector<std::uint8_t>& b,std::size_t w){return get(b,w)|(std::uint64_t(get(b,w+1))<<32);}
bool channel(const std::wstring& name){
    const std::wstring prefix=L"Local\\SL3Mailbox-";
    return name.size()==prefix.size()+32 && name.compare(0,prefix.size(),prefix)==0 &&
        std::all_of(name.begin()+static_cast<std::ptrdiff_t>(prefix.size()),name.end(),[](wchar_t c){return (c>=L'0' && c<=L'9') || (c>=L'a' && c<=L'f');});
}
void validate(const Snapshot& s){
    require(unsigned(s.phase)<=unsigned(Phase::closed) && unsigned(s.failure)<=unsigned(session::Failure::cleanup) &&
        unsigned(s.stream_fault)<=unsigned(StreamFault::release) && s.diagnostic.size()<=512);
    require(!s.rate_hz || s.rate_hz==44100 || s.rate_hz==48000);
    require(!s.intervals || (s.intervals>=8 && s.intervals<=64 && s.intervals%8==0 && s.rate_hz));
    require(s.stats.pending_mask<=255 && s.stats.retained_mask<=255 && s.stats.expected_outputs<=16);
    require(!s.device_released || s.io_retired);
    require(!s.selection_supported || !s.device_released);
    require(!s.io_retired || (!s.stats.pending_mask && !s.stats.retained_mask));
    require(s.phase!=Phase::empty || (!s.rate_hz && !s.intervals && s.io_retired && s.device_released));
    require(s.phase!=Phase::ready || (s.rate_hz && s.io_retired && !s.device_released && s.failure==session::Failure::none));
    require(s.phase!=Phase::running || (s.rate_hz && s.intervals && !s.io_retired && !s.device_released));
    require(s.phase!=Phase::closed || (s.io_retired && s.device_released));
    require(s.phase!=Phase::retained || !s.device_released);
    require(s.stats.input_submissions>=s.stats.input_blocks && s.stats.output_submissions<=s.stats.input_blocks &&
        s.stats.output_completions<=s.stats.output_submissions && s.stats.output_frames_submitted<=s.stats.input_frames);
}
}
std::vector<std::uint8_t> encode_hello(session::Kind kind){
    require(kind==session::Kind::native || kind==session::Kind::simulated);std::vector<std::uint8_t> b;
    for(auto v:std::array<std::uint32_t,10>{{magic,version,std::uint32_t(kind),session::queue_version,6,3,18,8,64,0}})put(b,v);return b;
}
session::Kind decode_hello(const std::vector<std::uint8_t>& b){
    require(b.size()==40);const auto kind=session::Kind(get(b,2));require(b==device_session::encode_hello(kind));return kind;
}
std::vector<std::uint8_t> encode_start(const Start& s){
    require(channel(s.audio_channel));auto b=session::encode_start(s.config);put(b,std::uint32_t(s.audio_channel.size()));
    for(const auto c:s.audio_channel)b.push_back(std::uint8_t(c));return b;
}
Start decode_start(const std::vector<std::uint8_t>& b){
    require(b.size()>=36 && b.size()<=128 && get(b,8)==b.size()-36);
    Start s;s.config=session::decode_start(std::vector<std::uint8_t>(b.begin(),b.begin()+32));
    for(std::size_t i=36;i<b.size();++i)s.audio_channel.push_back(wchar_t(b[i]));require(channel(s.audio_channel));return s;
}
std::vector<std::uint8_t> encode_snapshot(const Snapshot& s){
    validate(s);std::vector<std::uint8_t> b;
    for(auto v:std::array<std::uint32_t,14>{{magic,version,unsigned(s.phase),unsigned(s.failure),unsigned(s.stream_fault),s.rate_hz,s.intervals,
        (s.io_retired?1u:0u)|(s.device_released?2u:0u)|(s.selection_supported?4u:0u),s.stats.pending_mask,s.stats.retained_mask,s.stats.expected_outputs,s.native_error,unsigned(s.diagnostic.size()),0}})put(b,v);
    put64(b,s.stats.input_submissions);put64(b,s.stats.output_submissions);put64(b,s.stats.input_blocks);put64(b,s.stats.input_frames);
    put64(b,s.stats.output_frames_submitted);put64(b,s.stats.output_completions);
    for(unsigned i=0;i<6;++i)put(b,0);b.insert(b.end(),s.diagnostic.begin(),s.diagnostic.end());return b;
}
Snapshot decode_snapshot(const std::vector<std::uint8_t>& b){
    require(b.size()>=128 && b.size()<=640 && get(b,0)==magic && get(b,1)==version && get(b,12)==b.size()-128 && !(get(b,7)&~7u));
    require(!get(b,13));for(unsigned i=26;i<32;++i)require(!get(b,i));Snapshot s;
    s.phase=Phase(get(b,2));s.failure=session::Failure(get(b,3));s.stream_fault=StreamFault(get(b,4));s.rate_hz=get(b,5);s.intervals=get(b,6);
    s.io_retired=(get(b,7)&1)!=0;s.device_released=(get(b,7)&2)!=0;s.stats.pending_mask=get(b,8);s.stats.retained_mask=get(b,9);
    s.selection_supported=(get(b,7)&4)!=0;
    s.stats.expected_outputs=get(b,10);s.native_error=get(b,11);s.stats.input_submissions=get64(b,14);s.stats.output_submissions=get64(b,16);
    s.stats.input_blocks=get64(b,18);s.stats.input_frames=get64(b,20);s.stats.output_frames_submitted=get64(b,22);s.stats.output_completions=get64(b,24);
    s.diagnostic.assign(b.begin()+128,b.end());validate(s);return s;
}
std::vector<std::uint8_t> encode_controls(const ControlsReply& value){
    require(value.device.phase==Phase::ready && value.device.failure==session::Failure::none && value.device.stream_fault==StreamFault::none
            && value.sample.received_frames>=1 && value.sample.received_frames<=control::maximum_received_frames);
    auto body=encode_snapshot(value.device);put(body,value.sample.received_frames);
    body.insert(body.end(),value.sample.audio.raw.begin(),value.sample.audio.raw.end());return body;
}
ControlsReply decode_controls(const std::vector<std::uint8_t>& body){
    require(body.size()>=154 && body.size()<=666);
    const auto owner_bytes=body.size()-26;
    const auto owner=std::vector<std::uint8_t>(body.begin(),body.begin()+owner_bytes);
    ControlsReply value;value.device=decode_snapshot(owner);
    value.sample.received_frames=get(std::vector<std::uint8_t>(body.begin()+owner_bytes,body.begin()+owner_bytes+4),0);
    std::copy_n(body.begin()+owner_bytes+4,22,value.sample.audio.raw.begin());
    require(encode_controls(value)==body);return value;
}
std::vector<std::uint8_t> encode_selection(const SelectionReply& value){
    const auto& d=value.device;
    require(d.io_retired && !d.device_released && d.selection_supported && d.stream_fault==StreamFault::none &&
            d.native_error==value.outcome.native_error);
    const bool success=value.outcome.selection.error==control::SelectionIoError::none;
    require(success?(d.phase==Phase::ready && d.failure==session::Failure::none):
                    (d.phase==Phase::failed && d.failure==session::Failure::control));
    auto body=encode_snapshot(d);const auto selection=control::selection_wire::encode_reply(value.outcome);
    body.insert(body.end(),selection.begin(),selection.end());return body;
}
SelectionReply decode_selection(const std::vector<std::uint8_t>& body,control::selection_wire::Target expected){
    require(body.size()>=128+control::selection_wire::reply_bytes && body.size()<=640+control::selection_wire::reply_bytes);
    const auto owner_bytes=body.size()-control::selection_wire::reply_bytes;
    SelectionReply value{decode_snapshot(std::vector<std::uint8_t>(body.begin(),body.begin()+owner_bytes)),
        control::selection_wire::decode_reply(body.data()+owner_bytes,control::selection_wire::reply_bytes,expected)};
    require(encode_selection(value)==body);return value;
}
}
