#include "asio/queue_pump.hpp"
#include "windows/worker_process.hpp"
#include "audio_pattern.hpp"
#include <atomic>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <new>
#include <stdexcept>

using namespace sl3::asio;
using namespace sl3::worker;
static std::atomic<std::size_t> allocations{0};
void* operator new(std::size_t size){allocations.fetch_add(1);if(auto* p=std::malloc(size?size:1))return p;throw std::bad_alloc();}
void* operator new[](std::size_t size){return ::operator new(size);}
void operator delete(void* p) noexcept{std::free(p);}
void operator delete[](void* p) noexcept{std::free(p);}
void operator delete(void* p,std::size_t) noexcept{std::free(p);}
void operator delete[](void* p,std::size_t) noexcept{std::free(p);}
static void require(bool good,const char* message){if(!good)throw std::runtime_error(message);}
struct Host {
    BufferSet buffers;
    std::array<ASIOBufferInfo,12> info{};
    QueuePump* pump=nullptr;
    unsigned bank_frames=0,calls=0;
    bool throws=false;
};
static Host* current=nullptr;
static void callback(long bank,ASIOBool direct){
    auto& host=*current;
    require(direct==ASIOTrue && bank==long(host.calls%2),"Host callback bank/direct flag");
    const auto observed=host.buffers.observation();
    require(observed.valid && observed.first_frame==std::uint64_t(host.calls)*host.bank_frames,"Callback frame position");
    require(host.pump->step()==PumpResult::reentrant_call && host.pump->end()==PumpResult::reentrant_call &&
            host.pump->begin(44100)==PumpResult::reentrant_call,"Callback cannot reenter pump lifecycle");
    if(host.throws)throw std::runtime_error("Test host callback failure");
    for(unsigned c=0;c<6;++c){
        const auto* input=static_cast<const std::uint8_t*>(host.info[c].buffers[bank]);
        for(unsigned f=0;f<host.bank_frames;++f){
            std::uint8_t expected[3]{};pattern::pack(pattern::value(observed.first_frame+f,c),expected);
            require(std::memcmp(input+f*3,expected,3)==0,"Signed 24-bit host input differs");
        }
        std::memcpy(host.info[6+c].buffers[bank],host.info[5-c].buffers[bank],host.bank_frames*3);
    }
    ++host.calls;
}
static void prepare(Host& host,unsigned frames){
    host.bank_frames=frames;current=&host;
    for(long c=0;c<6;++c){host.info[std::size_t(c)]={ASIOTrue,c,{}};host.info[std::size_t(6+c)]={ASIOFalse,c,{}};}
    ASIOCallbacks callbacks{};callbacks.bufferSwitch=callback;
    require(host.buffers.create(host.info.data(),12,frames,&callbacks)==ASE_OK,"Prepare complete logical channel set");
}
static void local_flow(){
    auto channel=Mailbox::create();auto source=Mailbox::open(channel->name());Host host;prepare(host,64);
    QueuePump pump(*channel,host.buffers);host.pump=&pump;
    require(pump.step()==PumpResult::invalid_state && pump.begin(96000)==PumpResult::invalid_rate,"Reject unstarted/unsupported flow");
    require(pump.begin(44100)==PumpResult::ok && pump.begin(44100)==PumpResult::invalid_state,"Begin only once");
    require(pump.step()==PumpResult::idle && !host.calls,"Empty queue creates no callbacks");
    const auto allocated=allocations.load();std::uint64_t position=0;AudioBlock output;
    for(unsigned n=0;n<1000;++n){
        const auto input=pattern::input(n,position,44100);
        require(source->try_push_audio(AudioDirection::input,input)==AudioResult::ok,"Local source publication");
        require(pump.step()==PumpResult::ok,"Pump block into host/output queue");
        require(source->try_pop_audio(AudioDirection::output,output)==AudioResult::ok && pattern::output_matches(output,n,position,44100,64),"Every local output byte/schedule");
        position+=pattern::frames(input);
    }
    require(allocations.load()==allocated,"No C++ allocation in 1,000 full successful pump paths including host callbacks");
    require(pump.stats().received_frames==position && pump.stats().published_frames==position &&
            host.calls==position/64,"All actual frames counted once");
    require(pump.end()==PumpResult::ok && pump.end()==PumpResult::ok && pump.step()==PumpResult::ended &&
            pump.begin(44100)==PumpResult::invalid_state,"End is idempotent; fresh channel required for restart");
    require(host.buffers.dispose()==ASE_OK,"Owner ended before disposal");
}
static void backpressure(bool discard){
    auto channel=Mailbox::create();auto source=Mailbox::open(channel->name());Host host;prepare(host,128);
    QueuePump pump(*channel,host.buffers);host.pump=&pump;require(pump.begin(48000)==PumpResult::ok,"Begin full-output scenario");
    std::uint64_t position=0;
    for(unsigned n=0;n<9;++n){
        const auto input=pattern::input(n,position,48000);
        require(source->try_push_audio(AudioDirection::input,input)==AudioResult::ok,"Source full-output scenario");
        require(pump.step()==(n==8?PumpResult::backpressure:PumpResult::ok),"Retain exactly the ninth output block");
        position+=pattern::frames(input);
    }
    const auto next=pattern::input(9,position,48000);
    require(source->try_push_audio(AudioDirection::input,next)==AudioResult::ok,"Queue later input behind retained output");
    const auto calls=host.calls;
    for(unsigned n=0;n<10;++n)require(pump.step()==PumpResult::backpressure && host.calls==calls &&
        pump.stats().received_blocks==9 && pump.stats().published_blocks==8,"No consume/render/callback replay on full output");
    const auto pending_frames=pattern::frames(pattern::input(8,0,48000));
    if(discard){
        require(pump.end()==PumpResult::ok && pump.stats().discarded_pending_frames==pending_frames &&
                !pump.stats().pending_output && pump.stats().published_blocks==8,"Explicit end accounts for unpublished pending block");
    }else{
        AudioBlock output;std::uint64_t consumed_position=0;
        require(source->try_pop_audio(AudioDirection::output,output)==AudioResult::ok &&
                pattern::output_matches(output,0,0,48000,128),"Retire first output to free capacity");
        consumed_position+=pattern::frames(output);
        require(pump.step()==PumpResult::ok && host.calls==calls && pump.stats().received_blocks==9 &&
                pump.stats().published_blocks==9,"Retry publishes exact pending block before later input");
        for(unsigned n=1;n<9;++n){
            require(source->try_pop_audio(AudioDirection::output,output)==AudioResult::ok &&
                    pattern::output_matches(output,n,consumed_position,48000,128),"No duplicate/lost block after backpressure");
            consumed_position+=pattern::frames(output);
        }
        require(pump.step()==PumpResult::ok && pump.stats().received_blocks==10,"Later input consumed only after pending block retired");
        require(source->try_pop_audio(AudioDirection::output,output)==AudioResult::ok &&
                pattern::output_matches(output,9,position,48000,128),"Later block exact after recovery");
        require(pump.end()==PumpResult::ok && !pump.stats().discarded_pending_frames,"No unreported pending discard");
    }
}
static void faults(){
    for(unsigned fault=0;fault<4;++fault){
        auto channel=Mailbox::create();auto source=Mailbox::open(channel->name());Host host;prepare(host,64);
        QueuePump pump(fault==3?*source:*channel,host.buffers);host.pump=&pump;
        require(pump.begin(44100)==PumpResult::ok,"Begin fault scenario");
        if(fault==0)channel->close();
        if(fault==1)require(source->try_push_audio(AudioDirection::input,pattern::input(0,0,48000))==AudioResult::ok,"Mismatched rate metadata accepted by otherwise fresh queue");
        // Force enough frames to reach a callback. A valid eight-interval
        // block may contain fewer than the minimum 64-frame host bank.
        if(fault==2){host.throws=true;require(source->try_push_audio(AudioDirection::input,pattern::input(0,0,44100,64))==AudioResult::ok,"Queue throwing callback input");}
        require(pump.step()==PumpResult::faulted && pump.state()==PumpState::faulted,"Fault latches locally");
        const auto failure=pump.failure();
        require((fault==0 && failure.cause==PumpFault::queue && failure.queue==AudioResult::closed) ||
                (fault==1 && failure.cause==PumpFault::rate && failure.queue==AudioResult::rate_changed) ||
                (fault==2 && failure.cause==PumpFault::bridge && failure.bridge==sl3::BridgeStatus::callback_failure) ||
                (fault==3 && failure.cause==PumpFault::queue && failure.queue==AudioResult::wrong_role),"Specific first failure retained");
        const auto calls=host.calls;
        require(pump.step()==PumpResult::faulted && pump.failure().cause==failure.cause && host.calls==calls &&
                pump.begin(44100)==PumpResult::invalid_state,"Fault cannot silently resume or replay callbacks");
        require(pump.end()==PumpResult::ok && host.buffers.state()==sl3::BridgeState::ready,"Fault cleanup releases buffer flow");
    }
}
int wmain(int argc,wchar_t** argv){
    try{
        require(argc==2,"Fixture path required");local_flow();backpressure(false);backpressure(true);faults();
        const std::filesystem::path fixture=argv[1];const auto hash=Process::executable_sha256(fixture);
        for(unsigned rate:{44100u,48000u})for(unsigned bank_frames:{64u,128u,1024u})for(unsigned packets:{0u,8u,64u}){
            auto channel=Mailbox::create();Host host;prepare(host,bank_frames);
            QueuePump pump(*channel,host.buffers);host.pump=&pump;
            require(pump.begin(rate)==PumpResult::ok,"Begin synthetic worker flow");
            Process worker;worker.launch(fixture,hash,{L"--audio-source",channel->name(),std::to_wstring(rate),std::to_wstring(bank_frames),std::to_wstring(packets)});
            require(channel->send(1,nullptr,0),"Tell fixture to begin synthetic input");Message ready;
            require(channel->await_reply(worker.process_handle(),2000,ready)==MessageResult::ok,"Synthetic fixture ready");
            const auto started=GetTickCount64();
            while(pump.stats().published_blocks<pattern::process_blocks){
                const auto calls=host.calls;
                const auto result=pump.step();require(result==PumpResult::ok || result==PumpResult::idle || result==PumpResult::backpressure,"Synthetic worker flow remains valid");
                if(packets==8)require(host.calls-calls<=1,"One-ms batch cannot bunch two minimum-size host callbacks");
                require(GetTickCount64()-started<10000 && !worker.observe().process_exited,"Live synthetic flow bounded");
                if(result!=PumpResult::ok)Sleep(1);
            }
            require(channel->send(2,nullptr,0),"Finish synthetic source/output verification");Message final;
            require(channel->await_reply(worker.process_handle(),2000,final)==MessageResult::ok && final.status==0 &&
                    worker.wait_for_exit(2000) && worker.observe().exit_code==0,"Worker verified every output byte and exited");
            require(worker.terminate_and_wait().state.job_empty,"Synthetic source job retired");
            require(host.calls==pump.stats().received_frames/bank_frames && pump.stats().received_frames==pump.stats().published_frames,"Callback count and actual frame conservation across processes");
            require(pump.end()==PumpResult::ok && host.buffers.dispose()==ASE_OK,"Retire software owner before buffer disposal");
        }
        std::cout<<"Queue-to-SDK path: 7,200 real-process blocks with mixed/8/64 intervals, all logical channels/PCM bytes, variable packets, backpressure, faults, reentry and zero measured C++ allocations passed; no USB/ASIO DLL availability\n";
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
