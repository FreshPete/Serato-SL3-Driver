#include "core/audio_bridge.hpp"
#include <algorithm>
#include <cstring>
#include <limits>
#include <stdexcept>

namespace sl3 {
namespace {
void pack(std::int32_t value, std::uint8_t* target) noexcept {
    const auto bits=static_cast<std::uint32_t>(value);
    for(unsigned byte=0;byte<sample_bytes;++byte) target[byte]=static_cast<std::uint8_t>(bits>>(byte*8));
}
void select(const std::vector<unsigned>& requested,std::array<bool,channels>& selected) {
    for(auto channel:requested){
        if(channel>=channels || selected[channel])throw std::runtime_error("Invalid/duplicate logical audio channel");
        selected[channel]=true;
    }
}
}
AudioBridge::AudioBridge(std::size_t block_frames,const std::vector<unsigned>& inputs,
                          const std::vector<unsigned>& outputs):block_frames_(block_frames) {
    if(block_frames<32 || block_frames>1024 || (block_frames&(block_frames-1)) || (inputs.empty() && outputs.empty()))
        throw std::runtime_error("Bridge needs a power-of-two block of 32..1024 frames and active channels");
    select(inputs,active_input_);select(outputs,active_output_);
    for(unsigned bank=0;bank<2;++bank)for(unsigned channel=0;channel<channels;++channel){
        if(active_input_[channel])input_[bank][channel].resize(block_frames*sample_bytes);
        if(active_output_[channel])output_[bank][channel].resize(block_frames*sample_bytes);
    }
    output_ring_.resize(block_frames*8);
}
std::uint8_t* AudioBridge::plane(Direction direction,unsigned channel,unsigned bank) noexcept {
    if(channel>=channels || bank>1)return nullptr;
    auto& bytes=direction==Direction::input?input_[bank][channel]:output_[bank][channel];
    return bytes.empty()?nullptr:bytes.data();
}
BridgeStats AudioBridge::stats() const noexcept {return {input_frames_,output_frames_,blocks_,queued_};}
void AudioBridge::push(const PackedFrame& frame) noexcept {
    output_ring_[write_]=frame;
    if(++write_==output_ring_.size())write_=0;
    ++queued_;
}
BridgeStatus AudioBridge::fail(BridgeStatus reason) noexcept {state_=BridgeState::faulted;fault_=reason;return reason;}
BridgeStatus AudioBridge::start(unsigned rate,BlockCallbacks& callback) noexcept {
    if(inside_)return BridgeStatus::reentrant_call;
    if(state_!=BridgeState::ready)return BridgeStatus::invalid_state;
    if(rate!=44100 && rate!=48000)return BridgeStatus::invalid_argument;
    read_=write_=queued_=fill_=0;bank_=0;input_frames_=output_frames_=blocks_=last_observation_=0;
    have_observation_=false;fault_=BridgeStatus::ok;callback_=&callback;
    for(unsigned bank=0;bank<2;++bank)for(unsigned channel=0;channel<channels;++channel){
        std::fill(input_[bank][channel].begin(),input_[bank][channel].end(),std::uint8_t{0});
        std::fill(output_[bank][channel].begin(),output_[bank][channel].end(),std::uint8_t{0});
    }
    // One priming block plus the initially empty other bank produce two
    // blocks of startup silence. Host output is consumed at the NEXT switch,
    // allowing the ASIO host its full one-block processing window.
    for(std::size_t i=0;i<block_frames_;++i)push(PackedFrame{});
    state_=BridgeState::running;return BridgeStatus::ok;
}
BridgeStatus AudioBridge::stop() noexcept {
    if(inside_)return BridgeStatus::reentrant_call;
    callback_=nullptr;read_=write_=queued_=fill_=0;state_=BridgeState::ready;return BridgeStatus::ok;
}
BridgeStatus AudioBridge::process(const Frame* frames,std::size_t count,
                                  std::uint64_t first_frame,std::uint64_t observation_ns) noexcept {
    if(inside_)return BridgeStatus::reentrant_call;
    if(state_!=BridgeState::running)return BridgeStatus::invalid_state;
    if(!frames || !count || count>block_frames_*8)return BridgeStatus::invalid_argument;
    if(first_frame!=input_frames_ || count>std::numeric_limits<std::uint64_t>::max()-input_frames_)
        return fail(BridgeStatus::input_discontinuity);
    if(have_observation_ && observation_ns<last_observation_)return fail(BridgeStatus::clock_regression);
    const auto produced=((fill_+count)/block_frames_)*block_frames_;
    if(produced>output_ring_.size()-queued_)return fail(BridgeStatus::output_overflow);
    for(std::size_t i=0;i<count;++i)for(auto value:frames[i])
        if(value<-8388608 || value>8388607)return fail(BridgeStatus::invalid_sample);
    inside_=true;
    last_observation_=observation_ns;have_observation_=true;
    for(std::size_t i=0;i<count;++i){
        for(unsigned channel=0;channel<channels;++channel)if(active_input_[channel])
            pack(frames[i][channel],input_[bank_][channel].data()+fill_*sample_bytes);
        ++fill_;++input_frames_;
        if(fill_==block_frames_){
            const auto consumed_bank=bank_^1u;
            for(std::size_t frame=0;frame<block_frames_;++frame){
                PackedFrame values{};
                for(unsigned channel=0;channel<channels;++channel)if(active_output_[channel])
                    std::memcpy(values.data()+channel*sample_bytes,
                                output_[consumed_bank][channel].data()+frame*sample_bytes,sample_bytes);
                push(values);
            }
            // Never replay bytes from an earlier bank use if a host writes only
            // part of an output channel or supplies no output at all.
            for(auto& channel:output_[bank_])std::fill(channel.begin(),channel.end(),std::uint8_t{0});
            try{callback_->buffer_switch(bank_,input_frames_-block_frames_,observation_ns);}
            catch(...){inside_=false;return fail(BridgeStatus::callback_failure);}
            ++blocks_;fill_=0;bank_^=1;
        }
    }
    inside_=false;return BridgeStatus::ok;
}
BridgeStatus AudioBridge::render(const std::uint32_t* lengths,std::size_t packets,
                                 std::uint8_t* pcm,std::size_t capacity,
                                 Packet* layout,std::size_t layout_capacity) noexcept {
    if(inside_)return BridgeStatus::reentrant_call;
    if(state_!=BridgeState::running)return BridgeStatus::invalid_state;
    if(!lengths || !pcm || !layout || packets<8 || packets>1024 || packets%8 || layout_capacity<packets)
        return BridgeStatus::invalid_argument;
    std::size_t bytes=0;
    for(std::size_t i=0;i<packets;++i){
        if(!lengths[i] || lengths[i]>max_packet || lengths[i]%frame_bytes)return BridgeStatus::invalid_argument;
        bytes+=lengths[i];
    }
    if(capacity<bytes)return BridgeStatus::invalid_argument;
    const auto frames=bytes/frame_bytes;
    if(frames>queued_ || frames>std::numeric_limits<std::uint64_t>::max()-output_frames_)
        return fail(BridgeStatus::output_underrun);
    std::size_t offset=0;
    for(std::size_t packet=0;packet<packets;++packet){
        layout[packet]={static_cast<std::uint32_t>(offset),lengths[packet],0};
        const auto count=std::size_t(lengths[packet]/frame_bytes);
        const auto contiguous=std::min(count,output_ring_.size()-read_);
        std::memcpy(pcm+offset,output_ring_.data()+read_,contiguous*frame_bytes);
        if(contiguous<count)
            std::memcpy(pcm+offset+contiguous*frame_bytes,output_ring_.data(),(count-contiguous)*frame_bytes);
        read_+=count;
        if(read_>=output_ring_.size())read_-=output_ring_.size();
        offset+=lengths[packet];queued_-=count;output_frames_+=count;
    }
    return BridgeStatus::ok;
}
}
