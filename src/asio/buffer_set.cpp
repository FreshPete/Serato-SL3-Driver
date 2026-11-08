#include "asio/buffer_set.hpp"
#include <cstdio>
#include <new>

namespace sl3::asio {
static_assert(sizeof(long)==4 && sizeof(void*)==8,"Pinned SDK component targets Windows x64");
static_assert(sizeof(ASIOBufferInfo)==24 && sizeof(ASIOCallbacks)==32,"Unexpected ASIO buffer/callback ABI");
static_assert(ASIOSTInt24LSB==17,"Unexpected packed 24-bit sample identifier");

ASIOError BufferSet::create(ASIOBufferInfo* info,long count,long frames,const ASIOCallbacks* callbacks) noexcept {
    if(in_callback_ || bridge_)return ASE_InvalidMode;
    if(!info || !callbacks || count<=0 || count>12)return ASE_InvalidParameter;
    // No time-info negotiation until sample-position/timestamp provenance is
    // established by a real session. Hosts must supply the legacy callback.
    if(!callbacks->bufferSwitch || frames<32 || frames>1024 || (frames&(frames-1)))return ASE_InvalidMode;
    try{
        std::array<unsigned,6> in{},out{};
        std::array<bool,6> in_selected{},out_selected{};
        std::size_t in_count=0,out_count=0;
        for(long i=0;i<count;++i){
            if(info[i].channelNum<0 || info[i].channelNum>=6 ||
               (info[i].isInput!=ASIOTrue && info[i].isInput!=ASIOFalse))return ASE_InvalidParameter;
            const auto channel=static_cast<unsigned>(info[i].channelNum);
            auto& selected=info[i].isInput==ASIOTrue?in_selected:out_selected;
            if(selected[channel])return ASE_InvalidMode;
            selected[channel]=true;
            if(info[i].isInput==ASIOTrue)in[in_count++]=channel;else out[out_count++]=channel;
        }
        // Range construction permits allocation failure to propagate into this
        // handler. MSVC's Debug default-vector proxy may allocate inside its
        // noexcept default constructor, before reserve() can be reached.
        const std::vector<unsigned> inputs(in.begin(),in.begin()+static_cast<std::ptrdiff_t>(in_count));
        const std::vector<unsigned> outputs(out.begin(),out.begin()+static_cast<std::ptrdiff_t>(out_count));
        auto candidate=std::make_unique<AudioBridge>(static_cast<std::size_t>(frames),inputs,outputs);
        // Publish pointers only after every validation/allocation succeeded.
        for(long i=0;i<count;++i)for(unsigned bank=0;bank<2;++bank)
            info[i].buffers[bank]=candidate->plane(info[i].isInput==ASIOTrue?Direction::input:Direction::output,
                                                 static_cast<unsigned>(info[i].channelNum),bank);
        callbacks_=*callbacks;observation_={};bridge_=std::move(candidate);
        return ASE_OK;
    }catch(const std::bad_alloc&){return ASE_NoMemory;}
    catch(...){return ASE_InvalidMode;}
}
ASIOError BufferSet::dispose() noexcept {
    if(in_callback_ || !bridge_)return ASE_InvalidMode;
    if(bridge_->stop()!=BridgeStatus::ok)return ASE_InvalidMode;
    bridge_.reset();callbacks_={};observation_={};return ASE_OK;
}
ASIOError BufferSet::start_buffer_flow(unsigned rate) noexcept {
    if(in_callback_ || !bridge_)return ASE_InvalidMode;
    const auto result=bridge_->start(rate,*this);
    if(result==BridgeStatus::invalid_argument)return ASE_NoClock;
    if(result!=BridgeStatus::ok)return ASE_InvalidMode;
    observation_={};return ASE_OK;
}
ASIOError BufferSet::stop_buffer_flow() noexcept {
    if(in_callback_ || !bridge_)return ASE_InvalidMode;
    if(bridge_->stop()!=BridgeStatus::ok)return ASE_InvalidMode;
    observation_={};return ASE_OK;
}
ASIOError BufferSet::channel_info(ASIOChannelInfo* info) const noexcept {
    if(!info || info->channel<0 || info->channel>=6 ||
       (info->isInput!=ASIOTrue && info->isInput!=ASIOFalse))return ASE_InvalidParameter;
    const auto direction=info->isInput==ASIOTrue?Direction::input:Direction::output;
    info->isActive=bridge_ && bridge_->plane(direction,static_cast<unsigned>(info->channel),0)?ASIOTrue:ASIOFalse;
    info->channelGroup=0;info->type=ASIOSTInt24LSB;
    std::snprintf(info->name,sizeof(info->name),"SL3 %s %ld",info->isInput==ASIOTrue?"Input":"Output",info->channel+1);
    return ASE_OK;
}
BridgeStatus BufferSet::accept_capture(const Frame* frames,std::size_t count,std::uint64_t position,std::uint64_t time) noexcept {
    return bridge_?bridge_->process(frames,count,position,time):BridgeStatus::invalid_state;
}
BridgeStatus BufferSet::render_output(const std::uint32_t* lengths,std::size_t packets,std::uint8_t* pcm,
                                      std::size_t capacity,Packet* layout,std::size_t layout_capacity) noexcept {
    return bridge_?bridge_->render(lengths,packets,pcm,capacity,layout,layout_capacity):BridgeStatus::invalid_state;
}
void BufferSet::buffer_switch(unsigned bank,std::uint64_t position,std::uint64_t time) {
    observation_={true,bank,position,time};
    struct CallbackScope {
        bool& flag;
        explicit CallbackScope(bool& target):flag(target){flag=true;}
        ~CallbackScope(){flag=false;}
    } guard(in_callback_);
    // Ordinary user-mode callback: suggest immediate processing; the core also
    // permits a deferred host to fill this bank before the next switch.
    callbacks_.bufferSwitch(static_cast<long>(bank),ASIOTrue);
}
}
