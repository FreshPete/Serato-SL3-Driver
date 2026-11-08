#pragma once
#include "core/audio_block.hpp"
#include <memory>

namespace sl3::worker {
class StreamCaptureObserver {
public:
    virtual ~StreamCaptureObserver()=default;
    virtual void append(const AudioBlock&) noexcept=0;
    virtual void append_input(const AudioBlock&) noexcept=0;
};
// Optional single-shot diagnostic. Environment is read before audio activation.
// append/retire have one stream-owner caller; neither performs filesystem I/O.
class SoftwareOutputCapture final:public StreamCaptureObserver {
public:
    static std::unique_ptr<SoftwareOutputCapture> from_environment(unsigned rate);
    ~SoftwareOutputCapture();
    void append(const AudioBlock&) noexcept override;
    void append_input(const AudioBlock&) noexcept override;
    bool is_armed() const noexcept;
    void retire() noexcept;
private:
    struct State;std::unique_ptr<State> state_;
    explicit SoftwareOutputCapture(std::unique_ptr<State>);
};
}
