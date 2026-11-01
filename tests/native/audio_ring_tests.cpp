#include "windows/mailbox.hpp"
#include "windows/mailbox_layout.hpp"
#include "windows/worker_process.hpp"
#include <atomic>
#include <cstdlib>
#include <iostream>
#include <new>
#include <stdexcept>
#include <thread>

using namespace sl3::worker;
static std::atomic<std::size_t> allocations{0};
void* operator new(std::size_t size){allocations.fetch_add(1);if(auto* p=std::malloc(size?size:1))return p;throw std::bad_alloc();}
void* operator new[](std::size_t size){return ::operator new(size);}
void operator delete(void* p) noexcept{std::free(p);}
void operator delete[](void* p) noexcept{std::free(p);}
void operator delete(void* p,std::size_t) noexcept{std::free(p);}
void operator delete[](void* p,std::size_t) noexcept{std::free(p);}
static void require(bool value,const char* text){if(!value)throw std::runtime_error(text);}
static AudioBlock block(unsigned number,std::uint64_t position,unsigned rate=44100){
    AudioBlock value;value.first_frame=position;value.host_observation_ns=1000+number;
    value.reported_rate_hz=rate;value.frames_per_packet.fill(1);
    value.pcm.fill(0xa5);for(std::size_t i=0;i<64*18;++i)value.pcm[i]=std::uint8_t(number+i);
    return value;
}
static std::size_t frames(const AudioBlock& value){std::size_t count=0;for(auto n:value.frames_per_packet)count+=n;return count;}
static AudioBlock variable_block(unsigned number,std::uint64_t position,unsigned rate){
    auto value=block(number,position,rate);
    value.packet_count=8*(1+number%8);value.frames_per_packet.fill(0);
    for(std::size_t n=0;n<value.packet_count;++n)value.frames_per_packet[n]=std::uint8_t(1+(number+n)%7);
    for(std::size_t n=0;n<frames(value)*18;++n)value.pcm[n]=std::uint8_t(number+n);
    return value;
}
struct View {
    HANDLE handle=nullptr;wire::Shared* shared=nullptr;
    explicit View(const std::wstring& name){
        handle=OpenFileMappingW(FILE_MAP_ALL_ACCESS,FALSE,(name+L"-map").c_str());
        if(handle)shared=static_cast<wire::Shared*>(MapViewOfFile(handle,FILE_MAP_ALL_ACCESS,0,0,sizeof(wire::Shared)));
        require(shared!=nullptr,"Map only this test's private data queues");
    }
    ~View(){if(shared)UnmapViewOfFile(shared);if(handle)CloseHandle(handle);}
};
int wmain(int argc,wchar_t** argv){
    try{
        require(argc==2,"Fixture path required");
        {
            auto host=Mailbox::create();auto peer=Mailbox::open(host->name());AudioBlock output;output.first_frame=999;
            require(host->try_pop_audio(AudioDirection::input,output)==AudioResult::empty && output.first_frame==999,"Empty read leaves caller unchanged");
            require(host->try_push_audio(AudioDirection::input,block(0,0))==AudioResult::wrong_role,"Host cannot write worker input");
            for(unsigned n=0;n<8;++n)require(host->try_push_audio(AudioDirection::output,block(n,n*64))==AudioResult::ok,"Fill all bounded slots");
            require(host->try_push_audio(AudioDirection::output,block(8,512))==AudioResult::full,"Full publication never advances ownership");
            require(peer->try_pop_audio(AudioDirection::output,output)==AudioResult::ok && output.first_frame==0,"Oldest block first");
            require(output.pcm[1151]==std::uint8_t(1151u&255u) && output.pcm[1152]==0 && output.pcm.back()==0,"Only actual PCM bytes copied; padding excluded");
            require(host->try_push_audio(AudioDirection::output,block(8,512))==AudioResult::ok,"Retry same block after capacity returns");
            for(unsigned n=1;n<9;++n)require(peer->try_pop_audio(AudioDirection::output,output)==AudioResult::ok && output.first_frame==n*64,"FIFO after full queue and wrap");
            const auto before=allocations.load();
            for(unsigned n=9;n<1009;++n){
                const auto data=block(n,n*64);
                require(host->try_push_audio(AudioDirection::output,data)==AudioResult::ok,"Steady producer");
                require(peer->try_pop_audio(AudioDirection::output,output)==AudioResult::ok,"Steady consumer");
            }
            require(allocations.load()==before,"No C++ new allocations in successful data operations");
            auto maximum=block(1009,1009*64);maximum.frames_per_packet.fill(7);
            require(host->try_push_audio(AudioDirection::output,maximum)==AudioResult::ok &&
                peer->try_pop_audio(AudioDirection::output,output)==AudioResult::ok && output.pcm.back()==0xa5,"Maximum-size PCM block copied through the final byte");
            host->close();require(peer->try_pop_audio(AudioDirection::output,output)==AudioResult::closed,"Explicit close stops new queue operations");
        }
        for(const unsigned count:{8u,16u,24u,32u,40u,48u,56u,64u}){
            auto host=Mailbox::create();auto peer=Mailbox::open(host->name());AudioBlock output;
            auto input=block(0,0);input.packet_count=count;input.frames_per_packet.fill(0);
            for(unsigned i=0;i<count;++i)input.frames_per_packet[i]=1;
            require(host->try_push_audio(AudioDirection::output,input)==AudioResult::ok &&
                peer->try_pop_audio(AudioDirection::output,output)==AudioResult::ok && output.packet_count==count &&
                output.frames_per_packet==input.frames_per_packet,"Every allowed active interval count preserved");
            require(output.pcm[count*18-1]==input.pcm[count*18-1] && output.pcm[count*18]==0,"Only active packet PCM copied, caller tail excluded");
        }
        {
            auto host=Mailbox::create();auto peer=Mailbox::open(host->name());AudioBlock output;
            for(unsigned n=0;n<8;++n)require(host->try_push_audio(AudioDirection::output,block(n,n*64))==AudioResult::ok,"Fill host output before space wake");
            require(WaitForSingleObject(peer->output_event(),0)==WAIT_OBJECT_0 && WaitForSingleObject(host->input_event(),0)==WAIT_TIMEOUT,"Drain old data wake, no fabricated host work");
            require(peer->try_pop_audio(AudioDirection::output,output)==AudioResult::ok && WaitForSingleObject(host->input_event(),10)==WAIT_OBJECT_0 &&
                host->try_pop_audio(AudioDirection::input,output)==AudioResult::empty && host->try_push_audio(AudioDirection::output,block(8,512))==AudioResult::ok,
                "Retired output wakes a blocked host producer without inventing input");
            WaitForSingleObject(peer->output_event(),0);
            require(peer->try_push_audio(AudioDirection::input,block(0,0))==AudioResult::ok && host->try_pop_audio(AudioDirection::input,output)==AudioResult::ok &&
                WaitForSingleObject(peer->output_event(),10)==WAIT_OBJECT_0,"Retired input wakes worker publication-space retry");
        }
        for(const unsigned count:{0u,1u,7u,9u,63u,65u,0xffffffffu}){
            auto host=Mailbox::create();auto peer=Mailbox::open(host->name());auto invalid=block(0,0);invalid.packet_count=count;
            require(host->try_push_audio(AudioDirection::output,invalid)==AudioResult::invalid_packet &&
                peer->audio_fault()==AudioResult::invalid_packet,"Invalid local interval count rejected without indexing");
        }
        {
            auto host=Mailbox::create();auto peer=Mailbox::open(host->name());auto invalid=block(0,0);invalid.packet_count=8;
            require(host->try_push_audio(AudioDirection::output,invalid)==AudioResult::invalid_packet,"Nonzero inactive packet metadata rejected");
        }
        for(unsigned corruption=0;corruption<3;++corruption){
            auto host=Mailbox::create();auto peer=Mailbox::open(host->name());View view(host->name());AudioBlock output;output.first_frame=999;
            auto input=block(0,0);input.packet_count=8;input.frames_per_packet.fill(0);for(unsigned i=0;i<8;++i)input.frames_per_packet[i]=1;
            require(host->try_push_audio(AudioDirection::output,input)==AudioResult::ok,"Publish small block before wire mutation");
            if(corruption==0)view.shared->output.slots[0].packet_count=0xffffffffu;
            if(corruption==1)view.shared->output.slots[0].frames_per_packet[8]=1;
            if(corruption==2)view.shared->version_value=2;
            require(peer->try_pop_audio(AudioDirection::output,output)==(corruption==2?AudioResult::protocol_error:AudioResult::invalid_packet) &&
                output.first_frame==999,"Malformed wire count/tail or prior transport version never publishes partial output");
        }
        for(const auto expected:{AudioResult::discontinuity,AudioResult::clock_regression,AudioResult::rate_changed,AudioResult::invalid_packet}){
            auto host=Mailbox::create();auto peer=Mailbox::open(host->name());AudioBlock output;
            require(host->try_push_audio(AudioDirection::output,block(0,0))==AudioResult::ok,"Start fault scenario");
            require(peer->try_pop_audio(AudioDirection::output,output)==AudioResult::ok,"Retire prior valid data");
            auto invalid=block(1,64);
            if(expected==AudioResult::discontinuity)++invalid.first_frame;
            if(expected==AudioResult::clock_regression)invalid.host_observation_ns=1;
            if(expected==AudioResult::rate_changed)invalid.reported_rate_hz=48000;
            if(expected==AudioResult::invalid_packet)invalid.frames_per_packet[0]=0;
            require(host->try_push_audio(AudioDirection::output,invalid)==expected && peer->audio_fault()==expected,"Latch first audio fault");
            require(peer->try_pop_audio(AudioDirection::output,output)==AudioResult::faulted,"Fault never becomes silent data loss/retry");
            require(host->send(1,nullptr,0),"Control remains usable for shutdown after audio fault");Message request;
            require(peer->receive(10,request)==MessageResult::ok && peer->respond(0,nullptr,0),"Control request still retires after data fault");
        }
        {
            auto host=Mailbox::create();auto peer=Mailbox::open(host->name());View view(host->name());
            InterlockedExchange(&view.shared->output.read,LONG(0xfffffffcu));InterlockedExchange(&view.shared->output.write,LONG(0xfffffffcu));
            AudioBlock result;
            for(unsigned n=0;n<12;++n){
                require(host->try_push_audio(AudioDirection::output,block(n,n*64))==AudioResult::ok,"Unsigned publication counter wraps");
                require(peer->try_pop_audio(AudioDirection::output,result)==AudioResult::ok && result.first_frame==n*64,"Unsigned consumption counter wraps");
            }
        }
        {
            auto host=Mailbox::create();auto peer=Mailbox::open(host->name());View view(host->name());AudioBlock result;result.first_frame=999;
            require(host->try_push_audio(AudioDirection::output,block(0,0))==AudioResult::ok,"Publish wire corruption scenario");
            view.shared->output.slots[0].pcm_bytes=0xffffffff;
            require(peer->try_pop_audio(AudioDirection::output,result)==AudioResult::invalid_packet && result.first_frame==999,"Reject oversized wire count without copying or advancing caller output");
        }
        {
            auto host=Mailbox::create();auto peer=Mailbox::open(host->name());View view(host->name());AudioBlock result;result.first_frame=999;
            InterlockedExchange(&view.shared->output.write,9);
            require(peer->try_pop_audio(AudioDirection::output,result)==AudioResult::protocol_error && result.first_frame==999,"Reject impossible queue occupancy before slot access");
        }
        {
            auto host=Mailbox::create();auto peer=Mailbox::open(host->name());AudioBlock result;
            require(host->wait_pop_audio(AudioDirection::input,0,result)==AudioResult::timeout,"Empty data wait is bounded");
            std::atomic<AudioResult> published{AudioResult::protocol_error};
            std::thread producer([&]{Sleep(10);published=peer->try_push_audio(AudioDirection::input,block(0,0));});
            const auto waited=host->wait_pop_audio(AudioDirection::input,1000,result);producer.join();
            require(waited==AudioResult::ok && published==AudioResult::ok,"Separate data event wakes waiting consumer");
            std::thread closer([&]{Sleep(10);host->close();});
            const auto closed=host->wait_pop_audio(AudioDirection::input,1000,result);closer.join();
            // The prior publication's event may be consumed as an empty wake;
            // a subsequent read must then observe the explicit close.
            require(closed==AudioResult::closed || closed==AudioResult::empty,"Close/previous wake is explicit");
            require(host->try_pop_audio(AudioDirection::input,result)==AudioResult::closed,"Close blocks newly entered data operations");
        }
        const std::filesystem::path fixture=argv[1];const auto hash=Process::executable_sha256(fixture);
        for(const unsigned rate:{44100u,48000u}){
            auto channel=Mailbox::create();Process worker;worker.launch(fixture,hash,{L"--audio-rings",channel->name()});
            require(channel->send(1,nullptr,0),"Start synthetic data fixture");Message ready;
            require(channel->await_reply(worker.process_handle(),2000,ready)==MessageResult::ok && ready.status==0,"Fixture ready, no device availability claim");
            unsigned produced=0,consumed=0;std::uint64_t produced_position=0,consumed_position=0;
            const auto start=GetTickCount64();AudioBlock output;
            while(consumed<1000){
                bool progressed=false;
                if(produced<1000){
                    const auto data=variable_block(produced,produced_position,rate);
                    const auto status=channel->try_push_audio(AudioDirection::output,data);
                    if(status==AudioResult::ok){produced_position+=frames(data);++produced;progressed=true;}else require(status==AudioResult::full,"Producer only backpressures");
                }
                const auto status=channel->try_pop_audio(AudioDirection::input,output);
                if(status==AudioResult::ok){
                    const auto expected=variable_block(consumed,consumed_position,rate);
                    require(output.first_frame==consumed_position && output.reported_rate_hz==rate && output.packet_count==expected.packet_count && output.frames_per_packet==expected.frames_per_packet,"Ordered variable-packet metadata");
                    for(std::size_t n=0;n<frames(expected)*18;++n)require(output.pcm[n]==expected.pcm[n],"Every actual PCM byte preserved across both process queues");
                    consumed_position+=frames(expected);
                    ++consumed;progressed=true;
                }else require(status==AudioResult::empty,"Consumer only reports empty");
                require(GetTickCount64()-start<5000,"Bounded synthetic queue test");if(!progressed)Sleep(1);
            }
            require(channel->send(2,nullptr,0),"Stop synthetic fixture");Message final;
            require(channel->await_reply(worker.process_handle(),2000,final)==MessageResult::ok && worker.wait_for_exit(2000) && worker.observe().exit_code==0,"Synthetic fixture retired");
            const auto stop=worker.terminate_and_wait();require(stop.state.process_exited && stop.state.job_empty,"No data worker left alive");
        }
        std::cout<<"Fixed audio queues: ownership, backpressure, faults, counter wrap, zero C++ allocations and 2,000 real-process block round trips passed; no USB\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
