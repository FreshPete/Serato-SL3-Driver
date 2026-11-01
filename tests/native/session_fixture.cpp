// Test-only process: no UsbDk helper, device open, ASIO DLL or native USB backend.
#include "windows/stream_session.hpp"
#include "windows/heartbeat.hpp"
#include "session_fake_backend.hpp"
#include "windows/diagnostic.hpp"
#include <string>
#include <fstream>
#include <filesystem>

using namespace sl3;
using namespace sl3::worker;
namespace {
using sl3::testing::FakeBackend;
class FakeTarget final:public SessionTarget {
    FakeBackend backend_;std::wstring mode_;bool closed_=false;
public:
    explicit FakeTarget(std::wstring mode):backend_(mode),mode_(std::move(mode)){}
    ~FakeTarget(){if(!closed_)diagnostic::fail_stop();}
    ContinuousBackend& backend() noexcept override {return backend_;}
    bool close() noexcept override {
        if(mode_==L"hang-close")Sleep(INFINITE);
        if(mode_==L"fail-close" || !backend_.retired())return false;
        closed_=true;return true;
    }
    DWORD native_error() const noexcept override {return 0;}
    bool wait_for_work(Mailbox&,unsigned,DWORD) noexcept override {SwitchToThread();return true;}
};
unsigned fixture_rate(const std::wstring& mode){
    if(mode.rfind(L"clock:",0)==0){unsigned rate=0;std::ifstream input{std::filesystem::path(mode.substr(6))};input>>rate;return rate;}
    return mode==L"invalid-clock"?96000u:48000u;
}
}
int wmain(int argc,wchar_t** argv){
    try{
        if(argc==3 && std::wstring(argv[1])==L"--heartbeat-healthy"){
            const auto duration=std::stoul(argv[2]);if(duration>30000)return 2;
            Heartbeat heartbeat(1000);const auto start=GetTickCount64();
            while(GetTickCount64()-start<duration){Sleep(20);heartbeat.pulse(1000);}return 0;
        }
        if(argc==2 && std::wstring(argv[1])==L"--heartbeat-hang"){Heartbeat heartbeat(100);Sleep(INFINITE);return 99;}
        // Mimic native CLI only for a genuine kind-mismatch handshake test.
        const bool native_cli=(argc==6 || (argc==8 && std::wstring(argv[6])==L"--startup-log")) && std::wstring(argv[1])==L"--stream-worker" && std::wstring(argv[2])==L"--channel" && std::wstring(argv[4])==L"--helper";
        if(argc!=3 && !native_cli)return 2;
        const std::wstring mode=native_cli?L"normal":argv[2];auto mailbox=Mailbox::open(argv[native_cli?3:1]);
        return serve_stream_session(*mailbox,session::Kind::simulated,[mode](StreamConfig config){
            if(mode==L"hang-start")Sleep(INFINITE);
            if(mode==L"fail-start")throw std::runtime_error("Simulated startup failure before any target");
            if(fixture_rate(mode)!=config.rate_hz)throw std::runtime_error("Simulated factory clock differs; no target or audio submission");
            return std::make_unique<FakeTarget>(mode);
        },[mode]{
            if(mode==L"hang-inspect")Sleep(INFINITE);
            if(mode==L"fail-inspect")throw std::runtime_error("Simulated clock query rollback");
            return fixture_rate(mode);
        },SessionTimeouts{200,200,200,5000});
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
