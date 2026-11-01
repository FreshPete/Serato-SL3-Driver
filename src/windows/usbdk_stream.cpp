#include "windows/usbdk_stream.hpp"
#include "windows/diagnostic.hpp"
#include <cstring>
#include <limits>

namespace sl3::worker {
static_assert(sizeof(void*)==8 && sizeof(USB_DK_TRANSFER_REQUEST)==72 && sizeof(USB_DK_ISO_TRANSFER_RESULT)==16,"Pinned UsbDk x64 ABI");
UsbDkStreamBackend::UsbDkStreamBackend(UsbDkStreamApi usb,HANDLE redirect,HANDLE system,OverlappedApi win) noexcept:
    usb_(usb),win_(win),redirect_(redirect),system_(system) {
    if(!usb.read || !usb.write || !redirect || redirect==INVALID_HANDLE_VALUE || !system || system==INVALID_HANDLE_VALUE ||
       !win.create_event || !win.reset_event || !win.close_handle || !win.wait || !win.result || !win.cancel || !win.counter || !win.frequency){reject(ERROR_INVALID_PARAMETER);return;}
    LARGE_INTEGER frequency{},counter{};
    if(!win_.frequency(&frequency) || !win_.counter(&counter) || frequency.QuadPart<=0 || counter.QuadPart<0 ||
       std::uint64_t(frequency.QuadPart)>std::numeric_limits<std::uint64_t>::max()/1000000000){reject(ERROR_INVALID_DATA);return;}
    frequency_=std::uint64_t(frequency.QuadPart);valid_=true;
}
UsbDkStreamBackend::~UsbDkStreamBackend(){
    for(const auto& slot:slots_)if(slot.lease!=Lease::idle || slot.release_failed)diagnostic::fail_stop();
    for(unsigned i=0;i<slots_.size();++i)if(slots_[i].prepared && !release(i))diagnostic::fail_stop();
}
bool UsbDkStreamBackend::reject(DWORD error) noexcept {last_error_=error?error:ERROR_GEN_FAILURE;return false;}
bool UsbDkStreamBackend::immediate_poll() const noexcept {
    for(const auto& slot:slots_)if(slot.lease==Lease::synchronous || slot.lease==Lease::uncertain)return true;return false;
}
HANDLE UsbDkStreamBackend::pending_event(unsigned i) const noexcept {
    return i<slots_.size() && slots_[i].prepared && slots_[i].lease==Lease::pending?slots_[i].overlapped.hEvent:nullptr;
}
std::uint64_t UsbDkStreamBackend::now_ns() const noexcept {
    if(!valid_)return 0;
    LARGE_INTEGER counter{};if(!win_.counter(&counter) || counter.QuadPart<0)return 0;
    const auto ticks=std::uint64_t(counter.QuadPart),seconds=ticks/frequency_,remainder=ticks%frequency_;
    if(seconds>std::numeric_limits<std::uint64_t>::max()/1000000000)return 0;
    const auto whole=seconds*1000000000,fraction=remainder*1000000000/frequency_;
    return whole>std::numeric_limits<std::uint64_t>::max()-fraction?0:whole+fraction;
}
bool UsbDkStreamBackend::prepare(unsigned i,unsigned intervals) noexcept {
    if(!valid_ || i>=slots_.size() || intervals<8 || intervals>64 || intervals%8)return reject(ERROR_INVALID_PARAMETER);
    auto& slot=slots_[i];if(slot.prepared || slot.lease!=Lease::idle || slot.release_failed)return reject(ERROR_INVALID_STATE);
    const auto event=win_.create_event(nullptr,TRUE,FALSE,nullptr);if(!event)return reject(GetLastError());
    slot.overlapped={};slot.overlapped.hEvent=event;slot.intervals=intervals;slot.prepared=true;
    slot.request={};slot.request.EndpointAddress=i<4?0x82:0x06;
    slot.request.Buffer=slot.pcm.data();slot.request.TransferType=IsochronousTransferType;
    slot.request.IsochronousPacketsArraySize=intervals;slot.request.IsochronousPacketsArray=slot.lengths.data();
    slot.request.Result.IsochronousResultsArray=slot.results.data();return true;
}
bool UsbDkStreamBackend::submit(unsigned i,bool output) noexcept {
    auto& slot=slots_[i];const auto event=slot.overlapped.hEvent;
    if(!win_.reset_event(event))return reject(GetLastError());
    slot.overlapped={};slot.overlapped.hEvent=event;
    slot.results.fill({});slot.request.Result={};slot.request.Result.IsochronousResultsArray=slot.results.data();
    const auto result=output?usb_.write(redirect_,&slot.request,&slot.overlapped):usb_.read(redirect_,&slot.request,&slot.overlapped);
    if(result==TransferFailure)return reject(GetLastError());
    if(result==TransferSuccess)slot.lease=Lease::synchronous;
    else if(result==TransferSuccessAsync)slot.lease=Lease::pending;
    else{
        // Unknown helper return cannot establish that nothing was accepted.
        // Keep the lease and report unproven; only process containment can free it.
        slot.lease=Lease::uncertain;last_error_=ERROR_INVALID_DATA;
    }
    return true;
}
bool UsbDkStreamBackend::submit_input(unsigned i,bool) noexcept {
    if(i>=4 || !slots_[i].prepared || slots_[i].lease!=Lease::idle || slots_[i].release_failed)return reject(ERROR_INVALID_STATE);
    auto& slot=slots_[i];slot.pcm.fill(0);slot.lengths.fill(0);
    for(unsigned p=0;p<slot.intervals;++p)slot.lengths[p]=126;
    slot.request.BufferLength=slot.intervals*126;
    // UsbDk's API has no explicit frame placement/continuation parameter.
    // Logical continuation supplied by the core does not prove ASAP continuity.
    return submit(i,false);
}
bool UsbDkStreamBackend::submit_output(unsigned i,const AudioBlock& block,bool) noexcept {
    if(i<4 || i>=slots_.size() || !slots_[i].prepared || slots_[i].lease!=Lease::idle || slots_[i].release_failed)return reject(ERROR_INVALID_STATE);
    auto& slot=slots_[i];
    if(block.packet_count!=slot.intervals || (block.reported_rate_hz!=44100 && block.reported_rate_hz!=48000))return reject(ERROR_INVALID_DATA);
    std::size_t bytes=0;
    for(unsigned p=0;p<64;++p){
        const auto frames=block.frames_per_packet[p];
        if(p<slot.intervals){if(!frames || frames>7)return reject(ERROR_INVALID_DATA);bytes+=frames*18;}
        else if(frames)return reject(ERROR_INVALID_DATA);
    }
    slot.pcm.fill(0);slot.lengths.fill(0);
    for(unsigned p=0;p<slot.intervals;++p)slot.lengths[p]=block.frames_per_packet[p]*18;
    std::memcpy(slot.pcm.data(),block.pcm.data(),bytes);slot.request.BufferLength=bytes;
    return submit(i,true);
}
StreamPoll UsbDkStreamBackend::poll(unsigned i,StreamInput* input) noexcept {
    if(i>=slots_.size() || !slots_[i].prepared || slots_[i].lease==Lease::idle || (i>=4 && input)){reject(ERROR_INVALID_STATE);return StreamPoll::unproven;}
    auto& slot=slots_[i];
    if(slot.lease==Lease::uncertain)return StreamPoll::unproven;
    if(slot.lease==Lease::pending){
        const auto waited=win_.wait(slot.overlapped.hEvent,0);
        if(waited==WAIT_TIMEOUT)return StreamPoll::pending;
        if(waited!=WAIT_OBJECT_0){reject(GetLastError());return StreamPoll::unproven;}
        DWORD bytes=0;
        if(!win_.result(system_,&slot.overlapped,&bytes,FALSE)){
            const auto error=GetLastError();
            if(error==ERROR_IO_INCOMPLETE || error==ERROR_IO_PENDING)return StreamPoll::pending;
            reject(error);
            if(error!=ERROR_OPERATION_ABORTED)return StreamPoll::unproven;
            slot.lease=Lease::idle;return StreamPoll::failure;
        }
    }
    slot.lease=Lease::idle;
    if(slot.request.Result.GenResult.UsbdStatus)return StreamPoll::failure;
    if(i>=4){
        for(unsigned p=0;p<slot.intervals;++p)if(slot.results[p].TransferResult)return StreamPoll::failure;
        // Windows does not define OUT packet ActualLength as accepted bytes.
    }else if(input){
        StreamInput candidate;candidate.packet_count=slot.intervals;candidate.pcm=slot.pcm;
        for(unsigned p=0;p<slot.intervals;++p)candidate.packets[p]={slot.results[p].ActualLength,slot.results[p].TransferResult};
        *input=candidate;
    }
    return StreamPoll::success;
}
bool UsbDkStreamBackend::cancel(unsigned i) noexcept {
    if(i>=slots_.size() || !slots_[i].prepared)return reject(ERROR_INVALID_STATE);
    auto& slot=slots_[i];if(slot.lease==Lease::idle || slot.lease==Lease::synchronous)return true;
    if(!win_.cancel(system_,&slot.overlapped))return reject(GetLastError());
    return true; // Cancellation request only. The lease remains outstanding.
}
bool UsbDkStreamBackend::release(unsigned i) noexcept {
    if(i>=slots_.size() || !slots_[i].prepared || slots_[i].release_failed)return reject(ERROR_INVALID_STATE);
    auto& slot=slots_[i];if(slot.lease!=Lease::idle)return reject(ERROR_IO_PENDING);
    if(!win_.close_handle(slot.overlapped.hEvent)){slot.release_failed=true;return reject(GetLastError());}
    slot.overlapped.hEvent=nullptr;slot.prepared=false;return true;
}
}
