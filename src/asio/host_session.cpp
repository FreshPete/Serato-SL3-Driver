#include "asio/host_session.hpp"
#include <algorithm>
#include <stdexcept>
#include "core/control_test_target.hpp"
#include "core/rate_test_grant.hpp"

namespace sl3::asio {
namespace {
DWORD remaining(ULONGLONG deadline) noexcept {
    const auto now=GetTickCount64();return now>=deadline?0:DWORD(deadline-now);
}
}
HostSession::HostSession(WorkerSpec spec):spec_(std::move(spec)){
    if(spec_.kind!=session::Kind::native && spec_.kind!=session::Kind::simulated)throw std::invalid_argument("Invalid worker kind");
    if(spec_.lifetime!=DeviceLifetime::temporary && spec_.lifetime!=DeviceLifetime::retained)throw std::invalid_argument("Invalid device lifetime");
    if(spec_.kind==session::Kind::native && (!spec_.helper.is_absolute() || spec_.helper.native().find(L'\0')!=std::wstring::npos))
        throw std::invalid_argument("An absolute helper path is required");
    if(spec_.diagnostic_control_target){
        control::selection_wire::encode_request(*spec_.diagnostic_control_target);
        if(spec_.kind!=session::Kind::native || spec_.lifetime!=DeviceLifetime::retained || !spec_.diagnostic_directory.is_absolute())
            throw std::invalid_argument("Control target requires an explicit native retained diagnostic directory");
    }
    if(spec_.diagnostic_rate_target){
        (void)control::RateTestGrant(spec_.diagnostic_rate_target);
        if(spec_.kind!=session::Kind::native || spec_.lifetime!=DeviceLifetime::retained ||
           !spec_.diagnostic_directory.is_absolute() || spec_.diagnostic_control_target)
            throw std::invalid_argument("Rate target requires a separate native retained diagnostic directory");
    }
    if(spec_.diagnostic_playback_keepalive && (spec_.kind!=session::Kind::native ||
       spec_.lifetime!=DeviceLifetime::retained || !spec_.diagnostic_directory.is_absolute() ||
       spec_.diagnostic_control_target || spec_.diagnostic_rate_target))
        throw std::invalid_argument("Playback keepalive requires a separate native retained diagnostic");
}
HostSession::~HostSession(){
    // Graceful final release only when no executing audio owner can block this
    // destructor. Active/blocked callbacks retain the original nonwaiting path.
    if(spec_.lifetime==DeviceLifetime::retained && (!audio_ || audio_->report().retired))close();
    request_shutdown();
}
void HostSession::request_shutdown() noexcept {
    device_closed_=true;usable_=false;control_ok_=false;
    if(audio_)audio_->request_stop();
    if(data_channel_)data_channel_->close();
    if(channel_)channel_->close();
    // No host thread is forcibly terminated. AudioOwner retains all its leases
    // and module if a user callback is still executing after this owner dies.
    if(process_)try{process_->terminate_and_wait(0);}catch(...){}
}
bool HostSession::reentrant() const noexcept {return audio_ && audio_->on_audio_thread();}
void HostSession::failure(HostFailure value) noexcept {if(state_.failure==HostFailure::none)state_.failure=value;}
worker::Message HostSession::call(session::Command command,const std::vector<std::uint8_t>& body,DWORD timeout){
    return exchange(std::uint32_t(command),body,timeout);
}
worker::Message HostSession::device_call(device_session::Command command,const std::vector<std::uint8_t>& body,DWORD timeout){
    return exchange(std::uint32_t(command),body,timeout);
}
worker::Message HostSession::exchange(std::uint32_t command,const std::vector<std::uint8_t>& body,DWORD timeout){
    if(!control_ok_)throw std::runtime_error("Session control is sealed");
    try{
        if(!channel_->send(command,body.data(),body.size()))throw std::runtime_error("Publish host session command");
        worker::Message reply;
        if(channel_->await_reply(process_->process_handle(),timeout,reply)!=worker::MessageResult::ok)throw std::runtime_error("Host session reply unavailable");
        return reply;
    }catch(...){control_ok_=false;channel_->close();throw;}
}
void HostSession::launch(){
    // Called only after the prior audio/process ownership domains retire.
    audio_.reset();data_channel_.reset();process_.reset();channel_.reset();state_=HostReport{};
    channel_=worker::Mailbox::create();process_=std::make_shared<worker::Process>();
    state_.io_retired=false;state_.device_released=false;
    try{
        auto args=spec_.kind==session::Kind::native?
            std::vector<std::wstring>{spec_.lifetime==DeviceLifetime::retained?L"--device-worker":L"--stream-worker",L"--channel",channel_->name(),L"--helper",spec_.helper.native()}:
            std::vector<std::wstring>{channel_->name(),spec_.fixture_mode};
        if(spec_.kind==session::Kind::native && !spec_.diagnostic_directory.empty()){
            if(!spec_.diagnostic_directory.is_absolute())throw std::invalid_argument("Absolute diagnostic directory required");
            args.push_back(L"--startup-log");
            args.push_back((spec_.diagnostic_directory/(L"worker-"+std::to_wstring(++launch_number_)+L".tsv")).native());
        }
        if(spec_.diagnostic_control_target){
            args.push_back(L"--control-test-target");args.push_back(control::format_control_test_target(*spec_.diagnostic_control_target));
        }
        if(spec_.diagnostic_rate_target){
            args.push_back(L"--rate-test-target");args.push_back(std::to_wstring(*spec_.diagnostic_rate_target));
        }
        if(spec_.diagnostic_playback_keepalive)args.push_back(L"--playback-keepalive");
        process_->launch(spec_.executable,spec_.sha256,args);
    }catch(...){failure(HostFailure::launch);throw;}
    // Unknown until an authenticated typed reply states otherwise.
    state_.io_retired=false;state_.device_released=false;control_ok_=true;
    try{
        const bool held=spec_.lifetime==DeviceLifetime::retained;
        const auto hello=held?device_call(device_session::Command::hello,{},10000):call(session::Command::hello,{},10000);
        if(hello.status || (held?device_session::decode_hello(hello.bytes):session::decode_hello(hello.bytes))!=spec_.kind)throw std::runtime_error("Unexpected worker kind/protocol");
    }catch(...){failure(HostFailure::handshake);control_ok_=false;channel_->close();throw;}
}
void HostSession::accept_cleanup(const worker::Message& reply){
    if(reply.status>std::uint32_t(session::Status::operation_failed))throw std::runtime_error("Unknown worker status");
    try{
        const auto snapshot=session::decode_snapshot(reply.bytes);
        state_.worker_snapshot=snapshot;
        state_.io_retired=snapshot.io_retired;state_.device_released=snapshot.device_released;
        if(snapshot.failure!=session::Failure::none)failure(HostFailure::worker);
    }catch(...){control_ok_=false;channel_->close();throw;}
}
unsigned HostSession::query_clock(){
    try{
        const auto reply=call(session::Command::inspect,{},10000);
        if(reply.status){failure(HostFailure::inspection);accept_cleanup(reply);throw std::runtime_error("Worker clock inspection failed");}
        const auto rate=session::decode_clock(reply.bytes);state_.io_retired=true;state_.device_released=true;return rate;
    }catch(...){failure(HostFailure::inspection);control_ok_=false;channel_->close();throw;}
}
bool HostSession::retired() noexcept {
    const auto value=report();return value.audio.retired && (!value.process.started || (value.process.process_exited && value.process.job_empty));
}
bool HostSession::quiescent() noexcept {
    const auto value=report();
    if(!value.audio.retired)return false;
    if(!value.process.started || (value.process.process_exited && value.process.job_empty))return true;
    return spec_.lifetime==DeviceLifetime::retained && usable_ && control_ok_ && value.device_held && value.io_retired && !value.device_released &&
        value.failure==HostFailure::none && value.device_snapshot.phase==device_session::Phase::ready;
}
bool HostSession::inspect() noexcept {
    if(device_closed_)return false;
    if(spec_.lifetime==DeviceLifetime::retained)return acquire_retained();
    if(reentrant() || state_.running || !retired())return false;
    usable_=false;
    try{
        launch();state_.observed_rate_hz=query_clock();const auto result=stop();
        usable_=result.failure==HostFailure::none && result.io_retired && result.device_released &&
            result.process.process_exited && result.process.job_empty && !result.termination_requested;
    }catch(...){stop();}
    return usable_;
}
ASIOError HostSession::create_buffers(ASIOBufferInfo* info,long count,long frames,const ASIOCallbacks* cb) noexcept {
    if(reentrant() || state_.running || !quiescent())return ASE_InvalidMode;
    const auto result=buffers_->create(info,count,frames,cb);if(result==ASE_OK)prepared_=true;return result;
}
ASIOError HostSession::dispose_buffers() noexcept {
    if(reentrant() || state_.running || !quiescent())return ASE_InvalidMode;
    const auto result=buffers_->dispose();if(result==ASE_OK)prepared_=false;return result;
}
bool HostSession::start(unsigned intervals) noexcept {
    if(spec_.diagnostic_control_target || spec_.diagnostic_rate_target)return false;
    if(reentrant() || !usable_)return false;
    if(spec_.lifetime==DeviceLifetime::retained)return start_retained(intervals);
    return start_impl(state_.observed_rate_hz,intervals,true);
}
bool HostSession::start_checked(unsigned rate,unsigned intervals) noexcept {
    if(spec_.diagnostic_control_target || spec_.diagnostic_rate_target)return false;
    if(reentrant() || device_closed_ || spec_.lifetime==DeviceLifetime::retained || usable_ || state_.failure!=HostFailure::none || (rate!=44100 && rate!=48000))return false;
    return start_impl(rate,intervals,false);
}
bool HostSession::start_impl(unsigned expected_rate,unsigned intervals,bool inspect_first) noexcept {
    if(reentrant() || !prepared_ || state_.running || !retired() || intervals<8 || intervals>64 || intervals%8)return false;
    try{
        launch();
        if(inspect_first){
            state_.observed_rate_hz=query_clock();
            if(state_.observed_rate_hz!=expected_rate){usable_=false;failure(HostFailure::rate_changed);throw std::runtime_error("Observed clock changed");}
        }
        audio_=std::make_unique<AudioOwner>(buffers_,channel_,process_);
        if(!audio_->start(expected_rate)){failure(HostFailure::audio_start);throw std::runtime_error("Audio owner startup failed");}
        // A prior temporary clock inspection certifies only its released
        // handle. A newly published start requires new cleanup evidence.
        state_.io_retired=false;state_.device_released=false;
        const auto reply=call(session::Command::start,session::encode_start({expected_rate,intervals,1000,2000}),10000);
        accept_cleanup(reply);const auto snapshot=session::decode_snapshot(reply.bytes);
        if(reply.status || snapshot.phase!=session::Phase::running || snapshot.rate_hz!=expected_rate || snapshot.intervals!=intervals){
            failure(HostFailure::worker_start);throw std::runtime_error("Worker did not enter requested running state");
        }
        if(audio_->report().exit!=AudioExit::running){failure(HostFailure::audio);throw std::runtime_error("Audio owner already failed during startup");}
        // Native factory has independently checked the actual clock before
        // activation. Only its successful running reply publishes metadata.
        state_.observed_rate_hz=snapshot.rate_hz;state_.running=true;return true;
    }catch(...){failure(HostFailure::control);stop();return false;}
}
HostReport HostSession::stop(DWORD timeout) noexcept {
    if(spec_.lifetime==DeviceLifetime::retained)return stop_retained(timeout,false);
    if(reentrant()){HostReport value;value.reentrant=true;value.io_retired=false;value.device_released=false;value.audio=audio_->report();value.audio.reentrant=true;return value;}
    const auto deadline=GetTickCount64()+std::min<DWORD>(timeout,5000);
    if(audio_)audio_->request_stop();state_.running=false;
    if(process_){
        try{
            state_.process=process_->observe();
            if(control_ok_ && !state_.process.process_exited){
                const auto stopped=call(session::Command::stop,{},remaining(deadline));accept_cleanup(stopped);
                if(!state_.io_retired || !state_.device_released)throw std::runtime_error("Worker stop retained leases");
                const auto quit=call(session::Command::quit,{},remaining(deadline));accept_cleanup(quit);control_ok_=false;
            }
        }catch(...){failure(HostFailure::control);control_ok_=false;}
        if(channel_)channel_->close();
        try{
            process_->wait_for_exit(remaining(deadline));
            // Job accounting can lag the signalled root process. Observe it
            // through the same deadline before deciding containment is needed.
            do{
                state_.process=process_->observe();
                if(state_.process.process_exited && state_.process.job_empty)break;
                if(!remaining(deadline))break;Sleep(1);
            }while(true);
            const auto stopped=process_->terminate_and_wait(remaining(deadline));
            state_.termination_requested=state_.termination_requested || stopped.termination_requested;state_.process=stopped.state;
            if(state_.termination_requested)failure(HostFailure::containment);
        }catch(...){failure(HostFailure::containment);}
    }
    if(audio_)state_.audio=audio_->stop(remaining(deadline));
    return report();
}
HostReport HostSession::close(DWORD timeout) noexcept {
    return spec_.lifetime==DeviceLifetime::retained?stop_retained(timeout,true):stop(timeout);
}
void HostSession::accept_device(const worker::Message& reply){
    if(reply.status>std::uint32_t(session::Status::operation_failed))throw std::runtime_error("Unknown device worker status");
    try{
        accept_device_value(device_session::decode_snapshot(reply.bytes));
    }catch(...){control_ok_=false;channel_->close();throw;}
}
void HostSession::accept_device_value(const device_session::Snapshot& value){
    state_.device_snapshot=value;state_.io_retired=value.io_retired;state_.device_released=value.device_released;
    state_.device_held=!value.device_released && value.failure==session::Failure::none &&
        (value.phase==device_session::Phase::ready || value.phase==device_session::Phase::running || value.phase==device_session::Phase::draining);
    if(value.failure!=session::Failure::none)failure(HostFailure::worker);
}
std::optional<device_session::ControlSample> HostSession::inspect_controls() noexcept {
    if(reentrant() || spec_.lifetime!=DeviceLifetime::retained || device_closed_ || !usable_ || state_.running || !quiescent())return std::nullopt;
    try{
        // Publishing this request invalidates the earlier idle retirement proof.
        state_.io_retired=false;
        const auto reply=device_call(device_session::Command::controls,{},5000);
        if(reply.status){failure(HostFailure::inspection);accept_device(reply);throw std::runtime_error("Worker control inspection failed");}
        const auto value=device_session::decode_controls(reply.bytes);
        if(value.device.rate_hz!=state_.observed_rate_hz)throw std::runtime_error("Control reply changed the prior clock identity");
        accept_device_value(value.device);return value.sample;
    }catch(...){failure(HostFailure::inspection);usable_=false;close();return std::nullopt;}
}
std::optional<unsigned> HostSession::inspect_rate() noexcept {
    if(reentrant() || spec_.lifetime!=DeviceLifetime::retained || device_closed_ || !usable_ || prepared_ || state_.running || !quiescent())return std::nullopt;
    try{
        state_.io_retired=false;
        const auto reply=device_call(device_session::Command::clock,{},10000);accept_device(reply);
        if(reply.status || state_.failure!=HostFailure::none || state_.device_snapshot.phase!=device_session::Phase::ready ||
           !state_.io_retired || !state_.device_held || state_.device_released || !state_.device_snapshot.rate_hz)
            throw std::runtime_error("Fresh retained-device clock unavailable");
        state_.observed_rate_hz=state_.device_snapshot.rate_hz;return state_.observed_rate_hz;
    }catch(...){failure(HostFailure::inspection);usable_=false;close();return std::nullopt;}
}
ControlSelectionReport HostSession::select_control(control::selection_wire::Target target) noexcept {
    ControlSelectionReport result;
    if(spec_.diagnostic_rate_target)return result;
    if(spec_.diagnostic_control_target && !control::selection_wire::detail::same(target,*spec_.diagnostic_control_target))return result;
    if(reentrant() || spec_.lifetime!=DeviceLifetime::retained || device_closed_ || !usable_ || state_.running ||
       !quiescent() || !state_.device_snapshot.selection_supported)return result;
    std::vector<std::uint8_t> request;
    try{const auto bytes=control::selection_wire::encode_request(target);request.assign(bytes.begin(),bytes.end());}
    catch(...){return result;} // Invalid target is rejected without I/O or poisoning the idle owner.
    try{
        state_.io_retired=false;
        // An unavailable reply cannot prove whether the worker reached its setter.
        result.command_attempted=true;result.outcome_unknown=true;result.device_may_have_changed=true;
        const auto reply=device_call(device_session::Command::select_control,request,device_session::selection_reply_ms);
        if(reply.status==unsigned(session::Status::bad_request) || reply.status==unsigned(session::Status::bad_state)){
            accept_device(reply);result.outcome_unknown=false;result.device_may_have_changed=false;
            throw std::runtime_error("Worker rejected selection before device operation");
        }
        if(reply.status!=unsigned(session::Status::ok) && reply.status!=unsigned(session::Status::operation_failed))
            throw std::runtime_error("Unexpected selection status");
        // A snapshot-only failure does not carry operation evidence. Keep the
        // conservative possible-write result while still accepting owned cleanup.
        if(reply.status==unsigned(session::Status::operation_failed)){
            std::optional<device_session::Snapshot> owner_only;
            try{owner_only=device_session::decode_snapshot(reply.bytes);}catch(...){}
            if(owner_only){accept_device_value(*owner_only);throw std::runtime_error("Selection outcome unavailable");}
        }
        const auto value=device_session::decode_selection(reply.bytes,target);
        if(value.device.rate_hz!=state_.observed_rate_hz)throw std::runtime_error("Selection reply changed clock identity");
        const bool success=value.outcome.selection.error==control::SelectionIoError::none;
        if((reply.status==unsigned(session::Status::ok))!=success)throw std::runtime_error("Selection status/result differs");
        result.outcome=value.outcome;result.outcome_unknown=false;
        result.device_may_have_changed=value.outcome.selection.device_may_have_changed;
        if(!success)failure(HostFailure::control);
        accept_device_value(value.device);
        if(success)return result;
    }catch(...){failure(HostFailure::control);}
    usable_=false;close();return result; // Preserve an accepted outcome through failed final release.
}
RateSelectionReport HostSession::select_rate(unsigned target) noexcept {
    RateSelectionReport result;
    if(spec_.diagnostic_control_target || (spec_.diagnostic_rate_target && target!=*spec_.diagnostic_rate_target))return result;
    if(reentrant() || spec_.lifetime!=DeviceLifetime::retained || device_closed_ || !usable_ || prepared_ || state_.running ||
       !quiescent())return result;
    std::vector<std::uint8_t> request;
    try{const auto bytes=control::rate_wire::encode_request(target);request.assign(bytes.begin(),bytes.end());}
    catch(...){return result;} // Invalid target cannot poison an otherwise idle lease.
    const auto prior_rate=state_.observed_rate_hz;
    try{
        state_.io_retired=false;state_.observed_rate_hz=0;
        result.command_attempted=true;result.outcome_unknown=true;result.device_may_have_changed=true;
        const auto reply=device_call(device_session::Command::select_rate,request,device_session::rate_reply_ms);
        if(reply.status==unsigned(session::Status::bad_request) || reply.status==unsigned(session::Status::bad_state)){
            const auto owner=device_session::decode_snapshot(reply.bytes);
            // Optional-command refusal is safe to keep only with an unchanged,
            // fully retired idle owner. An arbitrary error status is not proof.
            if(owner.phase!=device_session::Phase::ready || owner.failure!=session::Failure::none ||
               owner.stream_fault!=StreamFault::none || !owner.io_retired || owner.device_released || owner.rate_hz!=prior_rate)
                throw std::runtime_error("Rate refusal did not preserve idle ownership");
            accept_device_value(owner);state_.observed_rate_hz=prior_rate;
            result.outcome_unknown=false;result.device_may_have_changed=false;result.rejected_before_operation=true;
            return result;
        }
        if(reply.status!=unsigned(session::Status::ok) && reply.status!=unsigned(session::Status::operation_failed))
            throw std::runtime_error("Unexpected rate-selection status");
        if(reply.status==unsigned(session::Status::operation_failed)){
            std::optional<device_session::Snapshot> owner_only;
            try{owner_only=device_session::decode_snapshot(reply.bytes);}catch(...){}
            if(owner_only){accept_device_value(*owner_only);throw std::runtime_error("Rate outcome unavailable");}
        }
        const auto value=device_session::decode_rate_selection(reply.bytes,target);
        const bool success=value.outcome.observation.error==control::DiagnosticError::none;
        if((reply.status==unsigned(session::Status::ok))!=success)throw std::runtime_error("Rate status/result differs");
        result.outcome=value.outcome;result.outcome_unknown=false;
        result.device_may_have_changed=value.outcome.observation.device_may_have_changed;
        state_.observed_rate_hz=value.device.rate_hz;
        if(!success)failure(HostFailure::control);
        accept_device_value(value.device);
        if(success)return result;
    }catch(...){failure(HostFailure::control);}
    usable_=false;close();return result; // Cleanup cannot erase accepted operation evidence.
}
bool HostSession::acquire_retained() noexcept {
    if(reentrant() || device_closed_ || state_.running || state_.failure!=HostFailure::none)return false;
    if(usable_)return quiescent();
    if(!retired())return false;
    try{
        launch();const auto reply=device_call(device_session::Command::acquire,{},10000);
        if(reply.status)failure(HostFailure::inspection);
        accept_device(reply);const auto& value=state_.device_snapshot;
        if(reply.status || value.phase!=device_session::Phase::ready || !state_.device_held || !value.io_retired || !value.rate_hz)
            throw std::runtime_error("Retained device acquisition failed");
        state_.observed_rate_hz=value.rate_hz;usable_=true;return true;
    }catch(...){failure(HostFailure::inspection);close();return false;}
}
bool HostSession::start_retained(unsigned intervals) noexcept {
    if(reentrant() || device_closed_ || !usable_ || !prepared_ || state_.running || !quiescent() || intervals<8 || intervals>64 || intervals%8)return false;
    const auto expected=state_.observed_rate_hz;
    try{
        audio_.reset();if(data_channel_)data_channel_->close();data_channel_=worker::Mailbox::create();
        audio_=std::make_unique<AudioOwner>(buffers_,data_channel_,process_);
        if(!audio_->start(expected)){failure(HostFailure::audio_start);throw std::runtime_error("Retained-session audio owner failed");}
        // Publication may start native I/O even if no reply is ever observed.
        // The earlier idle snapshot is no longer retirement evidence.
        state_.io_retired=false;
        const auto reply=device_call(device_session::Command::start,device_session::encode_start({{expected,intervals,1000,2000},data_channel_->name()}),10000);
        // An actual changed clock remains observed metadata but is not a valid
        // running session. Preserve this cause before the generic worker fault.
        const auto value=device_session::decode_snapshot(reply.bytes);
        if(value.rate_hz && value.rate_hz!=expected){state_.observed_rate_hz=value.rate_hz;failure(HostFailure::rate_changed);}
        accept_device(reply);
        if(reply.status || value.phase!=device_session::Phase::running || value.rate_hz!=expected || value.intervals!=intervals || !state_.device_held){
            failure(HostFailure::worker_start);throw std::runtime_error("Retained worker did not enter requested running state");
        }
        if(audio_->report().exit!=AudioExit::running){failure(HostFailure::audio);throw std::runtime_error("Retained audio owner already exited");}
        state_.running=true;return true;
    }catch(...){failure(HostFailure::control);close();return false;}
}
HostReport HostSession::stop_retained(DWORD timeout,bool final) noexcept {
    if(reentrant()){HostReport value;value.reentrant=true;value.io_retired=false;value.device_released=false;value.audio=audio_->report();value.audio.reentrant=true;return value;}
    const auto deadline=GetTickCount64()+std::min<DWORD>(timeout,5000);
    report();if(audio_)audio_->request_stop();state_.running=false;
    if(final){device_closed_=true;usable_=false;}
    bool keep=false;
    if(process_){
        try{
            state_.process=process_->observe();
            if(control_ok_ && !state_.process.process_exited){
                const auto reply=device_call(final?device_session::Command::quit:device_session::Command::stop,{},remaining(deadline));accept_device(reply);
                if(reply.status)throw std::runtime_error("Retained worker rejected stop/release");
                keep=!final && state_.failure==HostFailure::none && state_.device_snapshot.phase==device_session::Phase::ready &&
                    state_.io_retired && state_.device_held && !state_.device_released;
                if(!keep && !final){const auto quit=device_call(device_session::Command::quit,{},remaining(deadline));accept_device(quit);if(quit.status)throw std::runtime_error("Retained worker rejected final release");}
                if(!keep && (!state_.io_retired || !state_.device_released))throw std::runtime_error("Final retained-device release is unproved");
            }
        }catch(...){failure(HostFailure::control);control_ok_=false;keep=false;}
        if(!keep){
            usable_=false;device_closed_=true;control_ok_=false;state_.device_held=false;if(channel_)channel_->close();
            try{
                process_->wait_for_exit(remaining(deadline));
                do{state_.process=process_->observe();if(state_.process.process_exited && state_.process.job_empty)break;if(!remaining(deadline))break;Sleep(1);}while(true);
                const auto stopped=process_->terminate_and_wait(remaining(deadline));state_.process=stopped.state;
                state_.termination_requested=state_.termination_requested || stopped.termination_requested;
                if(state_.termination_requested)failure(HostFailure::containment);
            }catch(...){failure(HostFailure::containment);}
        }
    }
    if(audio_)state_.audio=audio_->stop(remaining(deadline));
    if(data_channel_ && state_.audio.retired)data_channel_->close();
    return report();
}
HostReport HostSession::report() noexcept {
    if(audio_){state_.audio=audio_->report();
        if(state_.audio.exit==AudioExit::pump_fault || state_.audio.exit==AudioExit::worker_exited || state_.audio.exit==AudioExit::wait_failed){
            failure(HostFailure::audio);state_.running=false;
        }
    }
    if(process_)try{
        state_.process=process_->observe();
        if(state_.device_held && state_.process.process_exited){failure(HostFailure::control);state_.device_held=false;usable_=false;}
        if(state_.running && state_.process.process_exited){failure(HostFailure::control);state_.running=false;}
    }catch(...){failure(HostFailure::containment);}
    return state_;
}
Observation HostSession::observation() const noexcept {return audio_?audio_->observation():Observation{};}
}
