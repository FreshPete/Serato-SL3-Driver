#include "descriptor-native-hooks.hpp"
#include <gum/guminterceptor.h>
#include <Windows.h>

namespace {
template<std::size_t Size>
bool matches(const void* address, const std::array<unsigned char, Size>& expected) {
    std::array<unsigned char, Size> actual{};
    return ReadProcessMemory(GetCurrentProcess(), address, actual.data(), actual.size(), nullptr) && actual == expected;
}
}

bool NativeDescriptorHooks::arm(GumInterceptor* interceptor, const DescriptorHookPlan& plan) {
    if (interceptor_ || !interceptor || !plan.getter || !plan.reader || plan.getter == plan.reader ||
        !plan.aggregationReturn || !plan.factory || !plan.primary || !plan.state || !plan.scope ||
        !plan.dispatch || !plan.supply || plan.state->phase || plan.scope->thread || plan.scope->hits ||
        static_cast<const volatile void*>(plan.state->readerThread) != &plan.scope->thread ||
        plan.primary->readerHits != &plan.scope->hits ||
        !matches(plan.getter, plan.getterBytes) || !matches(plan.reader, plan.readerBytes)) return false;

    interceptor_ = interceptor;
    plan_ = plan;
    GumReplaceOptions options{};
    options.replacement_data = this;
    gpointer originalReader = nullptr;
    gpointer originalGetter = nullptr;
    gum_interceptor_begin_transaction(interceptor_);
    readerArmed_ = gum_interceptor_replace(interceptor_, plan_.reader, reinterpret_cast<void*>(replaceReader),
        &originalReader, &options) == GUM_REPLACE_OK;
    if (readerArmed_) {
        originalReader_ = reinterpret_cast<decltype(originalReader_)>(originalReader);
        getterArmed_ = gum_interceptor_replace(interceptor_, plan_.getter, reinterpret_cast<void*>(replaceGetter),
            &originalGetter, &options) == GUM_REPLACE_OK;
        if (getterArmed_) {
            originalGetter_ = reinterpret_cast<decltype(originalGetter_)>(originalGetter);
        } else {
            gum_interceptor_revert(interceptor_, plan_.reader);
            readerArmed_ = false;
        }
    }
    gum_interceptor_end_transaction(interceptor_);
    if (getterArmed_) return true;
    retire();
    return false;
}

bool NativeDescriptorHooks::retire() {
    if (!interceptor_) return true;
    // Cancel an unclaimed gate before removing either hook. A claimed gate
    // still needs the reader until its factory transaction completes.
    if (InterlockedCompareExchange(&plan_.state->phase, 3, 0) == 1) return false;
    gum_interceptor_begin_transaction(interceptor_);
    if (getterArmed_) gum_interceptor_revert(interceptor_, plan_.getter);
    if (readerArmed_) gum_interceptor_revert(interceptor_, plan_.reader);
    getterArmed_ = readerArmed_ = false;
    gum_interceptor_end_transaction(interceptor_);
    if (!gum_interceptor_flush_function(interceptor_, plan_.getter) ||
        !gum_interceptor_flush_function(interceptor_, plan_.reader) ||
        !matches(plan_.getter, plan_.getterBytes) || !matches(plan_.reader, plan_.readerBytes)) return false;
    interceptor_ = nullptr;
    return true;
}

void* NativeDescriptorHooks::replaceGetter(void* manager) {
    auto* context = gum_interceptor_get_current_invocation();
    auto* self = static_cast<NativeDescriptorHooks*>(gum_invocation_context_get_replacement_data(context));
    const auto& plan = self->plan_;
    if (gum_invocation_context_get_return_address(context) == plan.aggregationReturn)
        plan.dispatch(manager, plan.factory, plan.primary, plan.state);
    return self->originalGetter_(manager);
}

void* NativeDescriptorHooks::replaceReader(void* provider, void* output, const unsigned char* identifier) {
    auto* context = gum_interceptor_get_current_invocation();
    auto* self = static_cast<NativeDescriptorHooks*>(gum_invocation_context_get_replacement_data(context));
    const auto& plan = self->plan_;
    const auto thread = GetCurrentThreadId();
    if (thread == static_cast<DWORD>(InterlockedCompareExchange(plan.state->readerThread, 0, 0))) {
        const auto caller = gum_invocation_context_get_return_address(context);
        if (auto* supplied = plan.supply(output, identifier, caller, thread, plan.scope)) return supplied;
    }
    return self->originalReader_(provider, output, identifier);
}
