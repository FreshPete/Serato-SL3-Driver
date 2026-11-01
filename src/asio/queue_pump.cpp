#include "asio/queue_pump.hpp"

namespace sl3::asio {
QueuePump::QueuePump(worker::Mailbox& channel,BufferSet& buffers) noexcept:channel_(channel),buffers_(buffers) {}
QueuePump::~QueuePump(){end();}
PumpResult QueuePump::begin(unsigned rate) noexcept {
    if(inside_)return PumpResult::reentrant_call;
    if(state_!=PumpState::ready)return PumpResult::invalid_state;
    if(rate!=44100 && rate!=48000)return PumpResult::invalid_rate;
    if(buffers_.start_buffer_flow(rate)!=ASE_OK)return PumpResult::invalid_state;
    rate_=rate;owns_flow_=true;state_=PumpState::flowing;return PumpResult::ok;
}
PumpResult QueuePump::fail(PumpFailure failure) noexcept {
    if(state_!=PumpState::faulted)failure_=failure;
    state_=PumpState::faulted;return PumpResult::faulted;
}
PumpResult QueuePump::publish() noexcept {
    const auto result=channel_.try_push_audio(worker::AudioDirection::output,output_);
    if(result==worker::AudioResult::full)return PumpResult::backpressure;
    if(result!=worker::AudioResult::ok)return fail({PumpFault::queue,result,BridgeStatus::ok});
    ++stats_.published_blocks;stats_.published_frames+=pending_frames_;
    stats_.pending_output=false;pending_frames_=0;return PumpResult::ok;
}
PumpResult QueuePump::step() noexcept {
    if(inside_)return PumpResult::reentrant_call;
    if(state_==PumpState::ended)return PumpResult::ended;
    if(state_==PumpState::faulted)return PumpResult::faulted;
    if(state_!=PumpState::flowing)return PumpResult::invalid_state;
    struct Scope {bool& flag;explicit Scope(bool& f):flag(f){flag=true;}~Scope(){flag=false;}} scope(inside_);
    if(stats_.pending_output)return publish();
    const auto received=channel_.try_pop_audio(worker::AudioDirection::input,input_);
    if(received==worker::AudioResult::empty)return PumpResult::idle;
    if(received!=worker::AudioResult::ok)return fail({PumpFault::queue,received,BridgeStatus::ok});
    if(input_.reported_rate_hz!=rate_)return fail({PumpFault::rate,worker::AudioResult::rate_changed,BridgeStatus::ok});
    if(input_.packet_count<8 || input_.packet_count>64 || input_.packet_count%8)
        return fail({PumpFault::queue,worker::AudioResult::invalid_packet,BridgeStatus::ok});
    std::size_t count=0;
    for(std::size_t i=0;i<input_.packet_count;++i){
        // Mailbox validates the wire before copying. Keep the local fixed-array
        // bound explicit, so later changes cannot turn metadata into an overrun.
        const auto frames=input_.frames_per_packet[i];
        if(!frames || frames>7)return fail({PumpFault::queue,worker::AudioResult::invalid_packet,BridgeStatus::ok});
        lengths_[i]=frames*static_cast<std::uint32_t>(frame_bytes);count+=frames;
    }
    ++stats_.received_blocks;stats_.received_frames+=count;
    for(std::size_t frame=0;frame<count;++frame)for(std::size_t channel=0;channel<channels;++channel){
        const auto* sample=input_.pcm.data()+frame*frame_bytes+channel*sample_bytes;
        const std::uint32_t bits=sample[0]|(std::uint32_t(sample[1])<<8)|(std::uint32_t(sample[2])<<16);
        decoded_[frame][channel]=bits&0x800000?static_cast<std::int32_t>(bits)-0x1000000:static_cast<std::int32_t>(bits);
    }
    auto result=buffers_.accept_capture(decoded_.data(),count,input_.first_frame,input_.host_observation_ns);
    if(result!=BridgeStatus::ok)return fail({PumpFault::bridge,worker::AudioResult::ok,result});
    // Metadata describes the output stream's logical position and the observed
    // IN packet schedule, not the source-sample age or future USB launch time.
    output_.first_frame=input_.first_frame;output_.host_observation_ns=input_.host_observation_ns;
    output_.reported_rate_hz=rate_;output_.frames_per_packet=input_.frames_per_packet;output_.packet_count=input_.packet_count;
    result=buffers_.render_output(lengths_.data(),input_.packet_count,output_.pcm.data(),output_.pcm.size(),layout_.data(),layout_.size());
    if(result!=BridgeStatus::ok)return fail({PumpFault::bridge,worker::AudioResult::ok,result});
    pending_frames_=count;stats_.pending_output=true;return publish();
}
PumpResult QueuePump::end() noexcept {
    if(inside_)return PumpResult::reentrant_call;
    if(state_==PumpState::ended)return PumpResult::ok;
    if(owns_flow_ && buffers_.stop_buffer_flow()!=ASE_OK)return PumpResult::invalid_state;
    owns_flow_=false;
    if(stats_.pending_output)stats_.discarded_pending_frames+=pending_frames_;
    pending_frames_=0;stats_.pending_output=false;state_=PumpState::ended;return PumpResult::ok;
}
}
