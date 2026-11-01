#include "core/device_session_protocol.hpp"
#include "windows/mailbox.hpp"
#include "windows/worker_process.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>

using namespace sl3;
using namespace sl3::worker;
namespace protocol=device_session;
static void require(bool good,const char* text){if(!good)throw std::runtime_error(text);}
template<class F>static void rejects(F f){bool rejected=false;try{f();}catch(const std::exception&){rejected=true;}require(rejected,"Malformed retained-device payload accepted");}
static void word(std::vector<std::uint8_t>& b,unsigned n,std::uint32_t v){for(unsigned i=0;i<4;++i)b[n*4+i]=std::uint8_t(v>>(8*i));}
static void codecs(){
    for(auto kind:{session::Kind::native,session::Kind::simulated}){
        const auto b=protocol::encode_hello(kind);require(protocol::decode_hello(b)==kind,"Explicit retained worker kind");
        for(unsigned n=0;n<10;++n){auto bad=b;word(bad,n,0xffffffff);rejects([&]{protocol::decode_hello(bad);});}
        for(unsigned old:{1u,2u}){auto legacy=b;word(legacy,1,old);rejects([&]{protocol::decode_hello(legacy);});}
    }
    rejects([]{protocol::decode_hello(session::encode_hello(session::Kind::native));});
    const std::wstring name=L"Local\\SL3Mailbox-0123456789abcdef0123456789abcdef";
    for(unsigned rate:{44100u,48000u})for(unsigned intervals:{8u,64u}){
        const auto b=protocol::encode_start({{rate,intervals,1000,200},name});const auto s=protocol::decode_start(b);
        require(s.audio_channel==name && s.config.rate_hz==rate && s.config.intervals==intervals,"Fresh channel/config round trip");
        for(unsigned n=0;n<9;++n){auto bad=b;word(bad,n,0xffffffff);rejects([&]{protocol::decode_start(bad);});}
        auto bad=b;bad.back()='Z';rejects([&]{protocol::decode_start(bad);});
        bad=b;bad.push_back(0);rejects([&]{protocol::decode_start(bad);});
    }
    rejects([&]{protocol::encode_start({{},L"Global\\SL3Mailbox-0123456789abcdef0123456789abcdef"});});
    protocol::Snapshot s;s.phase=protocol::Phase::ready;s.rate_hz=48000;s.device_released=false;
    s.stats.input_submissions=std::uint64_t(1)<<55;s.diagnostic.assign(512,'x');
    auto b=protocol::encode_snapshot(s);auto decoded=protocol::decode_snapshot(b);
    require(decoded.stats.input_submissions==s.stats.input_submissions && decoded.diagnostic==s.diagnostic && !decoded.device_released && decoded.io_retired,"Ready holds redirect after I/O retirement");
    for(unsigned n:{0u,1u,2u,3u,4u,5u,6u,7u,8u,9u,10u,12u,13u,26u,27u,28u,29u,30u,31u}){
        auto bad=b;word(bad,n,0xffffffff);rejects([&]{protocol::decode_snapshot(bad);});
    }
    s.device_released=true;rejects([&]{protocol::encode_snapshot(s);});
    s.phase=protocol::Phase::closed;s.io_retired=false;rejects([&]{protocol::encode_snapshot(s);});
    protocol::ControlsReply controls;controls.device.phase=protocol::Phase::ready;controls.device.rate_hz=48000;
    controls.device.device_released=false;controls.sample.received_frames=4;controls.sample.audio.raw.fill(0xe1);
    const auto encoded=protocol::encode_controls(controls);const auto inspected=protocol::decode_controls(encoded);
    require(inspected.sample.received_frames==4 && inspected.sample.audio.raw==controls.sample.audio.raw,"Fresh owner state and complete raw control table round trip");
    for(unsigned received:{0u,5u}){auto bad=controls;bad.sample.received_frames=received;rejects([&]{protocol::encode_controls(bad);});}
    for(std::size_t length=0;length<encoded.size();++length){const auto bad=std::vector<std::uint8_t>(encoded.begin(),encoded.begin()+length);rejects([&]{protocol::decode_controls(bad);});}
    {auto bad=encoded;bad.push_back(0);rejects([&]{protocol::decode_controls(bad);});}
    {auto bad=encoded;word(bad,32,5);rejects([&]{protocol::decode_controls(bad);});}
    {auto bad=controls;bad.device.stream_fault=StreamFault::release;rejects([&]{protocol::encode_controls(bad);});}
    controls.device.phase=protocol::Phase::closed;controls.device.device_released=true;rejects([&]{protocol::encode_controls(controls);});
}
struct Client {
    std::unique_ptr<Mailbox> control=Mailbox::create();Process process;std::filesystem::path audit;
    Client(const std::filesystem::path& executable,const std::wstring& mode,bool native=false){
        audit=std::filesystem::temp_directory_path()/(control->name().substr(17)+L"-device-audit.txt");
        require(!std::filesystem::exists(audit),"Fresh fixture audit required");
        if(native){
            const auto missing=std::filesystem::temp_directory_path()/(control->name().substr(17)+L"-absent-helper.dll");
            require(!std::filesystem::exists(missing),"Native negative helper must not exist");
            std::vector<std::wstring> args{L"--device-worker",L"--channel",control->name(),L"--helper",missing.native()};
            if(!mode.empty()){args.insert(args.end(),{L"--startup-log",audit.native(),L"--control-test-target",mode});}
            process.launch(executable,Process::executable_sha256(executable),args);
        }else process.launch(executable,Process::executable_sha256(executable),{control->name(),mode,audit.native()});
    }
    ~Client(){control->close();try{process.terminate_and_wait();}catch(...){}std::error_code ec;std::filesystem::remove(audit,ec);}
    Message call(protocol::Command cmd,const std::vector<std::uint8_t>& bytes={}){
        require(control->send(unsigned(cmd),bytes.data(),bytes.size()),"Publish retained device command");Message r;
        const auto entered=GetTickCount64();
        const auto result=control->await_reply(process.process_handle(),2000,r);
        if(result!=MessageResult::ok){
            const auto state=process.observe();
            std::cerr<<"Retained reply failure: command="<<unsigned(cmd)<<" result="<<unsigned(result)
                     <<" elapsed_ms="<<(GetTickCount64()-entered)<<" process_exited="<<state.process_exited
                     <<" exit_code_known="<<state.exit_code_known<<" exit_code="<<state.exit_code<<" audit=";
            for(const auto& mark:marks())std::cerr<<mark<<',';
            std::cerr<<'\n';
        }
        require(result==MessageResult::ok,"Receive retained device reply");return r;
    }
    void hello(session::Kind kind=session::Kind::simulated){const auto r=call(protocol::Command::hello);require(!r.status && protocol::decode_hello(r.bytes)==kind,"Retained device handshake");}
    protocol::Snapshot state(protocol::Command cmd){const auto r=call(cmd);require(!r.status,"Successful retained device operation");return protocol::decode_snapshot(r.bytes);}
    std::vector<std::string> marks(){std::ifstream in(audit);std::vector<std::string> lines;for(std::string line;std::getline(in,line);)lines.push_back(line);return lines;}
    void quit(unsigned expected=0){state(protocol::Command::quit);require(process.wait_for_exit(2000),"Retained worker exited");const auto s=process.observe();require(s.exit_code_known && s.exit_code==expected,"Retained worker exit code");}
};
static std::unique_ptr<Mailbox> run_stream(Client& c,unsigned intervals){
    auto data=Mailbox::create();require(data->audio_pristine(),"Fresh host queues");
    const auto r=c.call(protocol::Command::start,protocol::encode_start({{48000,intervals,1000,200},data->name()}));
    const auto started=protocol::decode_snapshot(r.bytes);
    require(!r.status && started.phase==protocol::Phase::running && !started.device_released && !started.io_retired,"Start retains device and audio leases");
    require(c.call(protocol::Command::clock).status==unsigned(session::Status::bad_state),"No interrupt clock query while audio owns device");
    std::uint64_t next=0;unsigned blocks=0;const auto deadline=GetTickCount64()+1000;
    while(blocks<24 && GetTickCount64()<deadline){
        AudioBlock input;const auto got=data->try_pop_audio(AudioDirection::input,input);
        if(got==AudioResult::empty){SwitchToThread();continue;}
        require(got==AudioResult::ok && input.first_frame==next && input.packet_count==intervals,"Each fresh stream starts at frame zero without old packets");
        unsigned frames=0;for(unsigned n=0;n<input.packet_count;++n)frames+=input.frames_per_packet[n];next+=frames;
        input.pcm.fill(0);
        for(;;){const auto sent=data->try_push_audio(AudioDirection::output,input);if(sent==AudioResult::full){require(GetTickCount64()<deadline,"Output queue deadline");SwitchToThread();continue;}require(sent==AudioResult::ok,"Publish matching silent output");break;}
        ++blocks;
    }
    require(blocks==24,"Real-process simulated stream made progress");
    const auto stopped=c.state(protocol::Command::stop);
    require(stopped.phase==protocol::Phase::ready && stopped.io_retired && !stopped.device_released && !stopped.stats.pending_mask && !stopped.stats.retained_mask && stopped.stats.output_completions>0,"Stop retires I/O but preserves redirect");
    return data;
}
static void lifecycle(const std::filesystem::path& fixture){
    Client c(fixture,L"normal");
    require(c.call(protocol::Command::acquire).status==unsigned(session::Status::bad_state),"No acquisition before handshake");c.hello();
    require(c.state(protocol::Command::state).phase==protocol::Phase::empty,"Hello does not acquire hardware");
    const auto acquired=c.state(protocol::Command::acquire);
    require(acquired.phase==protocol::Phase::ready && acquired.rate_hz==48000 && acquired.io_retired && !acquired.device_released,"Fresh clock on retained idle device");
    Sleep(300);require(c.state(protocol::Command::state).phase==protocol::Phase::ready,"Held device survives setup pause past pre-acquisition idle timeout");
    require(c.call(protocol::Command::acquire).status==unsigned(session::Status::bad_state),"Double acquisition cannot reopen redirect");
    const auto old=run_stream(c,8);const auto next=run_stream(c,64);
    require(old->name()!=next->name(),"Each start uses a different mapping");
    c.quit();require(c.marks()==std::vector<std::string>({"acquire","rate","rate","begin","end","rate","begin","end","release"}),"One physical lease, fresh clock and target per stream, final release once");
}
static void admission_failures(const std::filesystem::path& fixture){
    for(const auto mode:{L"normal",L"invalid-clock",L"fail-start",L"fail-acquire"}){
        Client c(fixture,mode);c.hello();const auto acquired=c.call(protocol::Command::acquire);
        if(std::wstring(mode)==L"invalid-clock" || std::wstring(mode)==L"fail-acquire"){
            const auto s=protocol::decode_snapshot(acquired.bytes);require(acquired.status && s.phase==protocol::Phase::failed && s.io_retired && s.device_released,"Acquire failure releases partial device");c.quit(1);continue;
        }
        require(!acquired.status,"Acquire before start fault");auto data=Mailbox::create();
        const auto rate=std::wstring(mode)==L"normal"?44100u:48000u;
        const auto r=c.call(protocol::Command::start,protocol::encode_start({{rate,8,1000,200},data->name()}));const auto s=protocol::decode_snapshot(r.bytes);
        require(r.status && s.phase==protocol::Phase::failed && s.io_retired && s.device_released && !s.stats.input_submissions && !s.stats.output_submissions,"Clock mismatch/activation fault sends no audio and releases device");
        require(c.call(protocol::Command::start,protocol::encode_start({{48000,8,1000,200},data->name()})).status==unsigned(session::Status::bad_state),"No silent retry after device failure");c.quit(1);
    }
    Client c(fixture,L"normal");c.hello();c.state(protocol::Command::acquire);auto old=run_stream(c,8);
    const auto r=c.call(protocol::Command::start,protocol::encode_start({{48000,8,1000,200},old->name()}));
    require(r.status && protocol::decode_snapshot(r.bytes).device_released,"Reused claimed stream mapping rejected and device released");c.quit(1);
}
static void control_loss(const std::filesystem::path& fixture){
    Client c(fixture,L"normal");c.hello();c.state(protocol::Command::acquire);c.control->close();
    require(c.process.wait_for_exit(2000),"Idle held redirect released after host channel close");
    require(c.marks()==std::vector<std::string>({"acquire","rate","release"}),"Host loss releases idle device once");
}
static void controls_inspection(const std::filesystem::path& fixture){
    Client c(fixture,L"normal");
    require(c.call(protocol::Command::controls).status==unsigned(session::Status::bad_state),"Controls cannot precede handshake");
    c.hello();require(c.call(protocol::Command::controls).status==unsigned(session::Status::bad_state),"Controls never acquire a device implicitly");
    c.state(protocol::Command::acquire);
    require(c.call(protocol::Command::controls,{1}).status==unsigned(session::Status::bad_request),"Control query rejects nonempty request body before device access");
    auto r=c.call(protocol::Command::controls);require(!r.status,"Idle control inspection succeeds");
    auto inspected=protocol::decode_controls(r.bytes);
    require(inspected.device.phase==protocol::Phase::ready && inspected.device.io_retired && !inspected.device.device_released
            && inspected.sample.received_frames==4 && inspected.sample.audio.raw[21]==38,"Control inspection preserves held device and full fresh payload");
    auto data=Mailbox::create();require(!c.call(protocol::Command::start,protocol::encode_start({{48000,8,1000,200},data->name()})).status,"Start after controls");
    require(c.call(protocol::Command::controls).status==unsigned(session::Status::bad_state),"No interrupt controls while audio owns the device");
    c.state(protocol::Command::stop);
    require(!c.call(protocol::Command::controls).status,"Controls may inspect the same device after audio retirement");
    c.quit();require(c.marks()==std::vector<std::string>({"acquire","rate","controls","rate","begin","end","controls","release"}),
                     "Inspections neither reopen nor activate audio; rejected states make no query");
    for(const auto mode:{L"fail-controls",L"bad-controls"}){
        Client failed(fixture,mode);failed.hello();failed.state(protocol::Command::acquire);
        const auto result=failed.call(protocol::Command::controls);const auto state=protocol::decode_snapshot(result.bytes);
        require(result.status==unsigned(session::Status::operation_failed) && state.phase==protocol::Phase::failed
                && state.failure==session::Failure::control && state.io_retired && state.device_released,"Failed/invalid control observation releases the idle device");
        require(failed.call(protocol::Command::controls).status==unsigned(session::Status::bad_state),"Failed controls do not retry");
        failed.quit(1);require(failed.marks()==std::vector<std::string>({"acquire","rate","controls","release"}),"Control failure final release occurs once");
    }
    Client stalled(fixture,L"hang-controls");stalled.hello();stalled.state(protocol::Command::acquire);
    require(stalled.control->send(unsigned(protocol::Command::controls),nullptr,0),"Publish stalled control inspection");
    require(stalled.process.wait_for_exit(2000),"Independent watchdog contains a stalled query");
    require(stalled.process.observe().exit_code==70,"Stalled inspection cannot advertise ordinary cleanup");
}
static std::vector<std::uint8_t> selection_request(){
    const auto b=control::selection_wire::encode_request({control::AudioControlSetting::through,0,1});return {b.begin(),b.end()};
}
static void selection(const std::filesystem::path& fixture){
    const auto body=selection_request();const control::selection_wire::Target target{control::AudioControlSetting::through,0,1};
    {
        Client dynamic(fixture,L"selection-after-controls");dynamic.hello();
        require(!dynamic.state(protocol::Command::acquire).selection_supported,"Capability absent before required baseline");
        require(dynamic.call(protocol::Command::select_control,body).status==unsigned(session::Status::bad_request),"Pre-baseline selection reaches no device operation");
        const auto controls=dynamic.call(protocol::Command::controls);
        require(!controls.status && protocol::decode_controls(controls.bytes).device.selection_supported,"Getter reply refreshes acquired-device capability");
        const auto r=dynamic.call(protocol::Command::select_control,body);require(!r.status && protocol::decode_selection(r.bytes,target).outcome.selection.verified,"Baseline-enabled simulated transaction");
        require(dynamic.call(protocol::Command::select_control,body).status==unsigned(session::Status::bad_request),"Current device capability rechecked before repeat operation");
        dynamic.quit();
    }
    Client c(fixture,L"normal");
    require(c.call(protocol::Command::select_control,body).status==unsigned(session::Status::bad_state),"Selection requires handshake");
    c.hello();require(c.call(protocol::Command::select_control,body).status==unsigned(session::Status::bad_state),"Selection never acquires implicitly");
    require(c.state(protocol::Command::acquire).selection_supported,"Device explicitly offers selection");
    require(c.call(protocol::Command::select_control,{1}).status==unsigned(session::Status::bad_request),"Malformed target makes no device call");
    const auto reply=c.call(protocol::Command::select_control,body);require(!reply.status,"Idle simulated selection");
    const auto selected=protocol::decode_selection(reply.bytes,target);
    require(selected.device.io_retired && !selected.device.device_released && selected.outcome.selection.verified &&
        selected.outcome.selection.device_may_have_changed && selected.outcome.native_error==1168,"Operation result stays separate from held ownership");
    auto bad=reply.bytes;word(bad,7,1);rejects([&]{protocol::decode_selection(bad,target);});
    for(std::size_t size=0;size<reply.bytes.size();++size){const auto truncated=std::vector<std::uint8_t>(reply.bytes.begin(),reply.bytes.begin()+size);
        rejects([&]{protocol::decode_selection(truncated,target);});}
    bad=reply.bytes;bad.push_back(0);rejects([&]{protocol::decode_selection(bad,target);});
    bad=reply.bytes;word(bad,2,unsigned(protocol::Phase::failed));rejects([&]{protocol::decode_selection(bad,target);});
    bad=reply.bytes;word(bad,11,0);rejects([&]{protocol::decode_selection(bad,target);});
    rejects([&]{protocol::decode_selection(reply.bytes,{control::AudioControlSetting::through,1,1});});
    require(protocol::decode_selection(c.call(protocol::Command::select_control,body).bytes,target).outcome.selection.setter_attempts==0,
        "Second explicit same-target command can be a getter-only no-op");
    const auto state=protocol::decode_controls(c.call(protocol::Command::controls).bytes);
    require(state.sample.audio.raw[8]==1,"Fixture control observation reflects selected byte");
    auto audio=Mailbox::create();require(!c.call(protocol::Command::start,protocol::encode_start({{48000,8,1000,200},audio->name()})).status,"Audio starts after selection");
    require(c.call(protocol::Command::select_control,body).status==unsigned(session::Status::bad_state),"No selection during active audio");
    c.state(protocol::Command::stop);c.quit();
    require(c.marks()==std::vector<std::string>({"acquire","rate","select","select","controls","rate","begin","end","release"}),
        "Rejected commands do not invoke setting engine or create extra ownership");
    Client unsupported(fixture,L"selection-unsupported");unsupported.hello();
    require(!unsupported.state(protocol::Command::acquire).selection_supported &&
        unsupported.call(protocol::Command::select_control,body).status==unsigned(session::Status::bad_request),"Unsupported device rejects before selection");
    unsupported.quit();require(unsupported.marks()==std::vector<std::string>({"acquire","rate","release"}),"Unsupported selection sends no control transfer");
    for(const auto mode:{L"fail-selection",L"mismatch-selection"}){
        Client failed(fixture,mode);failed.hello();failed.state(protocol::Command::acquire);
        const auto r=failed.call(protocol::Command::select_control,body);const auto value=protocol::decode_selection(r.bytes,target);
        require(r.status==unsigned(session::Status::operation_failed) && value.device.phase==protocol::Phase::failed && value.device.io_retired &&
            !value.device.device_released && value.outcome.selection.initial && !value.outcome.selection.verified && value.outcome.selection.device_may_have_changed,
            "A failed setting keeps partial operation evidence before final release");
        require(failed.call(protocol::Command::select_control,body).status==unsigned(session::Status::bad_state),"Failed setting cannot retry");
        failed.quit(1);
    }
}
static void admission_and_partial_start(const std::filesystem::path& fixture){
    {
        Client c(fixture,L"normal");c.hello();c.state(protocol::Command::acquire);
        const auto bad=c.call(protocol::Command::start,protocol::encode_start({{48000,8,1000,200},c.control->name()}));
        require(bad.status==unsigned(session::Status::bad_request) && protocol::decode_snapshot(bad.bytes).phase==protocol::Phase::ready,
                "Control mapping cannot be used for audio or consume held device");
        auto data=Mailbox::create();AudioBlock output;output.reported_rate_hz=48000;output.packet_count=8;
        for(unsigned p=0;p<8;++p)output.frames_per_packet[p]=6;
        require(data->try_push_audio(AudioDirection::output,output)==AudioResult::ok && !data->audio_pristine(),"Preloaded output is not fresh");
        const auto r=c.call(protocol::Command::start,protocol::encode_start({{48000,8,1000,200},data->name()}));
        const auto s=protocol::decode_snapshot(r.bytes);
        require(r.status && s.phase==protocol::Phase::failed && s.device_released && !s.stats.input_submissions && !s.stats.output_submissions,
                "Preloaded queue fails before clock/alternate/audio work");c.quit(1);
        require(c.marks()==std::vector<std::string>({"acquire","rate","release"}),"Queue admission failure releases idle lease without begin");
    }
    {
        Client c(fixture,L"partial-start");c.hello();c.state(protocol::Command::acquire);auto data=Mailbox::create();
        const auto r=c.call(protocol::Command::start,protocol::encode_start({{48000,8,1000,200},data->name()}));
        const auto s=protocol::decode_snapshot(r.bytes);
        require(r.status && s.phase==protocol::Phase::failed && s.io_retired && s.device_released && s.stats.input_submissions==1 && !s.stats.pending_mask,
                "Partially accepted startup drains its first request before releasing device");c.quit(1);
        require(c.marks()==std::vector<std::string>({"acquire","rate","rate","begin","end","release"}),"Partial-start target retires before final redirect release");
    }
    {
        Client c(fixture,L"normal");c.hello();c.state(protocol::Command::acquire);auto data=Mailbox::create();
        const auto started=c.call(protocol::Command::start,protocol::encode_start({{48000,8,1000,200},data->name()}));require(!started.status,"Start before explicit live quit");
        const auto stopped=c.state(protocol::Command::quit);
        require(stopped.phase==protocol::Phase::closed && stopped.io_retired && stopped.device_released,"Quit drains live audio then releases device");
        require(c.process.wait_for_exit(2000),"Live quit exits worker");
        require(c.marks()==std::vector<std::string>({"acquire","rate","rate","begin","end","release"}),"Live quit release ordering");
    }
}
static void containment(const std::filesystem::path& fixture){
    for(const auto mode:{L"hang-acquire",L"hang-rate",L"hang-start",L"hang-device-close",L"fail-device-close",L"retained",L"hang-close",L"fail-close"}){
        Client c(fixture,mode);c.hello();
        const bool acquire_hang=std::wstring(mode)==L"hang-acquire" || std::wstring(mode)==L"hang-rate";
        auto cmd=protocol::Command::acquire;std::vector<std::uint8_t> body;
        std::unique_ptr<Mailbox> data;
        if(!acquire_hang){
            c.state(cmd);cmd=protocol::Command::quit;
            if(std::wstring(mode)!=L"hang-device-close" && std::wstring(mode)!=L"fail-device-close"){
                data=Mailbox::create();body=protocol::encode_start({{48000,8,1000,200},data->name()});cmd=protocol::Command::start;
            }
        }
        require(c.control->send(unsigned(cmd),body.data(),body.size()),"Publish containment operation");Message r;
        const auto outcome=c.control->await_reply(c.process.process_handle(),2000,r);
        if(outcome==MessageResult::ok){
            require(cmd==protocol::Command::start,"Only start may reply before drain containment");
            c.control->close(); // Force cancellation/drain without host audio.
        }
        require(c.process.wait_for_exit(2000),"Independent watchdog/retirement containment exits worker");
        const auto s=c.process.observe();require(s.exit_code_known && s.exit_code==70,"Failed native ownership is fail-stop, not ordinary cleanup success");
    }
}
static void native_negative(const std::filesystem::path& native){
  for(const auto mode:{L"",L"through:0:1"}){
    Client c(native,mode,true);c.hello(session::Kind::native);
    require(c.call(protocol::Command::controls).status==unsigned(session::Status::bad_state),"Native controls before acquisition load no helper");
    require(c.call(protocol::Command::select_control,selection_request()).status==unsigned(session::Status::bad_state),"Native selection before acquisition loads no helper");
    const auto r=c.call(protocol::Command::acquire);const auto s=protocol::decode_snapshot(r.bytes);
    require(r.status && s.phase==protocol::Phase::failed && s.device_released && s.io_retired && !s.stats.input_submissions,"Native missing helper fails before device access");c.quit(1);
  }
  for(const auto args:std::vector<std::vector<std::wstring>>{
      {L"--control-test-target",L"through:0:1"},
      {L"--plan",L"--control-test-target",L"through:0:1"},
      {L"--device-worker",L"--channel",L"unused",L"--helper",L"missing",L"--control-test-target",L"through:0:1"},
      {L"--control-test-target",L"through:0:2"},
      {L"--control-test-target",L"sensitivity:0:16"}}){
      Process child;child.launch(native,Process::executable_sha256(native),args);require(child.wait_for_exit(2000),"Rejected native arguments exit");
      require(child.observe().exit_code==2,"Control grant requires isolated mode, valid target and journal before helper access");
  }
}
static void clock_inspection(const std::filesystem::path& fixture){
    Client c(fixture,L"normal");require(c.call(protocol::Command::clock).status==unsigned(session::Status::bad_state),"Clock requires handshake");
    c.hello();require(c.call(protocol::Command::clock).status==unsigned(session::Status::bad_state),"Clock query never acquires implicitly");
    c.state(protocol::Command::acquire);
    require(c.call(protocol::Command::clock,{1}).status==unsigned(session::Status::bad_request),"Clock query rejects extra bytes");
    const auto rate=c.state(protocol::Command::clock);
    require(rate.phase==protocol::Phase::ready && rate.rate_hz==48000 && rate.io_retired && !rate.device_released &&
            c.marks()==std::vector<std::string>({"acquire","rate","rate"}),"Explicit idle getter keeps acquired device and adds one rate read");
    c.quit();require(c.marks()==std::vector<std::string>({"acquire","rate","rate","release"}),"Clock query has no hidden reacquisition or audio");
    Client failed(fixture,L"fail-rate-refresh");failed.hello();failed.state(protocol::Command::acquire);
    const auto response=failed.call(protocol::Command::clock);const auto state=protocol::decode_snapshot(response.bytes);
    require(response.status==unsigned(session::Status::operation_failed) && state.phase==protocol::Phase::failed && state.io_retired && state.device_released,
            "Failed clock getter releases rather than presenting cached success");failed.quit(1);
}
int wmain(int argc,wchar_t** argv){
    try{if(argc!=3)return 2;codecs();clock_inspection(argv[1]);lifecycle(argv[1]);admission_failures(argv[1]);admission_and_partial_start(argv[1]);control_loss(argv[1]);controls_inspection(argv[1]);selection(argv[1]);containment(argv[1]);native_negative(argv[2]);std::cout<<"Retained-device codec, control inspection/selection, lifetime, fresh queues, failure and containment tests passed\n";return 0;}
    catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
