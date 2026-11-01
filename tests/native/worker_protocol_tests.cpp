#include "core/worker_protocol.hpp"
#include "windows/mailbox.hpp"
#include "windows/worker_process.hpp"
#include <iostream>
#include <stdexcept>

namespace protocol=sl3::protocol;
using namespace sl3::worker;
static void require(bool value,const char* text){if(!value)throw std::runtime_error(text);}
template<class F>static void rejects(F operation){bool failed=false;try{operation();}catch(const std::exception&){failed=true;}require(failed,"Invalid typed payload must fail");}
int wmain(int argc,wchar_t** argv){
    try{
        require(argc==2 || (argc==3 && std::wstring(argv[2])==L"--probe-absent"),"Worker path and optional --probe-absent");
        const bool probe_absent=argc==3;
        if(probe_absent){
            const auto manager=OpenSCManagerW(nullptr,nullptr,SC_MANAGER_CONNECT);require(manager!=nullptr,"Read service manager");
            const auto service=OpenServiceW(manager,L"UsbDk",SERVICE_QUERY_STATUS);const auto error=GetLastError();
            if(service)CloseServiceHandle(service);CloseServiceHandle(manager);
            require(!service && error==ERROR_SERVICE_DOES_NOT_EXIST,"Explicit absence test requires UsbDk absent; no probe attempted");
        }
        require(protocol::decode_hello(protocol::encode_hello()).features==(protocol::descriptor_probe|protocol::finite_input),"Hello advertises only finite features");
        auto hello=protocol::encode_hello();hello[4]|=4;rejects([&]{protocol::decode_hello(hello);});
        protocol::validate_probe(protocol::encode_probe());
        for(const unsigned rate:{44100u,48000u}){
            protocol::CaptureBatch batch;batch.reported_rate_hz=rate;batch.frames_per_packet.resize(256);
            for(std::size_t i=0;i<256;++i)batch.frames_per_packet[i]=std::uint8_t(1+i%7);
            std::size_t frames=0;for(auto n:batch.frames_per_packet)frames+=n;
            batch.pcm.resize(frames*18);for(std::size_t i=0;i<batch.pcm.size();++i)batch.pcm[i]=std::uint8_t(i*31);
            auto bytes=protocol::encode_capture(batch);auto decoded=protocol::decode_capture(bytes);
            require(decoded.reported_rate_hz==rate && decoded.frames_per_packet==batch.frames_per_packet && decoded.pcm==batch.pcm,"Exact finite packet/PCM codec round trip");
            for(const auto offset:{0u,4u,8u,12u,16u,20u,24u,28u,32u}){
                auto corrupt=bytes;corrupt[offset]^=0x80;rejects([&]{protocol::decode_capture(corrupt);});
            }
            bytes.pop_back();rejects([&]{protocol::decode_capture(bytes);});
            batch.frames_per_packet.assign(256,7);batch.pcm.assign(256*126,0);
            require(protocol::encode_capture(batch).size()==protocol::maximum_reply && protocol::maximum_reply<=32768,"Worst-case payload fits without truncation");
            batch.frames_per_packet[0]=0;rejects([&]{protocol::encode_capture(batch);});
            batch.frames_per_packet[0]=8;rejects([&]{protocol::encode_capture(batch);});
        }
        const std::filesystem::path executable=argv[1],helper=L"C:/deliberately-missing-sl3-worker-helper.dll";
        require(!std::filesystem::exists(helper),"The test helper path must not exist; no helper may load");
        auto channel=Mailbox::create();Process worker;
        worker.launch(executable,Process::executable_sha256(executable),{L"--worker",L"--channel",channel->name(),L"--helper",helper.native()});
        auto call=[&](std::uint32_t command,const std::vector<std::uint8_t>& body=std::vector<std::uint8_t>{}){
            require(channel->send(command,body.data(),body.size()),"Publish typed command");Message reply;
            require(channel->await_reply(worker.process_handle(),2000,reply)==MessageResult::ok,"Typed worker reply");return reply;
        };
        auto reply=call(std::uint32_t(protocol::Command::capture_input));
        require(reply.status==std::uint32_t(protocol::Status::bad_state),"Capture before handshake never reaches hardware");
        reply=call(std::uint32_t(protocol::Command::hello));
        require(reply.status==0 && protocol::decode_hello(reply.bytes).features==3,"Actual diagnostic worker handshake without helper access");
        require(call(std::uint32_t(protocol::Command::hello)).status==std::uint32_t(protocol::Status::bad_state),"Duplicate handshake rejected");
        require(call(0xffffffff).status==std::uint32_t(protocol::Status::bad_request),"Unknown command rejected");
        require(call(std::uint32_t(protocol::Command::probe),{1}).status==std::uint32_t(protocol::Status::bad_request),"Malformed probe rejected before hardware access");
        if(probe_absent){
            reply=call(std::uint32_t(protocol::Command::probe));
            const std::string error(reply.bytes.begin(),reply.bytes.end());
            require(reply.status==std::uint32_t(protocol::Status::operation_failed) && error.find("1060")!=std::string::npos,"Missing service produces an explicit failure before helper load");
        }
        require(call(std::uint32_t(protocol::Command::quit)).status==0,"Graceful typed worker shutdown");
        require(worker.wait_for_exit(2000) && worker.observe().exit_code==0,"Diagnostic worker exited normally");
        const auto stop=worker.terminate_and_wait();require(stop.state.process_exited && stop.state.job_empty,"Worker fully retired");
        {
            auto bounded=Mailbox::create();Process limited;
            limited.launch(executable,Process::executable_sha256(executable),{L"--worker",L"--channel",bounded->name(),L"--helper",helper.native()});
            for(unsigned i=0;i<64;++i){
                const auto opcode=i?0xffffffffu:std::uint32_t(protocol::Command::hello);
                require(bounded->send(opcode,nullptr,0),"Publish bounded worker request");Message final;
                require(bounded->await_reply(limited.process_handle(),2000,final)==MessageResult::ok,"Final bounded reply survives peer exit");
                require(final.status==(i?std::uint32_t(protocol::Status::bad_request):0),"Bounded worker status");
            }
            require(limited.wait_for_exit(2000) && limited.observe().exit_code==0,"Request-limited worker retires normally");
            const auto retired=limited.terminate_and_wait();require(retired.state.process_exited && retired.state.job_empty,"Request-limited job cleanup");
        }
        std::cout<<(probe_absent?"Typed worker and real missing-driver failure checks passed":"Typed finite worker codec/handshake checks passed; no helper or USB access")<<'\n';
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
