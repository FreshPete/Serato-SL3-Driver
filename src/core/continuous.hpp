#pragma once
#include "core/audio_block.hpp"
#include "core/duplex.hpp"

namespace sl3 {
enum class StreamPoll {pending,success,failure,unproven};
enum class StreamExchange {ok,empty,full,failure};
enum class StreamState {ready,running,draining,stopped,retained};
enum class StreamFault {none,configuration,prepare,submit,input_transfer,output_transfer,
    unproven_completion,invalid_input,input_backpressure,input_timeout,output_timeout,
    output_starved,peer,output_mismatch,clock,release};
struct StreamInput {
    unsigned packet_count=0;
    std::array<PacketResult64,64> packets{};
    // Native IN storage uses fixed 126-byte packet strides. Only successful
    // actual slices are compacted into AudioBlock; padding never becomes PCM.
    // This is a terminal snapshot, never storage for an outstanding native I/O.
    std::array<std::uint8_t,8064> pcm{};
};
class ContinuousBackend {
public:
    virtual ~ContinuousBackend()=default;
    // Slots 0..3 are IN, 4..7 OUT. Prepare all before submission. False means
    // no resource/lease was acquired. All methods execute on one worker owner.
    virtual bool prepare(unsigned slot,unsigned intervals) noexcept=0;
    // False means nothing accepted. True retains its native memory/OVERLAPPED
    // lease until poll confirms terminal success/failure. Never rearm pending I/O.
    virtual bool submit_input(unsigned slot,bool continue_stream) noexcept=0;
    // Output must be copied to backend-owned stable storage before return; the
    // caller reuses its AudioBlock immediately after an accepted submission.
    virtual bool submit_output(unsigned slot,const AudioBlock&,bool continue_stream) noexcept=0;
    // Nonblocking. Input data is written only on terminal IN success. A failed
    // observation is 'unproven', NOT evidence that a native request completed.
    // Input may be null while draining, when the completed bytes are discarded.
    // OUT success also requires successful aggregate/per-packet statuses. Do
    // not treat Windows OUT ActualLength fields as accepted-byte counts.
    virtual StreamPoll poll(unsigned slot,StreamInput* input) noexcept=0;
    virtual bool cancel(unsigned slot) noexcept=0;
    virtual bool release(unsigned slot) noexcept=0;
    virtual std::uint64_t now_ns() const noexcept=0;
};
class ContinuousPeer {
public:
    virtual ~ContinuousPeer()=default;
    // Successful publication copies/acquires its own bytes before returning.
    virtual StreamExchange publish_input(const AudioBlock&) noexcept=0;
    virtual StreamExchange receive_output(AudioBlock&) noexcept=0;
};
struct StreamConfig {unsigned rate_hz=44100,intervals=8,stall_ms=20,drain_ms=2000;};
struct StreamStats {
    std::uint64_t input_submissions=0,output_submissions=0,input_blocks=0,input_frames=0;
    std::uint64_t output_frames_submitted=0,output_completions=0;
    unsigned pending_mask=0,retained_mask=0,expected_outputs=0;
};
struct StartupDiscard {unsigned empty_packet=0,discarded_frames=0;};
struct InvalidInput {
    static constexpr unsigned no_packet=64;
    std::uint64_t first_frame=0;
    unsigned expected_packets=0,received_packets=0,packet_index=no_packet;
    PacketResult64 packet{};
};
// One non-reentrant worker owner; virtual methods must not call back into it.
// Construction/operation use fixed storage. Step only polls nonblocking APIs;
// actual native call duration still needs an independent process watchdog. This
// owns neither a thread nor a native backend. Referents must outlive it. Call
// stop then step until stopped/retained before freeing any native resources.
// 'retained' REQUIRES isolated-process containment, never ordinary unwinding.
class ContinuousStream final {
public:
    ContinuousStream(ContinuousBackend&,ContinuousPeer&,bool allow_startup_empty_packet=false) noexcept;
    ContinuousStream(const ContinuousStream&)=delete;
    ContinuousStream& operator=(const ContinuousStream&)=delete;
    // False can still leave state==draining after partial native submission.
    // Inspect/step to stopped or retained; false is NOT cleanup proof.
    bool start(StreamConfig) noexcept;
    StreamState step() noexcept;
    void stop() noexcept;
    StreamState state() const noexcept {return state_;}
    StreamFault fault() const noexcept {return fault_;}
    StreamStats stats() const noexcept;
    StartupDiscard startup_discard() const noexcept {return startup_discard_;}
    const InvalidInput* invalid_input() const noexcept {
        return fault_==StreamFault::invalid_input?&invalid_input_:nullptr;
    }
private:
    struct Slot {bool prepared=false,pending=false,complete=false;std::uint64_t since=0;};
    struct Schedule {
        std::uint64_t first=0,time=0,published=0;
        unsigned count=0,rate=0;
        std::array<std::uint8_t,64> frames{};
    };
    ContinuousBackend& backend_;ContinuousPeer& peer_;
    StreamState state_=StreamState::ready;StreamFault fault_=StreamFault::none;
    StreamConfig config_{};StreamStats stats_{};
    std::array<Slot,8> slots_{};
    std::array<StreamInput,4> input_{};
    std::array<Schedule,16> expected_{};
    AudioBlock held_{},output_{};
    unsigned input_head_=0,output_head_=4,expected_read_=0,expected_write_=0,expected_count_=0;
    bool held_valid_=false,clock_lost_=false;
    bool allow_startup_empty_packet_;
    StartupDiscard startup_discard_{};
    InvalidInput invalid_input_{};
    std::uint64_t last_time_=0,drain_since_=0;
    void fail(StreamFault,std::uint64_t now) noexcept;
    void begin_drain(std::uint64_t now) noexcept;
    StreamState drain(std::uint64_t now) noexcept;
    bool pack(unsigned slot,std::uint64_t now) noexcept;
    bool discard_startup_input(const StreamInput&) noexcept;
    bool matches(const AudioBlock&,const Schedule&) const noexcept;
};
}
