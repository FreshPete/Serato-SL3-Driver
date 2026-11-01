#include "asio/driver_session.hpp"
namespace sl3::asio {
namespace {
class OwnedDriverSession final:public DriverSession {
    HostSession session_;
public:
    explicit OwnedDriverSession(WorkerSpec spec):session_(std::move(spec)){}
    bool inspect() noexcept override{return session_.inspect();}
    std::optional<unsigned> inspect_rate() noexcept override{return session_.inspect_rate();}
    ASIOError create_buffers(ASIOBufferInfo* b,long c,long f,const ASIOCallbacks* cb) noexcept override{return session_.create_buffers(b,c,f,cb);}
    ASIOError dispose_buffers() noexcept override{return session_.dispose_buffers();}
    bool start(unsigned n) noexcept override{return session_.start(n);}
    HostReport stop(DWORD t) noexcept override{return session_.stop(t);}
    HostReport close(DWORD t) noexcept override{return session_.close(t);}
    void request_shutdown() noexcept override{session_.request_shutdown();}
    HostReport report() noexcept override{return session_.report();}
    bool on_audio_thread() const noexcept override{return session_.on_audio_thread();}
    Observation observation() const noexcept override{return session_.observation();}
};
}
std::unique_ptr<DriverSession> make_owned_driver_session(WorkerSpec spec){return std::make_unique<OwnedDriverSession>(std::move(spec));}
}
