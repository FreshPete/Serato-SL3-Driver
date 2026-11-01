#include "core/driver_timer_query.hpp"
#include <iostream>
#include <stdexcept>
#include <vector>
using namespace sl3::control;
void check(bool value){if(!value)throw std::runtime_error("Driver timer query check failed");}
struct Io final:DriverTimerIo {
    std::uint64_t tick=0;bool cancelled_=false,fail=false,short_frame=false,late=false,backwards=false,cancel_after=false;
    unsigned calls=0;Frame written{};std::vector<Frame> replies;
    std::uint64_t now_ms() noexcept override{return tick;}
    bool cancelled() noexcept override{return cancelled_;}
    bool transfer(bool output,Frame& frame,unsigned timeout,std::size_t& bytes) noexcept override {
        ++calls;check_budget=check_budget && timeout>0 && timeout<=(output?100u:300u);
        tick=backwards?0:late?1500:tick+1;if(cancel_after)cancelled_=true;
        bytes=short_frame?63:64;
        if(output)written=frame;else if(calls-2<replies.size())frame=replies[calls-2];else return false;
        return !fail;
    }
    bool check_budget=true;
};
Frame reply(){Frame result{};result[0]=0x37;result[1]=0x1c;result[2]=0xc5;result[4]=1;for(unsigned n=0;n<8;++n)result[5+n]=std::uint8_t(20+n);return result;}
Frame notification(){Frame result{};result[0]=0x38;result[4]=2;return result;}
int main(){try{
    const auto challenge=parse_driver_timer_challenge(L"0123456789aBcDeF");
    check(challenge.front()==1 && challenge.back()==0xef);
    for(const auto text:{L"",L"0123456789abcdef0",L"0123456789abcdeg",L" 123456789abcdef"}){
        bool rejected=false;try{parse_driver_timer_challenge(text);}catch(const std::invalid_argument&){rejected=true;}check(rejected);
    }
    {Io io;io.replies={notification(),notification(),notification(),reply()};const auto r=inspect_driver_timer(challenge,io);
        check(r.error==DriverTimerError::none && r.response && r.response->front()==20 && r.response->back()==27);
        check(r.write_attempts==1 && r.read_attempts==4 && io.check_budget && io.written==driver_timer_query(challenge).frame());}
    {Io io;io.replies={notification(),notification(),notification(),notification(),reply()};const auto r=inspect_driver_timer(challenge,io);
        check(r.error==DriverTimerError::exchange && r.exchange_error==Error::frame_limit && !r.response && io.calls==5);}
    for(unsigned kind=0;kind<6;++kind){Io io;io.replies={reply()};
        if(kind==0)io.fail=true;if(kind==1)io.short_frame=true;if(kind==2)io.late=true;
        if(kind==3)io.cancelled_=true;if(kind==4)io.cancel_after=true;if(kind==5){io.tick=10;io.backwards=true;}
        const auto r=inspect_driver_timer(challenge,io);check(r.error!=DriverTimerError::none && !r.response && io.calls<=1);}
    {Io io;auto bad=reply();bad[1]=0;io.replies={bad};const auto r=inspect_driver_timer(challenge,io);check(r.error==DriverTimerError::exchange && !r.response);}
    for(auto budget:{0u,1501u}){Io io;check(inspect_driver_timer(challenge,io,budget).error==DriverTimerError::invalid_budget && io.calls==0);}
    std::cout<<"Driver timer parser, notification budget, retirement/deadline failures passed; simulated only\n";return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}}
