#pragma once
#include <windows.h>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>
#include "windows/audio_ring.hpp"

namespace sl3::worker {
enum class MessageResult {ok,timeout,peer_exited,closed,protocol_error};
struct Message {
    std::uint32_t sequence=0,opcode=0,status=0;
    std::vector<std::uint8_t> bytes;
};
// Control methods have one owner and may allocate/wait. The separate fixed data
// queues have one producer/consumer per direction. Neither establishes an audio
// session, callback lifetime or real-time deadline. Retire callers before free.
class Mailbox final {
public:
    static std::unique_ptr<Mailbox> create();
    static std::unique_ptr<Mailbox> open(const std::wstring& name);
    ~Mailbox();
    Mailbox(const Mailbox&)=delete;
    Mailbox& operator=(const Mailbox&)=delete;
    const std::wstring& name() const noexcept;
    // Borrowed local wait handles only. Caller must never close them; they do
    // not transfer across IPC or extend Mailbox lifetime. Empty wakes are valid.
    HANDLE request_event() const noexcept;
    HANDLE input_event() const noexcept;
    HANDLE output_event() const noexcept;
    HANDLE mapping_handle() const noexcept; // Borrowed; do not close.
    // Bind a supplied name to a mapping reference held by this exact process.
    // Does not claim the worker peer or certify creator identity/I/O readiness.
    // Keep the returned reference through worker admission to prevent replacement.
    static std::shared_ptr<const void> hold_audio_reference(HANDLE process,HANDLE remote_mapping,const std::wstring& name);
    bool send(std::uint32_t opcode,const std::uint8_t*,std::size_t);
    MessageResult await_reply(HANDLE expected_peer,DWORD timeout_ms,Message&);
    MessageResult receive(DWORD timeout_ms,Message&);
    bool respond(std::uint32_t status,const std::uint8_t*,std::size_t);
    // After construction: one producer/consumer per direction, independent of
    // the single control owner. Caller must retire all threads before disposal.
    AudioResult try_push_audio(AudioDirection,const AudioBlock&) noexcept;
    AudioResult try_pop_audio(AudioDirection,AudioBlock&) noexcept;
    AudioResult wait_pop_audio(AudioDirection,DWORD timeout_ms,AudioBlock&) noexcept;
    AudioResult audio_fault() const noexcept;
    // Control-thread admission check for a newly claimed per-stream channel.
    // Never resets queues; callers must still obey one producer/consumer.
    bool audio_pristine() const noexcept;
    void close() noexcept;
private:
    struct State;
    explicit Mailbox(std::unique_ptr<State>) noexcept;
    std::unique_ptr<State> state_;
};
}
