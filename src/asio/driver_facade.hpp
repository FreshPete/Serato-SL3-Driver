#pragma once
#include "asio/driver_session.hpp"
#include <atomic>

namespace sl3::asio {
// Additional theoretical delays beyond the bridge's B-input/B-output frames.
// Includes native transport/device FIFOs for the fixed eight-interval session.
// The provider must establish these for its backend; zero is not an unknown
// sentinel. Production installation must supply measured/reviewed provenance.
struct LatencyProfile {
    unsigned input_extra_frames,output_extra_frames;
    // Zero leaves the test/component contract unrestricted. Production profiles
    // bind both values, so measurements are never extrapolated to other modes.
    unsigned rate_hz=0,buffer_frames=0;
    // Component diagnostics can stream while explicitly reporting unknown latency.
    // Production configuration never selects this mode.
    bool report_latency=true;
};
// Explicit control-scope owner. Retain this object across successive facades to
// keep a retained worker acquired. There is no global cache, timeout or reopen.
// Exactly one facade may borrow it; close is refused while borrowed.
class DriverOwner final {
public:
    explicit DriverOwner(WorkerSpec,std::shared_ptr<const void> configuration_lease={});
    explicit DriverOwner(BrokerAttachment,std::shared_ptr<const void> configuration_lease={});
    explicit DriverOwner(const BrokerActivationSpec&,std::shared_ptr<const void> configuration_lease={});
    std::optional<HostReport> close(DWORD total_timeout_ms=5000) noexcept;
private:
    friend class DriverFacade;
    std::shared_ptr<const void> configuration_lease_;
    std::unique_ptr<DriverSession> session_;
    std::atomic<bool> borrowed_{false},sealed_{false};
    void detach(bool buffers_created) noexcept;
};
// Official ASIO operations, independent of COM identity/configuration. One
// control owner; metadata/position reads may occur inside a buffer callback.
class DriverFacade final {
public:
    DriverFacade(WorkerSpec,LatencyProfile,std::shared_ptr<const void> configuration_lease={});
    DriverFacade(BrokerAttachment,LatencyProfile,std::shared_ptr<const void> configuration_lease={});
    DriverFacade(std::shared_ptr<DriverOwner>,LatencyProfile);
    ~DriverFacade();
    ASIOBool init() noexcept;
    void getErrorMessage(char*) const noexcept;
    ASIOError start() noexcept;
    ASIOError stop() noexcept;
    ASIOError getChannels(long*,long*) const noexcept;
    ASIOError getLatencies(long*,long*) const noexcept;
    ASIOError getBufferSize(long*,long*,long*,long*) const noexcept;
    ASIOError canSampleRate(ASIOSampleRate) const noexcept;
    ASIOError getSampleRate(ASIOSampleRate*) const noexcept;
    ASIOError setSampleRate(ASIOSampleRate) noexcept;
    ASIOError getClockSources(ASIOClockSource*,long*) const noexcept;
    ASIOError setClockSource(long) noexcept;
    ASIOError getSamplePosition(ASIOSamples*,ASIOTimeStamp*) const noexcept;
    ASIOError getChannelInfo(ASIOChannelInfo*) const noexcept;
    ASIOError createBuffers(ASIOBufferInfo*,long,long,ASIOCallbacks*) noexcept;
    ASIOError disposeBuffers() noexcept;
    ASIOError controlPanel() const noexcept;
    ASIOError future(long,void*) const noexcept;
    ASIOError outputReady() const noexcept;
private:
    std::shared_ptr<DriverOwner> owner_;
    DriverSession& session_;
    const LatencyProfile latency_;
    std::atomic<bool> initialized_{false},started_{false};
    std::atomic<unsigned> rate_{0},frames_{0},active_{0};
    std::atomic<const char*> error_{"Device has not been initialized."};
    ASIOError fail(ASIOError,const char*) noexcept;
    static std::shared_ptr<DriverOwner> claim(std::shared_ptr<DriverOwner>,LatencyProfile);
};
}
