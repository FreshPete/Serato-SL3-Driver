#include "core/continuous.hpp"
#include <atomic>
#include <cstdlib>
#include <iostream>
#include <new>
#include <stdexcept>

using namespace sl3;
static std::atomic<std::size_t> allocations{0};
void* operator new(std::size_t size){allocations.fetch_add(1);if(auto* p=std::malloc(size?size:1))return p;throw std::bad_alloc();}
void* operator new[](std::size_t size){return ::operator new(size);}
void operator delete(void* p) noexcept{std::free(p);}
void operator delete[](void* p) noexcept{std::free(p);}
void operator delete(void* p,std::size_t) noexcept{std::free(p);}
void operator delete[](void* p,std::size_t) noexcept{std::free(p);}
static void require(bool good,const char* message){if(!good)throw std::runtime_error(message);}
static std::uint8_t packet_frames(std::uint64_t batch,unsigned packet){return std::uint8_t(1+(batch+packet)%7);}
static std::uint8_t byte(std::uint64_t batch,unsigned packet,std::size_t index){return std::uint8_t(batch*17+packet*13+index);}
static std::uint64_t frames(std::uint64_t batch,unsigned intervals){std::uint64_t n=0;for(unsigned p=0;p<intervals;++p)n+=packet_frames(batch,p);return n;}
static bool same(const AudioBlock& a,const AudioBlock& b){return a.first_frame==b.first_frame && a.host_observation_ns==b.host_observation_ns &&
    a.reported_rate_hz==b.reported_rate_hz && a.packet_count==b.packet_count && a.frames_per_packet==b.frames_per_packet && a.pcm==b.pcm;}
struct Backend final:ContinuousBackend {
    struct Slot {bool prepared=false,pending=false,cancelled=false;std::uint64_t batch=0;};
    std::array<Slot,8> slots{};
    // Only OUT slots need retained output storage. Do not reserve an unused
    // AudioBlock in every IN slot and multiply Debug test stack requirements.
    std::array<AudioBlock,4> output{};
    std::uint64_t now=10000000,in=0,out=0,out_position=0,last_output_time=0,prepare_delay_ns=0;
    unsigned intervals=0,rate=44100,hold_in=0,hold_out=0,unproven=0,fail_poll=0,never_cancel=0,cancel_false=0,release_false=0;
    unsigned bad_input=0,prepare_false=8,prepared_calls=0,release_calls=0,cancel_mask=0;
    unsigned startup_empty_batches=0,output_batch_offset=0;
    std::uint64_t reject_input=~std::uint64_t(0),reject_output=~std::uint64_t(0);
    bool bad=false,record=false;
    std::array<unsigned,256> events{};unsigned event_count=0;
    void event(unsigned e) noexcept {if(record && event_count<events.size())events[event_count++]=e;}
    bool prepare(unsigned i,unsigned n) noexcept override {
        ++prepared_calls;if(i==prepare_false)return false;
        if(slots[i].prepared || slots[i].pending)bad=true;
        intervals=n;slots[i].prepared=true;now+=prepare_delay_ns;return true;
    }
    bool submit_input(unsigned i,bool continued) noexcept override {
        if(prepared_calls!=8 || i>=4 || !slots[i].prepared || slots[i].pending || continued!=(in!=0))bad=true;
        if(in==reject_input)return false;
        slots[i].batch=in++;slots[i].pending=true;slots[i].cancelled=false;return true;
    }
    bool submit_output(unsigned i,const AudioBlock& block,bool continued) noexcept override {
        if(i<4 || !slots[i].prepared || slots[i].pending || continued!=(out!=0))bad=true;
        if(out==reject_output)return false;
        if(block.packet_count!=intervals || block.first_frame!=out_position || block.reported_rate_hz!=rate || block.host_observation_ns<last_output_time)bad=true;
        const auto batch=out+output_batch_offset;
        std::size_t offset=0;
        for(unsigned p=0;p<64;++p){
            const auto count=p<intervals?packet_frames(batch,p):0;
            if(block.frames_per_packet[p]!=count)bad=true;
            for(unsigned k=0;k<unsigned(count)*18;++k)if(block.pcm[offset++]!=byte(batch,p,k))bad=true;
        }
        output[i-4]=block;slots[i].pending=true;slots[i].cancelled=false;
        out_position+=frames(batch,intervals);last_output_time=block.host_observation_ns;++out;return true;
    }
    StreamPoll poll(unsigned i,StreamInput* input) noexcept override {
        event(200+i);auto& slot=slots[i];if(!slot.pending){bad=true;return StreamPoll::unproven;}
        if(unproven&(1u<<i))return StreamPoll::unproven;
        if(slot.cancelled){
            if(never_cancel&(1u<<i))return StreamPoll::pending;
            slot.pending=false;return StreamPoll::failure;
        }
        if((i<4?hold_in:hold_out)&(1u<<i))return StreamPoll::pending;
        slot.pending=false;
        if(fail_poll&(1u<<i))return StreamPoll::failure;
        if(i<4 && input){
            input->packet_count=intervals;input->pcm.fill(0xed);
            for(unsigned p=0;p<intervals;++p){
                const auto bytes=std::uint64_t(packet_frames(slot.batch,p))*18;input->packets[p]={bytes,0};
                for(std::size_t k=0;k<bytes;++k)input->pcm[p*126+k]=byte(slot.batch,p,k);
            }
            if(i==0){
                if(bad_input==1)input->packet_count=65;
                if(bad_input==2)input->packets[0].status=std::uint64_t(1)<<32;
                if(bad_input==3)input->packets[0].length=0;
                if(bad_input==4)input->packets[0].length=127;
                if(bad_input==5)input->packets[0].length=19;
                if(bad_input==6)input->packets[0].length=(std::uint64_t(1)<<32)+18;
            }
            if(slot.batch<startup_empty_batches)
                for(unsigned p=0;p<intervals;++p)input->packets[p]={p==1?0u:108u,0};
        }
        return StreamPoll::success;
    }
    bool cancel(unsigned i) noexcept override {event(100+i);cancel_mask|=1u<<i;slots[i].cancelled=true;return !(cancel_false&(1u<<i));}
    bool release(unsigned i) noexcept override {
        event(300+i);++release_calls;if(!slots[i].prepared || slots[i].pending){bad=true;return false;}
        if(release_false&(1u<<i))return false;slots[i].prepared=false;return true;
    }
    std::uint64_t now_ns() const noexcept override {return now;}
    unsigned live() const {unsigned mask=0;for(unsigned i=0;i<8;++i)if(slots[i].pending)mask|=1u<<i;return mask;}
};
struct Peer final:ContinuousPeer {
    static constexpr unsigned capacity=8; // Same capacity as the real data queue.
    std::array<AudioBlock,capacity> queue{};
    AudioBlock retry{};
    unsigned read=0,write=0,count=0,wrong_output=0;
    std::uint64_t batches=0,position=0,last_time=0;
    unsigned input_batch_offset=0;
    bool full=false,empty=false,publish_error=false,receive_error=false,have_retry=false,bad=false;
    StreamExchange publish_input(const AudioBlock& block) noexcept override {
        if(publish_error)return StreamExchange::failure;
        if(full){if(have_retry && !same(retry,block))bad=true;retry=block;have_retry=true;return StreamExchange::full;}
        if(count==capacity)return StreamExchange::full;
        if(have_retry && !same(retry,block))bad=true;have_retry=false;
        if(block.first_frame!=position || block.host_observation_ns<last_time)bad=true;
        const auto batch=batches+input_batch_offset;
        std::size_t offset=0;
        for(unsigned p=0;p<64;++p){
            const auto n=p<block.packet_count?packet_frames(batch,p):0;
            if(block.frames_per_packet[p]!=n)bad=true;
            for(unsigned k=0;k<unsigned(n)*18;++k)if(block.pcm[offset++]!=byte(batch,p,k))bad=true;
        }
        queue[write]=block;write=(write+1)%capacity;++count;++batches;position+=frames(batch,block.packet_count);last_time=block.host_observation_ns;return StreamExchange::ok;
    }
    StreamExchange receive_output(AudioBlock& block) noexcept override {
        if(receive_error)return StreamExchange::failure;
        if(empty || !count)return StreamExchange::empty;
        block=queue[read];read=(read+1)%capacity;--count;
        if(wrong_output==1)++block.first_frame;
        if(wrong_output==2)++block.host_observation_ns;
        if(wrong_output==3)block.reported_rate_hz=48000;
        if(wrong_output==4)++block.packet_count;
        if(wrong_output==5)++block.frames_per_packet.back();
        return StreamExchange::ok;
    }
};
static void stopped(ContinuousStream& stream,Backend& backend){
    stream.stop();require(stream.step()==StreamState::stopped,"Terminal requests released on stop");
    require(!backend.bad && !backend.live() && backend.release_calls==8 && !stream.stats().retained_mask,"All native leases released only after terminal completion");
}
static void sustained(){
    for(unsigned rate:{44100u,48000u})for(unsigned intervals:{8u,16u,64u}){
        Backend backend;backend.rate=rate;Peer peer;ContinuousStream stream(backend,peer);
        require(stream.start({rate,intervals,20,2}) && stream.stats().pending_mask==15,"Prepare eight slots and queue four input requests");
        const auto before=allocations.load();
        for(unsigned step=0;step<750;++step){backend.now+=100000;require(stream.step()==StreamState::running,"Sustained rearming remains live");}
        require(allocations.load()==before,"No C++ allocations through 3,000 continuously rearmed input/output batches");
        require(stream.stats().input_blocks==3000 && stream.stats().input_submissions==3004 && stream.stats().output_submissions==3000 &&
                stream.stats().input_frames==backend.out_position && !peer.bad && !backend.bad,"Exact variable packet PCM, positions and rearming over many slot wraps");
        require(stream.stats().pending_mask==255,"Both native directions continuously owned");
        backend.record=true;stopped(stream,backend);
        for(unsigned i=0;i<8;++i)require(backend.events[i]==100+i,"Cancel every direction before any drain poll");
        require(stream.fault()==StreamFault::none && !stream.start({}),"Stopped session cannot restart or silently reset");
    }
}
static void ordering_and_backpressure(){
    Backend backend;Peer peer;ContinuousStream stream(backend,peer);require(stream.start({44100,8,20,2}),"Start ordering test");
    backend.hold_in=1;require(stream.step()==StreamState::running && !stream.stats().input_blocks,"Later completed requests cannot overtake earliest input");
    backend.hold_in=0;peer.full=true;require(stream.step()==StreamState::running && !stream.stats().input_blocks,"Full peer leaves input lease/batch retained");
    for(unsigned i=0;i<5;++i){backend.now+=100000;require(stream.step()==StreamState::running && stream.stats().input_submissions==4,"Full publication never rearms or advances input");}
    peer.full=false;require(stream.step()==StreamState::running && stream.stats().input_blocks==4 && !peer.bad,"Exact held batch retried despite later observation time");
    stopped(stream,backend);
}
static void startup_failures(){
    for(unsigned slot=0;slot<8;++slot){
        Backend backend;backend.prepare_false=slot;Peer peer;ContinuousStream stream(backend,peer);
        require(!stream.start({}) && stream.state()==StreamState::stopped && stream.fault()==StreamFault::prepare &&
                !backend.in && backend.release_calls==slot && !backend.bad,"Preparation failure releases only acquired resources before any I/O");
    }
    for(std::uint64_t sequence=0;sequence<5;++sequence){
        Backend backend;backend.reject_input=sequence;Peer peer;ContinuousStream stream(backend,peer);
        if(sequence<4)require(!stream.start({}),"Initial submission failure rejected");
        else{require(stream.start({}),"Start before rearm failure");stream.step();}
        require(stream.state()==StreamState::stopped && stream.fault()==StreamFault::submit && !backend.live() && !backend.bad &&
                backend.release_calls==8,"Initial/rearm failure retires previously accepted requests");
    }
    Backend backend;backend.prepare_delay_ns=10000000;Peer peer;ContinuousStream stream(backend,peer);
    for(unsigned n:{0u,1u,7u,9u,65u})require(!stream.start({44100,n,20,2}) && !backend.prepared_calls,"Invalid interval count cannot allocate or submit");
    require(!stream.start({96000,8,20,2}) && !stream.start({44100,8,0,2}) && !stream.start({44100,8,20,0}),"Reject unsupported rate and unbounded-zero deadlines");
    require(stream.start({}) && stream.step()==StreamState::running,"Allocation time is excluded from pending-I/O deadline; rejected no-lease configuration permits valid start");stopped(stream,backend);
}
static void startup_empty_packet(){
    {
        Backend backend;backend.startup_empty_batches=1;backend.output_batch_offset=1;backend.hold_in=0xe;
        Peer peer;peer.input_batch_offset=1;ContinuousStream stream(backend,peer,true);
        require(stream.start({}) && stream.step()==StreamState::running && !peer.batches && !backend.out,
            "Discard the first defective batch without publishing PCM or submitting output");
        const auto discard=stream.startup_discard();
        require(discard.empty_packet==1 && discard.discarded_frames==42 && backend.in==5,
            "Record empty index and actual discarded frames and rearm the original slot");
        backend.hold_in=0;
        require(stream.step()==StreamState::running && peer.batches==4 && backend.out==4 && !peer.bad,
            "Following valid input begins at frame zero with exact duplex bytes");
        backend.bad_input=3;
        require(stream.step()==StreamState::stopped && stream.fault()==StreamFault::invalid_input && !backend.bad,
            "Empty packets after valid input still fail");
    }
    for(unsigned scenario=0;scenario<3;++scenario){
        Backend backend;backend.startup_empty_batches=scenario==0?2:1;
        Peer peer;ContinuousStream stream(backend,peer,scenario!=1);
        require(stream.start({scenario==2?48000u:44100u,8,20,2}),"Start empty-batch refusal case");
        require(stream.step()==StreamState::stopped && stream.fault()==StreamFault::invalid_input && !peer.batches &&
                stream.startup_discard().discarded_frames==(scenario==0?42u:0u),
            "Refuse repeat startup empties, disabled policy and different clock");
    }
}
static void faults(){
    for(unsigned bad=1;bad<=6;++bad){
        Backend backend;backend.bad_input=bad;Peer peer;ContinuousStream stream(backend,peer);require(stream.start({}),"Start bad input case");
        require(stream.step()==StreamState::stopped && stream.fault()==StreamFault::invalid_input && !peer.batches && !backend.out &&
                !backend.live() && !backend.bad,"Reject full-width bad packet metadata before publication/OUT submission");
    }
    for(unsigned bad=1;bad<=5;++bad){
        Backend backend;Peer peer;peer.wrong_output=bad;ContinuousStream stream(backend,peer);require(stream.start({}),"Start bad output case");
        require(stream.step()==StreamState::stopped && stream.fault()==StreamFault::output_mismatch && !backend.out && !backend.bad,"Reject unsolicited/mismatched output schedule before native submission");
    }
    for(unsigned direction=0;direction<2;++direction){
        Backend backend;Peer peer;ContinuousStream stream(backend,peer);require(stream.start({}),"Start I/O error case");
        if(direction){require(stream.step()==StreamState::running,"Queue OUT before output error");backend.fail_poll=16;}
        else backend.fail_poll=1;
        require(stream.step()==StreamState::stopped && stream.fault()==(direction?StreamFault::output_transfer:StreamFault::input_transfer) &&
                !backend.live() && !backend.bad,"Terminal native error retires that lease and cancels other direction");
    }
    for(unsigned direction=0;direction<2;++direction){
        Backend backend;Peer peer;ContinuousStream stream(backend,peer);require(stream.start({}),"Start peer error case");
        if(direction)peer.receive_error=true;else peer.publish_error=true;
        require(stream.step()==StreamState::stopped && stream.fault()==StreamFault::peer && !backend.live(),"Peer failure contains both native directions");
    }
    Backend backend;backend.reject_output=0;Peer peer;ContinuousStream stream(backend,peer);require(stream.start({}),"Start output submit rejection");
    require(stream.step()==StreamState::stopped && stream.fault()==StreamFault::submit && !backend.out && !backend.bad,"Rejected OUT submission acquires no native pending lease");
}
static void deadlines_and_retention(){
    for(unsigned type=0;type<4;++type){
        Backend backend;Peer peer;ContinuousStream stream(backend,peer);
        if(type==0)backend.hold_in=15;
        if(type==1)peer.full=true;
        if(type==2)peer.empty=true;
        if(type==3)backend.hold_out=240;
        require(stream.start({44100,8,20,2}),"Start bounded stall case");
        for(unsigned n=0;n<25 && stream.state()==StreamState::running;++n){stream.step();backend.now+=1000000;}
        require(stream.state()==StreamState::stopped && stream.fault()==(type==0?StreamFault::input_timeout:type==1?StreamFault::input_backpressure:
                type==2?StreamFault::output_starved:StreamFault::output_timeout) && !backend.bad && !backend.live(),"Each distinct stalled lease/peer state faults under a bounded deadline");
    }
    for(bool unknown:{false,true}){
        Backend backend;Peer peer;ContinuousStream stream(backend,peer);require(stream.start({44100,8,20,2}),"Start retained lease case");
        if(unknown){backend.unproven=1;require(stream.step()==StreamState::draining && stream.fault()==StreamFault::unproven_completion,"Failed observation preserves lease while cancellation begins");}
        else{backend.never_cancel=1;backend.cancel_false=1;stream.stop();require(stream.step()==StreamState::draining,"Failed cancellation/pending completion is not cleanup");}
        require(backend.slots[0].prepared && backend.slots[0].pending && backend.release_calls==7,"Unproven native slot not released while other terminal slots retire");
        backend.now+=2000000;require(stream.step()==StreamState::retained && stream.stats().retained_mask==1 && stream.stats().pending_mask==1 &&
                backend.release_calls==7 && !backend.bad,"One drain deadline retains exact unresolved slot for process containment");
        const auto releases=backend.release_calls;stream.stop();require(stream.step()==StreamState::retained && backend.release_calls==releases,"Retained state never auto-retries or frees native memory");
    }
    {
        Backend backend;backend.reject_input=1;backend.never_cancel=1;Peer peer;ContinuousStream stream(backend,peer);
        require(!stream.start({44100,8,20,2}) && stream.state()==StreamState::draining && backend.live()==1,
                "Failed start can retain a previously accepted native request; false is not cleanup proof");
        backend.now+=2000000;require(stream.step()==StreamState::retained && stream.fault()==StreamFault::submit &&
                stream.stats().retained_mask==1 && backend.release_calls==7 && !backend.bad,"Partial-start drain uses same exact lease retention and preserves first error");
    }
    {
        Backend backend;backend.release_false=16;Peer peer;ContinuousStream stream(backend,peer);require(stream.start({}),"Start release failure");
        stream.stop();require(stream.step()==StreamState::retained && stream.fault()==StreamFault::release && stream.stats().retained_mask==16 &&
                backend.slots[4].prepared && !backend.live(),"Failed terminal resource release reported as incomplete cleanup");
    }
    {
        Backend backend;backend.never_cancel=1;Peer peer;ContinuousStream stream(backend,peer);require(stream.start({}),"Start regressed clock case");
        --backend.now;require(stream.step()==StreamState::retained && stream.fault()==StreamFault::clock && stream.stats().retained_mask==1 &&
                !backend.bad,"Lost monotonic clock cannot create an endless drain or free unproven I/O");
    }
}
int main(){
    try{sustained();ordering_and_backpressure();startup_failures();startup_empty_packet();faults();deadlines_and_retention();
        std::cout<<"Continuous request engine: 18,000 rearmed duplex batches, exact packet PCM, zero measured C++ allocations, ordering, deadlines, cross-direction cancellation and retained leases passed; fake I/O only\n";
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
