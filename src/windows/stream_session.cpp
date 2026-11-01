#include "windows/stream_session.hpp"
#include "windows/continuous_peer.hpp"
#include "windows/heartbeat.hpp"
#include "windows/mailbox_layout.hpp"
#include "windows/diagnostic.hpp"
#include <algorithm>

namespace sl3::worker {
namespace {
static_assert(wire::version==session::queue_version,"Session and audio queue versions must agree");
class Runtime {
    Mailbox& mailbox_;session::Kind kind_;SessionFactory factory_;SessionInspector inspector_;SessionTimeouts timeouts_;
    Heartbeat heartbeat_;MailboxStreamPeer peer_;
    std::unique_ptr<SessionTarget> target_;
    std::unique_ptr<ContinuousStream> stream_;
    session::Snapshot snapshot_{};Message request_;
    bool greeted_=false,pending_reply_=false,exit_=false;
    std::uint64_t last_control_=GetTickCount64();
    void failure(session::Failure code,const std::string& text={}){
        if(snapshot_.failure==session::Failure::none){snapshot_.failure=code;snapshot_.diagnostic=text.substr(0,512);}
    }
    void capture() noexcept {
        if(stream_){snapshot_.stats=stream_->stats();snapshot_.stream_fault=stream_->fault();}
        if(target_)snapshot_.native_error=target_->native_error();
    }
    bool reply(session::Status status){
        capture();const auto body=session::encode_snapshot(snapshot_);
        const bool sent=mailbox_.respond(std::uint32_t(status),body.data(),body.size());if(!sent)exit_=true;return sent;
    }
    void begin_stop(){
        if(!stream_)return;
        if(snapshot_.phase!=session::Phase::draining){heartbeat_.pulse(timeouts_.cleanup_ms);snapshot_.phase=session::Phase::draining;stream_->stop();}
    }
    void finish(){
        capture();
        if(stream_ && stream_->state()==StreamState::retained){
            snapshot_.phase=session::Phase::retained;snapshot_.io_retired=false;
            if(pending_reply_)reply(session::Status::operation_failed);
            diagnostic::fail_stop();
        }
        snapshot_.io_retired=true;stream_.reset();
        if(target_){
            heartbeat_.pulse(timeouts_.cleanup_ms);
            if(!target_->close()){
                snapshot_.native_error=target_->native_error();snapshot_.phase=session::Phase::retained;
                failure(session::Failure::cleanup,"Native device release failed");
                if(pending_reply_)reply(session::Status::operation_failed);
                diagnostic::fail_stop();
            }
            target_.reset();
        }
        snapshot_.device_released=true;
        snapshot_.phase=snapshot_.failure==session::Failure::none?session::Phase::stopped:session::Phase::failed;
        heartbeat_.pulse(timeouts_.live_ms);last_control_=GetTickCount64();
        if(pending_reply_){pending_reply_=false;reply(snapshot_.failure==session::Failure::none?session::Status::ok:session::Status::operation_failed);}
    }
    void command(){
        using namespace session;
        if(pending_reply_)return;
        const auto received=mailbox_.receive(0,request_);
        if(received==MessageResult::timeout)return;
        if(received!=MessageResult::ok){
            if(received!=MessageResult::closed)failure(Failure::control,"Invalid control mailbox");
            exit_=true;begin_stop();return;
        }
        last_control_=GetTickCount64();const auto command=Command(request_.opcode);StreamConfig config{};
        try{if(command==Command::start)config=decode_start(request_.bytes);
            else if(!request_.bytes.empty())throw std::invalid_argument("Unexpected session command body");}
        catch(const std::exception&){reply(Status::bad_request);return;}
        if(command==Command::quit){
            exit_=true;if(stream_){pending_reply_=true;begin_stop();}else reply(Status::ok);return;
        }
        if(command==Command::hello){
            if(greeted_){reply(Status::bad_state);return;}
            greeted_=true;const auto bytes=encode_hello(kind_);
            if(!mailbox_.respond(std::uint32_t(Status::ok),bytes.data(),bytes.size()))exit_=true;return;
        }
        if(!greeted_){reply(Status::bad_state);return;}
        if(command==Command::state){reply(Status::ok);return;}
        if(command==Command::inspect){
            if(snapshot_.phase!=Phase::idle){reply(Status::bad_state);return;}
            heartbeat_.pulse(timeouts_.startup_ms);
            try{
                const auto bytes=encode_clock(inspector_());
                heartbeat_.pulse(timeouts_.live_ms);last_control_=GetTickCount64();
                if(!mailbox_.respond(std::uint32_t(Status::ok),bytes.data(),bytes.size()))exit_=true;
            }catch(const std::exception& error){
                snapshot_.native_error=GetLastError();failure(Failure::startup,error.what());
                snapshot_.phase=Phase::failed;heartbeat_.pulse(timeouts_.live_ms);reply(Status::operation_failed);
            }
            return;
        }
        if(command==Command::stop){
            if(stream_){pending_reply_=true;begin_stop();}else reply(Status::ok);return;
        }
        if(command!=Command::start){reply(Status::bad_request);return;}
        if(snapshot_.phase!=Phase::idle){reply(Status::bad_state);return;}
        snapshot_.phase=Phase::starting;snapshot_.rate_hz=config.rate_hz;snapshot_.intervals=config.intervals;
        snapshot_.io_retired=false;snapshot_.device_released=false;heartbeat_.pulse(timeouts_.startup_ms);
        try{
            target_=factory_(config);if(!target_)throw std::runtime_error("Session factory returned no target");
            stream_=std::make_unique<ContinuousStream>(target_->backend(),peer_);
            if(!stream_->start(config)){
                capture();failure(Failure::stream,"Initial input submission failed");snapshot_.phase=Phase::draining;
                heartbeat_.pulse(timeouts_.cleanup_ms);
                if(stream_->state()==StreamState::stopped || stream_->state()==StreamState::retained)finish();
                reply(Status::operation_failed);return;
            }
            snapshot_.phase=Phase::running;heartbeat_.pulse(timeouts_.live_ms);reply(Status::ok);
        }catch(const std::exception& error){
            snapshot_.native_error=GetLastError();failure(Failure::startup,error.what());
            if(stream_){begin_stop();if(stream_->state()==StreamState::stopped)finish();}
            else{
                snapshot_.io_retired=true;
                if(target_){if(!target_->close())diagnostic::fail_stop();target_.reset();}
                snapshot_.device_released=true;snapshot_.phase=Phase::failed;heartbeat_.pulse(timeouts_.live_ms);
            }
            reply(Status::operation_failed);
        }
    }
public:
    Runtime(Mailbox& mailbox,session::Kind kind,SessionFactory factory,SessionInspector inspector,SessionTimeouts timeouts):
        mailbox_(mailbox),kind_(kind),factory_(std::move(factory)),inspector_(std::move(inspector)),timeouts_(timeouts),heartbeat_(timeouts.live_ms),peer_(mailbox){
        if(!factory_ || !inspector_ || timeouts.startup_ms<100 || timeouts.startup_ms>30000 || timeouts.cleanup_ms<100 || timeouts.cleanup_ms>30000 ||
           !timeouts.idle_ms || timeouts.idle_ms>30000)throw std::invalid_argument("Invalid continuous worker policy");
    }
    ~Runtime(){if(target_ || stream_)diagnostic::fail_stop();}
    int run(){
        for(;;){
            heartbeat_.pulse(snapshot_.phase==session::Phase::draining?timeouts_.cleanup_ms:timeouts_.live_ms);
            command();
            if(stream_){
                const auto state=stream_->step();capture();
                if(stream_->fault()!=StreamFault::none){failure(session::Failure::stream,"Continuous request engine fault");begin_stop();}
                if(state==StreamState::stopped || state==StreamState::retained)finish();
            }
            if(exit_ && !stream_)return snapshot_.failure==session::Failure::none?0:1;
            if(!stream_ && GetTickCount64()-last_control_>=timeouts_.idle_ms)return snapshot_.failure==session::Failure::none?0:1;
            if(target_){
                if(!target_->wait_for_work(mailbox_,snapshot_.stats.pending_mask,5)){failure(session::Failure::wait,"Native completion wait failed");begin_stop();}
            }else{
                const auto waited=WaitForSingleObject(mailbox_.request_event(),50);
                if(waited!=WAIT_OBJECT_0 && waited!=WAIT_TIMEOUT){failure(session::Failure::wait,"Control wait failed");return 1;}
            }
        }
    }
};
}
int serve_stream_session(Mailbox& mailbox,session::Kind kind,SessionFactory factory,SessionInspector inspector,SessionTimeouts timeouts){
    Runtime runtime(mailbox,kind,std::move(factory),std::move(inspector),timeouts);return runtime.run();
}
}
