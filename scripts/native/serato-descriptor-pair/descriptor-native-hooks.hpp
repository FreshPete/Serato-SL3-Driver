#pragma once
#include "descriptor-factory.hpp"
#include "descriptor-reader.hpp"
#include <array>

struct _GumInterceptor;

struct DescriptorHookPlan {
    void* getter;
    void* reader;
    void* aggregationReturn;
    std::array<unsigned char, 8> getterBytes;
    std::array<unsigned char, 16> readerBytes;
    const DescriptorFactoryRecipe* factory;
    const PrimaryDescriptorRecipe* primary;
    PrimaryGetterState* state;
    DescriptorReadScope* scope;
    decltype(&Sl3DispatchPrimaryGetter) dispatch;
    decltype(&Sl3SupplyScopedDescriptorText) supply;
};

// Keep this object and the plan's buffers alive until retire() succeeds.
class NativeDescriptorHooks {
public:
    NativeDescriptorHooks() = default;
    NativeDescriptorHooks(const NativeDescriptorHooks&) = delete;
    NativeDescriptorHooks& operator=(const NativeDescriptorHooks&) = delete;
    bool arm(_GumInterceptor*, const DescriptorHookPlan&);
    bool retire();

private:
    static void* replaceGetter(void*);
    static void* replaceReader(void*, void*, const unsigned char*);

    _GumInterceptor* interceptor_ = nullptr;
    DescriptorHookPlan plan_{};
    void* (*originalGetter_)(void*) = nullptr;
    void* (*originalReader_)(void*, void*, const unsigned char*) = nullptr;
    bool getterArmed_ = false;
    bool readerArmed_ = false;
};
