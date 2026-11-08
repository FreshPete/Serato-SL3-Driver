#pragma once
#include "core/continuous.hpp"
#include "windows/mailbox.hpp"
#include "windows/output_capture.hpp"

namespace sl3::worker {
// Worker endpoint only; one data owner independent of the control owner.
// Copies use the existing checked queues and never transfer host/native pointers.
class MailboxStreamPeer final:public ContinuousPeer {
public:
    explicit MailboxStreamPeer(Mailbox& channel,StreamCaptureObserver* capture=nullptr) noexcept:channel_(channel),capture_(capture){}
    StreamExchange publish_input(const AudioBlock& block) noexcept override {
        const auto result=channel_.try_push_audio(AudioDirection::input,block);
        if(result==AudioResult::ok && capture_)capture_->append_input(block);
        return result==AudioResult::ok?StreamExchange::ok:result==AudioResult::full?StreamExchange::full:StreamExchange::failure;
    }
    StreamExchange receive_output(AudioBlock& block) noexcept override {
        const auto result=channel_.try_pop_audio(AudioDirection::output,block);
        if(result==AudioResult::ok && capture_)capture_->append(block);
        return result==AudioResult::ok?StreamExchange::ok:result==AudioResult::empty?StreamExchange::empty:StreamExchange::failure;
    }
private:Mailbox& channel_;StreamCaptureObserver* capture_;
};
}
