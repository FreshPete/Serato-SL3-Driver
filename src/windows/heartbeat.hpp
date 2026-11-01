#pragma once
#include <windows.h>
#include <atomic>
#include <cstdint>
#include <thread>

namespace sl3::worker {
// Isolated worker only: an expired or unobservable deadline kills this process
// (70), never the audio host. Pulse cannot resurrect an already expired lease.
class Heartbeat final {
public:
    explicit Heartbeat(DWORD budget_ms);
    ~Heartbeat();
    Heartbeat(const Heartbeat&)=delete;
    Heartbeat& operator=(const Heartbeat&)=delete;
    void pulse(DWORD budget_ms) noexcept;
private:
    HANDLE stop_=nullptr;
    std::atomic<std::uint64_t> deadline_{0};
    std::thread thread_;
};
}
