#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>

namespace sl3 {
enum class InputRecordFault {none,configuration,empty_block,position,plane};
// One callback writer, caller-owned storage. Read only after callback retirement.
// Destination must not alias the input planes.
// Captures a fixed prefix, including startup; later complete callbacks are counted
// separately. No allocation, file I/O, timing/profile claim or sample conversion.
class PackedInputRecorder final {
public:
    PackedInputRecorder(std::uint8_t* storage,std::size_t capacity_frames) noexcept
        :storage_(storage),capacity_(capacity_frames) {
        if(!storage || !capacity_frames || capacity_frames>std::numeric_limits<std::size_t>::max()/18)
            fault_=InputRecordFault::configuration;
    }
    bool append(const std::array<const std::uint8_t*,6>& planes,unsigned frames,std::uint64_t first) noexcept {
        if(fault_!=InputRecordFault::none)return false;
        if(!frames || frames>128)return fail(InputRecordFault::empty_block);
        for(auto* p:planes)if(!p)return fail(InputRecordFault::plane);
        if(first!=next_ || first>std::numeric_limits<std::uint64_t>::max()-frames)return fail(InputRecordFault::position);
        next_=first+frames;++callbacks_;
        if(complete()){++trailing_;return true;}
        // The requested prefix is whole banks; do not silently take part of one.
        if(frames>capacity_-frames_)return fail(InputRecordFault::configuration);
        for(unsigned frame=0;frame<frames;++frame)for(unsigned channel=0;channel<6;++channel)
            std::memcpy(storage_+(frames_+frame)*18+channel*3,planes[channel]+frame*3,3);
        frames_+=frames;++recorded_;return true;
    }
    bool complete() const noexcept{return fault_==InputRecordFault::none && frames_==capacity_;}
    std::size_t frames() const noexcept{return frames_;}
    std::uint64_t callbacks() const noexcept{return callbacks_;}
    std::uint64_t recorded_callbacks() const noexcept{return recorded_;}
    std::uint64_t trailing_callbacks() const noexcept{return trailing_;}
    InputRecordFault fault() const noexcept{return fault_;}
private:
    std::uint8_t* storage_;std::size_t capacity_,frames_=0;
    std::uint64_t next_=0,callbacks_=0,recorded_=0,trailing_=0;
    InputRecordFault fault_=InputRecordFault::none;
    bool fail(InputRecordFault fault) noexcept{fault_=fault;return false;}
};
}
