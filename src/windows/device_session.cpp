#include "windows/device_session.hpp"
#include "windows/continuous_peer.hpp"
#include "windows/heartbeat.hpp"
#include "windows/diagnostic.hpp"

namespace sl3::worker {
namespace {
namespace protocol=device_session;
class Runtime {
    Mailbox& control_;session::Kind kind_;DeviceFactory factory_;SessionTimeouts timeouts_;Heartbeat heartbeat_;
    std::unique_ptr<SessionDevice> device_;
    std::unique_ptr<Mailbox> audio_;
    std::unique_ptr<MailboxStreamPeer> peer_;
    std::unique_ptr<SessionTarget> target_;
    std::unique_ptr<ContinuousStream> stream_;
    protocol::Snapshot snapshot_{};Message request_;
    bool greeted_=false,pending_reply_=false,exit_=false;
    const std::uint64_t entered_=GetTickCount64();
    void failure(session::Failure code,const std::string& text){
        if(snapshot_.failure==session::Failure::none){snapshot_.failure=code;snapshot_.diagnostic=text.substr(0,512);}
    }
    void capture() noexcept {
        if(stream_){snapshot_.stats=stream_->stats();snapshot_.stream_fault=stream_->fault();}
        if(target_)snapshot_.native_error=target_->native_error();
    }
    void release_device(){
        if(device_){
            heartbeat_.pulse(timeouts_.cleanup_ms);
            if(!device_->close()){
                snapshot_.native_error=device_->native_error();snapshot_.phase=protocol::Phase::retained;
                failure(session::Failure::cleanup,"Device redirect release failed");
                diagnostic::fail_stop();
            }
            device_.reset();
        }
        snapshot_.device_released=true;
        snapshot_.selection_supported=false;
    }
    void begin_stop(){
        if(stream_ && snapshot_.phase!=protocol::Phase::draining){
            heartbeat_.pulse(timeouts_.cleanup_ms);snapshot_.phase=protocol::Phase::draining;stream_->stop();
        }
    }
    void reply(session::Status status){
        capture();const auto body=protocol::encode_snapshot(snapshot_);
        if(!control_.respond(unsigned(status),body.data(),body.size())){exit_=true;begin_stop();}
    }
    void finish(){
        capture();
        if(stream_ && stream_->state()==StreamState::retained){
            snapshot_.phase=protocol::Phase::retained;snapshot_.io_retired=false;
            if(pending_reply_)reply(session::Status::operation_failed);
            diagnostic::fail_stop();
        }
        snapshot_.io_retired=true;stream_.reset();
        if(target_){
            heartbeat_.pulse(timeouts_.cleanup_ms);
            if(!target_->close()){
                snapshot_.native_error=target_->native_error();snapshot_.phase=protocol::Phase::retained;
                failure(session::Failure::cleanup,"Audio alternate/backend release failed");
                if(pending_reply_)reply(session::Status::operation_failed);
                diagnostic::fail_stop();
            }
            if(target_->control_failed()){
                snapshot_.native_error=target_->native_error();
                failure(session::Failure::control,"Retained-device playback keepalive failed");
            }
            target_.reset();
        }
        peer_.reset();
        // On an ordinary stop, detach our retired stream view without closing
        // the host-owned mapping. A callback already in progress may still
        // return/publish into that old queue before its audio owner retires.
        // The host closes it only after that thread exits; it is never reused.
        if(audio_ && snapshot_.failure!=session::Failure::none)audio_->close();
        audio_.reset();
        if(exit_ || snapshot_.failure!=session::Failure::none)release_device();
        snapshot_.phase=exit_?protocol::Phase::closed:snapshot_.failure!=session::Failure::none?protocol::Phase::failed:protocol::Phase::ready;
        heartbeat_.pulse(timeouts_.live_ms);
        if(pending_reply_){pending_reply_=false;reply(snapshot_.failure==session::Failure::none?session::Status::ok:session::Status::operation_failed);}
    }
    void command(){
        using session::Status;using protocol::Command;using protocol::Phase;
        if(pending_reply_)return;
        const auto result=control_.receive(0,request_);
        if(result==MessageResult::timeout)return;
        if(result!=MessageResult::ok){
            if(result!=MessageResult::closed)failure(session::Failure::control,"Invalid device control channel");
            exit_=true;begin_stop();return;
        }
        const auto command=Command(request_.opcode);protocol::Start start;
        control::selection_wire::Target selected{control::AudioControlSetting::through,0,0};
        unsigned selected_rate=0;
        try{
            if(command==Command::start)start=protocol::decode_start(request_.bytes);
            else if(command==Command::select_control)selected=control::selection_wire::decode_request(request_.bytes.data(),request_.bytes.size());
            else if(command==Command::select_rate)selected_rate=control::rate_wire::decode_request(request_.bytes.data(),request_.bytes.size());
            else if(!request_.bytes.empty())throw std::invalid_argument("Unexpected device command body");
        }catch(const std::exception&){reply(Status::bad_request);return;}
        if(command==Command::hello){
            if(greeted_){reply(Status::bad_state);return;}
            greeted_=true;const auto body=protocol::encode_hello(kind_);
            if(!control_.respond(unsigned(Status::ok),body.data(),body.size()))exit_=true;return;
        }
        if(!greeted_){reply(Status::bad_state);return;}
        if(command==Command::quit){
            exit_=true;
            if(stream_){pending_reply_=true;begin_stop();}
            else{release_device();snapshot_.phase=Phase::closed;reply(Status::ok);}
            return;
        }
        if(command==Command::state){reply(Status::ok);return;}
        if(command==Command::stop){
            if(stream_){pending_reply_=true;begin_stop();}else reply(Status::ok);return;
        }
        if(command==Command::acquire){
            if(snapshot_.phase!=Phase::empty){reply(Status::bad_state);return;}
            heartbeat_.pulse(timeouts_.startup_ms);
            try{
                device_=factory_();if(!device_)throw std::runtime_error("Device factory returned no device");
                snapshot_.device_released=false;
                snapshot_.selection_supported=device_->supports_selection();
                const auto rate=device_->read_rate();session::encode_clock(rate);snapshot_.rate_hz=rate;
                snapshot_.phase=Phase::ready;heartbeat_.pulse(timeouts_.live_ms);reply(Status::ok);
            }catch(const std::exception& e){
                snapshot_.native_error=GetLastError();failure(session::Failure::startup,e.what());release_device();
                snapshot_.phase=Phase::failed;heartbeat_.pulse(timeouts_.live_ms);reply(Status::operation_failed);
            }
            return;
        }
        if(command==Command::clock){
            if(snapshot_.phase!=Phase::ready || !device_ || stream_ || !snapshot_.io_retired){reply(Status::bad_state);return;}
            heartbeat_.pulse(timeouts_.startup_ms);snapshot_.io_retired=false;
            try{
                const auto rate=device_->read_rate();session::encode_clock(rate);
                snapshot_.rate_hz=rate;snapshot_.io_retired=true;
                heartbeat_.pulse(timeouts_.live_ms);reply(Status::ok);
            }catch(const std::exception& e){
                snapshot_.io_retired=true;snapshot_.native_error=GetLastError();
                failure(session::Failure::control,e.what());release_device();snapshot_.phase=Phase::failed;
                heartbeat_.pulse(timeouts_.live_ms);reply(Status::operation_failed);
            }
            return;
        }
        if(command==Command::controls){
            if(snapshot_.phase!=Phase::ready || !device_ || stream_ || !snapshot_.io_retired){reply(Status::bad_state);return;}
            heartbeat_.pulse(timeouts_.startup_ms);snapshot_.io_retired=false;
            try{
                const auto sample=device_->read_controls();snapshot_.io_retired=true;
                snapshot_.selection_supported=device_->supports_selection();
                const auto body=protocol::encode_controls({snapshot_,sample});
                heartbeat_.pulse(timeouts_.live_ms);
                if(!control_.respond(unsigned(Status::ok),body.data(),body.size())){exit_=true;release_device();}
            }catch(const std::exception& e){
                // The SessionDevice contract requires retired I/O on exception.
                snapshot_.io_retired=true;snapshot_.native_error=GetLastError();
                failure(session::Failure::control,e.what());release_device();snapshot_.phase=Phase::failed;
                heartbeat_.pulse(timeouts_.live_ms);reply(Status::operation_failed);
            }
            return;
        }
        if(command==Command::select_control){
            if(snapshot_.phase!=Phase::ready || !device_ || stream_ || !snapshot_.io_retired){reply(Status::bad_state);return;}
            if(!snapshot_.selection_supported || !device_->supports_selection()){
                snapshot_.selection_supported=false;reply(Status::bad_request);return;
            }
            heartbeat_.pulse(std::min<DWORD>(timeouts_.startup_ms,protocol::selection_watchdog_ms));snapshot_.io_retired=false;
            try{
                const auto outcome=device_->select_control(selected);
                // Validate before treating any sample or I/O-retirement claim as known.
                const auto checked=control::selection_wire::encode_reply(outcome);
                control::selection_wire::decode_reply(checked.data(),checked.size(),selected);
                snapshot_.io_retired=true;snapshot_.native_error=outcome.native_error;
                const bool success=outcome.selection.error==control::SelectionIoError::none;
                if(!success){failure(session::Failure::control,"Control selection did not verify");snapshot_.phase=Phase::failed;}
                const auto body=protocol::encode_selection({snapshot_,outcome});
                heartbeat_.pulse(timeouts_.live_ms);
                // Return valid observations before final redirect release. A later
                // failed close cannot erase a completed operation's evidence.
                if(!control_.respond(unsigned(success?Status::ok:Status::operation_failed),body.data(),body.size()))exit_=true;
            }catch(const std::exception& e){
                snapshot_.io_retired=true;snapshot_.native_error=GetLastError();
                failure(session::Failure::control,e.what());snapshot_.phase=Phase::failed;
                heartbeat_.pulse(timeouts_.live_ms);reply(Status::operation_failed);
            }
            return;
        }
        if(command==Command::select_rate){
            if(snapshot_.phase!=Phase::ready || !device_ || stream_ || !snapshot_.io_retired){reply(Status::bad_state);return;}
            if(!device_->supports_rate_selection()){reply(Status::bad_request);return;}
            heartbeat_.pulse(std::min<DWORD>(timeouts_.startup_ms,protocol::rate_watchdog_ms));snapshot_.io_retired=false;
            // An old stream's statistics/interval contract cannot describe a new
            // clock epoch, and pre-write clock state is not post-write evidence.
            snapshot_.rate_hz=0;snapshot_.intervals=0;snapshot_.stats={};snapshot_.stream_fault=StreamFault::none;
            try{
                const auto outcome=device_->select_rate(selected_rate);
                const auto checked=control::rate_wire::encode_reply(outcome);
                control::rate_wire::decode_reply(checked.data(),checked.size(),selected_rate);
                snapshot_.io_retired=true;snapshot_.native_error=outcome.native_error;
                const bool success=outcome.observation.error==control::DiagnosticError::none;
                snapshot_.rate_hz=success?outcome.observation.verified_rate_hz:outcome.observation.readback_rate_hz;
                if(!success){failure(session::Failure::control,"Rate selection did not verify");snapshot_.phase=Phase::failed;}
                const auto body=protocol::encode_rate_selection({snapshot_,outcome});
                heartbeat_.pulse(timeouts_.live_ms);
                // Preserve completed observations before any later close failure.
                if(!control_.respond(unsigned(success?Status::ok:Status::operation_failed),body.data(),body.size()))exit_=true;
            }catch(const std::exception& e){
                snapshot_.io_retired=true;snapshot_.native_error=GetLastError();
                failure(session::Failure::control,e.what());snapshot_.phase=Phase::failed;
                heartbeat_.pulse(timeouts_.live_ms);reply(Status::operation_failed);
            }
            return;
        }
        if(command!=Command::start){reply(Status::bad_request);return;}
        if(snapshot_.phase!=Phase::ready || !device_){reply(Status::bad_state);return;}
        // Control and each stream own distinct mappings. A claimed mapping can
        // never be reopened/reset for another stream, even if its queues emptied.
        if(start.audio_channel==control_.name()){reply(Status::bad_request);return;}
        heartbeat_.pulse(timeouts_.startup_ms);
        try{
            audio_=Mailbox::open(start.audio_channel);
            if(!audio_->audio_pristine())throw std::runtime_error("Audio channel was used before stream admission");
            const auto rate=device_->read_rate();session::encode_clock(rate);snapshot_.rate_hz=rate;
            if(rate!=start.config.rate_hz)throw std::runtime_error("Held device clock changed; no audio activation");
            snapshot_.stats={};snapshot_.stream_fault=StreamFault::none;snapshot_.intervals=start.config.intervals;
            peer_=std::make_unique<MailboxStreamPeer>(*audio_);
            target_=device_->begin(start.config);if(!target_)throw std::runtime_error("Device returned no audio target");
            stream_=std::make_unique<ContinuousStream>(target_->backend(),*peer_);snapshot_.io_retired=false;
            if(!stream_->start(start.config)){
                failure(session::Failure::stream,"Initial retained-device input submission failed");
                pending_reply_=true;begin_stop();
                if(stream_->state()==StreamState::stopped || stream_->state()==StreamState::retained)finish();
                return;
            }
            snapshot_.phase=Phase::running;heartbeat_.pulse(timeouts_.live_ms);reply(Status::ok);
        }catch(const std::exception& e){
            snapshot_.native_error=GetLastError();failure(session::Failure::startup,e.what());
            pending_reply_=true;
            if(stream_){begin_stop();if(stream_->state()==StreamState::stopped)finish();}
            else finish();
        }
    }
public:
    Runtime(Mailbox& control,session::Kind kind,DeviceFactory factory,SessionTimeouts t):
        control_(control),kind_(kind),factory_(std::move(factory)),timeouts_(t),heartbeat_(t.live_ms){
        if(!factory_ || t.startup_ms<100 || t.startup_ms>30000 || t.cleanup_ms<100 || t.cleanup_ms>30000 ||
           !t.idle_ms || t.idle_ms>30000)throw std::invalid_argument("Invalid retained-device worker policy");
    }
    ~Runtime(){if(device_ || target_ || stream_)diagnostic::fail_stop();}
    int run(){
        for(;;){
            heartbeat_.pulse(snapshot_.phase==protocol::Phase::draining?timeouts_.cleanup_ms:timeouts_.live_ms);
            command();
            if(stream_){
                if(target_->control_failed()){
                    failure(session::Failure::control,"Retained-device playback keepalive failed");
                    begin_stop();
                }
                const auto state=stream_->step();capture();
                if(stream_->fault()!=StreamFault::none){failure(session::Failure::stream,"Retained-device audio engine fault");begin_stop();}
                if(state==StreamState::stopped || state==StreamState::retained)finish();
            }
            if(exit_ && !stream_){release_device();return snapshot_.failure==session::Failure::none?0:1;}
            // A held device is intentionally idle through ASIO setup/UI pauses.
            // Host loss is observed via closed control mapping/private process job.
            if(!device_ && !stream_ && GetTickCount64()-entered_>=timeouts_.idle_ms)return snapshot_.failure==session::Failure::none?0:1;
            if(target_){
                // Completion/data wakes remain event-driven. A separate control
                // command is observed within the five-ms wait bound.
                if(!target_->wait_for_work(*audio_,snapshot_.stats.pending_mask,5)){
                    failure(session::Failure::wait,"Retained-device completion wait failed");begin_stop();
                }
            }else{
                const auto waited=WaitForSingleObject(control_.request_event(),50);
                if(waited!=WAIT_OBJECT_0 && waited!=WAIT_TIMEOUT){
                    failure(session::Failure::wait,"Retained-device control wait failed");exit_=true;
                }
            }
        }
    }
};
}
int serve_device_session(Mailbox& control,session::Kind kind,DeviceFactory factory,SessionTimeouts timeouts){
    Runtime runtime(control,kind,std::move(factory),timeouts);return runtime.run();
}
}
