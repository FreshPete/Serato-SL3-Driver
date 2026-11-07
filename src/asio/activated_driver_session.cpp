#include "asio/broker_activation.hpp"
#include <algorithm>

namespace sl3::asio {
namespace {
class ActivatedSession final:public DriverSession {
    BrokerActivationSpec spec_;
    std::shared_ptr<BrokerActivation> activation_;
    std::optional<DriverConfiguration> configuration_;
    std::unique_ptr<DriverSession> delegate_;
    HostReport state_{};
    bool attempted_=false,closed_=false;
public:
    explicit ActivatedSession(BrokerActivationSpec spec):spec_(std::move(spec)){
        state_.domain=HostDomain::broker_client;state_.device_released=false;
    }
    ~ActivatedSession(){
        const bool reentrant=delegate_ && delegate_->on_audio_thread();
        if(!reentrant)close(5000);
        if(activation_)activation_->request_retirement();
        delegate_.reset();
        configuration_.reset();
        if(activation_ && !reentrant){
            // A retired audio thread's reaper may still own its final lifetime
            // reference briefly. Keep normal cleanup on this control thread.
            const auto began=GetTickCount64();
            while(activation_->close().retirement_deferred && GetTickCount64()-began<2000)Sleep(1);
        }
    }
    bool inspect() noexcept override {
        if(closed_)return false;
        if(delegate_)return delegate_->inspect();
        if(attempted_)return false;attempted_=true;
        try{
            if(spec_.application_bound){
                configuration_=BrokerActivation::application_configuration(spec_);
            }else{
                if(spec_.output.empty())select_user_activation_output(spec_);
                activation_=BrokerActivation::start(spec_);configuration_=activation_->configuration();
            }
            delegate_=make_broker_driver_session(*configuration_->broker);
            return delegate_->inspect();
        }catch(const BrokerActivationError& error){
            state_.activation_failure=error.cleanup;
            state_.failure=activation_cleanup_contained(error.cleanup)?HostFailure::containment:HostFailure::launch;
        }catch(...){state_.failure=HostFailure::launch;}
        closed_=true;return false;
    }
    std::optional<unsigned> inspect_rate() noexcept override {return delegate_?delegate_->inspect_rate():std::nullopt;}
    ASIOError create_buffers(ASIOBufferInfo* info,long channel_count,long frames,const ASIOCallbacks* callbacks) noexcept override {
        return delegate_?delegate_->create_buffers(info,channel_count,frames,callbacks):ASE_NotPresent;
    }
    ASIOError dispose_buffers() noexcept override {return delegate_?delegate_->dispose_buffers():ASE_NotPresent;}
    bool start(unsigned intervals) noexcept override {return delegate_ && delegate_->start(intervals);}
    HostReport stop(DWORD timeout) noexcept override {return delegate_?delegate_->stop(timeout):state_;}
    HostReport close(DWORD timeout) noexcept override {
        if(on_audio_thread())return delegate_->close(timeout);
        closed_=true;
        if(!delegate_)return state_;
        const auto result=delegate_->close(timeout);
        if(driver_session_closed(result)){
            state_=result;if(activation_)activation_->request_retirement();
            delegate_.reset();configuration_.reset();
        }
        return result;
    }
    void request_shutdown() noexcept override {closed_=true;if(delegate_)delegate_->request_shutdown();}
    HostReport report() noexcept override {return delegate_?delegate_->report():state_;}
    bool on_audio_thread() const noexcept override {return delegate_ && delegate_->on_audio_thread();}
    Observation observation() const noexcept override {return delegate_?delegate_->observation():Observation{};}
};
}
std::unique_ptr<DriverSession> make_activated_driver_session(const BrokerActivationSpec& spec){
    return std::make_unique<ActivatedSession>(spec);
}
DriverOwner::DriverOwner(const BrokerActivationSpec& spec,std::shared_ptr<const void> lease):
    configuration_lease_(std::move(lease)),session_(make_activated_driver_session(spec)){}
}
