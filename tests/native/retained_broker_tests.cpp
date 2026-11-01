// Real separate audio-client and worker processes; synthetic PCM/backend only.
#include "windows/retained_broker.hpp"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <stdexcept>

using namespace sl3;
using namespace sl3::worker;
namespace ds=device_session;
static void require(bool good,const char* text){if(!good)throw std::runtime_error(text);}
template<class F>static void rejects(F f){bool bad=false;try{f();}catch(const std::exception&){bad=true;}require(bad,"Broker accepted invalid ownership operation");}
static Message exchange(Mailbox& channel,Process& peer,unsigned op){
    require(channel.send(op,nullptr,0),"Publish test-client command");Message reply;
    require(channel.await_reply(peer.process_handle(),4000,reply)==MessageResult::ok && !reply.status,"Test-client command reply");return reply;
}
static int audio_client(const std::wstring& name){
    auto command=Mailbox::open(name);std::unique_ptr<Mailbox> audio;
    for(;;){
        Message request;require(command->receive(10000,request)==MessageResult::ok,"Client control stays available");
        std::vector<std::uint8_t> response;
        if(request.opcode==1){
            require(!audio,"Client cannot recycle a live mapping");audio=Mailbox::create();
            response=ds::encode_start({{48000,8,1000,200},audio->name()});
        }else if(request.opcode==2){
            require(bool(audio),"Client audio mapping exists");unsigned blocks=0;std::uint64_t next=0;
            const auto deadline=GetTickCount64()+2000;
            while(blocks<24 && GetTickCount64()<deadline){
                AudioBlock block;const auto got=audio->try_pop_audio(AudioDirection::input,block);
                if(got==AudioResult::empty){SwitchToThread();continue;}
                require(got==AudioResult::ok && block.first_frame==next && block.packet_count==8,"Fresh client receives ordered packets from zero");
                unsigned frames=0;for(unsigned n=0;n<block.packet_count;++n)frames+=block.frames_per_packet[n];next+=frames;
                block.pcm.fill(0);
                for(;;){const auto sent=audio->try_push_audio(AudioDirection::output,block);
                    if(sent==AudioResult::full){require(GetTickCount64()<deadline,"Client output deadline");SwitchToThread();continue;}
                    require(sent==AudioResult::ok,"Client publishes silent output directly to worker");break;}
                ++blocks;
            }
            require(blocks==24,"Client audio progressed");response={24};
        }else if(request.opcode==3){audio.reset();}
        else if(request.opcode!=4)throw std::runtime_error("Unexpected test client operation");
        require(command->respond(0,response.data(),response.size()),"Client control response");
        // Peer destruction does not close its command mapping; parent's reply
        // remains consumable even after this clean process exit.
        if(request.opcode==4)return 0;
    }
}
struct Client {
    std::unique_ptr<Mailbox> channel=Mailbox::create();Process process;
    explicit Client(const std::filesystem::path& self){process.launch(self,Process::executable_sha256(self),{L"--audio-client",channel->name()});}
    ~Client(){channel->close();try{process.terminate_and_wait(2000);}catch(...){}}
    ds::Start prepare(){return ds::decode_start(exchange(*channel,process,1).bytes);}
    void pump(){require(exchange(*channel,process,2).bytes==std::vector<std::uint8_t>{24},"Independent audio client completed blocks");}
    void retire_audio(){exchange(*channel,process,3);}
    void exit(){exchange(*channel,process,4);require(process.wait_for_exit(2000) && process.observe().exit_code==0,"Client exits cleanly");}
};
struct Audit {
    std::filesystem::path path=std::filesystem::temp_directory_path()/(L"SL3Broker-"+std::to_wstring(GetCurrentProcessId())+L"-"+std::to_wstring(GetTickCount64())+L".txt");
    Audit(){require(!std::filesystem::exists(path),"Fresh broker audit");}
    ~Audit(){std::error_code ec;std::filesystem::remove(path,ec);}
    std::vector<std::string> lines(){std::ifstream in(path);std::vector<std::string> out;for(std::string line;std::getline(in,line);)out.push_back(line);return out;}
};
static BrokerSpec spec(const std::filesystem::path& worker,const std::wstring& mode=L"normal"){
    BrokerSpec s;s.executable=worker;s.sha256=Process::executable_sha256(worker);s.kind=session::Kind::simulated;s.fixture_mode=mode;return s;
}
static void idle(const BrokerReport& s){
    require(!s.failed && s.phase==BrokerPhase::idle && !s.client_attached && s.device.phase==ds::Phase::ready && s.device.io_retired &&
        !s.device.device_released && s.process.started && s.process.job_assigned && !s.process.process_exited,"Broker retains idle worker/device independently of clients");
}
static void closed(const BrokerReport& s){
    require(!s.failed && s.phase==BrokerPhase::closed && s.device.phase==ds::Phase::closed && s.device.io_retired && s.device.device_released &&
        s.process.process_exited && s.process.job_empty && !s.termination_requested,"Final broker shutdown confirms device and worker/job retirement");
}
static void lifecycle(const std::filesystem::path& worker,const std::filesystem::path& self){
    Audit audit;RetainedBroker owner(spec(worker,L"audit:"+audit.path.native()));
    require(!owner.report().process.started,"Construction never launches worker");
    Client first(self),second(self);
    rejects([&]{owner.attach(first.process.process_handle());});
    require(owner.open() && !owner.open(),"Only explicit first owner open acquires");idle(owner.report());
    rejects([&]{owner.attach(GetCurrentProcess());});
    const auto one=owner.attach(first.process.process_handle());require(one!=0,"First client admitted");
    rejects([&]{owner.attach(second.process.process_handle());});
    const auto a=first.prepare();require(owner.clock(one)==48000,"Fresh clock on existing held worker");
    auto malformed=a;malformed.audio_channel=L"not-a-mailbox";
    rejects([&]{owner.start(one,malformed);});require(owner.report().phase==BrokerPhase::leased,"Locally malformed start leaves healthy lease intact");
    owner.start(one,a);rejects([&]{owner.clock(one);});rejects([&]{owner.start(one,a);});first.pump();
    require(owner.stop(one).stats.output_completions>0,"Worker completed silent outputs");first.retire_audio();
    require(owner.detach(one),"First client detach retains redirect");idle(owner.report());first.exit();
    rejects([&]{owner.clock(one);});require(!owner.detach(one),"Stale detach cannot mutate owner");
    const auto two=owner.attach(second.process.process_handle());require(two && two!=one,"New client has distinct lease");
    require(!owner.detach(one) && owner.report().client_pid==GetProcessId(second.process.process_handle()),"Old detach cannot release a newer client");
    const auto b=second.prepare();require(a.audio_channel!=b.audio_channel,"Distinct client processes own fresh data channels");
    rejects([&]{owner.start(one,b);});owner.start(two,b);second.pump();
    // Running detach drains native I/O; the client still separately retires its
    // mapping/callback domain after the reply, never inferred by the broker.
    require(owner.detach(two),"Running detach drains while keeping redirect");second.retire_audio();second.exit();idle(owner.report());
    closed(owner.close());closed(owner.close());require(!owner.open(),"Final close permanently prevents reopening");
    const auto lines=audit.lines();
    require(std::count(lines.begin(),lines.end(),"acquire")==1 && std::count(lines.begin(),lines.end(),"release")==1 &&
        std::count(lines.begin(),lines.end(),"begin")==2 && std::count(lines.begin(),lines.end(),"end")==2 &&
        std::count(lines.begin(),lines.end(),"rate")==6,"One worker acquisition, six fresh getters, two separate client streams, one final release");
}
static void death(const std::filesystem::path& worker,const std::filesystem::path& self){
    RetainedBroker owner(spec(worker));require(owner.open(),"Open owner for client-death tests");
    Client dead(self),next(self);const auto old=owner.attach(dead.process.process_handle());dead.exit();
    owner.poll_client();idle(owner.report());rejects([&]{owner.clock(old);});rejects([&]{owner.attach(dead.process.process_handle());});
    const auto lease=owner.attach(next.process.process_handle());const auto data=next.prepare();owner.start(lease,data);
    next.process.terminate_and_wait(2000);owner.poll_client();const auto ended=owner.report();
    require(ended.failed && !ended.client_attached && (ended.phase==BrokerPhase::closed || ended.phase==BrokerPhase::sealed) && !owner.open(),"Running client death ends owner permanently without reacquisition");
    rejects([&]{owner.attach(dead.process.process_handle());});
}
static void failures(const std::filesystem::path& worker,const std::filesystem::path& self){
    {
        RetainedBroker unopened(spec(worker));const auto s=unopened.close();
        require(s.phase==BrokerPhase::closed && !s.failed && !s.process.started && !unopened.open(),"Closing dormant owner never launches or invents a failure");
    }
    {
        RetainedBroker lost(spec(worker));require(lost.open(),"Open before synthetic worker death");Client attached(self);
        const auto claim=lost.attach(attached.process.process_handle());
        require(TerminateProcess(lost.worker_process_handle(),73) && WaitForSingleObject(lost.worker_process_handle(),2000)==WAIT_OBJECT_0,"Terminate exact owned fixture process without PID lookup");
        require(!lost.detach(claim) && lost.report().failed && !lost.open(),"Idle detach cannot report success after worker death");
        const auto ended=lost.close();require(ended.failed && ended.process.process_exited && ended.process.job_empty && !ended.device.device_released,"Process death does not fabricate typed device release");
    }
    for(const auto mode:{L"fail-acquire",L"invalid-clock",L"hang-acquire"}){
        RetainedBroker owner(spec(worker,mode));require(!owner.open() && !owner.open(),"Failed acquisition never retries");
        const auto s=owner.report();require(s.failed && s.process.process_exited && s.process.job_empty,"Failed worker contained");
    }
    RetainedBroker mismatch(spec(worker));require(mismatch.open(),"Open for rejected stream");Client client(self);
    const auto lease=mismatch.attach(client.process.process_handle());auto data=client.prepare();data.config.rate_hz=44100;
    rejects([&]{mismatch.start(lease,data);});require(mismatch.report().phase==BrokerPhase::sealed,"Failed stream seals broker");
    rejects([&]{mismatch.clock(lease);});require(!mismatch.detach(lease),"No successful detach claim after failed stream");mismatch.close();
    {
        Audit rate_file;
        {std::ofstream out(rate_file.path);out<<48000;require(bool(out),"Initial synthetic clock");}
        RetainedBroker changed(spec(worker,L"clock:"+rate_file.path.native()));require(changed.open(),"Acquire before admission clock failure");
        {std::ofstream out(rate_file.path);out<<96000;require(bool(out),"Invalid synthetic clock");}
        rejects([&]{changed.attach(client.process.process_handle());});
        const auto s=changed.report();require(s.failed && !s.client_attached && s.phase==BrokerPhase::sealed,"Failed fresh clock cannot fall back to acquisition clock or admit client");
        require(!changed.open(),"Failed admission never reacquires");changed.close();
    }
    {
        RetainedBroker failed_start(spec(worker,L"fail-start"));require(failed_start.open(),"Acquire before synthetic activation fault");
        Client startup_client(self);const auto claim=failed_start.attach(startup_client.process.process_handle());const auto stream=startup_client.prepare();
        rejects([&]{failed_start.start(claim,stream);});require(failed_start.report().failed && !failed_start.open(),"Activation fault cannot restart owner");
        failed_start.close();
    }
    auto wrong=spec(worker);wrong.kind=session::Kind::native;wrong.helper=std::filesystem::absolute(L"absent-broker-helper.dll");
    RetainedBroker typed(wrong);require(!typed.open(),"Simulated handshake never admitted as native");
}
int wmain(int argc,wchar_t** argv){
    try{
        if(argc==3 && std::wstring(argv[1])==L"--audio-client")return audio_client(argv[2]);
        require(argc==2,"Fixture executable required");const auto self=std::filesystem::absolute(argv[0]);
        lifecycle(argv[1],self);death(argv[1],self);failures(argv[1],self);
        std::cout<<"Retained broker: separate clients, direct audio, exclusive leases, death and failure tests passed (simulation only)\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
