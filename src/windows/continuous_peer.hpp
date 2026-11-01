#pragma once
#include "core/continuous.hpp"
#include "windows/mailbox.hpp"

namespace sl3::worker {
// Worker endpoint only; one data owner independent of the control owner.
// Copies use the existing checked queues and never transfer host/native pointers.
class MailboxStreamPeer final:public ContinuousPeer {
public:
    explicit MailboxStreamPeer(Mailbox& channel) noexcept:channel_(channel){}
    StreamExchange publish_input(const AudioBlock& block) noexcept override {
        const auto result=channel_.try_push_audio(AudioDirection::input,block);
        return result==AudioResult::ok?StreamExchange::ok:result==AudioResult::full?StreamExchange::full:StreamExchange::failure;
    }
    StreamExchange receive_output(AudioBlock& block) noexcept override {
        const auto result=channel_.try_pop_audio(AudioDirection::output,block);
        return result==AudioResult::ok?StreamExchange::ok:result==AudioResult::empty?StreamExchange::empty:StreamExchange::failure;
    }
private:Mailbox& channel_;
};
}
