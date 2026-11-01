#include "windows/driver_timer_io.hpp"
#include <iostream>
#include <stdexcept>
#include <vector>
using namespace sl3;
void check(bool value){if(!value)throw std::runtime_error("Native timer adapter check failed");}
struct Clock {inline static std::uint64_t tick=0;static std::uint64_t now_ms() noexcept{return tick;}};
struct Device {
    unsigned submissions=0,notifications=0;
    bool short_frame=false,throws=false,late_prepare=false,bad_tag=false,late_completion=false;
    control::Frame written{};
};
struct Transfer {
    Device& device;std::vector<std::uint8_t> buffer;DWORD completion_error=0;
    struct Request {struct Result {struct General {std::uint64_t BytesTransferred=0;} GenResult;} Result;} request;
    explicit Transfer(Device& d):device(d){}
    void prepare(unsigned pipe,std::size_t bytes,bool iso){check((pipe==1 || pipe==0x81) && bytes==64 && !iso);buffer.resize(bytes);if(device.late_prepare)Clock::tick+=100;}
    void bounded(bool output,DWORD timeout){
        check(timeout>0 && timeout<=(output?100u:300u));++device.submissions;
        if(device.throws){completion_error=ERROR_OPERATION_ABORTED;throw std::runtime_error("retired fake transfer");}
        request.Result.GenResult.BytesTransferred=device.short_frame?63:64;
        if(output)std::copy(buffer.begin(),buffer.end(),device.written.begin());
        else if(device.notifications){--device.notifications;buffer[0]=0x38;buffer[4]=2;}
        else {buffer[0]=0x37;buffer[1]=device.bad_tag?0:0x1c;buffer[2]=0xc5;buffer[4]=1;for(unsigned i=0;i<8;++i)buffer[i+5]=std::uint8_t(i+1);}
        Clock::tick+=device.late_completion?1500:1;
    }
};
using Io=worker::NativeDriverTimerIo<Device,Transfer,Clock>;
int main(){try{
    const control::Challenge challenge{{0,1,2,3,4,5,6,7}};
    {Clock::tick=0;Device d;Io io(d,challenge);const auto r=control::inspect_driver_timer(challenge,io);
        check(r.error==control::DriverTimerError::none && r.response && d.submissions==2 && io.writes==1 && io.reads==1);
        check(d.written==control::driver_timer_query(challenge).frame());std::size_t bytes=0;control::Frame frame{};
        check(!io.transfer(false,frame,100,bytes) && d.submissions==2);}
    {Clock::tick=0;Device d;Io io(d,challenge);auto wrong=control::driver_timer_query(challenge).frame();wrong[0]=0x31;std::size_t bytes=99;
        check(!io.transfer(true,wrong,100,bytes) && bytes==0 && d.submissions==0 && io.error==ERROR_INVALID_PARAMETER);}
    {Clock::tick=0;Device d;Io io(d,challenge);control::Frame frame{};std::size_t bytes=0;
        check(!io.transfer(false,frame,100,bytes) && d.submissions==0);}
    {Clock::tick=0;Device d;d.late_prepare=true;Io io(d,challenge);const auto r=control::inspect_driver_timer(challenge,io);
        check(r.error!=control::DriverTimerError::none && !r.response && d.submissions==0 && io.error==ERROR_TIMEOUT);}
    {Clock::tick=0;Device d;d.short_frame=true;Io io(d,challenge);const auto r=control::inspect_driver_timer(challenge,io);
        check(r.error==control::DriverTimerError::transfer && !r.response && io.error==ERROR_BAD_LENGTH && d.submissions==1);}
    {Clock::tick=0;Device d;d.throws=true;Io io(d,challenge);const auto r=control::inspect_driver_timer(challenge,io);
        check(r.error==control::DriverTimerError::transfer && !r.response && io.error==ERROR_OPERATION_ABORTED && d.submissions==1);}
    {Clock::tick=0;Device d;d.notifications=3;Io io(d,challenge);const auto r=control::inspect_driver_timer(challenge,io);
        check(r.error==control::DriverTimerError::none && r.response && d.submissions==5 && io.reads==4);}
    {Clock::tick=0;Device d;d.notifications=4;Io io(d,challenge);const auto r=control::inspect_driver_timer(challenge,io);
        check(r.error==control::DriverTimerError::exchange && !r.response && d.submissions==5 && io.reads==4);
        control::Frame frame{};std::size_t bytes=0;check(!io.transfer(false,frame,100,bytes) && d.submissions==5);}
    {Clock::tick=0;Device d;d.bad_tag=true;Io io(d,challenge);const auto r=control::inspect_driver_timer(challenge,io);
        check(r.error==control::DriverTimerError::exchange && !r.response && io.error==ERROR_INVALID_DATA && d.submissions==2);}
    {Clock::tick=0;Device d;d.late_completion=true;Io io(d,challenge);const auto r=control::inspect_driver_timer(challenge,io);
        check(r.error==control::DriverTimerError::deadline && !r.response && io.error==ERROR_TIMEOUT && d.submissions==1);}
    {Clock::tick=0;Device d;Io io(d,challenge);auto frame=control::driver_timer_query(challenge).frame();std::size_t bytes=0;
        check(io.transfer(true,frame,100,bytes));check(!io.transfer(true,frame,100,bytes) && d.submissions==1);}
    {Clock::tick=0;Device d;Io io(d,challenge,[](const char*){throw std::runtime_error("record write failed");});
        const auto r=control::inspect_driver_timer(challenge,io);
        check(r.error==control::DriverTimerError::transfer && !r.response && d.submissions==0);}
    std::cout<<"Timer adapter whitelist, terminal state and failure retirement passed; fake transport only\n";return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}}
