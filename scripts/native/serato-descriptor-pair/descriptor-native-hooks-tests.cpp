#include "descriptor-native-hooks.hpp"
#include <gum/gum.h>
#include <Windows.h>
#include <intrin.h>
#include <cstdio>
#include <cstring>
#include <thread>

namespace {
constexpr char path[] = "userio/audio/audio_rane_sl3_rebuild.xml";
constexpr char xml[] = "<descriptor/>";
std::array<unsigned char, 232> identifier{};
std::array<char, 32> output{};
DescriptorReadScope scope{};
void* getterCaller = nullptr;
void* readerCaller = nullptr;
unsigned calls[5]{};
unsigned originals = 0;
unsigned dispatches = 0;
int fallback = 0;
HANDLE entered = nullptr;
HANDLE resume = nullptr;

__declspec(noinline) void* fixtureGetter(void* manager) {
    getterCaller = _ReturnAddress();
    return manager;
}

__declspec(noinline) void* fixtureReader(void*, void*, const unsigned char*) {
    readerCaller = _ReturnAddress();
    ++originals;
    return &fallback;
}

decltype(&fixtureGetter) volatile getter = fixtureGetter;
decltype(&fixtureReader) volatile reader = fixtureReader;

__declspec(noinline) void* invokeAggregate(void* manager) {
    auto* result = getter(manager);
    ++calls[0];
    return result;
}
__declspec(noinline) void* invokeOtherGetter(void* manager) {
    auto* result = getter(manager);
    ++calls[1];
    return result;
}
__declspec(noinline) void* readClassification() {
    auto* result = reader(nullptr, output.data(), identifier.data());
    ++calls[2];
    return result;
}
__declspec(noinline) void* readFullParse() {
    auto* result = reader(nullptr, output.data(), identifier.data());
    ++calls[3];
    return result;
}
__declspec(noinline) void* readOther() {
    auto* result = reader(nullptr, output.data(), identifier.data());
    ++calls[4];
    return result;
}

void* make(void* destination, const char* text) {
    std::memcpy(destination, text, sizeof(xml));
    return destination;
}

void dispatch(void*, const DescriptorFactoryRecipe*, const PrimaryDescriptorRecipe*, PrimaryGetterState* state) {
    if (InterlockedCompareExchange(&state->phase, 1, 0) != 0) return;
    ++dispatches;
    InterlockedExchange(state->readerThread, static_cast<long>(GetCurrentThreadId()));
    const bool released = SetEvent(entered) && WaitForSingleObject(resume, 3000) == WAIT_OBJECT_0;
    state->result = released && readClassification() == output.data() && readOther() == &fallback && readFullParse() == output.data();
    InterlockedExchange(state->readerThread, 0);
    InterlockedExchange(&state->phase, 2);
}

template<class T>
void store(std::size_t offset, T value) {
    std::memcpy(identifier.data() + offset, &value, sizeof(value));
}

int check(GumInterceptor* interceptor) {
    std::memcpy(identifier.data(), "resource", 8);
    store<std::size_t>(16, 8);
    store<std::size_t>(24, 15);
    constexpr std::uint32_t pathOffset = 96;
    store<const char*>(pathOffset, path);
    store<std::size_t>(pathOffset + 16, sizeof(path) - 1);
    store<std::size_t>(pathOffset + 24, sizeof(path) - 1);
    int manager = 0;
    if (invokeAggregate(&manager) != &manager) return 1;
    const auto aggregateReturn = getterCaller;
    if (invokeOtherGetter(&manager) != &manager || getterCaller == aggregateReturn) return 2;
    if (readClassification() != &fallback) return 3;
    const auto classificationReturn = readerCaller;
    if (readFullParse() != &fallback || readerCaller == classificationReturn) return 4;
    scope = {{classificationReturn, readerCaller}, xml, make, 0, 0, pathOffset, static_cast<std::uint32_t>(identifier.size())};
    DescriptorFactoryRecipe factory{};
    PrimaryDescriptorRecipe primary{};
    primary.readerHits = &scope.hits;
    PrimaryGetterState state{0, 0, reinterpret_cast<volatile long*>(&scope.thread), {}, 0};
    DescriptorHookPlan plan{reinterpret_cast<void*>(fixtureGetter), reinterpret_cast<void*>(fixtureReader), aggregateReturn,
        {}, {}, &factory, &primary, &state, &scope, dispatch, Sl3SupplyScopedDescriptorText};
    std::memcpy(plan.getterBytes.data(), plan.getter, plan.getterBytes.size());
    std::memcpy(plan.readerBytes.data(), plan.reader, plan.readerBytes.size());
    NativeDescriptorHooks hooks;
    auto invalid = plan;
    invalid.readerBytes[0] ^= 1;
    if (hooks.arm(interceptor, invalid) || !hooks.arm(interceptor, plan) || !hooks.retire() || state.phase != 3 || dispatches)
        return 5;
    state.phase = 0;
    if (!hooks.arm(interceptor, plan)) return 6;

    const bool other = invokeOtherGetter(&manager) == &manager && readClassification() == &fallback && !dispatches;
    entered = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    resume = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!entered || !resume) {
        if (entered) CloseHandle(entered);
        if (resume) CloseHandle(resume);
        hooks.retire();
        return 7;
    }
    void* returned = nullptr;
    std::thread startup([&] { returned = invokeAggregate(&manager); });
    const bool activeRefusal = WaitForSingleObject(entered, 2500) == WAIT_OBJECT_0 && !hooks.retire();
    SetEvent(resume);
    startup.join();
    CloseHandle(entered);
    CloseHandle(resume);
    const bool expected = returned == &manager && state.result == 1 && state.phase == 2 &&
        scope.hits == 2 && scope.thread == 0 && std::strcmp(output.data(), xml) == 0 && dispatches == 1;
    const bool repeated = invokeAggregate(&manager) == &manager && dispatches == 1 && originals == 4;
    if (!hooks.retire()) return 8;
    if (!activeRefusal || !other || !expected || !repeated) return 9;
    return invokeAggregate(&manager) == &manager && readFullParse() == &fallback && dispatches == 1 ? 0 : 10;
}
}

int main() {
    gum_init_embedded();
    auto* interceptor = gum_interceptor_obtain();
    const auto result = check(interceptor);
    g_object_unref(interceptor);
    gum_deinit_embedded();
    if (result == 0) std::puts("Native hooks scoped the two reads and restored both original functions.");
    return result;
}
