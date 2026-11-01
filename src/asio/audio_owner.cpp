#include "asio/audio_owner.hpp"
#include <process.h>
#include <stdexcept>

namespace sl3::asio {
namespace {constexpr unsigned closed_gate=0x80000000u;thread_local void* current_audio=nullptr;}
struct AudioOwner::State {
    std::shared_ptr<BufferLease> buffers;
    std::shared_ptr<worker::Mailbox> channel;
    std::shared_ptr<worker::ProcessWait> process;
    HANDLE stop=nullptr,ready=nullptr,retired=nullptr,thread=nullptr;
    std::atomic<unsigned> gate{0};
    std::atomic<AudioExit> exit{AudioExit::not_started};std::atomic<bool> flow_started{false};
    std::atomic<std::uint64_t> started{0},completed{0},input_frames{0},published_frames{0};
    std::atomic<std::uint64_t> observed_sequence{0},position{0},time{0};
    std::atomic<unsigned> bank{0};std::atomic<bool> observation_valid{false};
    unsigned rate=0;PumpFailure failure{};
    State(std::shared_ptr<BufferLease> b,std::shared_ptr<worker::Mailbox> c,std::shared_ptr<worker::ProcessWait> p):
        buffers(std::move(b)),channel(std::move(c)),process(std::move(p)){
        stop=CreateEventW(nullptr,TRUE,FALSE,nullptr);ready=CreateEventW(nullptr,TRUE,FALSE,nullptr);retired=CreateEventW(nullptr,TRUE,FALSE,nullptr);
        if(!stop || !ready || !retired){if(stop)CloseHandle(stop);if(ready)CloseHandle(ready);if(retired)CloseHandle(retired);throw std::runtime_error("Cannot create audio-owner lifetime events");}
    }
    ~State(){if(thread)CloseHandle(thread);CloseHandle(stop);CloseHandle(ready);CloseHandle(retired);}
    // The winning close distinguishes a live worker fault from a process exit
    // observed after an already requested stop/final release.
    bool close_gate() noexcept {const auto prior=gate.fetch_or(closed_gate);SetEvent(stop);return !(prior&closed_gate);}
};
struct AudioOwner::ThreadContext {std::shared_ptr<State> state;};
struct AudioOwner::ReaperContext {std::shared_ptr<State> state;HMODULE module=nullptr;};
ASIOError BufferLease::create(ASIOBufferInfo* info,long count,long frames,const ASIOCallbacks* callbacks) noexcept {
    if(acquired_)return ASE_InvalidMode;
    if(!callbacks || !callbacks->bufferSwitch)return ASE_InvalidMode;
    auto wrapped=*callbacks;wrapped.bufferSwitch=&AudioOwner::callback;
    const auto result=buffers_.create(info,count,frames,&wrapped);if(result==ASE_OK)callbacks_=*callbacks;return result;
}
ASIOError BufferLease::dispose() noexcept {if(acquired_)return ASE_InvalidMode;const auto result=buffers_.dispose();if(result==ASE_OK)callbacks_={};return result;}
AudioOwner::AudioOwner(std::shared_ptr<BufferLease> b,std::shared_ptr<worker::Mailbox> c,std::shared_ptr<worker::Process> p):
    AudioOwner(std::move(b),std::move(c),worker::ProcessWait::owned(std::move(p))){}
AudioOwner::AudioOwner(std::shared_ptr<BufferLease> b,std::shared_ptr<worker::Mailbox> c,std::shared_ptr<worker::ProcessWait> p){
    if(!b || !c || !p)throw std::invalid_argument("Audio owner needs shared buffers, channel and process");
    state_=std::make_shared<State>(std::move(b),std::move(c),std::move(p));
}
AudioOwner::~AudioOwner(){request_stop();if(attempted_ && WaitForSingleObject(state_->retired,0)!=WAIT_OBJECT_0)state_->channel->close();}
void AudioOwner::callback(long bank,ASIOBool direct){
    auto* state=static_cast<State*>(current_audio);if(!state)return;
    if(WaitForSingleObject(state->process->handle(),0)==WAIT_OBJECT_0){if(state->close_gate())state->exit=AudioExit::worker_exited;return;}
    auto value=state->gate.load();
    do{if(value&closed_gate)return;}while(!state->gate.compare_exchange_weak(value,value+1));
    struct Lease {State* state;~Lease(){state->gate.fetch_sub(1);}} lease{state};
    const auto observed=state->buffers->buffers_.observation();
    state->observed_sequence.fetch_add(1);state->position=observed.first_frame;state->time=observed.host_observation_ns;
    state->bank=observed.bank;state->observation_valid=observed.valid;state->observed_sequence.fetch_add(1);
    state->started.fetch_add(1);state->buffers->callbacks_.bufferSwitch(bank,direct);state->completed.fetch_add(1);
}
unsigned __stdcall AudioOwner::thread_entry(void* raw) noexcept {
    std::unique_ptr<ThreadContext> context(static_cast<ThreadContext*>(raw));auto state=std::move(context->state);context.reset();
    current_audio=state.get();
    {
        QueuePump pump(*state->channel,state->buffers->buffers_);
        if(pump.begin(state->rate)!=PumpResult::ok){state->exit=AudioExit::startup_failed;SetEvent(state->ready);}
        else{
            state->flow_started=true;state->exit=AudioExit::running;SetEvent(state->ready);
            const HANDLE waits[]={state->stop,state->process->handle(),state->channel->input_event()};
            while(!(state->gate.load()&closed_gate)){
                if(WaitForSingleObject(state->process->handle(),0)==WAIT_OBJECT_0){if(state->close_gate())state->exit=AudioExit::worker_exited;state->channel->close();break;}
                const auto result=pump.step();const auto stats=pump.stats();
                state->input_frames=stats.received_frames;state->published_frames=stats.published_frames;
                if(result==PumpResult::ok)continue;
                if(result!=PumpResult::idle && result!=PumpResult::backpressure){
                    const auto failure=pump.failure();
                    // An already executing callback may finish after its
                    // control owner completed stop/quit and closed the queue.
                    // Only that sealed-gate/closed-queue case is ordinary stop;
                    // callback, format, rate and other transport faults remain.
                    if((state->gate.load()&closed_gate) && failure.cause==PumpFault::queue && failure.queue==worker::AudioResult::closed)break;
                    state->failure=failure;state->exit=AudioExit::pump_fault;state->channel->close();break;
                }
                const auto waited=WaitForMultipleObjects(3,waits,FALSE,100);
                if(waited==WAIT_OBJECT_0)break;
                if(waited==WAIT_OBJECT_0+1){if(state->close_gate())state->exit=AudioExit::worker_exited;state->channel->close();break;}
                if(waited!=WAIT_OBJECT_0+2 && waited!=WAIT_TIMEOUT){state->exit=AudioExit::wait_failed;state->channel->close();break;}
            }
            if(state->exit==AudioExit::running)state->exit=AudioExit::stopped;
        }
        state->close_gate();pump.end();state->observation_valid=false;
    }
    current_audio=nullptr;return 0; // CRT epilogue completes before reaper fires.
}
void CALLBACK AudioOwner::thread_retired(PTP_CALLBACK_INSTANCE instance,void* raw,PTP_WAIT wait,TP_WAIT_RESULT result) noexcept {
    auto* context=static_cast<ReaperContext*>(raw);
    // A thread wait without a timeout should only report signalled. Unknown
    // observation retains the context/module/buffers; never free an active owner.
    if(result!=WAIT_OBJECT_0){CloseThreadpoolWait(wait);return;}
    if(context->module)FreeLibraryWhenCallbackReturns(instance,context->module);
    CloseThreadpoolWait(wait);
    auto state=std::move(context->state);delete context;
    state->buffers->acquired_=false;
    SetEvent(state->retired);
    // The DLL reference is released by Windows only after THIS callback returns.
}
bool AudioOwner::start(unsigned rate,DWORD timeout){
    if(attempted_ || (state_->gate.load()&closed_gate) || timeout>5000 || (rate!=44100 && rate!=48000) || !state_->buffers->buffers_.prepared() || !state_->process->handle())return false;
    bool expected=false;if(!state_->buffers->acquired_.compare_exchange_strong(expected,true))return false;
    attempted_=true;state_->rate=rate;HMODULE module=nullptr;PTP_WAIT wait=nullptr;ReaperContext* reaper=nullptr;ThreadContext* thread=nullptr;
    try{
        const auto address=reinterpret_cast<LPCWSTR>(&AudioOwner::thread_entry);HMODULE containing=nullptr;
        if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,address,&containing))throw std::runtime_error("Find audio-owner module");
        if(containing!=GetModuleHandleW(nullptr) && !GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,address,&module))throw std::runtime_error("Retain audio-owner DLL");
        reaper=new ReaperContext{state_,module};wait=CreateThreadpoolWait(&AudioOwner::thread_retired,reaper,nullptr);
        if(!wait)throw std::runtime_error("Create audio-thread retirement observer");
        thread=new ThreadContext{state_};
        const auto handle=_beginthreadex(nullptr,0,&AudioOwner::thread_entry,thread,0,nullptr);
        if(!handle)throw std::runtime_error("Create dedicated audio thread");
        thread=nullptr;state_->thread=reinterpret_cast<HANDLE>(handle);
        // Ownership is transferred BEFORE arming: a finished thread can invoke
        // and destroy its reaper immediately, even before this call returns.
        const auto armed=wait;wait=nullptr;reaper=nullptr;module=nullptr;
        SetThreadpoolWait(armed,state_->thread,nullptr);
    }catch(...){
        delete thread;if(wait)CloseThreadpoolWait(wait);delete reaper;if(module)FreeLibrary(module);
        state_->buffers->acquired_=false;state_->exit=AudioExit::startup_failed;SetEvent(state_->retired);return false;
    }
    if(WaitForSingleObject(state_->ready,timeout)!=WAIT_OBJECT_0 || !state_->flow_started || state_->exit!=AudioExit::running){request_stop();return false;}
    return true;
}
void AudioOwner::request_stop() noexcept {state_->close_gate();}
AudioReport AudioOwner::stop(DWORD timeout) noexcept {
    if(current_audio==state_.get()){auto value=report();value.reentrant=true;return value;}
    if(timeout>5000)timeout=5000;request_stop();if(attempted_)WaitForSingleObject(state_->retired,timeout);return report();
}
bool AudioOwner::on_audio_thread() const noexcept {return current_audio==state_.get();}
AudioReport AudioOwner::report() const noexcept {
    AudioReport value;value.exit=state_->exit;value.retired=!attempted_ || WaitForSingleObject(state_->retired,0)==WAIT_OBJECT_0;
    value.active_callbacks=state_->gate.load()&~closed_gate;value.callbacks_started=state_->started;value.callbacks_completed=state_->completed;
    value.input_frames=state_->input_frames;value.published_frames=state_->published_frames;
    if(value.retired)value.pump_failure=state_->failure;return value;
}
Observation AudioOwner::observation() const noexcept {
    for(unsigned i=0;i<8;++i){const auto before=state_->observed_sequence.load();if(before&1)continue;
        Observation value{state_->observation_valid.load(),state_->bank.load(),state_->position.load(),state_->time.load()};
        if(before==state_->observed_sequence.load())return value;
    }
    return {};
}
}
