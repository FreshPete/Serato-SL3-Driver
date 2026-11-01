#pragma once
#include <windows.h>
#include <array>
#include <cstddef>
#include <cstdint>

namespace sl3::worker::wire {
constexpr std::uint32_t magic=0x4d334c53,version=3;
constexpr std::size_t capacity=32768;
enum Phase:LONG {idle=0,request=1,processing=2,reply=3,reading=4,closed=5,writing=6};
constexpr std::uint32_t audio_slots=8;
struct alignas(64) AudioSlot {
    std::uint64_t first_frame,host_observation_ns;
    std::uint32_t reported_rate_hz,pcm_bytes,packet_count,reserved[9];
    std::array<std::uint8_t,64> frames_per_packet;
    std::array<std::uint8_t,8064> pcm;
};
struct alignas(64) AudioQueue {
    volatile LONG read,write;
    std::uint32_t reserved[14];
    std::array<AudioSlot,audio_slots> slots;
};
struct alignas(64) Shared {
    std::uint32_t magic_value,version_value,structure_bytes;
    volatile LONG phase;
    std::uint32_t request_sequence,opcode,request_bytes,reply_sequence,reply_bytes,status;
    volatile LONG peer_pid;
    volatile LONG audio_fault,audio_rate;
    std::uint32_t reserved[3];
    std::array<std::uint8_t,capacity> request_data,reply_data;
    AudioQueue input,output;
};
static_assert(sizeof(AudioSlot)==8192 && offsetof(AudioSlot,packet_count)==24 && offsetof(AudioSlot,pcm)==128 && offsetof(AudioQueue,slots)==64,"Audio ring v3 ABI");
static_assert(sizeof(LONG)==4 && offsetof(Shared,request_data)==64 && sizeof(Shared)==196800,"Mailbox v3 wire ABI");
}
