#include "core/control_frames.hpp"
#include <algorithm>

namespace sl3::control {
Query::Query(Kind kind,std::uint8_t command,std::size_t reply) noexcept:kind_(kind),reply_bytes_(reply){
    frame_[0]=command;frame_[1]=0x1c;frame_[2]=0xc5;frame_[4]=1;
}
Query rate_query() noexcept{return Query(Kind::rate,0x30,2);}
Query audio_controls_query() noexcept{return Query(Kind::audio_controls,0x32,22);}
Query overloads_query() noexcept{return Query(Kind::overloads,0x35,6);}
Query driver_timer_query(const Challenge& challenge) noexcept{
    Query query(Kind::driver_timer,0x37,8);
    std::copy(challenge.begin(),challenge.end(),query.frame_.begin()+5);
    return query;
}
Event Exchange::fail(Error error) noexcept{
    finished_=true;error_=error;
    Event event;event.error=error;return event;
}
Event Exchange::accept(const std::uint8_t* data,std::size_t bytes) noexcept{
    if(finished_){Event event;event.error=Error::terminal_state;return event;}
    if(!data || bytes!=frame_bytes)return fail(Error::invalid_size);
    ++received_;
    Event event;event.command=data[0];
    if(data[0]==query_.frame()[0]){
        if(data[1]!=0x1c || data[2]!=0xc5 || data[3] || data[4]!=1)return fail(Error::invalid_tag);
        if(query_.kind()==Kind::rate){
            const auto rate=(unsigned(data[5])<<8)|data[6];
            if(rate!=44100 && rate!=48000)return fail(Error::unsupported_rate);
            rate_=rate;
        }
        event.outcome=Outcome::reply;event.payload_bytes=query_.reply_bytes();
        std::copy_n(data+5,event.payload_bytes,event.payload.begin());
        finished_=true;return event;
    }
    const std::uint8_t tag=data[0]==0x34?1:data[0]==0x38?2:data[0]==0x39?3:0;
    if(!tag)return fail(Error::unexpected_command);
    if(data[1] || data[2] || data[3] || data[4]!=tag)return fail(Error::invalid_tag);
    if(received_>=maximum_received_frames)return fail(Error::frame_limit);
    event.outcome=Outcome::notification;
    event.payload_bytes=data[0]==0x34?6:data[0]==0x38?3:4;
    std::copy_n(data+5,event.payload_bytes,event.payload.begin());
    return event;
}
const char* error_message(Error error) noexcept{
    switch(error){
    case Error::none:return "No control-frame error";
    case Error::invalid_size:return "Incomplete SL3 control frame";
    case Error::invalid_tag:return "Unrecognized SL3 control-frame tag";
    case Error::unexpected_command:return "Unexpected SL3 command while awaiting reply";
    case Error::unsupported_rate:return "Unrecognized rate; no audio submitted";
    case Error::frame_limit:return "No SL3 reply within four status frames";
    case Error::terminal_state:return "SL3 control exchange already finished";
    }
    return "Invalid SL3 control-frame error";
}
}
