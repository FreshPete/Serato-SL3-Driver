#pragma once
#include <windows.h>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>

namespace sl3::diagnostic {
class Win32Failure final : public std::runtime_error {
    DWORD code_;
public:
    Win32Failure(const char* operation, DWORD code)
        : std::runtime_error(std::string(operation) + " failed, Win32=" + std::to_string(code)), code_(code) {}
    DWORD code() const noexcept { return code_; }
};
[[noreturn]] inline void failed(const char* operation) {
    throw Win32Failure(operation, GetLastError());
}
inline std::string quote(const std::string& value) {
    std::string out = "\"";
    for (const unsigned char c : value) {
        if (c == '\\' || c == '"') { out += '\\'; out += char(c); }
        else if (c == '\n') out += "\\n";
        else if (c == '\r') out += "\\r";
        else if (c < 32) out += '?';
        else out += char(c);
    }
    return out + '"';
}
inline std::string utc_now() {
    SYSTEMTIME value{};GetSystemTime(&value);
    std::ostringstream text;text<<std::setfill('0')<<std::setw(4)<<value.wYear<<'-'<<std::setw(2)<<value.wMonth<<'-'<<std::setw(2)<<value.wDay
        <<'T'<<std::setw(2)<<value.wHour<<':'<<std::setw(2)<<value.wMinute<<':'<<std::setw(2)<<value.wSecond<<'.'<<std::setw(3)<<value.wMilliseconds<<'Z';
    return text.str();
}
[[noreturn]] inline void fail_stop() noexcept {
    // No stream locks or logging waits on this watchdog path. The parent
    // records exit 70 and retains the last flushed progress record.
    TerminateProcess(GetCurrentProcess(), 70);
    std::_Exit(70);
}
struct Watchdog {
    std::mutex mutex;
    std::condition_variable signal;
    bool finished=false;
    std::thread worker{[this] {
        std::unique_lock<std::mutex> lock(mutex);
        if (!signal.wait_for(lock,std::chrono::seconds(20),[this]{return finished;})) fail_stop();
    }};
    ~Watchdog() {
        { std::lock_guard<std::mutex> lock(mutex);finished=true; }
        signal.notify_one();worker.join();
    }
};
}
