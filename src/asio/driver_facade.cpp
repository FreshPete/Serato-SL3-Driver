#include "asio/driver_facade.hpp"
#include <cstdio>
#include <limits>
#include <stdexcept>

namespace sl3::asio {
namespace {
template<class T>void split(std::uint64_t value,T& result) noexcept {
    result.hi=static_cast<unsigned long>(value>>32);result.lo=static_cast<unsigned long>(value);
}
}
DriverFacade::DriverFacade(WorkerSpec spec,LatencyProfile latency,std::shared_ptr<const void> lease):
    DriverFacade(std::make_shared<DriverOwner>(std::move(spec),std::move(lease)),latency){}
DriverFacade::DriverFacade(BrokerAttachment spec,LatencyProfile latency,std::shared_ptr<const void> lease):
    DriverFacade(std::make_shared<DriverOwner>(std::move(spec),std::move(lease)),latency){}
DriverOwner::DriverOwner(WorkerSpec spec,std::shared_ptr<const void> lease):
    configuration_lease_(std::move(lease)),session_(make_owned_driver_session(std::move(spec))){}
DriverOwner::DriverOwner(BrokerAttachment spec,std::shared_ptr<const void> lease):
    configuration_lease_(std::move(lease)),session_(make_broker_driver_session(std::move(spec))){}
std::optional<HostReport> DriverOwner::close(DWORD timeout) noexcept {
    bool idle=false;if(!borrowed_.compare_exchange_strong(idle,true))return std::nullopt;
    sealed_=true;const auto result=session_->close(timeout);borrowed_=false;return result;
}
void DriverOwner::detach(bool buffers_created) noexcept {
    const auto report=session_->report();
    // Active/blocked callbacks must stop admitting new calls immediately. Keep
    // the existing AudioOwner leases until an executing callback returns.
    bool clean=!session_->on_audio_thread() && report.audio.retired && !report.running &&
        report.failure==HostFailure::none && report.io_retired;
    if(clean && buffers_created)clean=session_->dispose_buffers()==ASE_OK;
    if(!clean){sealed_=true;session_->request_shutdown();}
    borrowed_=false;
}
std::shared_ptr<DriverOwner> DriverFacade::claim(std::shared_ptr<DriverOwner> owner,LatencyProfile latency){
    const auto limit=unsigned(std::numeric_limits<long>::max())-2048u;
    if(latency.input_extra_frames>limit || latency.output_extra_frames>limit)throw std::invalid_argument("ASIO latency exceeds signed frame range");
    if((latency.rate_hz && latency.rate_hz!=44100 && latency.rate_hz!=48000) ||
       (latency.buffer_frames && (latency.buffer_frames<64 || latency.buffer_frames>1024 || (latency.buffer_frames&(latency.buffer_frames-1)))))
        throw std::invalid_argument("Invalid timing profile mode");
    if(!owner)throw std::invalid_argument("Missing ASIO device owner");
    bool idle=false;
    if(!owner->borrowed_.compare_exchange_strong(idle,true))throw std::runtime_error("ASIO device owner is already borrowed");
    if(owner->sealed_){owner->borrowed_=false;throw std::runtime_error("ASIO device owner is sealed");}
    return owner;
}
DriverFacade::DriverFacade(std::shared_ptr<DriverOwner> owner,LatencyProfile latency):
    owner_(claim(std::move(owner),latency)),session_(*owner_->session_),latency_(latency){}
DriverFacade::~DriverFacade(){owner_->detach(frames_.load()!=0);}
ASIOError DriverFacade::fail(ASIOError code,const char* text) noexcept {error_=text;return code;}
ASIOBool DriverFacade::init() noexcept {
    if(session_.on_audio_thread())return ASIOFalse;
    if(initialized_)return ASIOTrue;
    if(frames_){error_="Dispose existing buffers before reinitializing.";return ASIOFalse;}
    const bool already_held=session_.report().device_held;
    if(!session_.inspect() || (already_held && !session_.inspect_rate())){error_="SL3 worker/clock inspection failed; device unavailable.";return ASIOFalse;}
    const auto observed=session_.report().observed_rate_hz;
    if(latency_.rate_hz && latency_.rate_hz!=observed){session_.close();error_="SL3 clock differs from the reviewed timing profile.";return ASIOFalse;}
    rate_=observed;initialized_=true;error_="No error.";return ASIOTrue;
}
void DriverFacade::getErrorMessage(char* message) const noexcept {if(message)std::snprintf(message,124,"%s",error_.load());}
ASIOError DriverFacade::start() noexcept {
    if(session_.on_audio_thread())return fail(ASE_InvalidMode,"Start is not a callback operation.");
    if(!initialized_)return ASE_NotPresent;
    if(started_)return fail(ASE_InvalidMode,"Session is already started.");
    if(!frames_)return fail(ASE_InvalidMode,"Create buffers before starting.");
    if(!session_.start(8)){initialized_=false;return fail(ASE_HWMalfunction,"SL3 startup failed; stop, dispose buffers and reopen the driver.");}
    started_=true;error_="No error.";return ASE_OK;
}
ASIOError DriverFacade::stop() noexcept {
    if(session_.on_audio_thread())return fail(ASE_InvalidMode,"Stop is not a callback operation.");
    if(!initialized_ && !frames_)return ASE_NotPresent;
    const auto result=session_.stop();started_=false;
    const bool released=result.device_released && (!result.process.started || (result.process.process_exited && result.process.job_empty));
    const bool live_owner=result.domain==HostDomain::broker_client?(result.broker.attached && result.broker.worker_alive):
        (result.process.started && result.process.job_assigned && !result.process.process_exited);
    const bool held=result.device_held && !result.device_released && live_owner &&
        result.device_snapshot.phase==device_session::Phase::ready;
    if(!result.audio.retired || !result.io_retired || (!released && !held) || result.failure!=HostFailure::none){
        initialized_=false;return fail(ASE_HWMalfunction,"SL3 stop is incomplete or the session failed; retained buffers stay owned.");
    }
    error_="No error.";return ASE_OK;
}
ASIOError DriverFacade::getChannels(long* input,long* output) const noexcept {
    if(!initialized_)return ASE_NotPresent;if(!input || !output)return ASE_InvalidParameter;
    *input=6;*output=6;return ASE_OK;
}
ASIOError DriverFacade::getLatencies(long* input,long* output) const noexcept {
    if(!initialized_)return ASE_NotPresent;if(!input || !output)return ASE_InvalidParameter;
    if (!latency_.report_latency) {
        // Some hosts consume both outputs even when the query returns an error.
        *input = 0;
        *output = 0;
        return ASE_InvalidMode;
    }
    auto frames=frames_.load();if(!frames)frames=latency_.buffer_frames;if(!frames)return ASE_InvalidMode;
    *input=long(frames+latency_.input_extra_frames);*output=long(frames+latency_.output_extra_frames);return ASE_OK;
}
ASIOError DriverFacade::getBufferSize(long* minimum,long* maximum,long* preferred,long* granularity) const noexcept {
    if(!initialized_)return ASE_NotPresent;if(!minimum || !maximum || !preferred || !granularity)return ASE_InvalidParameter;
    if(latency_.buffer_frames){*minimum=*maximum=*preferred=long(latency_.buffer_frames);*granularity=0;}
    else{*minimum=64;*maximum=1024;*preferred=128;*granularity=-1;}return ASE_OK;
}
ASIOError DriverFacade::canSampleRate(ASIOSampleRate rate) const noexcept {
    if(!initialized_)return ASE_NotPresent;
    // No rate setter has been validated: accept only the already observed rate.
    return rate==ASIOSampleRate(rate_.load())?ASE_OK:ASE_NoClock;
}
ASIOError DriverFacade::getSampleRate(ASIOSampleRate* rate) const noexcept {
    if(!initialized_)return ASE_NotPresent;if(!rate)return ASE_InvalidParameter;*rate=rate_.load();return ASE_OK;
}
ASIOError DriverFacade::setSampleRate(ASIOSampleRate rate) noexcept {
    if(session_.on_audio_thread())return fail(ASE_InvalidMode,"Rate selection is not a callback operation.");
    return canSampleRate(rate); // Successful same-rate selection performs no write.
}
ASIOError DriverFacade::getClockSources(ASIOClockSource* clocks,long* count) const noexcept {
    if(!initialized_)return ASE_NotPresent;if(!count || *count<0 || (*count && !clocks))return ASE_InvalidParameter;
    if(*count){ASIOClockSource source{};source.index=0;source.associatedChannel=-1;source.associatedGroup=-1;source.isCurrentSource=ASIOTrue;
        std::snprintf(source.name,sizeof(source.name),"SL3 device clock");clocks[0]=source;}
    *count=1;return ASE_OK;
}
ASIOError DriverFacade::setClockSource(long index) noexcept {
    if(session_.on_audio_thread())return fail(ASE_InvalidMode,"Clock selection is not a callback operation.");
    if(!initialized_)return ASE_NotPresent;return index==0?ASE_OK:ASE_InvalidParameter;
}
ASIOError DriverFacade::getSamplePosition(ASIOSamples* samples,ASIOTimeStamp* time) const noexcept {
    if(!initialized_)return ASE_NotPresent;if(!samples || !time)return ASE_InvalidParameter;
    const auto observed=session_.observation();if(!observed.valid)return ASE_SPNotAdvancing;
    // Current input-bank logical position and backend publication observation.
    // No DAC playhead, hardware clock interpolation or wall-clock pacing claim.
    ASIOSamples position{};ASIOTimeStamp timestamp{};
    split(observed.first_frame,position);split(observed.host_observation_ns,timestamp);
    *samples=position;*time=timestamp;return ASE_OK;
}
ASIOError DriverFacade::getChannelInfo(ASIOChannelInfo* info) const noexcept {
    if(!initialized_)return ASE_NotPresent;
    if(!info || info->channel<0 || info->channel>=6 || (info->isInput!=ASIOTrue && info->isInput!=ASIOFalse))return ASE_InvalidParameter;
    auto result=*info;const auto bit=unsigned(info->channel)+(info->isInput==ASIOTrue?0u:6u);
    result.isActive=(active_.load()&(1u<<bit))?ASIOTrue:ASIOFalse;result.channelGroup=0;result.type=ASIOSTInt24LSB;
    std::snprintf(result.name,sizeof(result.name),"SL3 %s %ld",info->isInput==ASIOTrue?"Input":"Output",info->channel+1);*info=result;return ASE_OK;
}
ASIOError DriverFacade::createBuffers(ASIOBufferInfo* info,long count,long frames,ASIOCallbacks* callbacks) noexcept {
    if(session_.on_audio_thread())return fail(ASE_InvalidMode,"Buffer creation is not a callback operation.");
    if(!initialized_)return ASE_NotPresent;
    if(latency_.buffer_frames && frames!=long(latency_.buffer_frames))return ASE_InvalidMode;
    const auto result=session_.create_buffers(info,count,frames,callbacks);
    if(result==ASE_OK){unsigned selected=0;for(long i=0;i<count;++i)selected|=1u<<(unsigned(info[i].channelNum)+(info[i].isInput==ASIOTrue?0u:6u));
        active_=selected;frames_=unsigned(frames);}
    return result;
}
ASIOError DriverFacade::disposeBuffers() noexcept {
    if(session_.on_audio_thread())return fail(ASE_InvalidMode,"Buffer disposal is not a callback operation.");
    if(!frames_)return initialized_?ASE_InvalidMode:ASE_NotPresent;
    const auto result=session_.dispose_buffers();if(result==ASE_OK){frames_=0;active_=0;}return result;
}
ASIOError DriverFacade::controlPanel() const noexcept {return ASE_NotPresent;}
ASIOError DriverFacade::future(long,void*) const noexcept {return ASE_NotPresent;}
ASIOError DriverFacade::outputReady() const noexcept {return ASE_NotPresent;}
}
