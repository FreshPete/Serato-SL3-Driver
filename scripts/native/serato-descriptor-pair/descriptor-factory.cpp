#include "descriptor-factory.hpp"
#include <Windows.h>
#include <cstring>

namespace {
constexpr char resource[] = "resource:userio/audio/audio_rane_sl3_rebuild.xml";

template<std::size_t Bytes>
struct NativeStorage {
    alignas(16) unsigned char bytes[Bytes]{};
    void (*destroy)(void*);
    bool owned = false;
    ~NativeStorage() { if (owned) destroy(bytes); }
};

struct NativeVector {
    DescriptorVector value{};
    const DescriptorFactoryRecipe& recipe;
    bool elementsOwned = true;

    bool bounds(std::size_t& used, std::size_t& reserved) const noexcept {
        const auto begin = reinterpret_cast<std::uintptr_t>(value.begin);
        const auto end = reinterpret_cast<std::uintptr_t>(value.end);
        const auto capacity = reinterpret_cast<std::uintptr_t>(value.capacity);
        if (!begin) return !end && !capacity;
        if (end < begin || capacity < end) return false;
        used = end - begin;
        reserved = capacity - begin;
        return reserved >= sizeof(DescriptorPair) && reserved < 4096 &&
            used % sizeof(DescriptorPair) == 0 && reserved % sizeof(DescriptorPair) == 0;
    }

    bool exactlyOne() const noexcept {
        std::size_t used = 0, reserved = 0;
        return bounds(used, reserved) && used == sizeof(DescriptorPair);
    }

    bool release() {
        std::size_t used = 0, reserved = 0;
        if (!bounds(used, reserved)) return false;
        if (!value.begin) return true;
        if (elementsOwned) recipe.releasePairs(value.begin, value.end, &value);
        recipe.freeAllocation(value.begin, reserved);
        value = {};
        return true;
    }

    ~NativeVector() { release(); }
};

template<class Consume>
int runScratchFactory(const DescriptorFactoryRecipe* recipe, Consume consume) {
    if (!recipe || !recipe->singleton || !recipe->makeString || !recipe->destroyString ||
        !recipe->makeIdentifier || !recipe->destroyIdentifier || !recipe->copyPair || !recipe->build ||
        !recipe->releasePairs || !recipe->freeAllocation || !recipe->context ||
        (recipe->context->entry == nullptr) != (recipe->context->owner == nullptr)) return -1;

    NativeStorage<32> text{{}, recipe->destroyString};
    NativeStorage<232> identifier{{}, recipe->destroyIdentifier};
    NativeVector context{{}, *recipe};
    NativeVector result{{}, *recipe};
    DescriptorOptions options{{}, 0x101};

    recipe->makeString(text.bytes, resource);
    text.owned = true;
    recipe->makeIdentifier(identifier.bytes, text.bytes);
    identifier.owned = true;
    if (recipe->context->owner) {
        recipe->copyPair(&context.value, nullptr, recipe->context);
        if (!context.exactlyOne() || context.value.begin->entry != recipe->context->entry ||
            context.value.begin->owner != recipe->context->owner) return -2;
        options.context = *context.value.begin;
    }

    // The factory takes ownership of the identifier and the copied reference.
    identifier.owned = false;
    context.elementsOwned = false;
    const auto* built = recipe->build(recipe->singleton, &result.value, identifier.bytes, &options);
    if (built != &result.value || !result.exactlyOne()) return -3;
    const auto accepted = consume(&result.value);
    const auto resultReleased = result.release();
    const auto contextReleased = context.release();
    if (!resultReleased || !contextReleased) return -4;
    return accepted == 1 ? 1 : 0;
}

template<class T>
bool read(const void* address, std::size_t offset, T& value) noexcept {
    if (!address || reinterpret_cast<std::uintptr_t>(address) > UINTPTR_MAX - offset) return false;
    const auto source = reinterpret_cast<const void*>(reinterpret_cast<std::uintptr_t>(address) + offset);
    return ReadProcessMemory(GetCurrentProcess(), source, &value, sizeof(value), nullptr) != FALSE;
}

struct UsbIdentity {
    std::uint16_t vid, pid, revision;

    bool isSl3() const noexcept { return vid == 0x1cc5 && pid == 1 && revision == 0; }
};

struct AsioName {
    char storage[16];
    std::size_t length, capacity;
};

static_assert(sizeof(UsbIdentity) == 6 && sizeof(AsioName) == 32);

// Windows x64 MSVC shared-owner layout for the reviewed factory ABI.
constexpr std::size_t strongReferenceOffset = 8;
constexpr char rebuiltAsioName[] = "SL3 Rebuild Development";

bool hasRebuiltName(const void* entry, std::size_t nameOffset, bool& rebuilt) noexcept {
    AsioName name{};
    if (!read(entry, nameOffset, name) || name.capacity < 15 || name.length > name.capacity ||
        name.length > 4096) return false;
    rebuilt = false;
    if (name.length != sizeof(rebuiltAsioName) - 1) return true;
    const char* data = nullptr;
    std::memcpy(&data, name.storage, sizeof(data));
    char text[sizeof(rebuiltAsioName) - 1]{};
    if (!read(data, 0, text)) return false;
    rebuilt = std::memcmp(text, rebuiltAsioName, sizeof(text)) == 0;
    return true;
}

bool hasOwnedDescriptor(const DescriptorPair& pair, const DescriptorPublication& publication, bool rebuilt) noexcept {
    const void* descriptorVtable = nullptr;
    const void* ownerVtable = nullptr;
    int strong = 0;
    bool rebuiltName = false;
    return read(pair.entry, 0, descriptorVtable) && descriptorVtable == publication.descriptorVtable &&
        read(pair.owner, 0, ownerVtable) && ownerVtable == publication.ownerVtable &&
        read(pair.owner, strongReferenceOffset, strong) && strong == 1 &&
        hasRebuiltName(pair.entry, publication.asioNameOffset, rebuiltName) && rebuiltName == rebuilt;
}

bool validDescriptorOffsets(std::uint32_t identity, std::uint32_t name) noexcept {
    return identity >= sizeof(void*) && identity % alignof(UsbIdentity) == 0 && name <= 4096 &&
        name % alignof(AsioName) == 0 && identity <= name && name - identity >= sizeof(UsbIdentity);
}

DescriptorPair* findSl3(const DescriptorVector* source, std::uint32_t identityOffset, DescriptorPair& match) noexcept {
    DescriptorVector registry{};
    if (!read(source, 0, registry)) return nullptr;
    const auto begin = reinterpret_cast<std::uintptr_t>(registry.begin);
    const auto end = reinterpret_cast<std::uintptr_t>(registry.end);
    const auto capacity = reinterpret_cast<std::uintptr_t>(registry.capacity);
    if (!begin || end < begin || capacity < end || capacity - begin > 2048 * sizeof(DescriptorPair) ||
        (end - begin) % sizeof(DescriptorPair) || (capacity - begin) % sizeof(DescriptorPair)) return nullptr;

    DescriptorPair* found = nullptr;
    for (auto address = begin; address < end; address += sizeof(DescriptorPair)) {
        auto* slot = reinterpret_cast<DescriptorPair*>(address);
        DescriptorPair pair{};
        UsbIdentity identity{};
        if (!read(slot, 0, pair)) return nullptr;
        if (!pair.entry) continue;
        if (!read(pair.entry, identityOffset, identity)) return nullptr;
        if (!identity.isSl3()) continue;
        if (found || !pair.owner) return nullptr;
        found = slot;
        match = pair;
    }
    return found;
}

int publishScratch(DescriptorVector* result, const DescriptorPublication& publication, DescriptorPair* published = nullptr) noexcept {
    const DescriptorPair candidate = *result->begin;
    std::uint32_t readerHits = 0;
    UsbIdentity identity{};
    if (!read(publication.readerHits, 0, readerHits) || readerHits != 2 ||
        !read(candidate.entry, publication.usbIdentityOffset, identity) || !identity.isSl3() ||
        !hasOwnedDescriptor(candidate, publication, true)) return 0;

    DescriptorPair current{};
    if (findSl3(publication.registry, publication.usbIdentityOffset, current) != publication.slot ||
        current.entry != publication.expected.entry || current.owner != publication.expected.owner ||
        !hasOwnedDescriptor(current, publication, false)) return 0;

    alignas(16) const auto expected = publication.expected;
    const auto exchanged = publication.exchange(reinterpret_cast<std::int64_t*>(publication.slot),
        reinterpret_cast<std::int64_t*>(result->begin), reinterpret_cast<const std::int64_t*>(&expected));
    if (exchanged == 1 && published) *published = candidate;
    return exchanged;
}

int publishPrimary(void* manager, const DescriptorFactoryRecipe* factory, const PrimaryDescriptorRecipe* layout,
    PrimaryGetterState* state) {
    if (!manager || !factory || !layout || !layout->managerVtable || !layout->descriptorVtable || !layout->exchange ||
        !layout->readerHits || !validDescriptorOffsets(layout->usbIdentityOffset, layout->asioNameOffset) ||
        layout->vectorOffset < sizeof(void*) || layout->vectorOffset > 4096 || layout->vectorOffset % alignof(DescriptorVector) ||
        layout->contextOffset < sizeof(void*) || layout->contextOffset > 4096 || layout->contextOffset % alignof(DescriptorPair)) return -1;
    const auto managerAddress = reinterpret_cast<std::uintptr_t>(manager);
    if (managerAddress > UINTPTR_MAX - layout->vectorOffset) return -1;

    const void* installedManager = nullptr;
    const void* managerVtable = nullptr;
    void* singleton = nullptr;
    DescriptorPair context{};
    int contextRefs = 0;
    if (!read(layout->managerGlobal, 0, installedManager) || installedManager != manager ||
        !read(manager, 0, managerVtable) || managerVtable != layout->managerVtable ||
        !read(layout->singletonGlobal, 0, singleton) || !singleton ||
        !read(manager, layout->contextOffset, context) || (context.entry == nullptr) != (context.owner == nullptr) ||
        (context.owner && (!read(context.owner, strongReferenceOffset, contextRefs) || contextRefs < 1 || contextRefs > 2048))) return 0;

    const auto* registry = reinterpret_cast<const DescriptorVector*>(managerAddress + layout->vectorOffset);
    DescriptorPair original{};
    auto* slot = findSl3(registry, layout->usbIdentityOffset, original);
    const void* ownerVtable = nullptr;
    if (!slot || !read(original.owner, 0, ownerVtable) || !ownerVtable) return 0;
    const DescriptorPublication publication{registry, slot, original, layout->descriptorVtable, ownerVtable,
        layout->exchange, layout->readerHits, layout->usbIdentityOffset, layout->asioNameOffset};
    if (!hasOwnedDescriptor(original, publication, false)) return 0;

    auto recipe = *factory;
    recipe.singleton = singleton;
    recipe.context = &context;
    return runScratchFactory(&recipe, [&](DescriptorVector* result) {
        int currentRefs = 0;
        DescriptorPair current{};
        if (!read(layout->managerGlobal, 0, installedManager) || installedManager != manager ||
            !read(manager, layout->contextOffset, current) || current.entry != context.entry || current.owner != context.owner ||
            (context.owner && (!read(context.owner, strongReferenceOffset, currentRefs) || currentRefs != contextRefs))) return 0;
        if (state) state->hadOptionsOwner = context.owner != nullptr;
        return publishScratch(result, publication, state ? &state->published : nullptr);
    });
}
}

extern "C" int Sl3RunScratchFactory(const DescriptorFactoryRecipe* recipe, ConsumeDescriptor consume) {
    return consume ? runScratchFactory(recipe, consume) : -1;
}

extern "C" int Sl3RunAndPublishScratchFactory(const DescriptorFactoryRecipe* recipe, const DescriptorPublication* publication) {
    if (!publication || !publication->registry || !publication->slot || !publication->descriptorVtable ||
        !publication->ownerVtable || !publication->exchange || !publication->readerHits) return -1;
    if (!validDescriptorOffsets(publication->usbIdentityOffset, publication->asioNameOffset)) return -1;
    return runScratchFactory(recipe, [publication](DescriptorVector* result) { return publishScratch(result, *publication); });
}

extern "C" int Sl3PublishPrimaryDescriptor(void* manager, const DescriptorFactoryRecipe* factory,
    const PrimaryDescriptorRecipe* layout) {
    return publishPrimary(manager, factory, layout, nullptr);
}

extern "C" void Sl3DispatchPrimaryGetter(void* manager, const DescriptorFactoryRecipe* factory,
    const PrimaryDescriptorRecipe* layout, PrimaryGetterState* state) {
    if (!state || !state->readerThread || InterlockedCompareExchange(&state->phase, 1, 0) != 0) return;
    if (InterlockedCompareExchange(state->readerThread, static_cast<long>(GetCurrentThreadId()), 0) != 0) {
        state->result = -5;
    } else {
        try {
            state->result = publishPrimary(manager, factory, layout, state);
        } catch (...) {
            state->result = -6;
        }
        InterlockedExchange(state->readerThread, 0);
    }
    InterlockedExchange(&state->phase, 2);
}
