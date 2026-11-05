#pragma once
#include "core/audio_block.hpp"
#include <algorithm>
#include <cstddef>
#include <cstring>
#include <limits>

namespace sl3 {
enum class OutputRecordFault {none,configuration,shape,rate,position};
// A single stream-owner writer, caller-owned storage of capacity_frames * 18
// bytes, disjoint from the source block. Call only after explicitly arming a
// capture. The first block may start anywhere in the stream. Read the result
// only after writer retirement or an external release/acquire publication.
// This records dequeued software PCM, not USB completion or analog output.
class PackedOutputRecorder final {
public:
    PackedOutputRecorder(std::uint8_t* storage,std::size_t capacity_frames,unsigned rate) noexcept
        :storage_(storage),capacity_(capacity_frames),rate_(rate) {
        if(!storage || (rate!=44100 && rate!=48000) || !capacity_frames || capacity_frames>std::size_t(rate)*5)
            fault_=OutputRecordFault::configuration;
    }
    bool append(const AudioBlock& block) noexcept {
        if(fault_!=OutputRecordFault::none)return false;
        if(complete())return true; // Sealed immutable clip, no later stream claims.
        if(block.reported_rate_hz!=rate_)return fail(OutputRecordFault::rate);
        if(block.packet_count<8 || block.packet_count>64 || block.packet_count%8)return fail(OutputRecordFault::shape);
        std::size_t count=0;
        for(unsigned i=0;i<64;++i){
            const auto n=block.frames_per_packet[i];
            if(i<block.packet_count){if(!n || n>7)return fail(OutputRecordFault::shape);count+=n;}
            else if(n)return fail(OutputRecordFault::shape);
        }
        if(block.first_frame>std::numeric_limits<std::uint64_t>::max()-count ||
           (frames_ && block.first_frame!=next_))return fail(OutputRecordFault::position);
        if(!frames_)first_=block.first_frame;
        const auto take=std::min(count,capacity_-frames_);
        // A final partial block trims the diagnostic clip only. The original
        // AudioBlock is never modified, truncated or delayed for transport.
        std::memcpy(storage_+frames_*18,block.pcm.data(),take*18);
        frames_+=take;next_=block.first_frame+count;++blocks_;return true;
    }
    bool complete() const noexcept{return fault_==OutputRecordFault::none && frames_==capacity_;}
    std::size_t frames() const noexcept{return frames_;}
    std::uint64_t first_frame() const noexcept{return first_;}
    std::uint64_t blocks() const noexcept{return blocks_;}
    unsigned rate() const noexcept{return rate_;}
    OutputRecordFault fault() const noexcept{return fault_;}
private:
    std::uint8_t* storage_;std::size_t capacity_,frames_=0;unsigned rate_;
    std::uint64_t first_=0,next_=0,blocks_=0;
    OutputRecordFault fault_=OutputRecordFault::none;
    bool fail(OutputRecordFault value) noexcept{fault_=value;return false;}
};
}
