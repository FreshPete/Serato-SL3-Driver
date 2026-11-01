#include "core/session_protocol.hpp"
#include "windows/mailbox.hpp"
#include "windows/worker_process.hpp"
#include <iostream>
#include <stdexcept>

using namespace sl3;
using namespace sl3::worker;
namespace protocol=sl3::session;
static void require(bool good,const char* text){if(!good)throw std::runtime_error(text);}
template<class F>static void rejects(F operation){bool failed=false;try{operation();}catch(const std::exception&){failed=true;}require(failed,"Malformed session payload accepted");}
static void word(std::vector<std::uint8_t>& bytes,unsigned index,std::uint32_t value){for(unsigned b=0;b<4;++b)bytes[index*4+b]=std::uint8_t(value>>(b*8));}
static void codecs(){
    for(auto kind:{protocol::Kind::native,protocol::Kind::simulated})require(protocol::decode_hello(protocol::encode_hello(kind))==kind,"Worker kind cannot be confused with audio readiness");
    auto hello=protocol::encode_hello(protocol::Kind::native);word(hello,2,2);rejects([&]{protocol::decode_hello(hello);});
    for(unsigned rate:{44100u,48000u})for(unsigned intervals:{8u,64u}){
        const auto encoded=protocol::encode_start({rate,intervals,20,2000});const auto decoded=protocol::decode_start(encoded);
        require(decoded.rate_hz==rate && decoded.intervals==intervals && decoded.stall_ms==20 && decoded.drain_ms==2000,"Strict configuration round trip");
        for(unsigned offset:{0u,1u,2u,3u,4u,5u,6u,7u}){auto corrupt=encoded;word(corrupt,offset,0xffffffff);rejects([&]{protocol::decode_start(corrupt);});}
    }
    for(unsigned rate:{44100u,48000u}){
        const auto clock=protocol::encode_clock(rate);require(protocol::decode_clock(clock)==rate,"Observed clock round trip");
        for(unsigned offset=0;offset<8;++offset){auto bad=clock;word(bad,offset,0xffffffff);rejects([&]{protocol::decode_clock(bad);});}
        auto bad=clock;bad.pop_back();rejects([&]{protocol::decode_clock(bad);});
    }
    rejects([]{protocol::encode_clock(96000);});
    auto old=protocol::encode_hello(protocol::Kind::native);word(old,0,1);rejects([&]{protocol::decode_hello(old);});
    protocol::Snapshot snapshot;snapshot.phase=protocol::Phase::stopped;snapshot.rate_hz=44100;snapshot.intervals=8;snapshot.diagnostic.assign(512,'x');
    snapshot.stats.input_submissions=std::uint64_t(1)<<40;snapshot.stats.input_blocks=std::uint64_t(1)<<35;
    snapshot.stats.output_submissions=std::uint64_t(1)<<34;snapshot.stats.output_completions=std::uint64_t(1)<<33;
    snapshot.stats.input_frames=std::uint64_t(1)<<60;snapshot.stats.output_frames_submitted=std::uint64_t(1)<<59;
    const auto encoded=protocol::encode_snapshot(snapshot);const auto decoded=protocol::decode_snapshot(encoded);
    require(encoded.size()==640 && decoded.stats.input_frames==snapshot.stats.input_frames && decoded.stats.output_submissions==snapshot.stats.output_submissions &&
            decoded.diagnostic==snapshot.diagnostic,"Bounded diagnostic and full-width counters preserved");
    for(unsigned offset:{0u,1u,2u,3u,4u,5u,6u,7u,8u,9u,11u,24u,31u}){
        auto corrupt=encoded;word(corrupt,offset,0xffffffff);rejects([&]{protocol::decode_snapshot(corrupt);});
    }
    auto corrupt=encoded;corrupt.pop_back();rejects([&]{protocol::decode_snapshot(corrupt);});
    snapshot.stats.pending_mask=1;rejects([&]{protocol::encode_snapshot(snapshot);});
}
struct Client {
    std::unique_ptr<Mailbox> channel=Mailbox::create();Process process;
    Client(const std::filesystem::path& executable,const std::wstring& mode,bool native=false){
        const auto hash=Process::executable_sha256(executable);
        if(native){
            const std::filesystem::path missing=L"C:/deliberately-missing-sl3-session-helper.dll";
            require(!std::filesystem::exists(missing),"Native negative test requires absent helper path");
            process.launch(executable,hash,{L"--stream-worker",L"--channel",channel->name(),L"--helper",missing.native()});
        }else process.launch(executable,hash,{channel->name(),mode});
    }
    Message call(protocol::Command command,const std::vector<std::uint8_t>& bytes={}){
        require(channel->send(std::uint32_t(command),bytes.data(),bytes.size()),"Send session command");Message reply;
        const auto received=channel->await_reply(process.process_handle(),2000,reply);
        if(received!=MessageResult::ok)throw std::runtime_error("Session reply failed: opcode="+std::to_string(std::uint32_t(command))+", result="+std::to_string(unsigned(received))+", exited="+std::to_string(process.observe().process_exited));
        return reply;
    }
    protocol::Snapshot state(){const auto reply=call(protocol::Command::state);require(reply.status==0,"State query status");return protocol::decode_snapshot(reply.bytes);}
    void hello(protocol::Kind kind=protocol::Kind::simulated){const auto reply=call(protocol::Command::hello);require(reply.status==0 && protocol::decode_hello(reply.bytes)==kind,"Typed session kind handshake");}
    void retired(DWORD expected){require(process.wait_for_exit(2000) && process.observe().exit_code==expected,"Exact worker exit code");require(process.terminate_and_wait().state.job_empty,"Session job fully retired");}
    void quit(DWORD expected=0){const auto reply=call(protocol::Command::quit);const auto snapshot=protocol::decode_snapshot(reply.bytes);
        require(snapshot.io_retired && snapshot.device_released,"Quit reply follows lease retirement and device release");retired(expected);}
};
static StreamConfig config(){return {48000,8,1000,20};}
static void healthy(const std::filesystem::path& fixture){
    Client client(fixture,L"normal");
    require(client.call(protocol::Command::start,protocol::encode_start(config())).status==std::uint32_t(protocol::Status::bad_state),"No hardware/factory before handshake");
    require(client.call(protocol::Command::inspect).status==std::uint32_t(protocol::Status::bad_state),"No inspection before handshake");
    client.hello();require(client.state().phase==protocol::Phase::idle,"Hello is not readiness");
    require(client.call(protocol::Command::inspect,{1}).status==std::uint32_t(protocol::Status::bad_request),"Inspection takes no body");
    for(unsigned i=0;i<2;++i){const auto clock=client.call(protocol::Command::inspect);
        require(clock.status==0 && protocol::decode_clock(clock.bytes)==48000,"Separate observed-clock reply");
        const auto idle=client.state();require(idle.phase==protocol::Phase::idle && !idle.rate_hz && !idle.stats.input_submissions && idle.io_retired && idle.device_released,"Inspection leaves no streaming ownership or fabricated readiness");
        AudioBlock unused;require(client.channel->try_pop_audio(AudioDirection::input,unused)==AudioResult::empty,"Inspection publishes no PCM");
    }
    require(client.call(protocol::Command::hello).status==std::uint32_t(protocol::Status::bad_state),"No duplicate hello");
    require(client.call(protocol::Command::start,{1}).status==std::uint32_t(protocol::Status::bad_request),"Malformed start rejected before factory");
    for(unsigned i=0;i<100;++i)require(client.state().phase==protocol::Phase::idle,"Continuous worker has no finite 64-request lifetime");
    auto reply=client.call(protocol::Command::start,protocol::encode_start(config()));auto snapshot=protocol::decode_snapshot(reply.bytes);
    require(reply.status==0 && snapshot.phase==protocol::Phase::running && !snapshot.io_retired && !snapshot.device_released,"Start means requests queued, never cleanup/audio validation");
    require(client.call(protocol::Command::start,protocol::encode_start(config())).status==std::uint32_t(protocol::Status::bad_state),"Live session cannot restart/reset queue positions");
    require(client.call(protocol::Command::inspect).status==std::uint32_t(protocol::Status::bad_state),"No redirect/clock inspection during active stream");
    AudioBlock block;unsigned batches=0;const auto start=GetTickCount64();std::uint64_t position=0;
    while(batches<100){
        const auto received=client.channel->try_pop_audio(AudioDirection::input,block);
        if(received==AudioResult::ok){
            require(block.first_frame==position && block.packet_count==8 && block.reported_rate_hz==48000,"Simulated session metadata and frame ordering");
            std::size_t offset=0;
            for(unsigned p=0;p<8;++p){require(block.frames_per_packet[p]==6,"Simulated fixed frame schedule");
                for(unsigned k=0;k<108;++k)require(block.pcm[offset++]==std::uint8_t(batches*17+p*13+k),"Actual shared-queue PCM bytes survive real session process");}
            auto pushed=client.channel->try_push_audio(AudioDirection::output,block);
            // Output capacity is independent of the next input publication.
            // Keep this exact block until accepted; do not consume more input,
            // drop PCM, reset ordering or extend the overall test deadline.
            while(pushed==AudioResult::full){
                require(GetTickCount64()-start<2000 && !client.process.observe().process_exited,"Bounded output backpressure");
                SwitchToThread();pushed=client.channel->try_push_audio(AudioDirection::output,block);
            }
            if(pushed!=AudioResult::ok)throw std::runtime_error("Echo actual schedule to simulated worker, queue result="+std::to_string(long(pushed)));
            position+=48;++batches;
        }else require(received==AudioResult::empty,"No unexpected data-plane result");
        require(GetTickCount64()-start<2000 && !client.process.observe().process_exited,"Bounded live cross-process session");if(received==AudioResult::empty)SwitchToThread();
    }
    reply=client.call(protocol::Command::stop);snapshot=protocol::decode_snapshot(reply.bytes);
    require(reply.status==0 && snapshot.phase==protocol::Phase::stopped && snapshot.io_retired && snapshot.device_released &&
            !snapshot.stats.pending_mask && !snapshot.stats.retained_mask && snapshot.stats.input_frames>=position,"Stop acknowledges complete native/device retirement");
    require(client.state().stats.input_frames==snapshot.stats.input_frames,"Stopped counts no longer advance");
    require(client.call(protocol::Command::start,protocol::encode_start(config())).status==std::uint32_t(protocol::Status::bad_state),"Stopped identity requires a fresh channel");
    require(client.call(protocol::Command::inspect).status==std::uint32_t(protocol::Status::bad_state),"Stopped identity cannot reopen inspection");
    client.quit();
}
static void failures(const std::filesystem::path& fixture){
    for(const auto* mode:{L"fail-inspect",L"invalid-clock"}){
        Client client(fixture,mode);client.hello();const auto reply=client.call(protocol::Command::inspect);
        const auto state=protocol::decode_snapshot(reply.bytes);
        require(reply.status==std::uint32_t(protocol::Status::operation_failed) && state.phase==protocol::Phase::failed && state.failure==protocol::Failure::startup &&
                state.io_retired && state.device_released && !state.stats.input_submissions && !state.rate_hz,"Failed/invalid inspection seals lifecycle without PCM or invented clock");
        require(client.call(protocol::Command::start,protocol::encode_start(config())).status==std::uint32_t(protocol::Status::bad_state),"Failed inspection cannot start on same identity");
        client.quit(1);
    }
    {
        Client client(fixture,L"hang-inspect");client.hello();
        require(client.channel->send(std::uint32_t(protocol::Command::inspect),nullptr,0),"Send stalled clock query");Message reply;
        require(client.channel->await_reply(client.process.process_handle(),2000,reply)==MessageResult::peer_exited,"Independent guardian contains stalled inspection");client.retired(70);
    }
    {
        Client client(fixture,L"partial-start");client.hello();const auto reply=client.call(protocol::Command::start,protocol::encode_start(config()));auto state=protocol::decode_snapshot(reply.bytes);
        require(reply.status==std::uint32_t(protocol::Status::operation_failed) && state.phase==protocol::Phase::draining && !state.io_retired &&
                !state.device_released && state.stats.pending_mask==1,"Failed start reports its still-owned native lease before delayed cleanup");
        const auto begin=GetTickCount64();do{state=client.state();require(GetTickCount64()-begin<2000,"Bounded partial-start drain");}while(state.phase!=protocol::Phase::failed);
        require(state.io_retired && state.device_released && state.stream_fault==StreamFault::submit,"Partial-start cleanup preserves original failure and retires device");client.quit(1);
    }
    {
        Client client(fixture,L"fail-start");client.hello();const auto reply=client.call(protocol::Command::start,protocol::encode_start(config()));const auto s=protocol::decode_snapshot(reply.bytes);
        require(reply.status==std::uint32_t(protocol::Status::operation_failed) && s.phase==protocol::Phase::failed && s.failure==protocol::Failure::startup &&
                s.io_retired && s.device_released && !s.stats.input_submissions,"Failed factory reports safe rollback, no fabricated readiness");client.quit(1);
    }
    {
        Client client(fixture,L"normal");client.hello();client.call(protocol::Command::start,protocol::encode_start(config()));AudioBlock input;
        const auto begin=GetTickCount64();while(client.channel->try_pop_audio(AudioDirection::input,input)==AudioResult::empty){require(GetTickCount64()-begin<1000,"Wait for simulated input");SwitchToThread();}
        input.frames_per_packet[0]=5; // Valid queue bytes, but wrong corresponding IN schedule.
        require(client.channel->try_push_audio(AudioDirection::output,input)==AudioResult::ok,"Queue itself accepts bounded but mismatched output");
        protocol::Snapshot state;
        do{state=client.state();require(GetTickCount64()-begin<2000,"Bounded automatic fault cleanup");}while(state.phase!=protocol::Phase::failed);
        require(state.failure==protocol::Failure::stream && state.stream_fault==StreamFault::output_mismatch && state.io_retired && state.device_released,
                "Data-plane fault stops both directions and preserves exact cause");client.quit(1);
    }
    {
        Client client(fixture,L"normal");client.hello();client.call(protocol::Command::start,protocol::encode_start(config()));client.channel->close();
        require(client.process.wait_for_exit(2000) && (client.process.observe().exit_code==0 || client.process.observe().exit_code==1),"Host close retires simulated target without fail-stop");
        require(client.process.terminate_and_wait().state.job_empty,"Closed-host session job empty");
    }
    for(const auto* mode:{L"hang-start",L"hang-submit",L"hang-poll",L"hang-close",L"fail-close",L"retained"}){
        Client client(fixture,mode);client.hello();const auto bytes=protocol::encode_start(config());
        require(client.channel->send(std::uint32_t(protocol::Command::start),bytes.data(),bytes.size()),"Send fault-injected session start");Message reply;
        const auto started=client.channel->await_reply(client.process.process_handle(),2000,reply);
        if(std::wstring(mode)==L"hang-start" || std::wstring(mode)==L"hang-submit")require(started==MessageResult::peer_exited,"Startup or initial native-submit hang independently contained");
        else{
            require(started==MessageResult::ok && reply.status==0,"Fault target initially queues requests");
            if(std::wstring(mode)==L"hang-close" || std::wstring(mode)==L"fail-close"){
                require(client.channel->send(std::uint32_t(protocol::Command::stop),nullptr,0),"Request injected cleanup failure");Message final;
                const auto stopped=client.channel->await_reply(client.process.process_handle(),2000,final);
                require(stopped==MessageResult::ok || stopped==MessageResult::peer_exited,"Cleanup containment can publish an error before exit");
                if(stopped==MessageResult::ok){const auto state=protocol::decode_snapshot(final.bytes);require(state.phase==protocol::Phase::retained && !state.device_released,"Failed cleanup never reports device release");}
            }
        }
        client.retired(70);
    }
}
static void native_negative(const std::filesystem::path& native){
    {
        Client inspection(native,L"",true);inspection.hello(protocol::Kind::native);
        const auto reply=inspection.call(protocol::Command::inspect);const auto state=protocol::decode_snapshot(reply.bytes);
        require(reply.status==std::uint32_t(protocol::Status::operation_failed) && state.phase==protocol::Phase::failed && state.failure==protocol::Failure::startup &&
                state.io_retired && state.device_released && !state.stats.input_submissions && !state.rate_hz && !state.diagnostic.empty(),"Native inspection rejects deliberately absent helper before loading or opening hardware");inspection.quit(1);
    }
    Client client(native,L"",true);client.hello(protocol::Kind::native);
    require(client.state().phase==protocol::Phase::idle,"Actual native executable waits for explicit start");
    require(client.call(protocol::Command::start,{1}).status==std::uint32_t(protocol::Status::bad_request),"Actual native malformed start never accesses hardware");
    const auto reply=client.call(protocol::Command::start,protocol::encode_start(config()));const auto snapshot=protocol::decode_snapshot(reply.bytes);
    require(reply.status==std::uint32_t(protocol::Status::operation_failed) && snapshot.phase==protocol::Phase::failed && snapshot.failure==protocol::Failure::startup &&
            snapshot.io_retired && snapshot.device_released && !snapshot.stats.input_submissions && !snapshot.diagnostic.empty(),
            "Actual native startup rejects missing service/helper before any audio; no helper can load from the deliberately absent path");
    client.quit(1);
}
static void long_heartbeat(const std::filesystem::path& fixture){
    Process child;const auto begin=GetTickCount64();child.launch(fixture,Process::executable_sha256(fixture),{L"--heartbeat-healthy",L"21500"});
    while(!child.wait_for_exit(1000))require(GetTickCount64()-begin<25000,"Long healthy heartbeat test bound");
    require(child.observe().exit_code==0 && child.terminate_and_wait().state.job_empty && GetTickCount64()-begin>=21500,"Healthy worker survives former fixed twenty-second cutoff");
    std::cout<<"{\"healthy_heartbeat_ms\":"<<GetTickCount64()-begin<<",\"exit_code\":0,\"job_empty\":true,\"physical_usb\":false}\n";
}
int wmain(int argc,wchar_t** argv){
    try{
        require(argc==3 || (argc==4 && std::wstring(argv[3])==L"--long-heartbeat"),"Fixture, native executable and optional long heartbeat mode");
        if(argc==4){long_heartbeat(argv[1]);return 0;}
        codecs();healthy(argv[1]);failures(argv[1]);native_negative(argv[2]);
        Process hung;hung.launch(argv[1],Process::executable_sha256(argv[1]),{L"--heartbeat-hang"});
        require(hung.wait_for_exit(2000) && hung.observe().exit_code==70 && hung.terminate_and_wait().state.job_empty,"Independent heartbeat contains a stuck worker without progress");
        std::cout<<"Continuous session codec, real-process start/state/stop/quit, shared audio, failed startup/fault cleanup, closed host and heartbeat/process containment passed; simulated I/O plus native absent-helper rejection only\n";
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
