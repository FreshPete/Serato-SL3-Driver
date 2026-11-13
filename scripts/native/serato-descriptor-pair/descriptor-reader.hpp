#pragma once
#include <cstddef>
#include <cstdint>

using MakeNativeString = void* (*)(void*, const char*);

struct DescriptorReadScope {
    const void* callers[2];
    const char* xml;
    MakeNativeString make;
    std::uint32_t thread;
    std::uint32_t hits;
    std::uint32_t pathOffset;
    std::uint32_t identifierBytes;
};

static_assert(sizeof(DescriptorReadScope) == 48 && offsetof(DescriptorReadScope, thread) == 32 &&
    offsetof(DescriptorReadScope, hits) == 36 && offsetof(DescriptorReadScope, pathOffset) == 40);

#ifdef SL3_DESCRIPTOR_READER_EXPORT
#define SL3_DESCRIPTOR_READER_API __declspec(dllexport)
#else
#define SL3_DESCRIPTOR_READER_API __declspec(dllimport)
#endif

extern "C" SL3_DESCRIPTOR_READER_API void* Sl3SupplyScopedDescriptorText(
    void*, const unsigned char*, const void*, std::uint32_t, DescriptorReadScope*);
