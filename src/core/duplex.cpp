#include "core/duplex.hpp"
#include <array>
#include <algorithm>
#include <exception>
#include <stdexcept>

namespace sl3 {
SilentStageResult stage_silent_output(const PacketResult64* input,std::size_t packets,
                                      std::uint64_t* lengths,std::size_t lengths_capacity,
                                      std::uint8_t* output,std::size_t capacity) noexcept {
    if(!input || !lengths || !output || packets<8 || packets>1024 || packets%8 ||
       lengths_capacity<packets || capacity>max_packet*1024)return {};
    std::size_t total=0;
    for(std::size_t i=0;i<packets;++i){
        const auto& packet=input[i];
        if(packet.status || !packet.length || packet.length>max_packet || packet.length%frame_bytes)
            return {SilentStageStatus::invalid_input_packet,0};
        total+=static_cast<std::size_t>(packet.length);
    }
    if(total>capacity)return {SilentStageStatus::insufficient_capacity,0};
    for(std::size_t i=0;i<packets;++i)lengths[i]=input[i].length;
    std::fill(output,output+capacity,std::uint8_t{0});
    return {SilentStageStatus::ok,total};
}
CaptureResult duplex_transaction(DuplexBackend& backend,std::size_t pairs,
                                  std::uint32_t deadline_ms,std::uint32_t drain_ms) {
    CaptureResult result;
    if(!pairs || pairs>4 || !deadline_ms || deadline_ms>5000 || !drain_ms || drain_ms>5000){
        result.error="Invalid bounded duplex parameters";return result;
    }
    std::array<bool,8> prepared{},pending{};
    const auto slots=pairs*2;
    const auto deadline=backend.now_ms()+deadline_ms;
    auto remaining=[&](std::uint64_t end)->std::uint32_t{
        const auto now=backend.now_ms();return now<end?static_cast<std::uint32_t>(end-now):0;
    };
    auto wait_terminal=[&](std::size_t slot){
        const auto completion=backend.wait(slot,remaining(deadline));
        if(completion==Completion::pending)throw std::runtime_error("Duplex deadline elapsed");
        pending[slot]=false;
        if(completion==Completion::failure)throw std::runtime_error("Duplex transfer failed");
    };
    try{
        for(std::size_t slot=0;slot<slots;++slot){backend.prepare(slot);prepared[slot]=true;}
        for(std::size_t pair=0;pair<pairs;++pair){
            const auto input=pair*2;backend.submit(input,pair!=0);pending[input]=true;
        }
        for(std::size_t pair=0;pair<pairs;++pair){
            const auto input=pair*2,output=input+1;
            wait_terminal(input);
            backend.stage_output(input,output);
            backend.submit(output,pair!=0);pending[output]=true;
        }
        for(std::size_t pair=0;pair<pairs;++pair)wait_terminal(pair*2+1);
        result.transfers_succeeded=true;
    }catch(const std::exception& error){result.error=error.what();}
    catch(...){result.error="Unknown duplex failure";}
    for(std::size_t slot=0;slot<slots;++slot)if(pending[slot]){
        try{backend.cancel(slot);}catch(...){/* Cancellation is not completion proof. */}
    }
    const auto drain_deadline=backend.now_ms()+drain_ms;
    for(std::size_t slot=0;slot<slots;++slot)if(pending[slot]){
        try{pending[slot]=backend.wait(slot,remaining(drain_deadline))==Completion::pending;}
        catch(...){/* Keep storage if completion cannot be established. */}
    }
    for(std::size_t slot=0;slot<slots;++slot)if(prepared[slot]){
        if(pending[slot]){result.cleanup_complete=false;result.retained_slots.push_back(slot);}
        else try{backend.release(slot);}catch(...){
            result.cleanup_complete=false;result.retained_slots.push_back(slot);
            if(result.error.empty())result.error="Duplex resource release failed";
        }
    }
    return result;
}
}
