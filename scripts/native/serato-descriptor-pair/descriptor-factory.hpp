#pragma once
#include <cstddef>
#include <cstdint>

struct DescriptorPair {
    void* entry;
    void* owner;
};

struct DescriptorVector {
    DescriptorPair* begin;
    DescriptorPair* end;
    DescriptorPair* capacity;
};

struct DescriptorOptions {
    DescriptorPair context;
    std::uint16_t flags;
};

struct DescriptorFactoryRecipe {
    void* singleton;
    void* (*makeString)(void*, const char*);
    void (*destroyString)(void*);
    void* (*makeIdentifier)(void*, const void*);
    void (*destroyIdentifier)(void*);
    void* (*copyPair)(DescriptorVector*, DescriptorPair*, const DescriptorPair*);
    DescriptorVector* (*build)(void*, DescriptorVector*, void*, DescriptorOptions*);
    void (*releasePairs)(DescriptorPair*, DescriptorPair*, DescriptorVector*);
    void (*freeAllocation)(void*, std::size_t);
    const DescriptorPair* context;
};

static_assert(sizeof(DescriptorPair) == 16 && sizeof(DescriptorVector) == 24);
static_assert(sizeof(DescriptorOptions) == 24 && offsetof(DescriptorOptions, flags) == 16);
static_assert(sizeof(DescriptorFactoryRecipe) == 80);

using ExchangeDescriptorPair = int (*)(std::int64_t*, std::int64_t*, const std::int64_t*) noexcept;

struct DescriptorPublication {
    const DescriptorVector* registry;
    DescriptorPair* slot;
    DescriptorPair expected;
    const void* descriptorVtable;
    const void* ownerVtable;
    ExchangeDescriptorPair exchange;
    const std::uint32_t* readerHits;
    std::uint32_t usbIdentityOffset;
    std::uint32_t asioNameOffset;
};

static_assert(sizeof(DescriptorPublication) == 72 && offsetof(DescriptorPublication, readerHits) == 56 &&
    offsetof(DescriptorPublication, usbIdentityOffset) == 64);

struct PrimaryDescriptorRecipe {
    const void* managerGlobal;
    const void* managerVtable;
    const void* singletonGlobal;
    const void* descriptorVtable;
    ExchangeDescriptorPair exchange;
    const std::uint32_t* readerHits;
    std::uint32_t vectorOffset;
    std::uint32_t contextOffset;
    std::uint32_t usbIdentityOffset;
    std::uint32_t asioNameOffset;
};

static_assert(sizeof(PrimaryDescriptorRecipe) == 64 && offsetof(PrimaryDescriptorRecipe, vectorOffset) == 48);

struct PrimaryGetterState {
    volatile long phase;
    int result;
    volatile long* readerThread;
    DescriptorPair published;
    std::uint32_t hadOptionsOwner;
};

static_assert(sizeof(PrimaryGetterState) == 40 && offsetof(PrimaryGetterState, published) == 16);

#ifdef SL3_DESCRIPTOR_FACTORY_EXPORT
#define SL3_DESCRIPTOR_FACTORY_API __declspec(dllexport)
#else
#define SL3_DESCRIPTOR_FACTORY_API __declspec(dllimport)
#endif

using ConsumeDescriptor = int (*)(DescriptorVector*);
extern "C" SL3_DESCRIPTOR_FACTORY_API int Sl3RunScratchFactory(const DescriptorFactoryRecipe*, ConsumeDescriptor);
extern "C" SL3_DESCRIPTOR_FACTORY_API int Sl3RunAndPublishScratchFactory(
    const DescriptorFactoryRecipe*, const DescriptorPublication*);
extern "C" SL3_DESCRIPTOR_FACTORY_API int Sl3PublishPrimaryDescriptor(
    void*, const DescriptorFactoryRecipe*, const PrimaryDescriptorRecipe*);
extern "C" SL3_DESCRIPTOR_FACTORY_API void Sl3DispatchPrimaryGetter(
    void*, const DescriptorFactoryRecipe*, const PrimaryDescriptorRecipe*, PrimaryGetterState*);
