#include "windows/heartbeat.hpp"
#include "windows/diagnostic.hpp"
#include <limits>
#include <stdexcept>

namespace sl3::worker {
static_assert(std::atomic<std::uint64_t>::is_always_lock_free,"Heartbeat needs lock-free x64 deadline access");
Heartbeat::Heartbeat(DWORD budget){
    if(budget<100 || budget>30000)throw std::invalid_argument("Worker heartbeat budget outside 100..30000 ms");
    const auto now=GetTickCount64();deadline_=now+budget;
    stop_=CreateEventW(nullptr,TRUE,FALSE,nullptr);if(!stop_)diagnostic::failed("Create worker heartbeat event");
    try{thread_=std::thread([this]{
        for(;;){
            const auto waited=WaitForSingleObject(stop_,20);
            if(waited==WAIT_OBJECT_0)return;
            if(waited!=WAIT_TIMEOUT)diagnostic::fail_stop();
            auto deadline=deadline_.load();
            if(GetTickCount64()>=deadline && deadline_.compare_exchange_strong(deadline,0))diagnostic::fail_stop();
        }
    });}catch(...){CloseHandle(stop_);stop_=nullptr;throw;}
}
Heartbeat::~Heartbeat(){
    if(!SetEvent(stop_))diagnostic::fail_stop();
    thread_.join();if(!CloseHandle(stop_))diagnostic::fail_stop();
}
void Heartbeat::pulse(DWORD budget) noexcept {
    if(budget<100 || budget>30000)diagnostic::fail_stop();
    auto deadline=deadline_.load();
    for(;;){
        const auto now=GetTickCount64();
        if(!deadline || now>=deadline || now>std::numeric_limits<std::uint64_t>::max()-budget)diagnostic::fail_stop();
        if(deadline_.compare_exchange_weak(deadline,now+budget))return;
    }
}
}
