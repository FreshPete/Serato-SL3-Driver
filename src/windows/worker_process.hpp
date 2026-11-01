#pragma once
#include <windows.h>
#include <filesystem>
#include <memory>
#include <string>
#include <vector>

namespace sl3::worker {
struct ProcessState {
    bool started=false,job_assigned=false,process_exited=false,exit_code_known=false,job_empty=false;
    // Windows accounting can retain terminated process objects while references
    // remain. This is not an exact count of executing processes.
    DWORD exit_code=0,associated_processes=0;
};
struct StopResult {
    bool termination_requested=false;
    ProcessState state;
};
// Single-owner control-thread component, never an audio callback operation. Owns exactly one
// private child job. No inherited handles, USB access, registration or elevation.
class Process final {
public:
    Process() noexcept;
    ~Process();
    Process(const Process&)=delete;
    Process& operator=(const Process&)=delete;
    static std::string executable_sha256(const std::filesystem::path&);
    // A failure after child creation retains its handle for observation/stop.
    // Never infer "no child" from an exception; inspect observe().started.
    void launch(const std::filesystem::path&,const std::string& expected_sha256,
                const std::vector<std::wstring>& arguments);
    ProcessState observe() const;
    bool wait_for_exit(DWORD timeout_ms) const;
    StopResult terminate_and_wait(DWORD timeout_ms=2000);
    HANDLE process_handle() const noexcept; // Borrowed; only valid while owner lives.
private:
    struct State;
    std::unique_ptr<State> state_;
};
}
