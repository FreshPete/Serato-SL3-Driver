#include "asio/driver_session.hpp"
#include "windows/broker_pipe.hpp"
#include <algorithm>
#include <stdexcept>

namespace sl3::asio {
namespace {
DWORD remaining(ULONGLONG deadline) noexcept {const auto now=GetTickCount64();return now>=deadline?0:DWORD(deadline-now);}
class BrokerSession final:public DriverSession {
    BrokerAttachment spec_;
    std::shared_ptr<BufferLease> buffers_=std::make_shared<BufferLease>();
    std::unique_ptr<worker::BrokerClient> client_;
    std::shared_ptr<worker::ProcessWait> worker_;
    std::shared_ptr<worker::Mailbox> data_;
    std::unique_ptr<AudioOwner> audio_;
    HostReport state_{};
    bool closed_=false,usable_=false,prepared_=false;
    void failure(HostFailure f) noexcept {if(state_.failure==HostFailure::none)state_.failure=f;usable_=false;}
    void accept(const device_session::Snapshot& s) noexcept {
        state_.device_snapshot=s;state_.io_retired=s.io_retired;state_.device_released=s.device_released;
        state_.observed_rate_hz=s.rate_hz;
        state_.device_held=state_.broker.attached && !s.device_released;
    }
    bool idle() noexcept {
        const auto r=report();return !closed_ && usable_ && r.failure==HostFailure::none && r.broker.attached &&
            r.broker.worker_alive && !r.running && r.audio.retired && r.io_retired && r.device_snapshot.phase==device_session::Phase::ready;
    }
    HostReport reentry() noexcept {
        auto r=state_;r.reentrant=true;r.audio=audio_->report();r.audio.reentrant=true;r.io_retired=false;r.device_released=false;return r;
    }
public:
    explicit BrokerSession(BrokerAttachment spec):spec_(std::move(spec)){
        if(!spec_.server || (spec_.kind!=session::Kind::native && spec_.kind!=session::Kind::simulated))throw std::invalid_argument("Explicit broker server/kind required");
        state_.domain=HostDomain::broker_client;state_.device_released=false;
    }
    ~BrokerSession(){if(!audio_ || audio_->report().retired)close();request_shutdown();}
    bool inspect() noexcept override {
        if(on_audio_thread() || closed_ || state_.running || state_.failure!=HostFailure::none)return false;
        if(client_)return idle();
        try{
            client_=std::make_unique<worker::BrokerClient>(spec_.endpoint,spec_.server->handle(),spec_.kind,spec_.worker_sha256);
            state_.broker.attached=state_.broker.ever_attached=true;
            worker_=worker::ProcessWait::duplicate(client_->worker_process_handle());
            state_.broker.worker_pid=GetProcessId(worker_->handle());accept(client_->observation());usable_=true;
            return idle();
        }catch(...){failure(HostFailure::handshake);request_shutdown();return false;}
    }
    std::optional<unsigned> inspect_rate() noexcept override {
        if(on_audio_thread() || prepared_ || !idle())return std::nullopt;
        try{client_->clock();accept(client_->observation());return state_.observed_rate_hz;}
        catch(...){state_.observed_rate_hz=0;state_.io_retired=false;failure(HostFailure::inspection);request_shutdown();return std::nullopt;}
    }
    ASIOError create_buffers(ASIOBufferInfo* b,long c,long f,const ASIOCallbacks* cb) noexcept override {
        if(on_audio_thread() || !idle())return ASE_InvalidMode;
        const auto result=buffers_->create(b,c,f,cb);if(result==ASE_OK)prepared_=true;return result;
    }
    ASIOError dispose_buffers() noexcept override {
        if(on_audio_thread() || state_.running || (audio_ && !audio_->report().retired))return ASE_InvalidMode;
        // Failed/disconnected sessions may dispose only after actual callbacks
        // retire. No broker or device recovery is inferred by disposing planes.
        const auto result=buffers_->dispose();if(result==ASE_OK)prepared_=false;return result;
    }
    bool start(unsigned intervals) noexcept override {
        if(on_audio_thread() || !prepared_ || !idle() || intervals<8 || intervals>64 || intervals%8)return false;
        const auto expected_rate=state_.observed_rate_hz;
        try{
            audio_.reset();if(data_)data_->close();data_=worker::Mailbox::create();
            audio_=std::make_unique<AudioOwner>(buffers_,data_,worker_);
            if(!audio_->start(state_.observed_rate_hz))throw std::runtime_error("Broker audio owner did not start");
            // Native operation may begin once the request is published. An old
            // idle snapshot is no longer proof of I/O retirement.
            state_.io_retired=false;state_.observed_rate_hz=0;
            accept(client_->start(*data_,{expected_rate,intervals,1000,2000}));
            if(audio_->report().exit!=AudioExit::running)throw std::runtime_error("Broker audio owner failed during start");
            state_.running=true;return true;
        }catch(...){failure(HostFailure::worker_start);request_shutdown();if(audio_)audio_->stop(2000);return false;}
    }
    HostReport stop(DWORD timeout=5000) noexcept override {
        if(on_audio_thread())return reentry();
        const auto deadline=GetTickCount64()+(std::min)(timeout,DWORD(5000));
        report();if(audio_)audio_->request_stop();state_.running=false;
        if(state_.broker.attached){
            try{
                if(!remaining(deadline))throw std::runtime_error("Broker stop deadline exhausted");
                accept(client_->stop(remaining(deadline)));
            }catch(...){state_.io_retired=false;state_.observed_rate_hz=0;failure(HostFailure::control);request_shutdown();}
        }
        if(audio_)state_.audio=audio_->stop(remaining(deadline));
        if(data_ && state_.audio.retired)data_->close();return report();
    }
    HostReport close(DWORD timeout=5000) noexcept override {
        if(on_audio_thread())return reentry();
        const auto deadline=GetTickCount64()+(std::min)(timeout,DWORD(5000));
        if(!closed_)stop(remaining(deadline));
        else if(audio_)state_.audio=audio_->stop(remaining(deadline));
        if(!closed_ && state_.broker.attached && state_.failure==HostFailure::none && state_.audio.retired && state_.io_retired){
            try{
                if(!remaining(deadline))throw std::runtime_error("Broker detach deadline exhausted");
                const auto detached=client_->detach(remaining(deadline));state_.broker.attached=false;state_.broker.detached=true;
                accept(detached);state_.device_held=false;
            }catch(...){failure(HostFailure::control);}
        }
        if(!closed_ && (state_.broker.attached || !state_.audio.retired))request_shutdown();
        closed_=true;usable_=false;return report();
    }
    void request_shutdown() noexcept override {
        closed_=true;usable_=false;state_.running=false;state_.device_held=false;
        if(audio_)audio_->request_stop();if(data_)data_->close();
        if(client_){if(state_.broker.attached && !state_.broker.detached)failure(HostFailure::control);client_->disconnect();}
        state_.broker.attached=false; // No acknowledged detach/release is implied.
    }
    HostReport report() noexcept override {
        if(audio_){state_.audio=audio_->report();
            if(state_.audio.exit==AudioExit::pump_fault || state_.audio.exit==AudioExit::worker_exited || state_.audio.exit==AudioExit::wait_failed){
                failure(HostFailure::audio);state_.running=false;
            }
        }
        if(worker_){
            const auto wait=WaitForSingleObject(worker_->handle(),0);state_.broker.worker_alive=wait==WAIT_TIMEOUT;state_.broker.worker_exited=wait==WAIT_OBJECT_0;
            if(state_.broker.attached && wait!=WAIT_TIMEOUT){failure(HostFailure::control);state_.device_held=false;state_.running=false;}
        }
        if(state_.broker.attached && WaitForSingleObject(spec_.server->handle(),0)!=WAIT_TIMEOUT){failure(HostFailure::control);state_.device_held=false;state_.running=false;}
        return state_;
    }
    bool on_audio_thread() const noexcept override{return audio_ && audio_->on_audio_thread();}
    Observation observation() const noexcept override{return audio_?audio_->observation():Observation{};}
};
}
std::unique_ptr<DriverSession> make_broker_driver_session(BrokerAttachment spec){return std::make_unique<BrokerSession>(std::move(spec));}
}
