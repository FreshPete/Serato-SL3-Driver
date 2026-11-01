// Test-only DLL: no COM registration, helper loading or hardware target.
#include "asio/audio_owner.hpp"
#include "core/session_protocol.hpp"
#include <stdexcept>

using namespace sl3;
using namespace sl3::asio;
using namespace sl3::worker;
namespace {
std::shared_ptr<BufferLease> buffers;
std::shared_ptr<Mailbox> channel;
std::shared_ptr<Process> process;
std::unique_ptr<AudioOwner> owner;
Message call(session::Command command,const std::vector<std::uint8_t>& body={}){
    if(!channel->send(std::uint32_t(command),body.data(),body.size()))throw std::runtime_error("Fixture command send");Message reply;
    if(channel->await_reply(process->process_handle(),2000,reply)!=MessageResult::ok || reply.status)throw std::runtime_error("Fixture command reply");return reply;
}
}
extern "C" __declspec(dllexport) BOOL owner_create(const wchar_t* fixture,const char* hash,ASIOBufferInfo* info,long count,long frames,const ASIOCallbacks* callbacks){
    try{
        if(owner)return FALSE;buffers=std::make_shared<BufferLease>();
        if(buffers->create(info,count,frames,callbacks)!=ASE_OK)return FALSE;
        channel=Mailbox::create();process=std::make_shared<Process>();process->launch(fixture,hash,{channel->name(),L"normal"});
        if(session::decode_hello(call(session::Command::hello).bytes)!=session::Kind::simulated)return FALSE;
        owner=std::make_unique<AudioOwner>(buffers,channel,process);
        if(!owner->start(48000))return FALSE;call(session::Command::start,session::encode_start({48000,8,1000,20}));return TRUE;
    }catch(...){return FALSE;}
}
extern "C" __declspec(dllexport) void owner_report(AudioReport* report){if(report && owner)*report=owner->report();}
extern "C" __declspec(dllexport) DWORD owner_worker_pid(){return process?GetProcessId(process->process_handle()):0;}
extern "C" __declspec(dllexport) void owner_destroy(){owner.reset();buffers.reset();channel.reset();process.reset();}
