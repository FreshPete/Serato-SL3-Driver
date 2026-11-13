#include "descriptor-factory.hpp"
#include <cstdio>
#include <cstring>
#include <utility>

namespace {
struct State {
    int strings = 0;
    int identifiers = 0;
    int contextRefs = 1;
    int resultRefs = 0;
    int allocations = 0;
    int buildCalls = 0;
    int consumeCalls = 0;
    bool wrongCopy = false;
    bool emptyResult = false;
    bool reject = false;
    bool replace = false;
    int retiredRefs = 1;
} state;
DescriptorPair published{};

void* makeString(void* out, const char* text) {
    if (std::strcmp(text, "resource:userio/audio/audio_rane_sl3_rebuild.xml") != 0) return nullptr;
    ++state.strings;
    *static_cast<char*>(out) = 's';
    return out;
}

void destroyString(void*) { --state.strings; }

void* makeIdentifier(void* out, const void* text) {
    if (*static_cast<const char*>(text) != 's') return nullptr;
    ++state.identifiers;
    *static_cast<char*>(out) = 'i';
    return out;
}

void destroyIdentifier(void*) { --state.identifiers; }

void* copyPair(DescriptorVector* out, DescriptorPair*, const DescriptorPair* context) {
    auto* pair = new DescriptorPair{state.wrongCopy ? nullptr : context->entry, context->owner};
    ++state.allocations;
    ++*static_cast<int*>(pair->owner);
    *out = {pair, pair + 1, pair + 1};
    return pair;
}

DescriptorVector* build(void* singleton, DescriptorVector* out, void* id, DescriptorOptions* options) {
    ++state.buildCalls;
    if (options->context.owner) --*static_cast<int*>(options->context.owner);
    destroyIdentifier(id);
    if (singleton != &state || *static_cast<char*>(id) != 'i' || options->flags != 0x101 || state.emptyResult) return out;
    auto* pair = new DescriptorPair{&state, &state.resultRefs};
    ++state.allocations;
    ++state.resultRefs;
    *out = {pair, pair + 1, pair + 1};
    return out;
}

void releasePairs(DescriptorPair* begin, DescriptorPair* end, DescriptorVector*) {
    for (auto* pair = begin; pair != end; ++pair) --*static_cast<int*>(pair->owner);
}

void freeAllocation(void* begin, std::size_t) {
    --state.allocations;
    delete static_cast<DescriptorPair*>(begin);
}

int consume(DescriptorVector* result) {
    ++state.consumeCalls;
    if (state.reject || result->begin->entry != &state || state.resultRefs != 1) return 0;
    if (state.replace) std::swap(*result->begin, published);
    return 1;
}

bool clean() {
    return state.strings == 0 && state.identifiers == 0 && state.allocations == 0 &&
           state.contextRefs == 1 && state.resultRefs == 0;
}

struct TestOwner {
    const void* vtable;
    int strong;
};

struct TestDescriptor {
    const void* vtable;
    char beforeIdentity[192]{};
    std::uint16_t identity[3]{0x1cc5, 1, 0};
    char beforeName[818]{};
    const char* name;
    char stringPadding[8]{};
    std::size_t length, capacity;
};

static_assert(offsetof(TestDescriptor, identity) == 200 && offsetof(TestDescriptor, name) == 1024);
static_assert(offsetof(TestOwner, strong) == 8);

constexpr char rebuiltName[] = "SL3 Rebuild Development";
const int descriptorVtable = 0, ownerVtable = 0;
TestDescriptor rebuilt{&descriptorVtable, {}, {0x1cc5, 1, 0}, {}, rebuiltName, {},
                       sizeof(rebuiltName) - 1, sizeof(rebuiltName) - 1};
TestOwner rebuiltOwner{&ownerVtable, 0};
bool exchangeRefused = false;
int exchangeCalls = 0;
bool retainContext = false;
volatile long* getterReaderThread = nullptr;
long readerThreadDuringBuild = 0;

void* copyPublication(DescriptorVector* result, DescriptorPair*, const DescriptorPair* source) {
    auto* pair = new DescriptorPair{*source};
    ++static_cast<TestOwner*>(pair->owner)->strong;
    *result = {pair, pair + 1, pair + 1};
    ++state.allocations;
    return pair;
}

DescriptorVector* buildPublication(void*, DescriptorVector* result, void* identifier, DescriptorOptions* options) {
    destroyIdentifier(identifier);
    if (options->context.owner && !retainContext) --static_cast<TestOwner*>(options->context.owner)->strong;
    if (getterReaderThread) readerThreadDuringBuild = *getterReaderThread;
    auto* pair = new DescriptorPair{&rebuilt, &rebuiltOwner};
    *result = {pair, pair + 1, pair + 1};
    ++rebuiltOwner.strong;
    ++state.allocations;
    return result;
}

void releasePublication(DescriptorPair* begin, DescriptorPair* end, DescriptorVector*) {
    for (auto* pair = begin; pair != end; ++pair) --static_cast<TestOwner*>(pair->owner)->strong;
}

int exchangePublication(std::int64_t* primary, std::int64_t* candidate, const std::int64_t* snapshot) noexcept {
    auto* slot = reinterpret_cast<DescriptorPair*>(primary);
    auto* scratch = reinterpret_cast<DescriptorPair*>(candidate);
    const auto* expected = reinterpret_cast<const DescriptorPair*>(snapshot);
    ++exchangeCalls;
    if (exchangeRefused || slot->entry != expected->entry || slot->owner != expected->owner) return 0;
    std::swap(*slot, *scratch);
    return 1;
}

bool testPublication(DescriptorFactoryRecipe recipe) {
    TestDescriptor original{};
    original.vtable = &descriptorVtable;
    original.capacity = 15;
    TestOwner originalOwner{&ownerVtable, 1};
    alignas(16) DescriptorPair slots[]{{&original, &originalOwner}, {}};
    DescriptorVector registry{slots, slots + 2, slots + 2};
    const DescriptorPair empty{};
    std::uint32_t readerHits = 2;
    DescriptorPublication publication{&registry, slots, slots[0], &descriptorVtable, &ownerVtable,
        exchangePublication, &readerHits, offsetof(TestDescriptor, identity), offsetof(TestDescriptor, name)};
    recipe.context = &empty;
    recipe.build = buildPublication;
    recipe.releasePairs = releasePublication;
    const auto refused = [&](int expectedCalls) {
        return Sl3RunAndPublishScratchFactory(&recipe, &publication) == 0 && clean() &&
            rebuiltOwner.strong == 0 && slots[0].entry == &original &&
            slots[0].owner == &originalOwner && exchangeCalls == expectedCalls;
    };

    const auto asioNameOffset = publication.asioNameOffset;
    publication.asioNameOffset = publication.usbIdentityOffset;
    if (Sl3RunAndPublishScratchFactory(&recipe, &publication) != -1 || !clean() || exchangeCalls != 0) return false;
    publication.asioNameOffset = asioNameOffset;
    publication.usbIdentityOffset = 168;
    if (!refused(0)) return false;
    publication.usbIdentityOffset = offsetof(TestDescriptor, identity);
    slots[1] = slots[0];
    if (!refused(0)) return false;
    slots[1] = {};
    readerHits = 1;
    if (!refused(0)) return false;
    readerHits = 2;
    ++originalOwner.strong;
    if (!refused(0)) return false;
    --originalOwner.strong;
    --rebuilt.length;
    if (!refused(0)) return false;
    ++rebuilt.length;
    publication.expected.owner = &rebuiltOwner;
    if (!refused(0)) return false;
    publication.expected = slots[0];
    exchangeRefused = true;
    if (!refused(1)) return false;
    exchangeRefused = false;
    if (Sl3RunAndPublishScratchFactory(&recipe, &publication) != 1 || !clean() || exchangeCalls != 2 ||
        originalOwner.strong != 0 || rebuiltOwner.strong != 1 || slots[0].entry != &rebuilt ||
        slots[0].owner != &rebuiltOwner || slots[1].entry) return false;

    // The primary entry point resolves the singleton, options and live slot itself.
    originalOwner.strong = 1;
    rebuiltOwner.strong = 0;
    slots[0] = {&original, &originalOwner};
    TestOwner optionsOwner{&ownerVtable, 1};
    const int managerVtable = 0;
    struct TestManager {
        const void* vtable;
        DescriptorPair options;
        DescriptorVector registry;
    } manager{&managerVtable, {&state, &optionsOwner}, registry};
    void* managerGlobal = nullptr;
    void* singletonGlobal = &state;
    const PrimaryDescriptorRecipe layout{&managerGlobal, &managerVtable, &singletonGlobal, &descriptorVtable,
        exchangePublication, &readerHits, offsetof(TestManager, registry), offsetof(TestManager, options),
        offsetof(TestDescriptor, identity), offsetof(TestDescriptor, name)};
    recipe.singleton = nullptr;
    recipe.context = nullptr;
    recipe.copyPair = copyPublication;
    const auto runPrimary = [&] { return Sl3PublishPrimaryDescriptor(&manager, &recipe, &layout); };
    const auto unchanged = [&] {
        return clean() && exchangeCalls == 2 && slots[0].entry == &original && originalOwner.strong == 1 && rebuiltOwner.strong == 0;
    };
    if (runPrimary() != 0 || !unchanged()) return false;
    managerGlobal = &manager;
    manager.vtable = &ownerVtable;
    if (runPrimary() != 0 || !unchanged()) return false;
    manager.vtable = &managerVtable;
    retainContext = true;
    if (runPrimary() != 0 || optionsOwner.strong != 2 || !unchanged()) return false;
    retainContext = false;
    --optionsOwner.strong;
    volatile long readerThread = 42;
    PrimaryGetterState unavailable{0, 0, &readerThread, {}, 0};
    Sl3DispatchPrimaryGetter(&manager, &recipe, &layout, &unavailable);
    if (unavailable.phase != 2 || unavailable.result != -5 || readerThread != 42 || !unchanged()) return false;

    readerThread = 0;
    getterReaderThread = &readerThread;
    PrimaryGetterState dispatched{0, 0, &readerThread, {}, 0};
    Sl3DispatchPrimaryGetter(&manager, &recipe, &layout, &dispatched);
    Sl3DispatchPrimaryGetter(&manager, &recipe, &layout, &dispatched);
    getterReaderThread = nullptr;
    return dispatched.phase == 2 && dispatched.result == 1 && dispatched.published.entry == &rebuilt &&
        dispatched.published.owner == &rebuiltOwner && dispatched.hadOptionsOwner == 1 &&
        readerThread == 0 && readerThreadDuringBuild != 0 && clean() && exchangeCalls == 3 && originalOwner.strong == 0 &&
        rebuiltOwner.strong == 1 && optionsOwner.strong == 1 && slots[0].owner == &rebuiltOwner && !slots[1].entry;
}
}

int main() {
    DescriptorPair context{&state, &state.contextRefs};
    DescriptorFactoryRecipe recipe{&state, makeString, destroyString, makeIdentifier, destroyIdentifier,
                                   copyPair, build, releasePairs, freeAllocation, &context};
    if (Sl3RunScratchFactory(&recipe, consume) != 1 || !clean() || state.buildCalls != 1 || state.consumeCalls != 1) return 1;
    state = {};
    state.reject = true;
    if (Sl3RunScratchFactory(&recipe, consume) != 0 || !clean() || state.consumeCalls != 1) return 2;
    state = {};
    state.wrongCopy = true;
    if (Sl3RunScratchFactory(&recipe, consume) != -2 || !clean() || state.buildCalls != 0) return 3;
    state = {};
    state.emptyResult = true;
    if (Sl3RunScratchFactory(&recipe, consume) != -3 || !clean() || state.consumeCalls != 0) return 4;
    state = {};
    context = {};
    if (Sl3RunScratchFactory(&recipe, consume) != 1 || !clean()) return 5;
    context.entry = &state;
    if (Sl3RunScratchFactory(&recipe, consume) != -1 || !clean()) return 6;
    state = {};
    state.replace = true;
    context = {&state, &state.contextRefs};
    published = {&published, &state.retiredRefs};
    if (Sl3RunScratchFactory(&recipe, consume) != 1 || state.retiredRefs != 0 ||
        published.owner != &state.resultRefs || state.resultRefs != 1) return 7;
    --state.resultRefs;
    if (!clean()) return 8;
    if (!testPublication(recipe)) return 9;
    std::puts("Scratch factory released its objects on success and after every exercised refusal.");
}
