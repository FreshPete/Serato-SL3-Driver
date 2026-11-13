#include "descriptor-native-hooks.hpp"
#include <gum/gum.h>
#include <Windows.h>
#include <string>

extern "C" int Sl3ExchangeOwnedDescriptorPair(std::int64_t*, std::int64_t*, const std::int64_t*) noexcept;

namespace {
struct HookInput {
    void* getter;
    void* reader;
    void* aggregationReturn;
    std::array<unsigned char, 8> getterBytes;
    std::array<unsigned char, 16> readerBytes;
    const DescriptorFactoryRecipe* factory;
    const PrimaryDescriptorRecipe* primary;
    const DescriptorReadScope* scope;
};

struct HookReceipt {
    int result;
    std::uint32_t readerHits;
    DescriptorPair published;
    std::uint32_t hadOptionsOwner;
};

static_assert(sizeof(HookInput) == 72 && offsetof(HookInput, factory) == 48);
static_assert(sizeof(HookReceipt) == 32 && offsetof(HookReceipt, published) == 8);

NativeDescriptorHooks hooks;
GumInterceptor* interceptor = nullptr;
DescriptorFactoryRecipe factory{};
PrimaryDescriptorRecipe primary{};
DescriptorReadScope reader{};
PrimaryGetterState state{};
std::string xml;

void releaseGum() {
    g_object_unref(interceptor);
    interceptor = nullptr;
    gum_deinit_embedded();
}
}

// A read-only export points at the atomically published phase in this process.
extern "C" __declspec(dllexport) volatile long* const Sl3DescriptorHookPhase = &state.phase;

extern "C" __declspec(dllexport) int Sl3ArmDescriptorHooks(const HookInput* input) {
    if (!input || !input->factory || !input->primary || !input->scope || !input->scope->xml || interceptor) return 0;
    const auto length = strnlen(input->scope->xml, 16384);
    if (length == 0 || length == 16384) return 0;
    try {
        xml.assign(input->scope->xml, length);
    } catch (...) {
        return 0;
    }
    factory = *input->factory;
    primary = *input->primary;
    reader = *input->scope;
    reader.xml = xml.c_str();
    primary.exchange = Sl3ExchangeOwnedDescriptorPair;
    primary.readerHits = &reader.hits;
    state = {};
    state.readerThread = reinterpret_cast<volatile long*>(&reader.thread);

    gum_init_embedded();
    interceptor = gum_interceptor_obtain();
    const DescriptorHookPlan plan{input->getter, input->reader, input->aggregationReturn, input->getterBytes,
        input->readerBytes, &factory, &primary, &state, &reader, Sl3DispatchPrimaryGetter, Sl3SupplyScopedDescriptorText};
    if (hooks.arm(interceptor, plan)) return 1;
    if (!hooks.retire()) return -1;
    releaseGum();
    return 0;
}

extern "C" __declspec(dllexport) int Sl3RetireDescriptorHooks(HookReceipt* receipt) {
    if (!interceptor || !receipt || !hooks.retire()) return 0;
    const auto phase = InterlockedCompareExchange(&state.phase, 0, 0);
    *receipt = {phase == 2 ? state.result : 0, reader.hits, state.published, state.hadOptionsOwner};
    releaseGum();
    return 1;
}
