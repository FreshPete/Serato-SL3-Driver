#pragma once
#ifdef _WIN32
#include "windows/control_transfer_io.hpp"
#include "windows/control_selection_diagnostic.hpp"
#include "core/control_test_target.hpp"

namespace native_control_io_tests {
using namespace sl3::control;
inline void check(bool ok,const char* reason){if(!ok)throw std::runtime_error(reason);}
struct Clock {static inline std::uint64_t tick=0;static std::uint64_t now_ms() noexcept{return tick;}};
struct Device {
    sl3::worker::ControlBaselineOwner control_baseline;
    struct Api {std::vector<std::string> markers;void mark(const char* text){markers.emplace_back(text);}} api;
    std::vector<Frame> incoming,writes;
    std::vector<unsigned> timeouts;
    std::vector<unsigned> advances;
    unsigned prepared=0,calls=0,fail_at=~0u,short_at=~0u,late_at=~0u,regress_at=~0u;
    unsigned prep_ms=0,completion_ms=1;
};
struct Transfer {
    static inline bool baseline_only=false;
    static inline Frame baseline_frame{};
    Device& device;std::vector<std::uint8_t> buffer;DWORD completion_error=0;
    struct {struct {struct {std::size_t BytesTransferred=0;} GenResult;} Result;} request;
    explicit Transfer(Device& d):device(d){}
    ~Transfer(){SetLastError(9999);} // Prove the adapter captures failures before destruction.
    void prepare(unsigned endpoint,std::size_t bytes,bool iso){
        check((endpoint==1 || endpoint==0x81) && bytes==64 && !iso,"Only interrupt control endpoints/shape");
        if(!baseline_only){++device.prepared;Clock::tick+=device.prep_ms;}buffer.resize(bytes);
    }
    void bounded(bool output,DWORD timeout){
        if(baseline_only){
            if(!output)buffer.assign(baseline_frame.begin(),baseline_frame.end());
            request.Result.GenResult.BytesTransferred=64;return;
        }
        const auto at=device.calls++;device.timeouts.push_back(timeout);
        if(at==device.fail_at){completion_error=1234;SetLastError(4321);throw std::runtime_error("Injected retired transfer failure");}
        if(output){Frame frame{};std::copy(buffer.begin(),buffer.end(),frame.begin());device.writes.push_back(frame);}
        else {check(!device.incoming.empty(),"Expected incoming frame");buffer.assign(device.incoming.front().begin(),device.incoming.front().end());device.incoming.erase(device.incoming.begin());}
        request.Result.GenResult.BytesTransferred=at==device.short_at?63:64;
        Clock::tick+=at==device.late_at?4500:at<device.advances.size()?device.advances[at]:device.completion_ms;
        if(at==device.regress_at)Clock::tick=0;
    }
};
using Io=sl3::worker::NativeControlsIo<Device,Transfer,Clock>;
inline Frame reply(unsigned command,unsigned index=0,unsigned value=0){
    Frame f{};f[0]=std::uint8_t(command);f[1]=0x1c;f[2]=0xc5;f[4]=1;
    if(command==0x32)f[5+index]=std::uint8_t(value);
    return f;
}
inline Frame setter(AudioControlSetting kind,unsigned group,unsigned value){
    auto f=audio_controls_query().frame();f[0]=0x33;
    const auto fields=input_control_indexes[group];f[5]=std::uint8_t(kind==AudioControlSetting::through?fields.through:fields.sensitivity);
    f[6]=1;f[7]=std::uint8_t(value);return f;
}
inline Io::Baseline baseline(Device& device,Frame table){
    struct Reset {~Reset(){Transfer::baseline_only=false;}} reset;
    Transfer::baseline_only=true;Transfer::baseline_frame=table;
    Io getter(device);const auto result=inspect_audio_controls(getter);auto token=getter.take_baseline();
    check(result.error==ControlsError::none && token.has_value(),"Baseline issued only through successful default getter");
    check(!getter.take_baseline(),"Getter baseline extracted once");
    return std::move(*token);
}
inline Io selected(Device& device,AudioControlSetting kind,unsigned group,unsigned value){
    const auto table=std::find_if(device.incoming.begin(),device.incoming.end(),[](const Frame& f){return f[0]==0x32;});
    auto token=baseline(device,table==device.incoming.end()?reply(0x32):*table);
    return Io(device,std::move(token),kind,group,value);
}
inline void run(){
    for(const auto kind:{AudioControlSetting::through,AudioControlSetting::sensitivity})
     for(unsigned group=0;group<3;++group)for(unsigned value=0;value<=(kind==AudioControlSetting::through?1u:15u);++value){
      const selection_wire::Target target{kind,group,value};const auto parsed=parse_control_test_target(format_control_test_target(target));
      check(selection_wire::detail::same(target,parsed),"All diagnostic targets use canonical exact parsing");
     }
    for(const auto text:{L"",L"through:3:0",L"through:0:2",L"through:00:1",L"through:0:01",L"through:0:-1",L"Through:0:1",
                         L"sensitivity:0:16",L"sensitivity:0:0 ",L"sensitivity:2:+1",L"sensitivity:2:1:0"}){
     bool rejected=false;try{parse_control_test_target(text);}catch(const std::invalid_argument&){rejected=true;}
     check(rejected,"Invalid diagnostic target rejects without I/O");
    }
    for(const auto kind:{AudioControlSetting::through,AudioControlSetting::sensitivity})
        for(unsigned group=0;group<3;++group)for(unsigned value=0;value<=(kind==AudioControlSetting::through?1u:15u);++value){
            const auto index=kind==AudioControlSetting::through?input_control_indexes[group].through:input_control_indexes[group].sensitivity;
            Clock::tick=100;Device d;d.incoming={reply(0x32,unsigned(index),value?0:1),reply(0x33),reply(0x32,unsigned(index),value)};
            auto io=selected(d,kind,group,value);const auto r=select_audio_control(io,kind,group,value);
            check(r.error==SelectionIoError::none && r.verified && d.writes.size()==3 && d.writes[1]==setter(kind,group,value),"Selected adapter executes exact inspect/set/verify");
            std::size_t bytes=99;auto f=audio_controls_query().frame();const auto calls=d.calls;
            check(!io.transfer(true,f,100,bytes) && !bytes && d.calls==calls,"Completed adapter cannot be reused");
            Clock::tick=100;Device same;same.incoming={reply(0x32,unsigned(index),value)};
            auto noop=selected(same,kind,group,value);const auto n=select_audio_control(noop,kind,group,value);
            check(n.error==SelectionIoError::none && !n.device_may_have_changed && same.writes.size()==1,"Already selected sends getter only");
        }
    // Mutate every byte of the otherwise admitted setter. The native transport
    // must see none of these frames, including mutations in unused padding.
    for(unsigned at=0;at<64;++at){
        Clock::tick=100;Device d;d.incoming={reply(0x32)};auto io=selected(d,AudioControlSetting::through,0,1);
        auto f=audio_controls_query().frame();std::size_t bytes=0;
        check(io.transfer(true,f,100,bytes) && io.transfer(false,f,300,bytes),"Inspect before mutation");
        f=setter(AudioControlSetting::through,0,1);f[at]^=0x80;const auto calls=d.calls;
        check(!io.transfer(true,f,100,bytes) && d.calls==calls && !bytes,"Every malformed setter rejected before native preparation");
        f=setter(AudioControlSetting::through,0,1);
        check(!io.transfer(true,f,100,bytes) && d.calls==calls,"Refusal seals transaction without retry");
    }
    for(unsigned at=0;at<6;++at){
        Clock::tick=100;Device d;d.incoming={reply(0x32),reply(0x33),reply(0x32,8,1)};d.fail_at=at;
        auto io=selected(d,AudioControlSetting::through,0,1);const auto r=select_audio_control(io,AudioControlSetting::through,0,1);
        check(r.error==SelectionIoError::transfer && io.error==1234 && r.device_may_have_changed==(at>=2),"Retired native error and possible-write evidence survive failure/destructor");
    }
    for(unsigned at=0;at<6;++at){
        Clock::tick=100;Device d;d.incoming={reply(0x32),reply(0x33),reply(0x32,8,1)};d.short_at=at;
        auto io=selected(d,AudioControlSetting::through,0,1);const auto r=select_audio_control(io,AudioControlSetting::through,0,1);
        check(r.error==SelectionIoError::transfer && io.error==ERROR_BAD_LENGTH && !r.verified,"Short transfer seals adapter");
    }
    for(unsigned at=0;at<6;++at){
        Clock::tick=100;Device d;d.incoming={reply(0x32),reply(0x33),reply(0x32,8,1)};d.late_at=at;
        auto io=selected(d,AudioControlSetting::through,0,1);const auto r=select_audio_control(io,AudioControlSetting::through,0,1);
        check(r.error==SelectionIoError::deadline && io.error==ERROR_TIMEOUT && !r.verified,"Late completion cannot verify");
    }
    {Clock::tick=100;Device d;d.incoming={reply(0x32)};Io io(d);const auto r=inspect_audio_controls(io);
     check(r.error==ControlsError::none && d.writes.size()==1,"Production default remains getter-only");}
    {Clock::tick=100;Device d;Io io(d);auto f=setter(AudioControlSetting::through,0,1);std::size_t bytes=42;
     check(!io.transfer(true,f,100,bytes) && !d.prepared && !bytes,"Default rejects setting before native preparation");}
    {Clock::tick=100;Device d;auto io=selected(d,AudioControlSetting::through,0,1);auto f=setter(AudioControlSetting::through,0,1);std::size_t bytes=42;
     check(!io.transfer(true,f,100,bytes) && !d.prepared,"Setter before initial observation rejected");}
    {Clock::tick=100;Device d;Io io(d);Frame f{};std::size_t bytes=42;
     check(!io.transfer(false,f,300,bytes) && !d.prepared,"Read before request rejected");}
    for(unsigned timeout:{0u,101u,301u}){
        Clock::tick=100;Device d;Io io(d);auto f=audio_controls_query().frame();std::size_t bytes=42;
        check(!io.transfer(true,f,timeout,bytes) && !d.prepared,"Invalid native timeout sends nothing");
    }
    {Clock::tick=100;Device d;d.prep_ms=100;Io io(d);auto f=audio_controls_query().frame();std::size_t bytes=42;
     check(!io.transfer(true,f,100,bytes) && d.prepared==1 && !d.calls && io.error==ERROR_TIMEOUT,"Preparation consumes submission budget");}
    {Clock::tick=100;Device d;d.prep_ms=10;d.incoming={reply(0x32)};Io io(d);const auto r=inspect_audio_controls(io);
     check(r.error==ControlsError::none && d.timeouts==std::vector<unsigned>({90,290}),"Native timeout excludes preparation time");}
    {Clock::tick=100;Device d;Io io(d);Clock::tick=99;auto f=audio_controls_query().frame();std::size_t bytes=42;
     check(!io.transfer(true,f,100,bytes) && !d.prepared && io.error==ERROR_TIMEOUT,"Clock regression before submission rejected");}
    {Clock::tick=100;Device d;auto io=selected(d,AudioControlSetting::through,3,1);auto f=audio_controls_query().frame();std::size_t bytes=42;
     check(!io.transfer(true,f,100,bytes) && !d.prepared,"Invalid target rejects before native preparation");}
    {Clock::tick=100;Device d;auto note=reply(0x38);note[1]=note[2]=note[3]=0;note[4]=2;
     d.incoming={note,note,note,reply(0x32),note,note,note,reply(0x33),note,note,note,reply(0x32,8,1)};
     auto io=selected(d,AudioControlSetting::through,0,1);const auto r=select_audio_control(io,AudioControlSetting::through,0,1);
     check(r.error==SelectionIoError::none && d.calls==15,"Maximum interleaved notification sequence admitted");}
    {Clock::tick=100;Device d;d.incoming={reply(0x32),reply(0x33),reply(0x32)};
     auto io=selected(d,AudioControlSetting::through,0,1);const auto r=select_audio_control(io,AudioControlSetting::through,0,1);
     check(r.error==SelectionIoError::readback_mismatch && r.observed && !r.verified,"Mismatching observation reaches evidence engine without fabricated success");}
    {Clock::tick=100;Device d;d.regress_at=0;Io io(d);const auto r=inspect_audio_controls(io);
     check(r.error==ControlsError::deadline && io.error==ERROR_TIMEOUT,"Clock regression during completion rejected");}
    {Clock::tick=100;Device d;d.incoming={reply(0x32)};Io io(d);Clock::tick+=1499;
     const auto r=inspect_audio_controls(io);
     check(r.error!=ControlsError::none && io.error==ERROR_TIMEOUT && d.timeouts==std::vector<unsigned>({1}),"Adapter lifetime deadline clamps a later outer invocation");}
    {Clock::tick=100;Device d;Io::Baseline empty;Io io(d,std::move(empty),AudioControlSetting::through,0,1);
     auto f=audio_controls_query().frame();std::size_t bytes=99;
     check(!io.transfer(true,f,100,bytes) && !bytes && !d.prepared,"Unissued baseline refuses before native preparation");}
    {Clock::tick=100;Device a,b;auto token=baseline(a,reply(0x32));
     Io wrong(b,std::move(token),AudioControlSetting::through,0,1);Io reused(a,std::move(token),AudioControlSetting::through,0,1);
     auto f=audio_controls_query().frame();std::size_t bytes=0;
     check(!wrong.transfer(true,f,100,bytes) && !reused.transfer(true,f,100,bytes) && !a.prepared && !b.prepared,"Wrong-owner attempt consumes baseline without permitting reuse");}
    {Clock::tick=100;Device d;auto token=baseline(d,reply(0x32));Io first(d,std::move(token),AudioControlSetting::through,0,1);
     Io second(d,std::move(token),AudioControlSetting::through,0,1);auto f=audio_controls_query().frame();std::size_t bytes=0;
     check(!second.transfer(true,f,100,bytes) && first.transfer(true,f,100,bytes) && d.calls==1,"One token reserves one selection and failed reuse cannot revoke that reservation");}
    for(const auto tick:{99u,1600u}){
     Clock::tick=100;Device d;auto token=baseline(d,reply(0x32));Clock::tick=tick;
     Io io(d,std::move(token),AudioControlSetting::through,0,1);auto f=audio_controls_query().frame();std::size_t bytes=0;
     check(!io.transfer(true,f,100,bytes) && !d.prepared,"Regressed or exactly expired baseline refuses");}
    {Clock::tick=100;Device d;auto token=baseline(d,reply(0x32));auto newer=baseline(d,reply(0x32));
     Io io(d,std::move(token),AudioControlSetting::through,0,1);auto f=audio_controls_query().frame();std::size_t bytes=0;
     check(!io.transfer(true,f,100,bytes) && !d.prepared,"New observation invalidates old baseline");}
    {Clock::tick=100;std::optional<Device> slot;slot.emplace();const auto address=&*slot;
     auto token=baseline(*slot,reply(0x32));slot.reset();slot.emplace();check(address==&*slot,"Exercise reused device storage");
     Io io(*slot,std::move(token),AudioControlSetting::through,0,1);auto f=audio_controls_query().frame();std::size_t bytes=0;
     check(!io.transfer(true,f,100,bytes) && !slot->prepared,"Destroyed owner cannot authorize new device at the same address");}
    {Clock::tick=100;Device d;d.incoming={reply(0x32)};auto io=selected(d,AudioControlSetting::through,0,1);
     d.control_baseline.invalidate();auto f=audio_controls_query().frame();std::size_t bytes=0;
     check(!io.transfer(true,f,100,bytes) && !d.prepared,"Revocation invalidates reserved selection");}
    {Clock::tick=100;Device d;auto token=baseline(d,reply(0x32));auto changed=reply(0x32);changed[5+21]=0xff;
     d.incoming={changed};Io io(d,std::move(token),AudioControlSetting::through,0,1);
     const auto r=select_audio_control(io,AudioControlSetting::through,0,1);
     check(r.error==SelectionIoError::transfer && r.initial && r.initial->raw[21]==0xff && r.device_may_have_changed &&
           io.error==ERROR_REVISION_MISMATCH && d.calls==2 && d.writes.size()==1,"Full-table mismatch preserves fresh observation/uncertainty but submits no setter");}
    {Clock::tick=100;Device d;d.incoming={reply(0x32)};d.completion_ms=800;auto io=selected(d,AudioControlSetting::through,0,1);
     const auto r=select_audio_control(io,AudioControlSetting::through,0,1);
     check(r.error==SelectionIoError::transfer && r.initial && io.error==ERROR_INVALID_STATE && d.writes.size()==1,"Baseline expiry during inspection prevents setter");}
    {Clock::tick=100;Device d;d.incoming={reply(0x32)};auto io=selected(d,AudioControlSetting::through,0,1);
     auto f=audio_controls_query().frame();std::size_t bytes=0;
     check(io.transfer(true,f,100,bytes) && io.transfer(false,f,300,bytes),"Inspect before preparation expiry");
     Clock::tick=1599;d.prep_ms=1;f=setter(AudioControlSetting::through,0,1);
     check(!io.transfer(true,f,100,bytes) && io.error==ERROR_INVALID_STATE && d.calls==2,"Baseline rechecked after setter preparation");}
    {Clock::tick=100;Device d;auto note=reply(0x38);note[1]=note[2]=note[3]=0;note[4]=2;
     d.incoming={reply(0x32),note,note,note,reply(0x33),reply(0x32,8,1)};
     d.advances={100,300,100,300,300,300,300,100,300};auto io=selected(d,AudioControlSetting::through,0,1);
     const auto r=select_audio_control(io,AudioControlSetting::through,0,1);
     check(r.error==SelectionIoError::none && r.verified && Clock::tick>1600,"Timely setter can finish verification after baseline freshness interval");}
    {Clock::tick=100;Device d;auto token=baseline(d,reply(0x32));d.incoming={reply(0x32,8,1)};
     Io io(d,std::move(token),AudioControlSetting::through,0,1);const auto r=select_audio_control(io,AudioControlSetting::through,0,1);
     check(r.error==SelectionIoError::none && !r.device_may_have_changed && d.writes.size()==1,"Fresh already-selected observation remains a write-free no-op");}
    {Clock::tick=100;Device d;d.incoming={reply(0x30)};Io io(d);const auto r=inspect_audio_controls(io);
     check(r.error!=ControlsError::none && !io.take_baseline(),"Malformed getter cannot issue a baseline");}
    using Diagnostic=sl3::worker::ControlSelectionDiagnostic<Device,Transfer,Clock>;
    const selection_wire::Target target{AudioControlSetting::through,0,1};
    const auto inspect=[](Diagnostic& diagnostic){
        struct Reset{~Reset(){Transfer::baseline_only=false;}} reset;
        Transfer::baseline_only=true;Transfer::baseline_frame=reply(0x32);
        check(diagnostic.inspect().error==ControlsError::none,"Diagnostic baseline via same default getter");
    };
    const auto valid=[](const selection_wire::Reply& outcome){
        const auto bytes=selection_wire::encode_reply(outcome);selection_wire::decode_reply(bytes.data(),bytes.size(),outcome.target);
    };
    {Clock::tick=100;Device d;Diagnostic disabled(d);inspect(disabled);
     check(!disabled.enabled() && !disabled.supported(),"Default runtime path remains read-only even with a fresh baseline");
     const auto r=disabled.select(target);valid(r);
     check(r.native_error==ERROR_ACCESS_DENIED && !r.selection.device_may_have_changed && !d.prepared,"Default refusal is typed known-no-write evidence");}
    {Clock::tick=100;Device d;Diagnostic diag(d,target);check(!diag.supported(),"Target alone grants no selection");
     const auto r=diag.select(target);valid(r);inspect(diag);
     check(!diag.supported() && !d.prepared && !r.selection.device_may_have_changed,"Failed attempt cannot rearm through inspection");}
    {Clock::tick=100;Device d;d.incoming={reply(0x32),reply(0x33),reply(0x32,8,1)};Diagnostic diag(d,target);inspect(diag);
     check(diag.supported(),"Explicit target plus fresh baseline offers capability");const auto r=diag.select(target);valid(r);
     check(r.selection.verified && r.selection.device_may_have_changed && !diag.supported() && d.calls==6,"Same native diagnostic glue performs one bounded verified selection");
     const auto again=diag.select(target);valid(again);check(again.selection.write_attempts==0 && d.calls==6,"No repeat transaction");
     inspect(diag);check(!diag.supported(),"New read cannot rearm consumed diagnostic target");
     check(std::find(d.api.markers.begin(),d.api.markers.end(),"audio_control_selection_possible_write.return")!=d.api.markers.end() &&
           std::find(d.api.markers.begin(),d.api.markers.end(),"audio_control_selection_verified.return")!=d.api.markers.end(),"Journal distinguishes possible write and verified result");}
    {Clock::tick=100;Device d;Diagnostic diag(d,target);inspect(diag);const selection_wire::Target wrong{AudioControlSetting::through,1,1};
     const auto r=diag.select(wrong);valid(r);check(r.native_error==ERROR_ACCESS_DENIED && !diag.supported() && !d.prepared,"Different target seals without native transfer");}
    {Clock::tick=100;Device d;Diagnostic diag(d,target);inspect(diag);Clock::tick+=1500;
     check(!diag.supported(),"Capability expires with observation");const auto r=diag.select(target);valid(r);
     check(r.native_error==ERROR_INVALID_STATE && !r.selection.device_may_have_changed && !d.prepared,"Expired diagnostic supplies known no-write outcome");}
}
}
#endif
