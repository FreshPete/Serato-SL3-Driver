#pragma once
#include "core/continuous.hpp"
#include <windows.h>
#include <string>

namespace sl3::testing {
class FakeBackend final:public ContinuousBackend {
    struct Slot {bool prepared=false,pending=false,cancelled=false;std::uint64_t sequence=0;};
    std::array<Slot,8> slots_{};unsigned intervals_=8;
    std::uint64_t next_=0;std::wstring mode_;unsigned partial_polls_=0;
public:
    explicit FakeBackend(std::wstring mode):mode_(std::move(mode)){}
    bool prepare(unsigned i,unsigned n) noexcept override {intervals_=n;slots_[i].prepared=true;return true;}
    bool submit_input(unsigned i,bool) noexcept override {
        if(mode_==L"hang-submit")Sleep(INFINITE);
        if(mode_==L"partial-start" && i==1)return false;
        slots_[i].sequence=next_++;slots_[i].pending=true;slots_[i].cancelled=false;return true;
    }
    bool submit_output(unsigned i,const AudioBlock&,bool) noexcept override {slots_[i].pending=true;slots_[i].cancelled=false;return true;}
    StreamPoll poll(unsigned i,StreamInput* input) noexcept override {
        if(mode_==L"hang-poll")Sleep(INFINITE);
        if(mode_==L"retained")return StreamPoll::unproven;
        if(mode_==L"partial-start" && slots_[i].cancelled && partial_polls_++<2)return StreamPoll::pending;
        auto& slot=slots_[i];slot.pending=false;
        if(slot.cancelled)return StreamPoll::failure;
        if(i<4 && input){
            input->packet_count=intervals_;input->pcm.fill(0);
            for(unsigned p=0;p<intervals_;++p){input->packets[p]={108,0};
                for(unsigned k=0;k<108;++k)input->pcm[p*126+k]=std::uint8_t(slot.sequence*17+p*13+k);}
        }
        return StreamPoll::success;
    }
    bool cancel(unsigned i) noexcept override {slots_[i].cancelled=true;return mode_!=L"retained";}
    bool release(unsigned i) noexcept override {if(slots_[i].pending)return false;slots_[i].prepared=false;return true;}
    std::uint64_t now_ns() const noexcept override {return GetTickCount64()*1000000;}
    bool retired() const noexcept {for(const auto& slot:slots_)if(slot.prepared || slot.pending)return false;return true;}
};
}
