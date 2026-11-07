// No helper/device/ASIO DLL. Audit records distinguish physical-device lifetime
// from independent per-stream backend/alternate lifetime.
#include "windows/device_session.hpp"
#include "windows/diagnostic.hpp"
#include "session_fake_backend.hpp"
#include <filesystem>
#include <fstream>

using namespace sl3;
using namespace sl3::worker;
namespace {
class Audit {
    std::filesystem::path path_;
public:
    explicit Audit(std::filesystem::path path):path_(std::move(path)){}
    void mark(const char* text){if(path_.empty())return;std::ofstream out(path_,std::ios::app);out<<text<<'\n'<<std::flush;if(!out)throw std::runtime_error("Fixture audit write failed");}
};
class Target final:public SessionTarget {
    testing::FakeBackend backend_;std::wstring mode_;Audit& audit_;bool& active_;bool closed_=false;
public:
    Target(std::wstring mode,Audit& audit,bool& active):backend_(mode),mode_(std::move(mode)),audit_(audit),active_(active){
        audit_.mark("begin");active_=true;
    }
    ~Target(){if(!closed_)diagnostic::fail_stop();}
    ContinuousBackend& backend() noexcept override{return backend_;}
    bool close() noexcept override{
        if(closed_)return true;
        if(mode_==L"hang-close")Sleep(INFINITE);
        if(mode_==L"fail-close" || !backend_.retired())return false;
        try{audit_.mark("end");}catch(...){return false;}
        closed_=true;active_=false;return true;
    }
    DWORD native_error() const noexcept override{return 0;}
    bool wait_for_work(Mailbox&,unsigned,DWORD) noexcept override{SwitchToThread();return true;}
};
class Device final:public SessionDevice {
    std::wstring mode_;Audit& audit_;bool active_=false,closed_=false;
    control::AudioControlsSnapshot controls_{};
    bool observed_controls_=false,selected_control_=false;
    unsigned rate_reads_=0;
    unsigned selected_rate_=48000;
public:
    Device(std::wstring mode,Audit& audit):mode_(std::move(mode)),audit_(audit){
        audit_.mark("acquire");for(unsigned i=0;i<controls_.raw.size();++i)controls_.raw[i]=std::uint8_t(i+17);
        if(mode_==L"selection-noop")controls_.raw[8]=1;
    }
    ~Device(){if(!closed_)diagnostic::fail_stop();}
    unsigned read_rate() override{
        if(active_ || closed_)throw std::runtime_error("Fixture clock queried outside idle lease");
        if(mode_==L"hang-rate")Sleep(INFINITE);
        audit_.mark("rate");
        if(++rate_reads_>1 && mode_==L"fail-rate-refresh")throw std::runtime_error("Fixture fresh rate failed after retirement");
        if(mode_.rfind(L"clock:",0)==0){unsigned rate=0;std::ifstream in{std::filesystem::path(mode_.substr(6))};in>>rate;return rate;}
        return mode_==L"invalid-clock"?96000u:selected_rate_;
    }
    device_session::ControlSample read_controls() override{
        if(active_ || closed_)throw std::runtime_error("Fixture controls queried outside idle lease");
        audit_.mark("controls");
        if(mode_==L"hang-controls")Sleep(INFINITE);
        if(mode_==L"fail-controls")throw std::runtime_error("Fixture control transfer failed after retirement");
        device_session::ControlSample sample;
        sample.audio=controls_;
        sample.received_frames=mode_==L"bad-controls"?0u:4u;observed_controls_=true;return sample;
    }
    bool supports_selection() const noexcept override{return mode_!=L"selection-unsupported" &&
        (mode_!=L"selection-after-controls" || (observed_controls_ && !selected_control_));}
    control::selection_wire::Reply select_control(control::selection_wire::Target target) override{
        if(active_ || closed_)throw std::runtime_error("Fixture selection outside idle lease");
        audit_.mark("select");
        selected_control_=true;
        if(mode_==L"hang-selection")Sleep(INFINITE);
        if(mode_==L"throw-selection")throw std::runtime_error(std::string(400,'x')); // Snapshot-only failure can exceed selection's minimum length.
        struct Io final:control::AudioControlsIo {
            Device& device;std::uint64_t tick=100;std::uint8_t command=0;bool failed=false;
            explicit Io(Device& d):device(d){}
            std::uint64_t now_ms() noexcept override{return tick;}
            bool cancelled() noexcept override{return false;}
            bool transfer(bool output,control::Frame& frame,unsigned,std::size_t& bytes) noexcept override{
                ++tick;bytes=control::frame_bytes;
                if(output){
                    command=frame[0];
                    if(command==0x33){
                        if(frame[6]!=1 || frame[5]>=device.controls_.raw.size())return false;
                        device.controls_.raw[frame[5]]=device.mode_==L"mismatch-selection"?std::uint8_t(frame[7]^1):frame[7];
                        if(device.mode_==L"fail-selection" || device.mode_==L"selection-fail-close"){failed=true;return false;}
                    }else if(command!=0x32)return false;
                    return true;
                }
                frame.fill(0);frame[0]=command;frame[1]=0x1c;frame[2]=0xc5;frame[4]=1;
                if(command==0x32)std::copy(device.controls_.raw.begin(),device.controls_.raw.end(),frame.begin()+5);
                else{frame[5]=0xe7;frame[6]=0xa1;}
                return true;
            }
        } io(*this);
        auto result=control::select_audio_control(io,target.setting,target.group,target.value);
        if(mode_==L"slow-selection")Sleep(5500); // Dispatch delay, not simulated native I/O timing.
        if(mode_==L"bad-selection" && result.verified)result.verified->raw[0]^=1;
        return {target,result,io.failed?31u:1168u};
    }
    bool supports_rate_selection() const noexcept override{return mode_.rfind(L"rate-",0)==0;}
    control::rate_wire::Reply select_rate(unsigned target) override{
        if(active_ || closed_)throw std::runtime_error("Fixture rate selection outside idle lease");
        audit_.mark("select-rate");
        if(mode_==L"rate-hang")Sleep(INFINITE);
        if(mode_==L"rate-throw")throw std::runtime_error("Fixture rate operation failed after retired I/O");
        struct Io final:control::RateIo {
            Device& device;std::uint64_t tick=100;unsigned command=0;
            explicit Io(Device& d):device(d){}
            std::uint64_t now_ms() noexcept override{return tick;}
            bool cancelled() noexcept override{return false;}
            bool transfer(bool output,control::Frame& frame,unsigned,std::size_t& bytes) noexcept override{
                ++tick;bytes=control::frame_bytes;
                if(output){
                    command=frame[0];
                    if(command==0x31){
                        device.audit_.mark("rate-setter");
                        if(device.mode_!=L"rate-mismatch")device.selected_rate_=(unsigned(frame[5])<<8)|frame[6];
                        if(device.mode_==L"rate-transfer" || device.mode_==L"rate-transfer-close")return false;
                    }
                }else{
                    frame.fill(0);frame[0]=std::uint8_t(command);frame[1]=0x1c;frame[2]=0xc5;frame[4]=1;
                    const auto value=command==0x31?0xe7a1u:device.selected_rate_;
                    frame[5]=std::uint8_t(value>>8);frame[6]=std::uint8_t(value);
                }
                return true;
            }
        } io(*this);
        auto result=control::diagnose_rate(target,io);
        if(mode_==L"rate-bad")result.verified_rate_hz=96000;
        return {target,result,0};
    }
    std::unique_ptr<SessionTarget> begin(StreamConfig) override{
        if(active_ || closed_)throw std::runtime_error("Fixture double activation");
        if(mode_==L"hang-start")Sleep(INFINITE);
        if(mode_==L"fail-start")throw std::runtime_error("Fixture activation rolled back");
        return std::make_unique<Target>(mode_,audit_,active_);
    }
    bool close() noexcept override{
        if(closed_)return true;
        if(active_)return false;
        if(mode_==L"hang-device-close")Sleep(INFINITE);
        if(mode_==L"fail-device-close" || mode_==L"selection-fail-close" || mode_==L"selection-success-close" ||
           mode_==L"rate-transfer-close" || mode_==L"rate-success-close")return false;
        try{audit_.mark("release");}catch(...){return false;}
        closed_=true;return true;
    }
    DWORD native_error() const noexcept override{return 0;}
};
}
int wmain(int argc,wchar_t** argv){
    try{
        // Native-shaped invocation is only for truthful kind-mismatch tests.
        const bool native_cli=(argc==6 || (argc==8 && std::wstring(argv[6])==L"--startup-log")) &&
            std::wstring(argv[1])==L"--device-worker" && std::wstring(argv[2])==L"--channel" && std::wstring(argv[4])==L"--helper";
        if(argc!=3 && argc!=4 && !native_cli)return 2;
        auto control=Mailbox::open(argv[native_cli?3:1]);std::wstring mode=native_cli?L"normal":argv[2];
        std::filesystem::path audit_path=(!native_cli && argc==4)?argv[3]:L"";
        if(mode.rfind(L"audit:",0)==0){audit_path=mode.substr(6);mode=L"normal";}
        if(mode.rfind(L"rate-audit:",0)==0){audit_path=mode.substr(11);mode=L"rate-normal";}
        if(mode.rfind(L"cancel-acquire:",0)==0){
            const auto signal=OpenEventW(EVENT_MODIFY_STATE,FALSE,mode.c_str()+15);
            if(!signal)throw std::runtime_error("Open fixture cancellation event");
            const auto signalled=SetEvent(signal);CloseHandle(signal);
            if(!signalled)throw std::runtime_error("Signal fixture cancellation event");
            mode=L"fail-acquire";
        }
        Audit audit(audit_path);
        return serve_device_session(*control,session::Kind::simulated,[&]{
            if(mode==L"hang-acquire")Sleep(INFINITE);
            if(mode==L"fail-acquire")throw std::runtime_error("Fixture acquire rollback");
            return std::make_unique<Device>(mode,audit);
        },SessionTimeouts{mode==L"slow-selection"?8000u:250u,500,250,200});
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
