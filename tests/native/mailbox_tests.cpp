#include "windows/mailbox.hpp"
#include "windows/mailbox_layout.hpp"
#include "windows/worker_process.hpp"
#include <iostream>
#include <stdexcept>

using namespace sl3::worker;
static void require(bool value,const char* text){if(!value)throw std::runtime_error(text);}
template<class F>static void rejects(F operation){bool failed=false;try{operation();}catch(const std::exception&){failed=true;}require(failed,"Expected rejection");}
static void stop(Process& process){const auto result=process.terminate_and_wait();require(result.state.process_exited && result.state.job_empty,"Owned worker retired");}
struct Event {HANDLE value=nullptr;~Event(){if(value)CloseHandle(value);}};
int wmain(int argc,wchar_t** argv){
    try{
        require(argc==2,"Fixture path required");const std::filesystem::path fixture=argv[1];
        const auto hash=Process::executable_sha256(fixture);
        rejects([]{Mailbox::open(L"Global\\invalid");});
        {
            auto host=Mailbox::create();auto peer=Mailbox::open(host->name());
            rejects([&]{Mailbox::open(host->name());});
            Message request;
            require(peer->receive(0,request)==MessageResult::timeout,"Idle peer timeout does not fault session");
            require(!peer->respond(0,nullptr,0),"No reply without a request lease");
            require(!host->send(0,nullptr,0) && !host->send(1,nullptr,1) && !host->send(1,nullptr,wire::capacity+1),"Reject invalid publication before ownership");
            require(host->send(1,nullptr,0),"Publish empty request");
            require(WaitForSingleObject(peer->request_event(),10)==WAIT_OBJECT_0,"Combined worker wait consumes the command event");
            require(!host->send(1,nullptr,0),"One request outstanding");
            require(peer->receive(10,request)==MessageResult::ok && request.sequence==1,"Peer claims ordered request");
            rejects([&]{peer->receive(0,request);});
            require(!peer->respond(0,nullptr,wire::capacity+1),"Reject oversized response without losing lease");
            require(peer->respond(55,nullptr,0),"Valid response retires lease");
            Message reply;
            HANDLE self=nullptr;
            require(DuplicateHandle(GetCurrentProcess(),GetCurrentProcess(),GetCurrentProcess(),&self,
                SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,0)!=FALSE,"Retain real process observation handle");
            const auto local_result=host->await_reply(self,10,reply);CloseHandle(self);
            require(local_result==MessageResult::ok && reply.status==55,"Local ABI test reply");
            require(SetEvent(peer->request_event()) && peer->receive(0,request)==MessageResult::timeout && host->send(2,nullptr,0),
                "Late publication edge carries no new message and does not seal a valid channel");
            host->close();require(peer->receive(0,request)==MessageResult::closed && !host->send(1,nullptr,0),"Closed session cannot restart");
        }
        {
            auto host=Mailbox::create();Process worker;worker.launch(fixture,hash,{L"--mailbox",host->name()});
            for(unsigned n=0;n<100;++n){
                const std::size_t lengths[]={0,18,18432,wire::capacity};
                std::vector<std::uint8_t> payload(lengths[n%4]);
                for(std::size_t i=0;i<payload.size();++i)payload[i]=std::uint8_t((i*31+n*17)&255);
                require(host->send(1,payload.data(),payload.size()),"Publish bounded cross-process batch");
                Message reply;
                require(host->await_reply(worker.process_handle(),2000,reply)==MessageResult::ok,"Cross-process response");
                require(reply.sequence==n+1 && reply.opcode==1 && reply.status==1234 && reply.bytes==payload,"Exact ordered binary round trip including maximum payload");
            }
            require(host->send(2,nullptr,0),"Request fixture shutdown");Message final;
            require(host->await_reply(worker.process_handle(),2000,final)==MessageResult::ok,"Reply survives peer destruction/exit");
            require(worker.wait_for_exit(2000) && worker.observe().exit_code==0,"Graceful worker exit");stop(worker);
        }
        for(const auto fault:{L"sequence",L"length",L"version",L"opcode"}){
            auto host=Mailbox::create();Process worker;worker.launch(fixture,hash,{L"--mailbox-corrupt",host->name(),fault});
            require(host->send(1,nullptr,0),"Publish corruption test request");Message reply;reply.status=999;reply.bytes={7,8};
            require(host->await_reply(worker.process_handle(),2000,reply)==MessageResult::protocol_error,"Reject malformed/stale reply");
            require(reply.status==999 && reply.bytes==std::vector<std::uint8_t>({7,8}) && !host->send(1,nullptr,0),"Failure preserves caller output and seals session");stop(worker);
        }
        {
            auto host=Mailbox::create();Process worker;worker.launch(fixture,hash,{L"--mailbox-die",host->name()});
            require(host->send(1,nullptr,0),"Send before worker exit");Message reply;
            require(host->await_reply(worker.process_handle(),2000,reply)==MessageResult::peer_exited,"Peer exit is not a reply");stop(worker);
        }
        {
            auto host=Mailbox::create();Process worker;worker.launch(fixture,hash,{L"--mailbox-hang",host->name()});
            require(host->send(1,nullptr,0),"Send pending hang request");Message reply;
            rejects([&]{host->await_reply(worker.process_handle(),INFINITE,reply);});
            require(host->await_reply(worker.process_handle(),50,reply)==MessageResult::timeout,"Bounded pending reply timeout");
            require(!host->send(1,nullptr,0) && host->await_reply(worker.process_handle(),0,reply)==MessageResult::closed,"Timed-out session cannot accept late reply or restart");stop(worker);
        }
        {
            auto host=Mailbox::create();Event ready,release;
            ready.value=CreateEventW(nullptr,TRUE,FALSE,(host->name()+L"-test-ready").c_str());
            release.value=CreateEventW(nullptr,TRUE,FALSE,(host->name()+L"-test-release").c_str());
            require(ready.value && release.value,"Create private test rendezvous");
            Process worker;worker.launch(fixture,hash,{L"--mailbox-late",host->name()});
            require(host->send(1,nullptr,0) && WaitForSingleObject(ready.value,2000)==WAIT_OBJECT_0,"Peer holds a request lease before timeout");
            Message reply;
            require(host->await_reply(worker.process_handle(),1,reply)==MessageResult::timeout,"Close a processing request at its deadline");
            SetEvent(release.value);
            require(worker.wait_for_exit(2000) && worker.observe().exit_code==43,"Late peer response cannot reopen the closed phase");stop(worker);
        }
        {
            auto host=Mailbox::create();auto peer=Mailbox::open(host->name());Message request;
            require(host->send(1,nullptr,0) && peer->receive(10,request)==MessageResult::ok,"Peer owns mapped request storage");
            host.reset();
            require(!peer->respond(0,nullptr,0),"Host destruction seals channel while peer's own mapping remains valid");
        }
        for(const bool bad_length:{false,true}){
            auto host=Mailbox::create();auto peer=Mailbox::open(host->name());
            require(host->send(1,nullptr,0),"Publish request for wire rejection");
            const auto map=OpenFileMappingW(FILE_MAP_ALL_ACCESS,FALSE,(host->name()+L"-map").c_str());
            auto* value=static_cast<wire::Shared*>(MapViewOfFile(map,FILE_MAP_ALL_ACCESS,0,0,sizeof(wire::Shared)));
            require(value!=nullptr,"Map only this test's private wire slot");
            if(bad_length)value->request_bytes=wire::capacity+1;else value->request_sequence=0;
            Message request;request.status=999;request.bytes={9};
            const auto result=peer->receive(10,request);
            UnmapViewOfFile(value);CloseHandle(map);
            require(result==MessageResult::protocol_error && request.status==999 && request.bytes==std::vector<std::uint8_t>({9}),"Reject stale/oversized request before copying or publishing caller output");
        }
        {
            auto host=Mailbox::create();Process worker,sentry;
            worker.launch(fixture,hash,{L"--mailbox",host->name()});sentry.launch(fixture,hash,{L"--hang"});
            require(host->send(1,nullptr,0),"Send identity test request");Message reply;
            require(host->await_reply(sentry.process_handle(),2000,reply)==MessageResult::protocol_error,"Reject reply from a process other than the retained expected handle");stop(worker);stop(sentry);
        }
        std::cout<<"Mailbox ownership, binary batches, sequence/length/header validation, peer identity, timeout and worker-exit tests passed; no USB\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
