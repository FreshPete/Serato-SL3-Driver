#include "core/control_frames.hpp"
#include "core/audio_controls.hpp"
#include "core/audio_controls_query.hpp"
#include "core/audio_control_selection.hpp"
#include "core/audio_control_selection_io.hpp"
#include "core/audio_control_selection_wire.hpp"
#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <utility>
#include <vector>
#include "control_transfer_io_tests.hpp"

namespace {
using namespace sl3::control;
void require(bool value,const char* reason){if(!value)throw std::runtime_error(reason);}
Frame reply(std::uint8_t command){
    Frame frame{};frame.fill(0xe7);frame[0]=command;frame[1]=0x1c;frame[2]=0xc5;frame[3]=0;frame[4]=1;return frame;
}
Frame notification(std::uint8_t command,std::uint8_t tag){
    auto frame=reply(command);frame[1]=frame[2]=frame[3]=0;frame[4]=tag;return frame;
}
void requests(){
    const Challenge challenge{{0x00,0xff,0x03,0x7a,0x80,0x11,0x22,0x33}};
    const std::array<Query,4> queries{{rate_query(),audio_controls_query(),overloads_query(),driver_timer_query(challenge)}};
    const std::array<std::uint8_t,4> commands{{0x30,0x32,0x35,0x37}};
    const std::array<std::size_t,4> replies{{2,22,6,8}};
    for(std::size_t i=0;i<queries.size();++i){
        const auto& frame=queries[i].frame();
        require(frame[0]==commands[i] && frame[1]==0x1c && frame[2]==0xc5 && !frame[3] && frame[4]==1,"Exact original command/tag");
        require(queries[i].reply_bytes()==replies[i],"Defined reply width");
        for(std::size_t n=5;n<frame.size();++n){
            const auto expected=i==3 && n<13?challenge[n-5]:std::uint8_t{0};
            require(frame[n]==expected,"Only challenge bytes may be nonzero in request payload");
        }
    }
}
void replies_and_notifications(){
    for(const auto rate:{44100u,48000u}){
        Exchange exchange(rate_query());auto frame=reply(0x30);
        frame[5]=std::uint8_t(rate>>8);frame[6]=std::uint8_t(rate);
        require(!exchange.rate_hz() && !exchange.finished(),"No inferred rate before reply");
        for(const auto command:{0x34,0x38,0x39}){
            const auto tag=command==0x34?1:command==0x38?2:3;
            const auto input=notification(std::uint8_t(command),std::uint8_t(tag));
            const auto event=exchange.accept(input.data(),input.size());
            const auto width=command==0x34?6u:command==0x38?3u:4u;
            require(event.outcome==Outcome::notification && event.payload_bytes==width && !exchange.finished(),"Distinct asynchronous notification tags");
            require(std::all_of(event.payload.begin()+width,event.payload.end(),[](auto x){return !x;}),"Unused notification tail is not exported");
        }
        const auto event=exchange.accept(frame.data(),frame.size());
        require(event.outcome==Outcome::reply && event.payload_bytes==2 && exchange.rate_hz()==rate,"Matching reply allowed in fourth frame");
        require(exchange.finished() && exchange.error()==Error::none && exchange.received_frames()==4,"Successful bounded terminal state");
        require(std::all_of(event.payload.begin()+2,event.payload.end(),[](auto x){return !x;}),"Uninterpreted rate-reply tail remains absent");
        const auto extra=exchange.accept(frame.data(),frame.size());
        require(extra.outcome==Outcome::failed && extra.error==Error::terminal_state && !extra.payload_bytes,"No duplicate reply consumption");
        require(exchange.error()==Error::none && exchange.received_frames()==4,"Terminal success is immutable");
    }
    for(const auto& query:{audio_controls_query(),overloads_query(),driver_timer_query(Challenge{})}){
        Exchange exchange(query);const auto frame=reply(query.frame()[0]);
        const auto event=exchange.accept(frame.data(),frame.size());
        require(event.outcome==Outcome::reply && event.payload_bytes==query.reply_bytes(),"Opaque controls/overload/device-response payload");
        require(std::all_of(event.payload.begin(),event.payload.begin()+event.payload_bytes,[](auto x){return x==0xe7;}),"Defined reply bytes preserved without fabricated interpretation");
        require(std::all_of(event.payload.begin()+event.payload_bytes,event.payload.end(),[](auto x){return !x;}),"Undefined reply tail excluded");
        require(!exchange.rate_hz(),"Other replies never establish a sample rate");
    }
}
void rejection(){
    auto rate=reply(0x30);rate[5]=0xac;rate[6]=0x44;
    for(std::size_t size=0;size<frame_bytes;++size){
        Exchange exchange(rate_query());const auto event=exchange.accept(rate.data(),size);
        require(event.error==Error::invalid_size && exchange.finished() && !exchange.rate_hz(),"Reject every short frame");
    }
    for(const auto size:{std::size_t{64},std::size_t{65}}){
        Exchange exchange(rate_query());require(exchange.accept(nullptr,size).error==Error::invalid_size,"Reject null/oversized frame before read");
    }
    {Exchange exchange(rate_query());require(exchange.accept(rate.data(),65).error==Error::invalid_size,"Oversize nonnull input is rejected without reading beyond frame");}
    for(std::size_t byte=1;byte<5;++byte){
        auto bad=rate;bad[byte]^=0xff;Exchange exchange(rate_query());
        require(exchange.accept(bad.data(),bad.size()).error==Error::invalid_tag,"Every reply tag byte checked");
        require(!exchange.rate_hz() && exchange.accept(rate.data(),rate.size()).error==Error::terminal_state,"Rejected exchange cannot recover into success");
    }
    for(unsigned command=0;command<256;++command){
        if(command==0x30 || command==0x34 || command==0x38 || command==0x39)continue;
        const auto bad=reply(std::uint8_t(command));Exchange exchange(rate_query());
        require(exchange.accept(bad.data(),bad.size()).error==Error::unexpected_command,"Other commands cannot masquerade as a rate reply");
    }
    for(const auto command:{0x34,0x38,0x39}){
        Exchange exchange(rate_query());const auto bad=reply(std::uint8_t(command));
        require(exchange.accept(bad.data(),bad.size()).error==Error::invalid_tag,"Notifications reject the ordinary reply tag");
    }
    {Exchange exchange(rate_query());auto bad=rate;bad[5]=0x77;bad[6]=0x00;
        require(exchange.accept(bad.data(),bad.size()).error==Error::unsupported_rate && !exchange.rate_hz(),"Unexpected rate rejected");}
    {Exchange exchange(rate_query());const auto status=notification(0x34,1);
        for(std::size_t i=0;i<maximum_received_frames-1;++i)require(exchange.accept(status.data(),status.size()).outcome==Outcome::notification,"Bounded notification consumption");
        require(exchange.accept(status.data(),status.size()).error==Error::frame_limit && exchange.received_frames()==4,"No unbounded status loop");
        require(exchange.accept(rate.data(),rate.size()).error==Error::terminal_state && !exchange.rate_hz(),"Late reply cannot extend budget");}
}
void audio_control_views(){
    // Distinct byte positions catch a wrong control-table stride or offset.
    auto frame=reply(0x32);
    const std::array<std::uint8_t,22> table{{0,2,0xff,0,0x91,0x92,0x93,0x94,1,7,0x95,0x96,0x97,0x98,0,15,0x99,0x9a,0x9b,0x9c,0xff,0xe1}};
    std::copy(table.begin(),table.end(),frame.begin()+5);
    Exchange exchange(audio_controls_query());const auto event=exchange.accept(frame.data(),frame.size());
    const auto view=audio_controls_snapshot(event);
    require(view.has_value() && view->raw==table,"Preserve complete control table, including unknown bytes");
    const auto first=view->input(0),second=view->input(1),third=view->input(2);
    require(first && first->phono_raw==0 && first->sensitivity_raw==0 && first->through_raw==1,"First original table tuple");
    require(second && second->phono_raw==2 && second->sensitivity_raw==7 && second->through_raw==0,"Second original table tuple");
    require(third && third->phono_raw==0xff && third->sensitivity_raw==15 && third->through_raw==0xff,"Third original table tuple");
    require(!first->phono_switch_nonzero() && first->through_nonzero() && second->phono_switch_nonzero()
            && !second->through_nonzero() && third->through_nonzero(),"Original nonzero flag interpretation, without losing raw values");
    require(first->original_ui_sensitivity_tenths_mv()==25u && second->original_ui_sensitivity_tenths_mv()==60u
            && third->original_ui_sensitivity_tenths_mv()==100u,"Original UI mV scale, not a sample multiplier");
    require(!view->input(3) && !view->input(std::size_t(-1)),"No out-of-range table reads");
    for(unsigned code=16;code<=255;++code){
        auto unknown=*view;unknown.raw[3]=std::uint8_t(code);
        const auto input=unknown.input(0);
        require(input && input->sensitivity_raw==code && !input->original_ui_sensitivity_tenths_mv(),"Unknown sensitivity preserved without clamping or guessed scale");
    }
    for(const auto size:{0u,3u,21u,23u,64u}){auto bad=event;bad.payload_bytes=size;require(!audio_controls_snapshot(bad),"Exact table width required");}
    {auto bad=event;bad.command=0x35;require(!audio_controls_snapshot(bad),"Overload reply is not an audio-control table");}
    {auto bad=event;bad.outcome=Outcome::notification;require(!audio_controls_snapshot(bad),"Notification cannot become a full snapshot");}
    {auto bad=event;bad.error=Error::invalid_tag;require(!audio_controls_snapshot(bad),"Failed exchange is not a state snapshot");}
    for(const auto command:{0x38,0x39}){
        auto status=notification(std::uint8_t(command),std::uint8_t(command==0x38?2:3));
        status[5]=0;status[6]=2;status[7]=0xff;status[8]=0xb7;
        Exchange pending(rate_query());const auto received=pending.accept(status.data(),status.size());
        const auto change=switch_notification(received);
        require(change && change->raw==std::array<std::uint8_t,3>{{0,2,0xff}},"Notification raw switch bytes preserved");
        require(change->kind==(command==0x38?SwitchKind::phono:SwitchKind::through),"Original notification-to-callback link");
        require(command==0x38?!change->extra:change->extra==0xb7,"Fourth through byte preserved but not assigned a new meaning");
        require(!audio_controls_snapshot(received),"Partial switch update cannot manufacture other controls");
        auto bad=received;bad.payload_bytes=command==0x38?4:3;require(!switch_notification(bad),"Notification width is command-specific");
        bad=received;bad.outcome=Outcome::reply;require(!switch_notification(bad),"Ordinary reply is not asynchronous switch state");
        bad=received;bad.error=Error::invalid_tag;require(!switch_notification(bad),"No typed notification on an exchange error");
    }
    auto status=notification(0x34,1);Exchange pending(rate_query());
    require(!switch_notification(pending.accept(status.data(),status.size())),"Overload notification is not switch state");
}
void audio_control_selection(){
    using Phase=AudioControlPhase;using Failure=AudioControlError;
    const std::array<unsigned,3> sensitivity{{3,9,15}},through{{8,14,20}};
    for(const auto setting:{AudioControlSetting::sensitivity,AudioControlSetting::through}){
        for(unsigned group=0;group<3;++group)for(unsigned value=0;value<(setting==AudioControlSetting::sensitivity?16u:2u);++value){
            const auto index=setting==AudioControlSetting::sensitivity?sensitivity[group]:through[group];
            AudioControlSelection selection(setting,group,value);Frame request{};
            require(selection.take_request(request) && request==audio_controls_query().frame(),"Inspect before considering any setting write");
            const auto initial=reply(0x32);selection.accept(initial.data(),initial.size());
            require(selection.initial_controls() && selection.phase()==Phase::set_ready && !selection.device_may_have_changed(),"Initial table preserved; preparing write alone changes nothing");
            Frame expected{};expected[0]=0x33;expected[1]=0x1c;expected[2]=0xc5;expected[4]=1;
            expected[5]=std::uint8_t(index);expected[6]=1;expected[7]=std::uint8_t(value);
            require(selection.take_request(request) && request==expected && selection.device_may_have_changed(),"Exact indexed single-byte command and conservative change flag");
            const auto unchanged=request;
            require(!selection.take_request(request) && request==unchanged,"No duplicate setter while awaiting receipt");
            auto receipt=reply(0x33);receipt[5]=0xa5;receipt[6]=0x5a;
            selection.accept(receipt.data(),receipt.size());
            require(selection.acknowledgement()==std::optional<std::array<std::uint8_t,2>>({{0xa5,0x5a}}) &&
                    !selection.verified_controls() && selection.phase()==Phase::verify_ready,"Opaque acknowledgement cannot certify new control state");
            require(selection.take_request(request) && request==audio_controls_query().frame(),"Read back controls after receipt");
            auto final=reply(0x32);final[5+index]=std::uint8_t(value);final[5]=0x37;
            selection.accept(final.data(),final.size());
            require(selection.phase()==Phase::complete && selection.error()==Failure::none && selection.received_frames()==3 &&
                    selection.verified_controls()->raw[index]==value && selection.verified_controls()->raw[0]==0x37 &&
                    selection.initial_controls()->raw[0]==0xe7,"Verify only targeted setting; preserve independent observed table changes");
            selection.abort();require(selection.phase()==Phase::complete && !selection.take_request(request),"Completed selection cannot retry or roll back");
            const auto late=selection.accept(final.data(),final.size());
            require(late.error==Error::terminal_state && selection.phase()==Phase::complete,"Late frame cannot alter completed evidence");
        }
    }
    for(const auto setting:{AudioControlSetting::sensitivity,AudioControlSetting::through}){
        AudioControlSelection selection(setting,1,1);Frame request{};selection.take_request(request);
        auto already=reply(0x32);already[5+(setting==AudioControlSetting::sensitivity?9:14)]=1;
        selection.accept(already.data(),already.size());
        require(selection.phase()==Phase::complete && selection.verified_controls() && !selection.acknowledgement() &&
                !selection.device_may_have_changed() && !selection.take_request(request),"Already selected byte needs one getter and no setting write");
    }
    for(unsigned code=16;code<=256;++code){AudioControlSelection invalid(AudioControlSetting::sensitivity,0,code);Frame output{};
        require(invalid.error()==Failure::invalid_target && !invalid.take_request(output),"Do not encode sensitivity outside original UI range");}
    for(const auto group:{std::size_t(3),std::size_t(-1)}){AudioControlSelection invalid(AudioControlSetting::through,group,1);Frame output{};
        require(invalid.error()==Failure::invalid_target && !invalid.take_request(output),"Reject unverified groups");}
    {AudioControlSelection invalid(AudioControlSetting::through,0,2);Frame output{};require(!invalid.take_request(output),"No nonbinary through setting");}
    {AudioControlSelection invalid(static_cast<AudioControlSetting>(77),0,1);Frame output{};require(!invalid.take_request(output),"Unknown setting is not phono or another table field");}
    for(unsigned stop=0;stop<6;++stop){
        AudioControlSelection selection(AudioControlSetting::through,0,1);Frame request{};
        for(unsigned step=0;step<stop;++step){
            if(step%2==0)require(selection.take_request(request),"Take next bounded stage");
            else{auto response=reply(step==3?0x33:0x32);selection.accept(response.data(),response.size());}
        }
        const auto changed=selection.device_may_have_changed();selection.abort();const auto saved=request;
        require(selection.phase()==Phase::failed && selection.error()==Failure::aborted && changed==(stop>=3) &&
                !selection.verified_controls() && !selection.take_request(request) && request==saved,"Abort preserves uncertainty and never emits compensating write");
        selection.abort();require(selection.error()==Failure::aborted,"Failed evidence is terminal");
    }
    {AudioControlSelection selection(AudioControlSetting::through,0,1);Frame request{};
        require(selection.accept(nullptr,0).error==Error::terminal_state && !selection.take_request(request),"Reject reply before taking request");}
    for(unsigned fault=0;fault<3;++fault){
        AudioControlSelection selection(AudioControlSetting::through,0,1);Frame request{};selection.take_request(request);
        auto bad=reply(fault==0?0x33:0x32);if(fault==1)bad[1]=0;
        selection.accept(bad.data(),fault==2?63:bad.size());
        require(selection.error()==Failure::exchange && !selection.initial_controls() && !selection.device_may_have_changed(),"Invalid inspection never prepares a write");
    }
    {AudioControlSelection selection(AudioControlSetting::sensitivity,2,7);Frame request{};
        for(unsigned stage=0;stage<3;++stage){
            require(selection.take_request(request),"Bounded notification-interleaved stage");
            for(const auto command:{0x34,0x38,0x39}){const auto status=notification(std::uint8_t(command),std::uint8_t(command==0x34?1:command==0x38?2:3));
                require(selection.accept(status.data(),status.size()).outcome==Outcome::notification,"Notifications remain separate from transaction replies");}
            auto response=reply(stage==1?0x33:0x32);if(stage==2)response[5+15]=7;
            selection.accept(response.data(),response.size());
        }
        require(selection.phase()==Phase::complete && selection.received_frames()==12,"At most three requests and twelve received frames");}
    for(unsigned stage=0;stage<3;++stage){
        for(const bool flood:{false,true}){
            AudioControlSelection selection(AudioControlSetting::through,0,1);Frame request{};
            for(unsigned step=0;step<stage*2;++step){
                if(step%2==0)selection.take_request(request);
                else{auto response=reply(step==3?0x33:0x32);selection.accept(response.data(),response.size());}
            }
            selection.take_request(request);
            if(flood){const auto status=notification(0x38,2);for(unsigned i=0;i<4;++i)selection.accept(status.data(),status.size());}
            else{auto bad=reply(stage==1?0x33:0x32);bad[1]=0;selection.accept(bad.data(),bad.size());}
            require(selection.error()==Failure::exchange && selection.exchange_error()==(flood?Error::frame_limit:Error::invalid_tag) &&
                    selection.device_may_have_changed()==(stage!=0) && !selection.verified_controls() && !selection.take_request(request),
                    "Every stage has a finite notification/error budget and preserves possible-write uncertainty");
        }
    }
    {AudioControlSelection selection(AudioControlSetting::through,0,1);Frame request{};
        selection.take_request(request);auto table=reply(0x32);selection.accept(table.data(),table.size());
        selection.take_request(request);auto receipt=reply(0x33);selection.accept(receipt.data(),receipt.size());
        selection.take_request(request);selection.accept(table.data(),table.size());
        require(selection.error()==Failure::readback_mismatch && selection.device_may_have_changed() &&
                selection.acknowledgement() && selection.observed_controls() && !selection.verified_controls() && !selection.take_request(request),
                "Receipt followed by wrong readback stays failed/uncertain without retry or rollback");}
}
struct ControlsIo final:AudioControlsIo {
    std::vector<Frame> incoming;
    std::vector<unsigned> timeouts;
    std::array<unsigned,5> advances{{1,1,1,1,1}};
    unsigned calls=0,reads=0,fail_at=99,short_at=99,cancel_at=99,regress_at=99;
    std::uint64_t clock=100;bool bad_write=false;
    ControlsIo(){
        incoming={notification(0x34,1),notification(0x38,2),notification(0x39,3),reply(0x32)};
    }
    std::uint64_t now_ms() noexcept override{return clock;}
    bool cancelled() noexcept override{return calls>=cancel_at;}
    bool transfer(bool output,Frame& frame,unsigned timeout,std::size_t& bytes) noexcept override{
        timeouts.push_back(timeout);const auto index=calls++;
        clock=index==regress_at?99:clock+advances[index];
        if(output){if(frame!=audio_controls_query().frame()){bad_write=true;return false;}}
        else{if(reads>=incoming.size())return false;frame=incoming[reads++];}
        bytes=index==short_at?63:64;return index!=fail_at;
    }
};
void bounded_controls_query(){
    {
        ControlsIo io;const auto result=inspect_audio_controls(io);
        require(result.error==ControlsError::none && result.controls && result.write_attempts==1 && result.read_attempts==4
                && io.calls==5 && !io.bad_write && result.controls->raw[21]==0xe7,"One exact getter accepts three notifications and fourth-frame reply");
    }
    for(unsigned operation=0;operation<5;++operation){
        for(bool partial:{false,true}){
            ControlsIo io;if(partial)io.short_at=operation;else io.fail_at=operation;
            const auto result=inspect_audio_controls(io);
            require(result.error==ControlsError::transfer && !result.controls && io.calls==operation+1,"Every transfer/short-completion failure stops without a retry or snapshot");
        }
        ControlsIo io;io.cancel_at=operation+1;const auto result=inspect_audio_controls(io);
        require(result.error==ControlsError::cancelled && !result.controls && io.calls==operation+1,"Post-transfer cancellation never yields a state snapshot");
    }
    {ControlsIo io;io.cancel_at=0;require(inspect_audio_controls(io).error==ControlsError::cancelled && !io.calls,"Pre-request cancellation sends nothing");}
    for(unsigned budget:{0u,1501u}){ControlsIo io;require(inspect_audio_controls(io,budget).error==ControlsError::invalid_budget && !io.calls,"Invalid budgets send nothing");}
    {ControlsIo io;io.advances={{90,100,100,40,1}};const auto result=inspect_audio_controls(io,350);
        require(result.controls && io.timeouts==std::vector<unsigned>({100,260,160,60,20}),"Every timeout shrinks against one total deadline");}
    {ControlsIo io;io.advances[4]=10;const auto result=inspect_audio_controls(io,14);
        require(result.error==ControlsError::deadline && !result.controls && io.calls==5,"A correctly framed reply at the deadline is rejected");}
    {ControlsIo io;io.regress_at=0;const auto result=inspect_audio_controls(io);
        require(result.error==ControlsError::deadline && !result.controls && io.calls==1,"Clock regression prevents another operation");}
    {ControlsIo io;io.incoming[3]=notification(0x38,2);const auto result=inspect_audio_controls(io);
        require(result.error==ControlsError::exchange && result.exchange_error==Error::frame_limit && !result.controls && io.calls==5,"Notification flood cannot extend the four-frame budget");}
    {ControlsIo io;io.incoming[0]=reply(0x30);const auto result=inspect_audio_controls(io);
        require(result.error==ControlsError::exchange && !result.controls && io.calls==2,"Unrelated reply terminates the control query");}
    {ControlsIo io;io.incoming[0]=reply(0x32);io.incoming[0][1]=0;const auto result=inspect_audio_controls(io);
        require(result.error==ControlsError::exchange && result.exchange_error==Error::invalid_tag && !result.controls,"Wrong getter reply tag cannot yield controls");}
}
struct SelectionIo final:AudioControlsIo {
    std::uint64_t tick=100;unsigned calls=0,cancel_checks=0,cancel_check=99,fail_at=99,short_at=99,expire_at=99,regress_at=99;
    std::vector<Frame> incoming,writes;std::vector<unsigned> timeouts;
    std::size_t next=0;
    SelectionIo(){auto before=reply(0x32),after=reply(0x32);before[5+8]=0;after[5+8]=1;
        incoming={before,reply(0x33),after};}
    std::uint64_t now_ms() noexcept override{return tick;}
    bool cancelled() noexcept override{return ++cancel_checks==cancel_check;}
    bool transfer(bool output,Frame& frame,unsigned timeout,std::size_t& bytes) noexcept override{
        const auto at=calls++;timeouts.push_back(timeout);++tick;
        if(output)writes.push_back(frame);
        else if(next<incoming.size())frame=incoming[next++];
        else return false;
        if(at==expire_at)tick+=control_selection_budget_ms;
        if(at==regress_at)tick=99;
        bytes=at==short_at?63:frame_bytes;return at!=fail_at;
    }
};
void bounded_control_selection(){
    const auto run=[](SelectionIo& io,unsigned budget=control_selection_budget_ms){
        const auto result=select_audio_control(io,AudioControlSetting::through,0,1,budget);
        const selection_wire::Reply evidence{{AudioControlSetting::through,0,1},result,1168};
        const auto bytes=selection_wire::encode_reply(evidence);
        const auto decoded=selection_wire::decode_reply(bytes.data(),bytes.size(),evidence.target);
        const auto same=[](const auto& a,const auto& b){return bool(a)==bool(b) && (!a || a->raw==b->raw);};
        const auto& d=decoded.selection;
        require(selection_wire::encode_reply(decoded)==bytes && decoded.native_error==1168,
                "Every success/fault/cancel/deadline observation survives the checked wire format");
        require(d.error==result.error && d.selection_error==result.selection_error && d.exchange_error==result.exchange_error &&
            d.phase==result.phase && d.write_attempts==result.write_attempts && d.read_attempts==result.read_attempts &&
            d.setter_attempts==result.setter_attempts && d.device_may_have_changed==result.device_may_have_changed &&
            d.acknowledgement==result.acknowledgement && same(d.initial,result.initial) && same(d.observed,result.observed) &&
            same(d.verified,result.verified),"Original observations, opaque bytes and failure fields survive without normalization");return result;};
    {SelectionIo io;const auto result=run(io);
        require(result.error==SelectionIoError::none && result.phase==AudioControlPhase::complete && result.initial &&
                result.observed && result.verified && result.acknowledgement && result.device_may_have_changed &&
                result.write_attempts==3 && result.setter_attempts==1 && result.read_attempts==3 && io.calls==6,
                "Bounded I/O must verify a single write through a fresh getter");
        require(io.writes[0]==audio_controls_query().frame() && io.writes[1][0]==0x33 && io.writes[1][5]==8 &&
                io.writes[1][6]==1 && io.writes[1][7]==1 && io.writes[2]==audio_controls_query().frame(),"Only exact selected setter between getters");
        require(result.initial->raw[8]==0 && result.verified->raw[8]==1 && (*result.acknowledgement)[0]==0xe7,
                "Initial, opaque receipt and verified state remain distinct");}
    {SelectionIo io;io.incoming[0][5+8]=1;const auto result=run(io);
        require(result.error==SelectionIoError::none && result.verified && !result.device_may_have_changed &&
                !result.acknowledgement && !result.setter_attempts && io.calls==2,"Already selected value is a read-only no-op");}
    for(unsigned at=0;at<6;++at){
        for(bool short_transfer:{false,true}){SelectionIo io;if(short_transfer)io.short_at=at;else io.fail_at=at;
            const auto result=run(io);
            require(result.error==SelectionIoError::transfer && !result.verified && io.calls==at+1 &&
                    result.device_may_have_changed==(at>=2) && bool(result.initial)==(at>=2) &&
                    bool(result.acknowledgement)==(at>=4),"Failed/short I/O preserves stage evidence and never retries");}}
    for(unsigned cancel=1;cancel<=12;++cancel){SelectionIo io;io.cancel_check=cancel;const auto result=run(io);
        require(result.error==SelectionIoError::cancelled && !result.verified && result.device_may_have_changed==(cancel>=6) &&
                result.setter_attempts<=1 && io.calls<=6,"Cancellation before/after every transfer preserves possible-write uncertainty");}
    for(unsigned at=0;at<6;++at){
        for(bool regression:{false,true}){SelectionIo io;if(regression)io.regress_at=at;else io.expire_at=at;
            const auto result=run(io);
            require(result.error==SelectionIoError::deadline && !result.verified && io.calls==at+1 &&
                    result.device_may_have_changed==(at>=2),"Expired/regressing completion cannot establish verified state");}}
    for(unsigned budget:{0u,control_selection_budget_ms+1}){SelectionIo io;
        require(run(io,budget).error==SelectionIoError::invalid_budget && !io.calls && !io.cancel_checks,"Invalid budget sends nothing");}
    {SelectionIo io;const auto result=select_audio_control(io,AudioControlSetting::through,3,1);
        require(result.error==SelectionIoError::invalid_target && !io.calls && !result.device_may_have_changed,"Invalid selection sends nothing");}
    {SelectionIo io;const auto result=run(io,5);
        require(result.error==SelectionIoError::deadline && io.timeouts==std::vector<unsigned>({5,4,3,2,1}) &&
                result.device_may_have_changed && !result.verified,"All stages share one shrinking budget");}
    {SelectionIo io;io.incoming[2][5+8]=0;const auto result=run(io);
        require(result.error==SelectionIoError::readback_mismatch && result.observed && result.observed->raw[8]==0 &&
                result.initial && result.acknowledgement && !result.verified && result.device_may_have_changed && io.calls==6,
                "Mismatched readback never rolls back or claims success");}
    {SelectionIo io;io.incoming[1]=reply(0x32);const auto result=run(io);
        require(result.error==SelectionIoError::protocol && result.selection_error==AudioControlError::exchange &&
                result.initial && !result.acknowledgement && !result.verified && result.device_may_have_changed && io.calls==4,
                "Wrong receipt command cannot authorize verification or another setter");}
    {SelectionIo io;io.incoming.clear();
        for(unsigned stage=0;stage<3;++stage){
            for(auto command:{0x34,0x38,0x39})io.incoming.push_back(notification(std::uint8_t(command),std::uint8_t(command==0x34?1:command==0x38?2:3)));
            auto response=reply(stage==1?0x33:0x32);response[5+8]=stage==2?1:0;io.incoming.push_back(response);}
        const auto result=run(io);
        require(result.error==SelectionIoError::none && result.verified && io.calls==15 && result.read_attempts==12 &&
                result.write_attempts==3 && result.setter_attempts==1,"Maximum notification interleave still terminates within fifteen transfers");}
}
void selection_evidence_wire(){
    namespace wire=selection_wire;
    const auto rejected=[](const auto& call){try{call();}catch(const std::invalid_argument&){return;}throw std::runtime_error("Invalid selection wire record was accepted");};
    unsigned targets=0;
    for(auto setting:{AudioControlSetting::sensitivity,AudioControlSetting::through}){
        for(unsigned group=0;group<3;++group)for(unsigned value=0;value<=(setting==AudioControlSetting::sensitivity?15u:1u);++value){
            const wire::Target target{setting,group,value};const auto request=wire::encode_request(target);
            const auto read=wire::decode_request(request.data(),request.size());
            require(read.setting==setting && read.group==group && read.value==value && request[0]==0x53 && request[1]==0x4c &&
                request[2]==0x33 && request[3]==0x53 && request[4]==1,"Explicit little-endian request and exact target identity");
            const auto fields=input_control_indexes[group];const auto field=setting==AudioControlSetting::sensitivity?fields.sensitivity:fields.through;
            for(bool noop:{false,true}){
                SelectionIo io;io.incoming[0][5+field]=std::uint8_t(noop?value:value?0:1);io.incoming[2][5+field]=std::uint8_t(value);
                const auto result=select_audio_control(io,setting,group,value);
                const auto bytes=wire::encode_reply({target,result,0xabcdef01});
                const auto decoded=wire::decode_reply(bytes.data(),bytes.size(),target);
                require(decoded.selection.verified && decoded.selection.verified->raw[field]==value &&
                    decoded.selection.setter_attempts==(noop?0u:1u) && decoded.native_error==0xabcdef01 &&
                    decoded.selection.initial->raw==result.initial->raw && decoded.selection.observed->raw==result.observed->raw &&
                    decoded.selection.verified->raw==result.verified->raw && decoded.selection.acknowledgement==result.acknowledgement &&
                    wire::encode_reply(decoded)==bytes,"All 54 targets preserve setter/no-op observations and unknown bytes");
                auto wrong=target;wrong.group=(group+1)%3;rejected([&]{wire::decode_reply(bytes.data(),bytes.size(),wrong);});
            }
            ++targets;
        }
    }
    require(targets==54,"All original offered sensitivity/through targets covered");
    const wire::Target target{AudioControlSetting::through,0,1};
    SelectionIo io;const auto success=select_audio_control(io,target.setting,target.group,target.value);
    const auto valid=wire::encode_reply({target,success,1168});
    for(const auto wrong:std::array<wire::Target,2>{{{AudioControlSetting::sensitivity,0,1},{AudioControlSetting::through,0,0}}})
        rejected([&]{wire::decode_reply(valid.data(),valid.size(),wrong);});
    auto request=wire::encode_request(target);
    for(std::size_t size=0;size<160;++size){
        if(size!=wire::request_bytes)rejected([&]{wire::decode_request(request.data(),size);});
        if(size!=wire::reply_bytes)rejected([&]{wire::decode_reply(valid.data(),size,target);});
    }
    rejected([&]{wire::decode_request(nullptr,wire::request_bytes);});
    rejected([&]{wire::decode_reply(nullptr,wire::reply_bytes,target);});
    for(const auto bad:std::array<std::pair<unsigned,std::uint32_t>,6>{{{0,0},{1,2},{2,2},{3,3},{4,2},{5,1}}}){
        auto bytes=request;wire::detail::put(bytes,bad.first,bad.second);rejected([&]{wire::decode_request(bytes.data(),bytes.size());});
    }
    for(const auto bad:std::array<std::pair<unsigned,std::uint32_t>,15>{{{0,0},{1,2},{2,2},{3,3},{4,2},{5,99},{6,99},{7,99},
            {8,unsigned(AudioControlPhase::inspect_wait)},{9,4},{10,13},{11,2},{12,63},{13,1},{14,1}}}){
        auto bytes=valid;wire::detail::put(bytes,bad.first,bad.second);rejected([&]{wire::decode_reply(bytes.data(),bytes.size(),target);});
    }
    for(auto offset:{64u+8,86u+8,108u+8,108u,48u}){
        auto bytes=valid;bytes[offset]^=1;rejected([&]{wire::decode_reply(bytes.data(),bytes.size(),target);});
    }
    {SelectionIo stopped;stopped.fail_at=2;auto failed=select_audio_control(stopped,target.setting,target.group,target.value);
        const auto bytes=wire::encode_reply({target,failed,31});const auto read=wire::decode_reply(bytes.data(),bytes.size(),target);
        require(read.selection.device_may_have_changed && read.selection.initial && !read.selection.acknowledgement &&
            !read.selection.verified && read.selection.error==SelectionIoError::transfer,"A failed setter preserves uncertainty without invented receipt/readback");
        failed.device_may_have_changed=false;rejected([&]{wire::encode_reply({target,failed,31});});}
    {SelectionIo noop;noop.incoming[0][5+8]=1;const auto result=select_audio_control(noop,target.setting,target.group,target.value);
        auto bytes=wire::encode_reply({target,result,0});bytes[131]=1;
        rejected([&]{wire::decode_reply(bytes.data(),bytes.size(),target);});}
    {SelectionIo cancelled;cancelled.cancel_check=1;const auto result=select_audio_control(cancelled,target.setting,target.group,target.value);
        auto bytes=wire::encode_reply({target,result,0});bytes[64]=1;
        rejected([&]{wire::decode_reply(bytes.data(),bytes.size(),target);});}
    {auto bad=success;bad.error=SelectionIoError::transfer;rejected([&]{wire::encode_reply({target,bad,0});});}
    {auto bad=success;bad.write_attempts=2;rejected([&]{wire::encode_reply({target,bad,0});});}
    rejected([&]{wire::encode_request({AudioControlSetting::sensitivity,0,16});});
    rejected([&]{wire::encode_request({AudioControlSetting(99),0,0});});
}
}
int main(){try{requests();replies_and_notifications();rejection();audio_control_views();audio_control_selection();bounded_controls_query();bounded_control_selection();selection_evidence_wire();
#ifdef _WIN32
native_control_io_tests::run();
#endif
std::cout<<"Bounded SL3 control engines, checked setting evidence and injected I/O checks passed; no USB operations\n";return 0;}
catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}}
