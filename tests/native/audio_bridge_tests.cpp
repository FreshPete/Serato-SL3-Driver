#include "core/audio_bridge.hpp"
#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <new>
#include <stdexcept>

static bool count_allocations=false;
static std::size_t allocations=0;
void* operator new(std::size_t size) {
    if(count_allocations)++allocations;
    if(void* p=std::malloc(size?size:1))return p;
    throw std::bad_alloc();
}
void* operator new[](std::size_t size){return ::operator new(size);}
void operator delete(void* p) noexcept{std::free(p);}
void operator delete[](void* p) noexcept{std::free(p);}
void operator delete(void* p,std::size_t) noexcept{std::free(p);}
void operator delete[](void* p,std::size_t) noexcept{std::free(p);}

using sl3::BridgeStatus;
static void require(bool condition,const char* message){if(!condition)throw std::runtime_error(message);}
template<class F> static void rejects(F call){bool caught=false;try{call();}catch(const std::runtime_error&){caught=true;}require(caught,"Invalid bridge configuration accepted");}
static std::int32_t signal(std::uint64_t frame,unsigned channel){
    if(frame==0 && channel==1)return -1;
    if(frame==0 && channel==5)return 8388607;
    if(frame==1 && channel==1)return -8388608;
    return static_cast<std::int32_t>((frame*7919+channel*104729)%0x1000000)-0x800000;
}
static std::int32_t read_sample(const std::uint8_t* bytes){
    const std::uint32_t unsigned_value=bytes[0]|(std::uint32_t(bytes[1])<<8)|(std::uint32_t(bytes[2])<<16);
    return unsigned_value>=0x800000?static_cast<std::int32_t>(unsigned_value)-0x1000000:static_cast<std::int32_t>(unsigned_value);
}
struct Host final:sl3::BlockCallbacks {
    sl3::AudioBridge& bridge;
    unsigned calls=0;
    bool throws=false,partial=false;
    BridgeStatus reentrant_stop=BridgeStatus::ok;
    explicit Host(sl3::AudioBridge& source):bridge(source){}
    void buffer_switch(unsigned bank,std::uint64_t position,std::uint64_t) override {
        if(throws)throw std::runtime_error("Host callback fault");
        require(bank==calls%2 && position==std::uint64_t(calls)*bridge.block_frames(),"Bank/sample-position sequence changed");
        for(unsigned channel:{1u,5u}){
            const auto* input=bridge.plane(sl3::Direction::input,channel,bank);
            for(std::size_t i=0;i<bridge.block_frames();++i)
                require(read_sample(input+i*3)==signal(position+i,channel),"Input frame/channel/endian mapping changed");
        }
        const auto frames=partial && calls>0?bridge.block_frames()/2:bridge.block_frames();
        std::memcpy(bridge.plane(sl3::Direction::output,0,bank),bridge.plane(sl3::Direction::input,1,bank),frames*3);
        std::memcpy(bridge.plane(sl3::Direction::output,4,bank),bridge.plane(sl3::Direction::input,5,bank),frames*3);
        reentrant_stop=bridge.stop();
        ++calls;
    }
};
struct DeferredHost final:sl3::BlockCallbacks {
    unsigned offered_bank=99,calls=0;
    void buffer_switch(unsigned bank,std::uint64_t,std::uint64_t) override {offered_bank=bank;++calls;}
};
static void deferred_host(){
    sl3::AudioBridge bridge(64,{1},{0});DeferredHost host;bridge.start(44100,host);
    std::array<sl3::Frame,64> input{};
    std::array<std::uint32_t,16> lengths{};lengths.fill(72);
    std::array<std::uint8_t,1152> bytes{};std::array<sl3::Packet,16> layout{};
    for(unsigned block=0;block<6;++block){
        require(bridge.process(input.data(),64,std::uint64_t(block)*64,block)==BridgeStatus::ok,"Deferred-host input failed");
        // Intentionally AFTER buffer_switch returned, before the next switch.
        auto* output=bridge.plane(sl3::Direction::output,0,host.offered_bank);
        const auto value=2000u+block;
        for(unsigned sample=0;sample<64;++sample)for(unsigned byte=0;byte<3;++byte)
            output[sample*3+byte]=static_cast<std::uint8_t>(value>>(byte*8));
        require(bridge.render(lengths.data(),16,bytes.data(),bytes.size(),layout.data(),16)==BridgeStatus::ok,"Deferred-host output failed");
        for(unsigned sample=0;sample<64;++sample)for(unsigned channel=0;channel<6;++channel){
            const auto expected=channel==0 && block>=2?static_cast<std::int32_t>(1998+block):0;
            require(read_sample(bytes.data()+sample*18+channel*3)==expected,"Output was consumed before the host's processing window elapsed");
        }
    }
    require(host.calls==6,"Deferred callback count changed");
    for(bool input_only:{true,false}){
        sl3::AudioBridge selected(64,input_only?std::vector<unsigned>{0}:std::vector<unsigned>{},input_only?std::vector<unsigned>{}:std::vector<unsigned>{0});
        DeferredHost silent;selected.start(48000,silent);
        require(selected.process(input.data(),64,0,0)==BridgeStatus::ok,"One-direction channel selection stopped the clock");
        require(selected.render(lengths.data(),16,bytes.data(),bytes.size(),layout.data(),16)==BridgeStatus::ok,"Silent unselected output failed");
        require(std::all_of(bytes.begin(),bytes.end(),[](auto value){return value==0;}),"Unselected/unwritten channels were not silent");
    }
}
static void stream(unsigned rate,bool partial,std::size_t block=64){
    sl3::AudioBridge bridge(block,{1,5},{0,4});Host host(bridge);host.partial=partial;
    auto* stable=bridge.plane(sl3::Direction::output,0,0);
    require(stable && !bridge.plane(sl3::Direction::input,0,0) && !bridge.plane(sl3::Direction::output,6,0),"Channel selection/pointer bounds failed");
    const auto allocation_before=allocations;count_allocations=true;
    require(bridge.start(rate,host)==BridgeStatus::ok,"Start failed");
    std::uint32_t phase=0;
    std::uint64_t received=0,rendered=0;
    // Run long enough to check packets spanning the wrap in the eight-bank ring.
    const auto groups=static_cast<unsigned>((block*18+43)/44);
    for(unsigned group=0;group<groups;++group){
        std::array<std::uint32_t,8> lengths{};
        std::array<sl3::Frame,56> batch{};
        const auto batch_start=received;
        for(unsigned packet=0;packet<8;++packet){
            phase+=rate;const auto frames=phase/8000;phase%=8000;lengths[packet]=frames*18;
            std::array<sl3::Frame,7> input{};
            for(unsigned i=0;i<frames;++i)for(unsigned c=0;c<6;++c)input[i][c]=signal(received+i,c);
            if(block==32)std::copy_n(input.begin(),frames,batch.begin()+(received-batch_start));
            else require(bridge.process(input.data(),frames,received,std::uint64_t(group*8+packet)*125000)==BridgeStatus::ok,"Stream input failed");
            received+=frames;
        }
        if(block==32)
            require(bridge.process(batch.data(),static_cast<std::size_t>(received-batch_start),batch_start,
                                   std::uint64_t(group)*1000000)==BridgeStatus::ok,"One USB batch may complete two 32-frame banks");
        std::array<std::uint8_t,1008> bytes{};std::array<sl3::Packet,8> layout{};
        require(bridge.render(lengths.data(),8,bytes.data(),bytes.size(),layout.data(),8)==BridgeStatus::ok,"Stream output failed");
        std::size_t offset=0;
        for(unsigned packet=0;packet<8;++packet){
            require(layout[packet].offset==offset && layout[packet].length==lengths[packet],"Observed packet layout changed");
            for(unsigned frame=0;frame<lengths[packet]/18;++frame){
                for(unsigned c=0;c<6;++c){
                    std::int32_t expected=0;
                    if(rendered>=2*block && (c==0 || c==4)){
                        const auto source=rendered-2*block;
                        if(!partial || source<block || source%block<block/2)expected=signal(source,c==0?1:5);
                    }
                    require(read_sample(bytes.data()+offset+c*3)==expected,"Output delay/channel mapping or bank clearing failed");
                }
                offset+=18;++rendered;
            }
        }
    }
    const auto stats=bridge.stats();
    require(stats.input_frames==received && stats.output_frames==rendered && stats.completed_blocks==received/block,"Stream accounting failed");
    require(host.reentrant_stop==BridgeStatus::reentrant_call && bridge.state()==sl3::BridgeState::running,"Callback reentrancy was not rejected");
    require(bridge.stop()==BridgeStatus::ok,"Stop failed");
    host.calls=0;
    require(bridge.start(rate,host)==BridgeStatus::ok && bridge.plane(sl3::Direction::output,0,0)==stable,"Restart moved ASIO planes");
    require(std::all_of(stable,stable+block*3,[](auto value){return value==0;}),"Restart retained old output");
    require(bridge.stats().input_frames==0 && bridge.stats().queued_output_frames==block,"Restart counters/priming failed");
    require(bridge.stop()==BridgeStatus::ok,"Second stop failed");
    count_allocations=false;
    require(allocations==allocation_before,"Stream path performed a heap allocation");
}
int main(){
    try{
        for(auto block:{64u,128u,256u,512u,1024u}){stream(44100,false,block);stream(48000,false,block);}
        stream(44100,false,32);
        stream(44100,true);deferred_host();
        rejects([]{sl3::AudioBridge b(0,{1},{0});});rejects([]{sl3::AudioBridge b(65,{1},{0});});
        rejects([]{sl3::AudioBridge b(2048,{1},{0});});rejects([]{sl3::AudioBridge b(64,{},{});});
        rejects([]{sl3::AudioBridge b(64,{1,1},{0});});rejects([]{sl3::AudioBridge b(64,{6},{0});});
        sl3::AudioBridge bridge(64,{1,5},{0,4});Host host(bridge);
        require(bridge.start(96000,host)==BridgeStatus::invalid_argument && bridge.state()==sl3::BridgeState::ready,"Unsupported rate accepted");
        require(bridge.start(44100,host)==BridgeStatus::ok,"Start after rejection failed");
        require(bridge.start(44100,host)==BridgeStatus::invalid_state,"Live stream was reset");
        std::array<sl3::Frame,512> frames{};
        require(bridge.process(frames.data(),1,1,100)==BridgeStatus::input_discontinuity && host.calls==0,"Discontinuity not stopped before callback");
        bridge.stop();host.calls=0;bridge.start(44100,host);
        require(bridge.process(frames.data(),1,0,100)==BridgeStatus::ok,"First timestamp rejected");
        require(bridge.process(frames.data(),1,1,99)==BridgeStatus::clock_regression,"Regressing observation time accepted");
        bridge.stop();bridge.start(44100,host);
        require(bridge.process(frames.data(),512,0,0)==BridgeStatus::output_overflow && bridge.stats().input_frames==0 && host.calls==0,"Overflow partially consumed input");
        bridge.stop();bridge.start(44100,host);frames[0][0]=8388608;
        require(bridge.process(frames.data(),1,0,0)==BridgeStatus::invalid_sample && bridge.stats().input_frames==0,"Out-of-range sample accepted");
        bridge.stop();bridge.start(44100,host);
        std::array<std::uint32_t,24> lengths{};lengths.fill(126);
        std::array<std::uint8_t,3024> bytes{};bytes.fill(0x5a);std::array<sl3::Packet,24> layout{};
        require(bridge.render(lengths.data(),24,bytes.data(),bytes.size(),layout.data(),24)==BridgeStatus::output_underrun,"Underrun accepted");
        require(bridge.stats().queued_output_frames==64 && bytes[0]==0x5a,"Underrun partially wrote or consumed audio");
        bridge.stop();bridge.start(44100,host);lengths.fill(18);lengths[3]=17;
        require(bridge.render(lengths.data(),8,bytes.data(),bytes.size(),layout.data(),24)==BridgeStatus::invalid_argument && bridge.stats().queued_output_frames==64,"Malformed packet consumed output");
        lengths[3]=18;
        require(bridge.render(lengths.data(),8,bytes.data(),1,layout.data(),24)==BridgeStatus::invalid_argument,"Output capacity ignored");
        bridge.stop();bridge.start(44100,host);host.throws=true;frames.fill(sl3::Frame{});
        require(bridge.process(frames.data(),64,0,0)==BridgeStatus::callback_failure && bridge.state()==sl3::BridgeState::faulted,"Host exception escaped or stream continued");
        require(bridge.render(lengths.data(),8,bytes.data(),bytes.size(),layout.data(),24)==BridgeStatus::invalid_state,"Faulted stream continued output");
        std::cout<<"Variable-packet/fixed-block streams, channel maps, zero-allocation lifecycle and fault cases passed\n";
    }catch(const std::exception& error){count_allocations=false;std::cerr<<error.what()<<'\n';return 1;}
}
