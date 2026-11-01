#include "core/rate_selection.hpp"
#include "core/rate_diagnostic.hpp"
#include "core/rate_selection_wire.hpp"
#include "core/rate_test_grant.hpp"
#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <type_traits>

namespace {
using namespace sl3::control;
void require(bool value,const char* text){if(!value)throw std::runtime_error(text);}
Frame reply(unsigned command,unsigned payload){
    Frame frame{};frame.fill(0xe7);frame[0]=std::uint8_t(command);
    frame[1]=0x1c;frame[2]=0xc5;frame[3]=0;frame[4]=1;
    frame[5]=std::uint8_t(payload>>8);frame[6]=std::uint8_t(payload);return frame;
}
void feed(RateSelection& change,unsigned command,unsigned payload){
    for(unsigned tag=1;tag<=3;++tag){
        auto status=reply(tag==1?0x34:tag==2?0x38:0x39,0xffff);
        status[1]=status[2]=status[3]=0;status[4]=std::uint8_t(tag);
        require(change.accept(status.data(),status.size()).outcome==Outcome::notification,"Three notifications allowed before each reply, at most twelve received frames per transaction");
    }
    const auto frame=reply(command,payload);
    require(change.accept(frame.data(),frame.size()).outcome==Outcome::reply,"Defined reply accepted");
}
void request(RateSelection& change,unsigned command,unsigned payload){
    Frame frame{};require(change.take_request(frame),"Request available exactly once");
    require(frame[0]==command && frame[1]==0x1c && frame[2]==0xc5 && frame[3]==0 && frame[4]==1,"Exact command/tag");
    require(frame[5]==std::uint8_t(payload>>8) && frame[6]==std::uint8_t(payload),"Big-endian payload");
    require(std::all_of(frame.begin()+7,frame.end(),[](auto x){return !x;}),"No unrelated write bytes");
    Frame sentinel{};sentinel.fill(0x5a);
    require(!change.take_request(sentinel) && std::all_of(sentinel.begin(),sentinel.end(),[](auto x){return x==0x5a;}),"No duplicate request or output mutation");
}
void terminal(RateSelection& change){
    const auto phase=change.phase();const auto error=change.error();
    const auto verified=change.verified_rate_hz();const auto possible=change.device_may_have_changed();
    const auto readback=change.readback_rate_hz();const auto ack=change.acknowledgement_received();
    const auto frame=reply(0x30,48000);Frame output{};
    require(!change.take_request(output) && change.accept(frame.data(),frame.size()).error==Error::terminal_state,"No terminal request or reply revival");
    change.abort();require(change.phase()==phase && change.error()==error && change.verified_rate_hz()==verified && change.device_may_have_changed()==possible,"Terminal status immutable");
    require(change.readback_rate_hz()==readback && change.acknowledgement_received()==ack,"Terminal observation history immutable");
}
void success(){
    static_assert(!std::is_copy_constructible<RateSelection>::value && !std::is_move_constructible<RateSelection>::value,"Transaction cannot be cloned into duplicate writes");
    for(const auto target:{44100u,48000u}){
        {RateSelection same(target);request(same,0x30,0);feed(same,0x30,target);
         require(same.phase()==RatePhase::complete && same.initial_rate_hz()==target && same.verified_rate_hz()==target && !same.device_may_have_changed(),"Already selected rate submits no setter");
         require(!same.readback_rate_hz() && !same.acknowledgement_received(),"No-op initial getter does not fabricate setter acknowledgement or second getter");terminal(same);}
        RateSelection change(target);const auto initial=target==44100?48000u:44100u;
        request(change,0x30,0);feed(change,0x30,initial);
        require(change.phase()==RatePhase::set_ready && change.initial_rate_hz()==initial && !change.device_may_have_changed(),"Prepare change after independent inspection");
        request(change,0x31,target);require(change.device_may_have_changed(),"Uncertain effect begins when setter leaves owner");
        feed(change,0x31,0xffff); // Original consumes opaque bytes, not an echoed rate.
        require(change.phase()==RatePhase::verify_ready && !change.verified_rate_hz(),"Acknowledgement alone never proves selected rate");
        require(change.acknowledgement_received() && !change.readback_rate_hz(),"Accepted opaque acknowledgement is separate from verification getter");
        request(change,0x30,0);feed(change,0x30,target);
        require(change.phase()==RatePhase::complete && change.verified_rate_hz()==target && change.device_may_have_changed(),"Fresh readback verifies target without erasing write history");
        require(change.readback_rate_hz()==target,"Successful verification preserves actual getter");terminal(change);
    }
}
void failures(){
    for(const auto target:{0u,1u,44099u,44101u,47999u,48001u,96000u,0xffffffffu}){
        RateSelection invalid(target);require(invalid.phase()==RatePhase::failed && invalid.error()==RateError::invalid_target && !invalid.device_may_have_changed(),"Only two supported targets");terminal(invalid);
    }
    for(unsigned stop=0;stop<6;++stop){
        RateSelection change(48000);
        if(stop>=1)request(change,0x30,0);
        if(stop>=2)feed(change,0x30,44100);
        if(stop>=3)request(change,0x31,48000);
        if(stop>=4)feed(change,0x31,0);
        if(stop>=5)request(change,0x30,0);
        change.abort();require(change.error()==RateError::aborted && !change.verified_rate_hz() && change.device_may_have_changed()==(stop>=3),"Cancellation preserves uncertainty at every boundary");terminal(change);
        require(change.acknowledgement_received()==(stop>=4) && !change.readback_rate_hz(),"Cancellation preserves only already accepted observations");
    }
    for(unsigned stage=0;stage<3;++stage){
        for(unsigned fault=0;fault<5;++fault){
            RateSelection change(48000);request(change,0x30,0);
            if(stage>=1){feed(change,0x30,44100);request(change,0x31,48000);}
            if(stage>=2){feed(change,0x31,0);request(change,0x30,0);}
            auto input=reply(stage==1?0x31:0x30,stage==2?48000:44100);
            if(fault==0)input[1]^=0xff;
            if(fault==1)input[0]=0x33;
            if(fault==2){input[0]=0x30;input[5]=0x77;input[6]=0;}
            if(fault==3){input[0]=0x34;input[1]=input[2]=input[3]=0;input[4]=1;}
            if(fault==3){
                for(unsigned i=0;i<3;++i)require(change.accept(input.data(),input.size()).outcome==Outcome::notification,"Bounded notification allowance per exchange");
            }
            // Opaque setter payloads are accepted only with command 0x31;
            // fourth notifications and short frames fail in every stage.
            const auto event=change.accept(input.data(),fault==4?63:input.size());
            if(stage==1 && fault==2)require(event.outcome==Outcome::failed,"Getter cannot replace setter acknowledgement");
            require(change.phase()==RatePhase::failed && change.error()==RateError::exchange && !change.verified_rate_hz() && change.device_may_have_changed()==(stage>=1),"Malformed exchange cannot continue or erase possible write");terminal(change);
        }
    }
    {RateSelection mismatch(48000);request(mismatch,0x30,0);feed(mismatch,0x30,44100);request(mismatch,0x31,48000);feed(mismatch,0x31,48000);request(mismatch,0x30,0);feed(mismatch,0x30,44100);
     require(mismatch.error()==RateError::readback_mismatch && !mismatch.verified_rate_hz() && mismatch.device_may_have_changed(),"Acknowledged setter with different supported readback fails");
     require(mismatch.readback_rate_hz()==44100 && mismatch.acknowledgement_received(),"Mismatch retains actual returned clock without verification");terminal(mismatch);}
    {RateSelection unordered(48000);const auto frame=reply(0x30,48000);unordered.accept(frame.data(),frame.size());require(unordered.phase()==RatePhase::failed && !unordered.device_may_have_changed(),"No reply accepted before request ownership");terminal(unordered);}
}
struct FakeIo final:RateIo {
    std::uint64_t clock=1000;unsigned elapsed=1,operations=0,fail_at=99,cancel_at=99,short_at=99;
    unsigned current=44100,command=0,notifications=0,notifications_per_reply=3,setters=0;
    unsigned last_timeout=0;bool malformed_ack=false,mismatch=false,rollback_clock=false;
    std::uint64_t now_ms() noexcept override{return clock;}
    bool cancelled() noexcept override{return operations==cancel_at;}
    bool transfer(bool output,Frame& frame,unsigned timeout,std::size_t& bytes) noexcept override{
        const auto index=operations++;last_timeout=timeout;bytes=index==short_at?63:64;
        clock=rollback_clock?clock-1:clock+elapsed;
        if(output){
            command=frame[0];notifications=notifications_per_reply;
            if(command==0x31){++setters;if(!mismatch)current=(unsigned(frame[5])<<8)|frame[6];}
        }else if(notifications){
            frame=reply(0x34,0);frame[1]=frame[2]=frame[3]=0;frame[4]=1;--notifications;
        }else frame=reply(malformed_ack && command==0x31?0x30:command,command==0x31?0xffff:current);
        return index!=fail_at;
    }
};
template<class F> void rejects(F action){
    bool refused=false;try{action();}catch(const std::invalid_argument&){refused=true;}
    require(refused,"Malformed or inconsistent rate wire evidence must fail closed");
}
RateDiagnosticResult checked_diagnose(unsigned target,RateIo& io,unsigned budget=3000){
    const auto result=diagnose_rate(target,io,budget);
    if(target==44100 || target==48000){
        const rate_wire::Reply original{target,result,0x87654321u};
        const auto bytes=rate_wire::encode_reply(original);
        const auto decoded=rate_wire::decode_reply(bytes.data(),bytes.size(),target);
        require(rate_wire::encode_reply(decoded)==bytes && decoded.native_error==original.native_error,
            "Actual runner success/fault history roundtrips canonically with native error");
    }
    return result;
}
void wire(){
    using namespace rate_wire;
    for(const auto target:{44100u,48000u}){
        const auto request=encode_request(target);
        require(decode_request(request.data(),request.size())==target,"Both explicit rate targets roundtrip");
        for(std::size_t n=0;n<request_bytes;++n){
            auto bad=request;bad[n]^=0x80;rejects([&]{decode_request(bad.data(),bad.size());});
        }
        rejects([&]{decode_request(nullptr,request.size());});
        rejects([&]{decode_request(request.data(),request.size()-1);});
        rejects([&]{decode_request(request.data(),request.size()+1);});
        FakeIo io;io.current=target==44100?48000:44100;
        const auto result=checked_diagnose(target,io);
        const Reply good{target,result,0};const auto bytes=encode_reply(good);
        rejects([&]{decode_reply(bytes.data(),bytes.size(),target==44100?48000:44100);});
        rejects([&]{decode_reply(nullptr,bytes.size(),target);});
        rejects([&]{decode_reply(bytes.data(),bytes.size()-1,target);});
        rejects([&]{decode_reply(bytes.data(),bytes.size()+1,target);});
        // Native error is an unrestricted Windows status; every other word is
        // constrained by format, bounds, target or observation consistency.
        for(std::size_t word=0;word<16;++word){
            if(word==13)continue;
            auto bad=bytes;rate_wire::detail::put(bad,word,0xffffffffu);
            rejects([&]{decode_reply(bad.data(),bad.size(),target);});
        }
        for(unsigned fault=0;fault<10;++fault){
            auto bad=good;auto& v=bad.observation;
            if(fault==0)v.setter_attempts=0;
            if(fault==1)v.acknowledgement_received=false;
            if(fault==2)v.readback_rate_hz=0;
            if(fault==3)v.initial_rate_hz=target;
            if(fault==4)v.device_may_have_changed=false;
            if(fault==5)v.write_attempts=2;
            if(fault==6)v.read_attempts=2;
            if(fault==7)v.verified_rate_hz=0;
            if(fault==8)v.transaction_error=RateError::readback_mismatch;
            if(fault==9)v.error=DiagnosticError::transfer;
            rejects([&]{encode_reply(bad);});
        }
        FakeIo unchanged;unchanged.current=target;
        const auto noop=checked_diagnose(target,unchanged);
        require(!noop.setter_attempts && !noop.readback_rate_hz,"No-op wire has no fabricated second getter");
        FakeIo mismatch;mismatch.current=target==44100?48000:44100;mismatch.mismatch=true;
        const auto failed=checked_diagnose(target,mismatch);
        const auto failed_bytes=encode_reply({target,failed,0});
        const auto retained=decode_reply(failed_bytes.data(),failed_bytes.size(),target);
        require(retained.observation.readback_rate_hz==mismatch.current && !retained.observation.verified_rate_hz,
            "Wrong supported readback remains a failed observation across IPC serialization");
    }
    for(const auto target:{0u,96000u,0xffffffffu})rejects([&]{encode_request(target);});
}
void grants(){
    static_assert(!std::is_copy_constructible<RateTestGrant>::value && !std::is_move_constructible<RateTestGrant>::value,
        "A process-local diagnostic grant cannot be cloned or transferred");
    RateTestGrant disabled;require(!disabled.enabled() && !disabled.available() && !disabled.consume(44100),"Default adapter has no rate grant");
    for(const auto target:{44100u,48000u}){
        RateTestGrant once(target);require(once.enabled() && once.available() && once.consume(target),"Explicit target permits one attempt");
        require(once.enabled() && !once.available() && !once.consume(target),"Consumption cannot re-enable audio or repeat a rate attempt");
        RateTestGrant wrong(target);require(!wrong.consume(target==44100?48000:44100) && !wrong.available() && !wrong.consume(target),"Mismatched attempt consumes grant without permission to submit");
    }
    for(const auto target:{0u,96000u,0xffffffffu})rejects([&]{RateTestGrant invalid(target);});
    require(parse_rate_test_target(L"44100")==44100 && parse_rate_test_target(L"48000")==48000,"Canonical diagnostic target parse");
    for(const auto text:{L"",L"+48000",L"48000 ",L" 48000",L"048000",L"96000",L"44100junk"})rejects([&]{parse_rate_test_target(text);});
    rejects([]{parse_rate_test_target(std::wstring_view(L"48000\0junk",10));});
}
void diagnostics(){
    {FakeIo io;const auto result=checked_diagnose(48000,io);require(result.error==DiagnosticError::none && result.verified_rate_hz==48000 && result.initial_rate_hz==44100 && result.device_may_have_changed && result.write_attempts==3 && result.read_attempts==12 && io.operations==15 && io.setters==1,"Full bounded runner uses twelve frames and one setter");}
    {FakeIo io;const auto result=checked_diagnose(48000,io);require(result.readback_rate_hz==48000 && result.acknowledgement_received && result.setter_attempts==1,"Runner exports accepted readback, acknowledgement and one setter attempt");}
    {FakeIo io;io.current=48000;const auto result=checked_diagnose(48000,io);require(result.error==DiagnosticError::none && result.verified_rate_hz==48000 && !result.device_may_have_changed && result.write_attempts==1 && io.setters==0,"Runner no-op path never changes rate");}
    for(unsigned op=0;op<15;++op){
        for(unsigned fault=0;fault<3;++fault){
            FakeIo io;if(fault==0)io.fail_at=op;if(fault==1)io.short_at=op;if(fault==2)io.cancel_at=op;
            const auto result=checked_diagnose(48000,io);
            require(result.error==(fault==2?DiagnosticError::cancelled:DiagnosticError::transfer) && !result.verified_rate_hz && result.device_may_have_changed==(fault==2?op>=6:op>=5),"Failure/cancellation at every operation preserves possible effects");
            require(io.setters<=1 && io.operations<=15,"Runner never retries a setter or extends receive bounds");
            require(result.setter_attempts==unsigned(result.device_may_have_changed) && !result.readback_rate_hz,"Failed runner retains possible setter but no unaccepted late getter");
        }
    }
    {FakeIo io;io.elapsed=10;const auto result=checked_diagnose(48000,io,150);require(result.error==DiagnosticError::deadline && !result.verified_rate_hz && result.device_may_have_changed && io.last_timeout==10,"Late final reply cannot escape total deadline");}
    {FakeIo io;io.elapsed=10;const auto result=checked_diagnose(48000,io,151);require(result.error==DiagnosticError::none && result.verified_rate_hz==48000 && io.last_timeout==11,"Remaining deadline clamps individual waits");}
    {FakeIo io;const auto result=checked_diagnose(48000,io,0);require(result.error==DiagnosticError::deadline && !io.operations && !result.device_may_have_changed,"Expired budget starts no I/O");}
    {FakeIo io;io.rollback_clock=true;const auto result=checked_diagnose(48000,io);require(result.error==DiagnosticError::deadline && io.operations==1 && !result.device_may_have_changed,"Clock rollback fails without further requests");}
    {FakeIo io;io.malformed_ack=true;const auto result=checked_diagnose(48000,io);require(result.error==DiagnosticError::transaction && result.transaction_error==RateError::exchange && result.device_may_have_changed && result.write_attempts==2,"Bad acknowledgement stops before readback submission");}
    {FakeIo io;io.mismatch=true;const auto result=checked_diagnose(48000,io);require(result.error==DiagnosticError::transaction && result.transaction_error==RateError::readback_mismatch && !result.verified_rate_hz && result.device_may_have_changed,"Runner distinguishes reply framing from transaction success");}
    {FakeIo io;io.mismatch=true;const auto result=checked_diagnose(48000,io);require(result.readback_rate_hz==44100 && result.initial_rate_hz==44100 && result.acknowledgement_received && result.setter_attempts==1,"Mismatching getter survives runner failure");}
    {FakeIo io;io.notifications_per_reply=4;const auto result=checked_diagnose(48000,io);require(result.error==DiagnosticError::transaction && result.exchange_error==Error::frame_limit && io.setters==0,"Notification flood cannot cause a setter");}
    {FakeIo io;const auto result=checked_diagnose(96000,io);require(result.error==DiagnosticError::invalid_target && !io.operations,"Invalid diagnostic target performs no I/O");}
}
}
int main(){try{success();failures();diagnostics();wire();grants();std::cout<<"Bounded rate-selection transaction and injected diagnostic runner passed; no physical device operations\n";}
catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}}
