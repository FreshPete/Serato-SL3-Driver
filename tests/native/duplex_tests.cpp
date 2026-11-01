#include "core/duplex.hpp"
#include <algorithm>
#include <array>
#include <iostream>
#include <stdexcept>

static void require(bool condition,const char* message){if(!condition)throw std::runtime_error(message);}
struct Fake final:sl3::DuplexBackend {
    std::array<bool,8> prepared{},pending{},canceled{},staged{},released{};
    std::vector<std::string> events;
    int bad_prepare=-1,bad_submit=-1,bad_completion=-1,bad_stage=-1,stuck=-1,bad_release=-1;
    bool cancel_throws=false;
    std::size_t expected_slots=8;
    mutable std::uint64_t clock=0;
    void prepare(std::size_t slot) override {
        if(int(slot)==bad_prepare)throw std::runtime_error("Prepare failure");
        prepared[slot]=true;events.push_back("prepare"+std::to_string(slot));
    }
    void submit(std::size_t slot,bool continuity) override {
        require(std::all_of(prepared.begin(),prepared.begin()+static_cast<std::ptrdiff_t>(expected_slots),[](bool value){return value;}),"I/O preceded full resource preparation");
        require(continuity==(slot/2!=0),"Wrong stream continuity hint");
        if(slot%2)require(staged[slot],"OUT submitted without validated IN layout");
        if(int(slot)==bad_submit)throw std::runtime_error("Submit failure");
        pending[slot]=true;events.push_back("submit"+std::to_string(slot));
    }
    sl3::Completion wait(std::size_t slot,std::uint32_t timeout) override {
        require(pending[slot],"Wait on nonpending slot");events.push_back("wait"+std::to_string(slot));
        if(int(slot)==stuck){clock+=timeout;return sl3::Completion::pending;}
        pending[slot]=false;
        return canceled[slot] || int(slot)==bad_completion?sl3::Completion::failure:sl3::Completion::success;
    }
    void stage_output(std::size_t input,std::size_t output) override {
        require(!pending[input] && output==input+1,"Invalid IN/OUT staging ownership");
        if(int(input)==bad_stage)throw std::runtime_error("Invalid input packet");
        staged[output]=true;events.push_back("stage"+std::to_string(output));
    }
    void cancel(std::size_t slot) override {
        events.push_back("cancel"+std::to_string(slot));
        if(cancel_throws)throw std::runtime_error("Cancel failure");
        canceled[slot]=true;
    }
    void release(std::size_t slot) override {
        require(!pending[slot],"Pending duplex memory released");
        if(int(slot)==bad_release)throw std::runtime_error("Release failure");
        released[slot]=true;events.push_back("release"+std::to_string(slot));
    }
    std::uint64_t now_ms() const override{return clock;}
};
static void retired(const Fake& backend){require(std::none_of(backend.pending.begin(),backend.pending.end(),[](bool value){return value;}),"Request was not drained");}
static void silent_layout(){
    std::array<sl3::PacketResult64,8> input{};
    std::array<std::uint64_t,8> lengths{};std::array<std::uint8_t,1008> output{};
    std::size_t expected=0;
    for(std::size_t i=0;i<8;++i){input[i]={i%2?108u:90u,0};expected+=static_cast<std::size_t>(input[i].length);}
    output.fill(0x5a);
    auto result=sl3::stage_silent_output(input.data(),8,lengths.data(),8,output.data(),output.size());
    require(result.status==sl3::SilentStageStatus::ok && result.bytes==expected,"Silent layout total changed");
    for(std::size_t i=0;i<8;++i)require(lengths[i]==input[i].length,"Variable input lengths changed");
    require(std::all_of(output.begin(),output.end(),[](auto value){return value==0;}),"Silent output contains nonzero data");
    for(unsigned fault=0;fault<6;++fault){
        auto bad=input;
        if(fault==0)bad[3].length=0;
        if(fault==1)bad[3].length=17;
        if(fault==2)bad[3].length=127;
        if(fault==3)bad[3].length=0xffffffffffffffffull;
        if(fault==4)bad[3].status=0xc0000001;
        if(fault==5)bad[3].status=0x100000000ull;
        output.fill(0x5a);lengths.fill(777);
        result=sl3::stage_silent_output(bad.data(),8,lengths.data(),8,output.data(),output.size());
        require(result.status==sl3::SilentStageStatus::invalid_input_packet && lengths[0]==777 && output[0]==0x5a,"Invalid full-width input partially changed OUT storage");
    }
    require(sl3::stage_silent_output(input.data(),8,lengths.data(),8,output.data(),1).status==sl3::SilentStageStatus::insufficient_capacity,"Short output buffer accepted");
    require(sl3::stage_silent_output(input.data(),7,lengths.data(),8,output.data(),output.size()).status==sl3::SilentStageStatus::invalid_arguments,"Ungrouped intervals accepted");
}
int main(){
    try{
        silent_layout();
        Fake success;auto result=sl3::duplex_transaction(success);
        require(result.transfers_succeeded && result.cleanup_complete,"Duplex success failed");retired(success);
        require(std::all_of(success.released.begin(),success.released.end(),[](bool value){return value;}),"Success leaked a resource");
        Fake single;single.expected_slots=2;result=sl3::duplex_transaction(single,1);
        require(result.transfers_succeeded && single.released[1] && !single.prepared[2],"Single-pair bound ignored");
        Fake preparation;preparation.bad_prepare=3;result=sl3::duplex_transaction(preparation);
        require(!result.transfers_succeeded && result.cleanup_complete && preparation.released[2] && !preparation.prepared[3],"Partial prepare cleanup failed");retired(preparation);
        Fake submission;submission.bad_submit=4;result=sl3::duplex_transaction(submission);
        require(!result.transfers_succeeded && result.cleanup_complete && submission.canceled[0] && submission.canceled[2],"Partial IN submission not retired");retired(submission);
        Fake invalid;invalid.bad_stage=2;result=sl3::duplex_transaction(invalid);
        require(!result.transfers_succeeded && result.cleanup_complete && invalid.canceled[1] && invalid.canceled[4] && !invalid.staged[3],"Invalid input queued OUT or skipped cross-direction cancellation");retired(invalid);
        const auto cancel_last=std::find(invalid.events.begin(),invalid.events.end(),"cancel6");
        const auto drain_first=std::find(invalid.events.begin(),invalid.events.end(),"wait1");
        require(cancel_last<drain_first,"Drain started before all pending directions were canceled");
        Fake output_submission;output_submission.bad_submit=3;result=sl3::duplex_transaction(output_submission);
        require(!result.transfers_succeeded && result.cleanup_complete && output_submission.canceled[1] && output_submission.canceled[6],"OUT submission failure cleanup failed");retired(output_submission);
        Fake input_completion;input_completion.bad_completion=2;result=sl3::duplex_transaction(input_completion);
        require(!result.transfers_succeeded && result.cleanup_complete && input_completion.canceled[1] && input_completion.canceled[6] && !input_completion.staged[3],"IN failure did not stop corresponding OUT and drain both directions");retired(input_completion);
        Fake output_completion;output_completion.bad_completion=3;result=sl3::duplex_transaction(output_completion);
        require(!result.transfers_succeeded && result.cleanup_complete && output_completion.canceled[5] && output_completion.canceled[7],"OUT completion failure cleanup failed");retired(output_completion);
        Fake cancel_failure;cancel_failure.bad_stage=2;cancel_failure.cancel_throws=true;result=sl3::duplex_transaction(cancel_failure);
        require(!result.transfers_succeeded && result.cleanup_complete,"Cancel exception prevented completion drain");retired(cancel_failure);
        Fake pending_output;pending_output.stuck=1;result=sl3::duplex_transaction(pending_output);
        require(!result.cleanup_complete && result.retained_slots==std::vector<std::size_t>{1} && pending_output.pending[1] && !pending_output.released[1],"Unretired OUT storage was not retained");
        require(pending_output.clock==7000,"OUT failure did not use shared capture/drain deadlines");
        Fake pending_input;pending_input.stuck=2;result=sl3::duplex_transaction(pending_input);
        require(!result.cleanup_complete && result.retained_slots==std::vector<std::size_t>{2} && !pending_input.released[2],"Unretired IN storage was not retained");
        require(pending_input.clock==7000,"IN failure did not use shared capture/drain deadlines");
        Fake release;release.bad_release=7;result=sl3::duplex_transaction(release);
        require(!result.cleanup_complete && result.retained_slots==std::vector<std::size_t>{7},"Failed OUT release lost its lease");
        require(!sl3::duplex_transaction(success,0).error.empty() && !sl3::duplex_transaction(success,5).error.empty(),"Unbounded pair count accepted");
        std::cout<<"Duplex staging, cross-direction cancellation/drain and retained-lease fault cases passed\n";
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
