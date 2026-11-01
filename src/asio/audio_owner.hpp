#pragma once
#include "asio/queue_pump.hpp"
#include "windows/worker_process.hpp"
#include <atomic>

namespace sl3::asio {
class AudioOwner;
// Shared ASIO planes survive an owner timeout/destruction. Mutate configuration
// only from one control owner, with no acquired audio owner. Reuse these exact
// planes across fresh worker/channel identities after a completed retirement.
class BufferLease final {
public:
    ASIOError create(ASIOBufferInfo*,long channels,long frames,const ASIOCallbacks*) noexcept;
    ASIOError dispose() noexcept;
    bool acquired() const noexcept {return acquired_.load();}
private:
    friend class AudioOwner;
    BufferSet buffers_;
    ASIOCallbacks callbacks_{};
    std::atomic<bool> acquired_{false};
};
enum class AudioExit {not_started,running,stopped,startup_failed,pump_fault,worker_exited,wait_failed};
struct AudioReport {
    AudioExit exit=AudioExit::not_started;
    bool retired=true,reentrant=false;
    unsigned active_callbacks=0;
    std::uint64_t callbacks_started=0,callbacks_completed=0,input_frames=0,published_frames=0;
    PumpFailure pump_failure{};
};
// One control owner, plus a dedicated CRT audio thread. This does not launch,
// stop, kill or certify the native worker. The caller must own its typed control
// lifecycle separately. Process/queue/buffers remain shared until actual thread
// exit, even if this object is destroyed while user callback code is blocked.
class AudioOwner final {
    friend class BufferLease;
public:
    AudioOwner(std::shared_ptr<BufferLease>,std::shared_ptr<worker::Mailbox>,std::shared_ptr<worker::Process>);
    ~AudioOwner();
    AudioOwner(const AudioOwner&)=delete;
    AudioOwner& operator=(const AudioOwner&)=delete;
    bool start(unsigned metadata_rate_hz,DWORD ready_timeout_ms=2000);
    void request_stop() noexcept;
    AudioReport stop(DWORD timeout_ms=2000) noexcept;
    bool on_audio_thread() const noexcept;
    AudioReport report() const noexcept;
    Observation observation() const noexcept;
private:
    struct State;
    struct ThreadContext;
    struct ReaperContext;
    std::shared_ptr<State> state_;
    bool attempted_=false;
    static void callback(long,ASIOBool);
    static unsigned __stdcall thread_entry(void*) noexcept;
    static void CALLBACK thread_retired(PTP_CALLBACK_INSTANCE,void*,PTP_WAIT,TP_WAIT_RESULT) noexcept;
};
}
