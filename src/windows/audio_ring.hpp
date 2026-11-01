#pragma once
#include "core/audio_block.hpp"

namespace sl3::worker {
enum class AudioDirection {input,output};
enum class AudioResult:long {
    ok=0,empty,full,closed,wrong_role,invalid_packet,discontinuity,
    clock_regression,rate_changed,protocol_error,faulted,timeout,invalid_argument
};
using AudioBlock=sl3::AudioBlock;
}
