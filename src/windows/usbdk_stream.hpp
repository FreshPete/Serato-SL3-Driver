#pragma once
#include <windows.h>
#include <cfgmgr32.h>
#include <usb.h>
#include "UsbDkHelper.h"
#include "core/continuous.hpp"

namespace sl3::worker {
struct UsbDkStreamApi {
    decltype(&UsbDk_ReadPipe) read=nullptr;
    decltype(&UsbDk_WritePipe) write=nullptr;
};
// Defaults are the real Windows APIs. Tests replace only the explicit boundary,
// without loading a helper, opening a device or submitting actual USB requests.
struct OverlappedApi {
    decltype(&CreateEventW) create_event=&CreateEventW;
    decltype(&ResetEvent) reset_event=&ResetEvent;
    decltype(&CloseHandle) close_handle=&CloseHandle;
    decltype(&WaitForSingleObject) wait=&WaitForSingleObject;
    decltype(&GetOverlappedResult) result=&GetOverlappedResult;
    decltype(&CancelIoEx) cancel=&CancelIoEx;
    decltype(&QueryPerformanceCounter) counter=&QueryPerformanceCounter;
    decltype(&QueryPerformanceFrequency) frequency=&QueryPerformanceFrequency;
};
// ISOLATED WORKER ONLY: destruction with any unproved I/O/release terminates
// this process (70). Never instantiate inside an ASIO/audio-host process.
// Caller pins/loads the reviewed helper, verifies the exact device, redirects,
// reads its rate and activates audio alts first. These borrowed handles/module
// must outlive this backend. It never installs, resets, redirects or programs.
class UsbDkStreamBackend final:public ContinuousBackend {
public:
    UsbDkStreamBackend(UsbDkStreamApi,HANDLE redirect,HANDLE system,OverlappedApi={}) noexcept;
    ~UsbDkStreamBackend();
    UsbDkStreamBackend(const UsbDkStreamBackend&)=delete;
    UsbDkStreamBackend& operator=(const UsbDkStreamBackend&)=delete;
    bool prepare(unsigned slot,unsigned intervals) noexcept override;
    bool submit_input(unsigned slot,bool continue_stream) noexcept override;
    bool submit_output(unsigned slot,const AudioBlock&,bool continue_stream) noexcept override;
    StreamPoll poll(unsigned slot,StreamInput*) noexcept override;
    bool cancel(unsigned slot) noexcept override;
    bool release(unsigned slot) noexcept override;
    std::uint64_t now_ns() const noexcept override;
    bool valid() const noexcept {return valid_;}
    DWORD last_error() const noexcept {return last_error_;}
    // Borrowed events, never close them. Synchronous/uncertain leases must be
    // polled immediately rather than waiting on an event that may not signal.
    bool immediate_poll() const noexcept;
    HANDLE pending_event(unsigned slot) const noexcept;
private:
    enum class Lease {idle,synchronous,pending,uncertain};
    struct Slot {
        std::array<std::uint8_t,8064> pcm{};
        std::array<ULONG64,64> lengths{};
        std::array<USB_DK_ISO_TRANSFER_RESULT,64> results{};
        USB_DK_TRANSFER_REQUEST request{};
        OVERLAPPED overlapped{};
        Lease lease=Lease::idle;
        unsigned intervals=0;
        bool prepared=false,release_failed=false;
    };
    UsbDkStreamApi usb_;OverlappedApi win_;
    HANDLE redirect_,system_;
    std::array<Slot,8> slots_{};
    std::uint64_t frequency_=0;
    bool valid_=false;
    DWORD last_error_=ERROR_SUCCESS;
    bool reject(DWORD error) noexcept;
    bool submit(unsigned slot,bool output) noexcept;
};
}
