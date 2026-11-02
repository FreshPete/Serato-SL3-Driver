#pragma once
#include <Windows.h>
#include <evntprov.h>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cwchar>

namespace sl3::asio::trace {
// Original project provider, independent of Serato/Rane providers and identities.
inline constexpr GUID provider_id={0x953df2f7,0x5f98,0x4895,{0xa5,0x7a,0x73,0xc0,0x18,0x8c,0x43,0x21}};
inline constexpr std::uint64_t keyword=1,maximum_calls=4096;
#ifdef SL3_ASIO_SESSION_FIXTURE
inline constexpr const wchar_t* build_kind=L"session_fixture";
#else
inline constexpr const wchar_t* build_kind=L"production";
#endif
enum class Operation:unsigned {class_object=1,init,name,version,error,start,stop,channels,latencies,
    buffer_size,can_rate,get_rate,set_rate,clocks,set_clock,create_buffers,dispose_buffers,panel};
enum class Phase {begin,end,abandoned};
struct Record {
    Phase phase;Operation operation;std::uint64_t instance,call;
    std::int64_t result,argument0,argument1;
    std::uint64_t qpc,frequency,elapsed;
};
inline bool format(const Record& r,wchar_t* buffer,std::size_t count) noexcept {
    if(!buffer || !count)return false;
    const wchar_t* phase=r.phase==Phase::begin?L"begin":r.phase==Phase::end?L"end":L"abandoned";
    const int n=_snwprintf_s(buffer,count,_TRUNCATE,
        L"{\"schema\":\"sl3.asio-call.v1\",\"build\":\"%ls\",\"phase\":\"%ls\",\"op\":%u,\"object\":%llu,\"call\":%llu,\"result\":%lld,\"a0\":%lld,\"a1\":%lld,\"qpc\":%llu,\"frequency\":%llu,\"elapsedQpc\":%llu}",
        build_kind,phase,static_cast<unsigned>(r.operation),static_cast<unsigned long long>(r.instance),
        static_cast<unsigned long long>(r.call),static_cast<long long>(r.result),
        static_cast<long long>(r.argument0),static_cast<long long>(r.argument1),
        static_cast<unsigned long long>(r.qpc),static_cast<unsigned long long>(r.frequency),
        static_cast<unsigned long long>(r.elapsed));
    return n>=0;
}
class Provider {
    REGHANDLE handle_=0;
public:
    Provider() noexcept {(void)EventRegister(&provider_id,nullptr,nullptr,&handle_);}
    ~Provider(){(void)EventUnregister(handle_);}
    Provider(const Provider&)=delete;Provider& operator=(const Provider&)=delete;
    bool registered() const noexcept {return handle_!=0;}
    bool enabled() const noexcept {return handle_ && EventProviderEnabled(handle_,4,keyword)!=FALSE;}
    void write(const Record& r) const noexcept {
        wchar_t payload[512]{};
        if(format(r,payload,512))(void)EventWriteString(handle_,4,keyword,payload);
    }
};
inline Provider& provider() noexcept {static Provider value;return value;}
inline std::uint64_t counter() noexcept {LARGE_INTEGER v{};return QueryPerformanceCounter(&v) && v.QuadPart>=0?static_cast<std::uint64_t>(v.QuadPart):0;}
inline std::uint64_t frequency() noexcept {LARGE_INTEGER v{};return QueryPerformanceFrequency(&v) && v.QuadPart>0?static_cast<std::uint64_t>(v.QuadPart):0;}
struct Backend {
    bool(*enabled)() noexcept;
    void(*write)(const Record&) noexcept;
    std::uint64_t(*now)() noexcept;
    std::uint64_t(*ticks_per_second)() noexcept;
};
inline const Backend& backend() noexcept {
    static const Backend value{[]() noexcept{return provider().enabled();},
        [](const Record& r) noexcept{provider().write(r);},counter,frequency};
    return value;
}
inline std::atomic<std::uint64_t> next_call{1},next_instance{1};
// Use only on control/activation paths. Do not instantiate on audio callbacks,
// getSamplePosition, outputReady, AddRef or Release.
class Call {
    const Backend* backend_;
    Record record_{};
    bool active_=false,finished_=false;
public:
    Call(Operation op,std::uint64_t instance,std::int64_t a0=0,std::int64_t a1=0,const Backend& b=backend()) noexcept:backend_(&b) {
        if(!b.enabled())return;
        // Saturation prevents wraparound from reopening the per-module budget.
        auto ordinal=next_call.load(std::memory_order_relaxed);
        while(ordinal<=maximum_calls && !next_call.compare_exchange_weak(ordinal,ordinal+1,std::memory_order_relaxed)){}
        if(ordinal>maximum_calls)return;
        active_=true;record_={Phase::begin,op,instance,ordinal,0,a0,a1,b.now(),b.ticks_per_second(),0};
        b.write(record_);
    }
    Call(const Call&)=delete;Call& operator=(const Call&)=delete;
    ~Call(){if(active_ && !finished_)emit(Phase::abandoned,0);}
    template<class T>T finish(T result) noexcept {
        if(active_ && !finished_)emit(Phase::end,static_cast<std::int64_t>(result));
        return result;
    }
private:
    void emit(Phase phase,std::int64_t result) noexcept {
        finished_=true;const auto now=backend_->now();
        record_.elapsed=now>=record_.qpc?now-record_.qpc:0;
        record_.phase=phase;record_.result=result;backend_->write(record_);
    }
};
}
