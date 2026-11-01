#include "core/continuous.hpp"
#include <cstring>
#include <limits>

namespace sl3 {
namespace {constexpr std::uint64_t ns_per_ms=1000000;}
ContinuousStream::ContinuousStream(ContinuousBackend& backend,ContinuousPeer& peer) noexcept:backend_(backend),peer_(peer) {}
StreamStats ContinuousStream::stats() const noexcept {
    auto result=stats_;result.expected_outputs=expected_count_;result.pending_mask=0;
    for(unsigned i=0;i<8;++i)if(slots_[i].pending)result.pending_mask|=1u<<i;
    return result;
}
void ContinuousStream::begin_drain(std::uint64_t now) noexcept {
    if(state_==StreamState::draining || state_==StreamState::stopped || state_==StreamState::retained)return;
    state_=StreamState::draining;drain_since_=now;
    // Cancel ALL pending directions before observing/draining any one request.
    // Failed cancellation never changes the memory lease or pending flag.
    for(unsigned i=0;i<8;++i)if(slots_[i].pending)backend_.cancel(i);
}
void ContinuousStream::fail(StreamFault cause,std::uint64_t now) noexcept {
    if(fault_==StreamFault::none)fault_=cause;
    begin_drain(now);
}
bool ContinuousStream::start(StreamConfig config) noexcept {
    if(state_!=StreamState::ready)return false;
    if((config.rate_hz!=44100 && config.rate_hz!=48000) || config.intervals<8 || config.intervals>64 ||
       config.intervals%8 || !config.stall_ms || config.stall_ms>1000 || !config.drain_ms || config.drain_ms>5000){
        fault_=StreamFault::configuration;return false;
    }
    config_=config;fault_=StreamFault::none;last_time_=backend_.now_ns();
    for(unsigned i=0;i<8;++i){
        if(!backend_.prepare(i,config.intervals)){fail(StreamFault::prepare,last_time_);drain(last_time_);return false;}
        slots_[i].prepared=true;
    }
    const auto prepared_time=backend_.now_ns();
    if(prepared_time<last_time_){clock_lost_=true;fail(StreamFault::clock,last_time_);drain(last_time_);return false;}
    last_time_=prepared_time; // Resource allocation is not a pending-I/O stall.
    for(unsigned i=0;i<4;++i){
        if(!backend_.submit_input(i,i!=0)){fail(StreamFault::submit,last_time_);drain(last_time_);return false;}
        slots_[i].pending=true;slots_[i].since=last_time_;++stats_.input_submissions;
    }
    state_=StreamState::running;return true;
}
bool ContinuousStream::pack(unsigned slot,std::uint64_t now) noexcept {
    const auto& raw=input_[slot];
    if(raw.packet_count!=config_.intervals)return false;
    std::size_t total=0;
    for(unsigned i=0;i<raw.packet_count;++i){
        const auto& packet=raw.packets[i];
        if(packet.status || !packet.length || packet.length>max_packet || packet.length%frame_bytes)return false;
        total+=static_cast<std::size_t>(packet.length);
    }
    if(stats_.input_frames>std::numeric_limits<std::uint64_t>::max()-total/frame_bytes)return false;
    held_={};held_.first_frame=stats_.input_frames;held_.host_observation_ns=now;
    held_.reported_rate_hz=config_.rate_hz;held_.packet_count=raw.packet_count;
    std::size_t offset=0;
    for(unsigned i=0;i<raw.packet_count;++i){
        const auto bytes=static_cast<std::size_t>(raw.packets[i].length);
        held_.frames_per_packet[i]=static_cast<std::uint8_t>(bytes/frame_bytes);
        std::memcpy(held_.pcm.data()+offset,raw.pcm.data()+i*max_packet,bytes);offset+=bytes;
    }
    held_valid_=true;return true;
}
bool ContinuousStream::matches(const AudioBlock& block,const Schedule& schedule) const noexcept {
    return block.first_frame==schedule.first && block.host_observation_ns==schedule.time &&
        block.reported_rate_hz==schedule.rate && block.packet_count==schedule.count && block.frames_per_packet==schedule.frames;
}
StreamState ContinuousStream::drain(std::uint64_t now) noexcept {
    for(unsigned i=0;i<8;++i)if(slots_[i].pending){
        const auto result=backend_.poll(i,nullptr);
        if(result==StreamPoll::success || result==StreamPoll::failure)slots_[i].pending=false;
    }
    bool pending=false;
    for(unsigned i=0;i<8;++i)if(slots_[i].prepared){
        if(slots_[i].pending){pending=true;continue;}
        if(!backend_.release(i)){
            stats_.retained_mask|=1u<<i;
            if(fault_==StreamFault::none)fault_=StreamFault::release;
        }
        // Failed release is never retried or represented as successful cleanup.
        slots_[i].prepared=false;
    }
    if(pending && !clock_lost_ && now-drain_since_<std::uint64_t(config_.drain_ms)*ns_per_ms)return state_;
    for(unsigned i=0;i<8;++i)if(slots_[i].pending)stats_.retained_mask|=1u<<i;
    state_=stats_.retained_mask?StreamState::retained:StreamState::stopped;return state_;
}
void ContinuousStream::stop() noexcept {
    if(state_==StreamState::stopped || state_==StreamState::retained || state_==StreamState::draining)return;
    auto now=backend_.now_ns();
    if(now<last_time_){clock_lost_=true;now=last_time_;if(fault_==StreamFault::none)fault_=StreamFault::clock;}
    last_time_=now;begin_drain(now);
}
StreamState ContinuousStream::step() noexcept {
    if(state_==StreamState::ready || state_==StreamState::stopped || state_==StreamState::retained)return state_;
    auto now=backend_.now_ns();
    if(now<last_time_){clock_lost_=true;now=last_time_;fail(StreamFault::clock,now);}
    last_time_=now;
    if(state_==StreamState::draining)return drain(now);
    const auto stall=std::uint64_t(config_.stall_ms)*ns_per_ms;
    if(expected_count_ && now-expected_[expected_read_].published>=stall){fail(StreamFault::output_starved,now);return drain(now);}
    for(unsigned i=0;i<8;++i)if((slots_[i].pending || slots_[i].complete) && now-slots_[i].since>=stall){
        fail(i>=4?StreamFault::output_timeout:(slots_[i].pending?StreamFault::input_timeout:StreamFault::input_backpressure),now);return drain(now);
    }
    for(unsigned i=0;i<8;++i)if(slots_[i].pending){
        const auto result=backend_.poll(i,i<4?&input_[i]:nullptr);
        if(result==StreamPoll::pending)continue;
        if(result==StreamPoll::unproven){fail(StreamFault::unproven_completion,now);return drain(now);}
        slots_[i].pending=false;
        if(result==StreamPoll::failure){fail(i<4?StreamFault::input_transfer:StreamFault::output_transfer,now);return drain(now);}
        if(i<4)slots_[i].complete=true;else ++stats_.output_completions;
    }
    for(unsigned n=0;n<4 && slots_[input_head_].complete && expected_count_<expected_.size();++n){
        if(!held_valid_ && !pack(input_head_,now)){fail(StreamFault::invalid_input,now);return drain(now);}
        const auto published=peer_.publish_input(held_);
        if(published==StreamExchange::full)break;
        if(published!=StreamExchange::ok){fail(StreamFault::peer,now);return drain(now);}
        auto& schedule=expected_[expected_write_];
        schedule={held_.first_frame,held_.host_observation_ns,now,held_.packet_count,held_.reported_rate_hz,held_.frames_per_packet};
        expected_write_=(expected_write_+1)%static_cast<unsigned>(expected_.size());++expected_count_;
        std::uint64_t frames=0;for(auto count:held_.frames_per_packet)frames+=count;
        ++stats_.input_blocks;stats_.input_frames+=frames;
        auto& slot=slots_[input_head_];slot.complete=false;held_valid_=false;
        if(!backend_.submit_input(input_head_,true)){fail(StreamFault::submit,now);return drain(now);}
        slot.pending=true;slot.since=now;++stats_.input_submissions;
        input_head_=(input_head_+1)%4;
    }
    for(unsigned n=0;n<4;++n){
        unsigned available=8;
        for(unsigned j=0;j<4;++j){const auto i=4+(output_head_-4+j)%4;if(!slots_[i].pending){available=i;break;}}
        if(available==8)break;
        const auto received=peer_.receive_output(output_);
        if(received==StreamExchange::empty)break;
        if(received!=StreamExchange::ok){fail(StreamFault::peer,now);return drain(now);}
        if(!expected_count_ || !matches(output_,expected_[expected_read_])){fail(StreamFault::output_mismatch,now);return drain(now);}
        if(!backend_.submit_output(available,output_,stats_.output_submissions!=0)){fail(StreamFault::submit,now);return drain(now);}
        slots_[available].pending=true;slots_[available].since=now;++stats_.output_submissions;
        for(auto count:output_.frames_per_packet)stats_.output_frames_submitted+=count;
        expected_read_=(expected_read_+1)%static_cast<unsigned>(expected_.size());--expected_count_;
        output_head_=4+(available-3)%4;
    }
    return state_;
}
}
