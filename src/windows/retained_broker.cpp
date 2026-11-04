#include "windows/retained_broker.hpp"
#include <stdexcept>

namespace sl3::worker {
namespace ds=device_session;
namespace {
bool ready(const ds::Snapshot& s) noexcept {
    return s.phase==ds::Phase::ready && s.failure==session::Failure::none &&
        s.stream_fault==StreamFault::none && s.io_retired && !s.device_released &&
        !s.stats.pending_mask && !s.stats.retained_mask;
}
}
RetainedBroker::RetainedBroker(BrokerSpec spec):spec_(std::move(spec)){
    if(spec_.kind!=session::Kind::native && spec_.kind!=session::Kind::simulated)
        throw std::invalid_argument("Explicit broker worker kind required");
    if(spec_.kind==session::Kind::native && (!spec_.helper.is_absolute() || spec_.helper.native().find(L'\0')!=std::wstring::npos))
        throw std::invalid_argument("Absolute broker helper path required");
    if(!spec_.startup_journal.empty() && (spec_.kind!=session::Kind::native || !spec_.startup_journal.is_absolute()))
        throw std::invalid_argument("Startup journal requires an explicit native absolute path");
}
RetainedBroker::~RetainedBroker(){close();}
void RetainedBroker::clear_client() noexcept {
    if(client_)CloseHandle(client_);client_=nullptr;lease_=0;
    state_.client_attached=false;state_.client_alive=false;state_.client_pid=0;
}
void RetainedBroker::seal() noexcept {state_.failed=true;state_.phase=BrokerPhase::sealed;}
Message RetainedBroker::call(ds::Command command,const std::vector<std::uint8_t>& body){
    if(!control_ok_)throw std::runtime_error("Broker worker control sealed");
    try{
        if(!control_->send(unsigned(command),body.data(),body.size()))throw std::runtime_error("Publish broker worker command");
        Message reply;
        if(control_->await_reply(process_.process_handle(),5000,reply)!=MessageResult::ok)
            throw std::runtime_error("Broker worker reply unavailable");
        return reply;
    }catch(...){control_ok_=false;control_->close();seal();throw;}
}
ds::Snapshot RetainedBroker::snapshot(ds::Command command,const std::vector<std::uint8_t>& body){
    state_.snapshot_valid=false;
    const auto reply=call(command,body);
    try{
        state_.device=ds::decode_snapshot(reply.bytes);
        state_.snapshot_valid=true;
        if(reply.status || state_.device.failure!=session::Failure::none || state_.device.stream_fault!=StreamFault::none)
            throw std::runtime_error("Broker worker operation failed");
        return state_.device;
    }catch(...){seal();throw;}
}
bool RetainedBroker::open() noexcept {
    if(state_.phase!=BrokerPhase::dormant)return false;
    // Seal before launch, including partial child-creation failures.
    state_.phase=BrokerPhase::sealed;
    try{
        control_=Mailbox::create();
        auto args=spec_.kind==session::Kind::native?
            std::vector<std::wstring>{L"--device-worker",L"--channel",control_->name(),L"--helper",spec_.helper.native()}:
            std::vector<std::wstring>{control_->name(),spec_.fixture_mode};
        if(!spec_.startup_journal.empty()){args.push_back(L"--startup-log");args.push_back(spec_.startup_journal.native());}
        if(spec_.playback_keepalive){
            if(spec_.kind!=session::Kind::native || spec_.startup_journal.empty())
                throw std::runtime_error("Playback keepalive requires a journalled native worker");
            args.push_back(L"--playback-keepalive");
        }
        process_.launch(spec_.executable,spec_.sha256,args);control_ok_=true;
        const auto hello=call(ds::Command::hello);
        if(hello.status || ds::decode_hello(hello.bytes)!=spec_.kind)throw std::runtime_error("Broker worker kind mismatch");
        state_.acquire_attempted=true;
        if(!ready(snapshot(ds::Command::acquire)))throw std::runtime_error("Broker did not acquire an idle device");
        state_.phase=BrokerPhase::idle;return true;
    }catch(...){seal();close();return false;}
}
std::uint64_t RetainedBroker::attach(HANDLE client){
    poll_client();
    if(state_.phase!=BrokerPhase::idle || client_ || !next_lease_)
        throw std::runtime_error("Broker has no available client lease");
    HANDLE copy=nullptr;
    if(!DuplicateHandle(GetCurrentProcess(),client,GetCurrentProcess(),&copy,
                        SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,0))
        throw std::invalid_argument("Broker client requires a queryable process handle");
    const auto pid=GetProcessId(copy);
    if(!pid || pid==GetCurrentProcessId() || WaitForSingleObject(copy,0)!=WAIT_TIMEOUT){
        CloseHandle(copy);throw std::invalid_argument("Broker client must be a separate live process");
    }
    try{
        if(!ready(snapshot(ds::Command::clock)))throw std::runtime_error("Broker admission clock unavailable");
        // Reobserve the same object, never re-open a recycled PID.
        if(WaitForSingleObject(copy,0)!=WAIT_TIMEOUT){CloseHandle(copy);return 0;}
    }catch(...){CloseHandle(copy);seal();throw;}
    client_=copy;lease_=next_lease_++;
    state_.client_pid=pid;state_.client_attached=state_.client_alive=true;state_.phase=BrokerPhase::leased;
    return lease_;
}
void RetainedBroker::check(std::uint64_t lease){
    poll_client();
    if(!lease || lease!=lease_ || !client_ || (state_.phase!=BrokerPhase::leased && state_.phase!=BrokerPhase::running))
        throw std::runtime_error("Broker client lease is stale or unavailable");
    try{
        state_.process=process_.observe();
        if(!state_.process.started || !state_.process.job_assigned || state_.process.process_exited)
            throw std::runtime_error("Broker worker is no longer live");
    }catch(...){seal();throw;}
}
unsigned RetainedBroker::clock(std::uint64_t lease){
    check(lease);if(state_.phase!=BrokerPhase::leased)throw std::runtime_error("Broker clock requires idle client");
    try{if(!ready(snapshot(ds::Command::clock)))throw std::runtime_error("Broker clock did not retire");return state_.device.rate_hz;}
    catch(...){seal();throw;}
}
ds::Snapshot RetainedBroker::start(std::uint64_t lease,const ds::Start& start){
    check(lease);if(state_.phase!=BrokerPhase::leased)throw std::runtime_error("Broker stream already active");
    // Validate locally before publishing any request. The worker claims the
    // client's fresh audio mapping directly; the broker never copies PCM.
    const auto body=ds::encode_start(start);
    try{
        const auto s=snapshot(ds::Command::start,body);
        if(s.phase!=ds::Phase::running || s.device_released || s.io_retired ||
           s.rate_hz!=start.config.rate_hz || s.intervals!=start.config.intervals)
            throw std::runtime_error("Broker worker did not enter requested stream");
        state_.phase=BrokerPhase::running;return s;
    }catch(...){seal();throw;}
}
ds::Snapshot RetainedBroker::stop(std::uint64_t lease){
    check(lease);
    if(state_.phase==BrokerPhase::leased)return state_.device;
    try{
        if(!ready(snapshot(ds::Command::stop)))throw std::runtime_error("Broker worker retained stream leases");
        state_.phase=BrokerPhase::leased;return state_.device;
    }catch(...){seal();throw;}
}
bool RetainedBroker::detach(std::uint64_t lease) noexcept {
    try{check(lease);stop(lease);clear_client();state_.phase=BrokerPhase::idle;return true;}
    catch(...){return false;}
}
void RetainedBroker::poll_client() noexcept {
    if(!client_)return;
    const auto wait=WaitForSingleObject(client_,0);
    if(wait==WAIT_TIMEOUT)return;
    if(wait==WAIT_OBJECT_0 && state_.phase==BrokerPhase::leased){clear_client();state_.phase=BrokerPhase::idle;return;}
    seal();close();
}
BrokerReport RetainedBroker::report() noexcept {
    poll_client();
    try{
        state_.process=process_.observe();
        if(state_.process.started && state_.process.process_exited && state_.phase!=BrokerPhase::closed)seal();
    }catch(...){seal();}
    return state_;
}
BrokerReport RetainedBroker::close() noexcept {
    if(state_.phase==BrokerPhase::closed)return state_;
    // Explicit final owner shutdown; idle detach is deliberately different.
    const auto deadline=GetTickCount64()+5000;
    bool clean=true;
    try{
        if(control_ok_){
            const auto s=snapshot(ds::Command::quit);
            clean=s.phase==ds::Phase::closed && s.io_retired && s.device_released;
        }else clean=!process_.observe().started;
    }catch(...){clean=false;}
    control_ok_=false;if(control_)control_->close();clear_client();
    try{
        state_.process=process_.observe();
        if(state_.process.started){
            const auto now=GetTickCount64();process_.wait_for_exit(now>=deadline?0:DWORD(deadline-now));
        }
        // Independent job accounting may lag the root's exit signal.
        do{
            state_.process=process_.observe();
            if(!state_.process.started || (state_.process.process_exited && state_.process.job_empty))break;
            if(GetTickCount64()>=deadline)break;Sleep(1);
        }while(true);
        if(state_.process.started && (!state_.process.process_exited || !state_.process.job_empty)){
            const auto stopped=process_.terminate_and_wait(0);state_.termination_requested|=stopped.termination_requested;
            state_.process=stopped.state;clean=false;
        }
        if(state_.process.exit_code_known && state_.process.exit_code!=0)clean=false;
    }catch(...){clean=false;}
    if(clean)state_.phase=BrokerPhase::closed;else seal();return state_;
}
}
