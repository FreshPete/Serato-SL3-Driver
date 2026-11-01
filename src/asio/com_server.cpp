#include "asio/com_identity.hpp"
#include "asio/scope_interface.hpp"
#include "iasiodrv.h"
#include <atomic>
#include <cstring>
#include <cstdio>
#include <limits>
#include <new>
#include <mutex>
#include <stdexcept>
#include "asio/driver_configuration.hpp"
#ifdef SL3_ASIO_SESSION_FIXTURE
std::unique_ptr<sl3::asio::DriverFacade> make_test_asio_facade();
bool test_asio_owner_held() noexcept;
std::shared_ptr<sl3::asio::DriverScope> make_test_asio_scope();
#endif

namespace {
std::atomic<ULONG> objects{0},locks{0};
struct ObjectLease {
    ObjectLease() noexcept {objects.fetch_add(1);}
    ~ObjectLease(){objects.fetch_sub(1);}
};

// Production resolves only an adjacent reviewed native configuration. The
// separately built test DLL supplies its own explicitly simulated provider.
class Device final:public IASIO {
    ObjectLease lease_;
    std::atomic<ULONG> references_{1};
    std::shared_ptr<sl3::asio::DriverScope> bound_scope_;
    std::unique_ptr<sl3::asio::DriverFacade> facade_;
    const char* configuration_error_="Reviewed isolated audio configuration is absent; device unavailable.";
public:
    explicit Device(std::shared_ptr<sl3::asio::DriverScope> scope={}):bound_scope_(std::move(scope)){}
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid,void** result) noexcept override {
        if(!result)return E_POINTER;
        *result=nullptr;
        // The official Windows ASIO loader requests the driver's CLSID as IID.
        if(iid!=IID_IUnknown && iid!=sl3::asio::driver_clsid)return E_NOINTERFACE;
        *result=static_cast<IASIO*>(this);AddRef();return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() noexcept override {return references_.fetch_add(1)+1;}
    ULONG STDMETHODCALLTYPE Release() noexcept override {
        const auto remaining=references_.fetch_sub(1)-1;
        if(!remaining)delete this;
        return remaining;
    }
    ASIOBool init(void*) noexcept override {
        try{
            if(!facade_){
                if(bound_scope_)facade_=std::make_unique<sl3::asio::DriverFacade>(bound_scope_->owner,bound_scope_->latency);
                else{
#ifdef SL3_ASIO_SESSION_FIXTURE
                facade_=make_test_asio_facade();
#else
                facade_=sl3::asio::make_native_asio_facade();
#endif
                }
            }
            return facade_?facade_->init():ASIOFalse;
        }catch(const std::bad_alloc&){configuration_error_="ASIO configuration allocation failed; device unavailable.";}
        catch(...){configuration_error_="ASIO configuration is missing, invalid or inconsistent; device unavailable.";}
        return ASIOFalse;
    }
    void getDriverName(char* name) noexcept override {
        constexpr char value[]="SL3 Rebuild Development";
        if(name)std::memcpy(name,value,sizeof(value));
    }
    long getDriverVersion() noexcept override {return 1;}
    void getErrorMessage(char* message) noexcept override {
        if(facade_){facade_->getErrorMessage(message);return;}
        if(message)std::snprintf(message,124,"%s",configuration_error_);
    }
    ASIOError start() noexcept override {return facade_?facade_->start():ASE_NotPresent;}
    ASIOError stop() noexcept override {return facade_?facade_->stop():ASE_NotPresent;}
    ASIOError getChannels(long* a,long* b) noexcept override {return facade_?facade_->getChannels(a,b):ASE_NotPresent;}
    ASIOError getLatencies(long* a,long* b) noexcept override {return facade_?facade_->getLatencies(a,b):ASE_NotPresent;}
    ASIOError getBufferSize(long* a,long* b,long* c,long* d) noexcept override {return facade_?facade_->getBufferSize(a,b,c,d):ASE_NotPresent;}
    ASIOError canSampleRate(ASIOSampleRate rate) noexcept override {return facade_?facade_->canSampleRate(rate):ASE_NotPresent;}
    ASIOError getSampleRate(ASIOSampleRate* rate) noexcept override {return facade_?facade_->getSampleRate(rate):ASE_NotPresent;}
    ASIOError setSampleRate(ASIOSampleRate rate) noexcept override {return facade_?facade_->setSampleRate(rate):ASE_NotPresent;}
    ASIOError getClockSources(ASIOClockSource* clocks,long* count) noexcept override {return facade_?facade_->getClockSources(clocks,count):ASE_NotPresent;}
    ASIOError setClockSource(long index) noexcept override {return facade_?facade_->setClockSource(index):ASE_NotPresent;}
    ASIOError getSamplePosition(ASIOSamples* position,ASIOTimeStamp* time) noexcept override {return facade_?facade_->getSamplePosition(position,time):ASE_NotPresent;}
    ASIOError getChannelInfo(ASIOChannelInfo* info) noexcept override {return facade_?facade_->getChannelInfo(info):ASE_NotPresent;}
    ASIOError createBuffers(ASIOBufferInfo* info,long channels,long frames,ASIOCallbacks* cb) noexcept override {return facade_?facade_->createBuffers(info,channels,frames,cb):ASE_NotPresent;}
    ASIOError disposeBuffers() noexcept override {return facade_?facade_->disposeBuffers():ASE_NotPresent;}
    ASIOError controlPanel() noexcept override {return facade_?facade_->controlPanel():ASE_NotPresent;}
    ASIOError future(long selector,void* option) noexcept override {return facade_?facade_->future(selector,option):ASE_NotPresent;}
    ASIOError outputReady() noexcept override {return facade_?facade_->outputReady():ASE_NotPresent;}

};

class Factory final:public IClassFactory,public sl3::asio::DeviceScope {
    ObjectLease lease_;
    std::atomic<ULONG> references_{1};
    enum class ScopeState {unused,preparing,active,closed,failed};
    std::mutex scope_mutex_;
    ScopeState scope_state_=ScopeState::unused;
    bool created_=false;
    std::shared_ptr<sl3::asio::DriverScope> scope_;
public:
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid,void** result) noexcept override {
        if(!result)return E_POINTER;
        *result=nullptr;
        if(iid==IID_IUnknown || iid==IID_IClassFactory)*result=static_cast<IClassFactory*>(this);
        else if(iid==sl3::asio::scope_iid)*result=static_cast<sl3::asio::DeviceScope*>(this);
        else return E_NOINTERFACE;
        AddRef();return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() noexcept override {return references_.fetch_add(1)+1;}
    ULONG STDMETHODCALLTYPE Release() noexcept override {
        const auto remaining=references_.fetch_sub(1)-1;
        if(!remaining)delete this;
        return remaining;
    }
    HRESULT STDMETHODCALLTYPE CreateInstance(IUnknown* outer,REFIID iid,void** result) noexcept override {
        if(!result)return E_POINTER;
        *result=nullptr;
        if(outer)return CLASS_E_NOAGGREGATION;
        Device* object=nullptr;
        try{
            std::shared_ptr<sl3::asio::DriverScope> scope;
            {std::lock_guard<std::mutex> guard(scope_mutex_);
                if(scope_state_==ScopeState::preparing)return E_PENDING;
                if(scope_state_==ScopeState::closed || scope_state_==ScopeState::failed)return E_UNEXPECTED;
                created_=true;scope=scope_;
            }
            object=new Device(std::move(scope));
        }catch(const std::bad_alloc&){return E_OUTOFMEMORY;}catch(...){return E_FAIL;}
        const auto status=object->QueryInterface(iid,result);
        object->Release();return status;
    }
    HRESULT STDMETHODCALLTYPE BeginScope() noexcept override {
        {std::lock_guard<std::mutex> guard(scope_mutex_);
            if(created_ || scope_state_!=ScopeState::unused)return E_UNEXPECTED;
            scope_state_=ScopeState::preparing;
        }
        try{
#ifdef SL3_ASIO_SESSION_FIXTURE
            auto scope=make_test_asio_scope();
#else
            auto scope=sl3::asio::make_native_asio_scope();
#endif
            if(!scope || !scope->owner)throw std::runtime_error("Missing explicit ASIO scope");
            std::lock_guard<std::mutex> guard(scope_mutex_);scope_=std::move(scope);scope_state_=ScopeState::active;return S_OK;
        }catch(...){std::lock_guard<std::mutex> guard(scope_mutex_);scope_state_=ScopeState::failed;return E_FAIL;}
    }
    HRESULT STDMETHODCALLTYPE EndScope() noexcept override {
        std::shared_ptr<sl3::asio::DriverScope> scope;
        {std::lock_guard<std::mutex> guard(scope_mutex_);
            if(scope_state_==ScopeState::preparing)return E_PENDING;
            if(!scope_)return S_FALSE;scope=scope_;
        }
        // Do not hold the factory mutex through worker/callback retirement.
        const auto value=scope->owner->close();if(!value)return S_FALSE;
        const bool retired=value->failure==sl3::asio::HostFailure::none && !value->reentrant && value->audio.retired &&
            value->io_retired && value->device_released && !value->device_held &&
            (!value->process.started || (value->process.process_exited && value->process.job_empty));
        std::lock_guard<std::mutex> guard(scope_mutex_);
        if(!retired){scope_state_=ScopeState::failed;return E_FAIL;}
        scope_.reset();scope_state_=ScopeState::closed;return S_OK;
    }
    HRESULT STDMETHODCALLTYPE LockServer(BOOL lock) noexcept override {
        auto value=locks.load();
        for(;;){
            if((lock && value==std::numeric_limits<ULONG>::max()) || (!lock && !value))return E_UNEXPECTED;
            if(locks.compare_exchange_weak(value,lock?value+1:value-1))return S_OK;
        }
    }
};
}
STDAPI DllGetClassObject(REFCLSID clsid,REFIID iid,void** result) {
    if(!result)return E_POINTER;
    *result=nullptr;
    if(clsid!=sl3::asio::driver_clsid)return CLASS_E_CLASSNOTAVAILABLE;
    auto* factory=new(std::nothrow) Factory;
    if(!factory)return E_OUTOFMEMORY;
    const auto status=factory->QueryInterface(iid,result);
    factory->Release();return status;
}
STDAPI DllCanUnloadNow() {
#ifdef SL3_ASIO_SESSION_FIXTURE
    if(test_asio_owner_held())return S_FALSE;
#endif
    return objects.load()==0 && locks.load()==0?S_OK:S_FALSE;
}
