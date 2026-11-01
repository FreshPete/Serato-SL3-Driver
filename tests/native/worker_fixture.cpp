// Test-only executable: never links a USB backend or ASIO DLL.
#include "windows/worker_process.hpp"
#include "windows/mailbox.hpp"
#include "windows/mailbox_layout.hpp"
#include "audio_pattern.hpp"
#include <array>
#include <filesystem>
#include <string>

int wmain(int argc,wchar_t** argv){
    if(argc<2)return 2;
    const std::wstring mode=argv[1];
    if(mode==L"--audio-source" && argc==6){
        try{
            using namespace sl3::worker;
            const auto rate=static_cast<unsigned>(std::stoul(argv[3])),bank_frames=static_cast<unsigned>(std::stoul(argv[4]));
            const auto packets=static_cast<unsigned>(std::stoul(argv[5]));
            if((rate!=44100 && rate!=48000) || (bank_frames!=64 && bank_frames!=128 && bank_frames!=1024))return 30;
            if(packets && (packets<8 || packets>64 || packets%8))return 30;
            auto channel=Mailbox::open(argv[2]);Message control;
            if(channel->receive(2000,control)!=MessageResult::ok || control.opcode!=1 || !channel->respond(0,nullptr,0))return 31;
            unsigned produced=0,consumed=0;std::uint64_t in_position=0,out_position=0;
            const auto started=GetTickCount64();AudioBlock output;
            while(consumed<pattern::process_blocks){
                bool progressed=false;
                if(produced<pattern::process_blocks){
                    const auto input=pattern::input(produced,in_position,rate,packets);
                    const auto result=channel->try_push_audio(AudioDirection::input,input);
                    if(result==AudioResult::ok){in_position+=pattern::frames(input);++produced;progressed=true;}
                    else if(result!=AudioResult::full)return 32;
                }
                const auto result=channel->try_pop_audio(AudioDirection::output,output);
                if(result==AudioResult::ok){
                    if(!pattern::output_matches(output,consumed,out_position,rate,bank_frames,packets))return 33;
                    out_position+=pattern::frames(output);++consumed;progressed=true;
                }else if(result!=AudioResult::empty)return 34;
                if(GetTickCount64()-started>10000)return 35;
                if(!progressed)Sleep(1);
            }
            if(channel->receive(2000,control)!=MessageResult::ok || control.opcode!=2 || !channel->respond(0,nullptr,0))return 36;
            return 0;
        }catch(...){return 37;}
    }
    if(mode==L"--audio-rings" && argc==3){
        try{
            using namespace sl3::worker;
            auto channel=Mailbox::open(argv[2]);Message control;
            if(channel->receive(2000,control)!=MessageResult::ok || !channel->respond(0,nullptr,0))return 20;
            AudioBlock block;bool pending=false;
            for(;;){
                const auto message=channel->receive(0,control);
                if(message==MessageResult::closed)return 0;
                if(message==MessageResult::ok){channel->respond(0,nullptr,0);return control.opcode==2?0:21;}
                if(message!=MessageResult::timeout)return 22;
                bool progressed=false;
                if(!pending){
                    const auto input=channel->try_pop_audio(AudioDirection::output,block);
                    if(input==AudioResult::ok){pending=true;progressed=true;}
                    else if(input!=AudioResult::empty)return 23;
                }
                if(pending){
                    const auto output=channel->try_push_audio(AudioDirection::input,block);
                    if(output==AudioResult::ok){pending=false;progressed=true;}
                    else if(output!=AudioResult::full)return 24;
                }
                if(!progressed)Sleep(1); // Test fixture only; no real-time pacing claim.
            }
        }catch(...){return 25;}
    }
    if((mode==L"--mailbox" || mode==L"--mailbox-die" || mode==L"--mailbox-hang" || mode==L"--mailbox-corrupt" || mode==L"--mailbox-late") && argc>=3){
        try{
            auto mailbox=sl3::worker::Mailbox::open(argv[2]);
            for(;;){
                sl3::worker::Message request;
                const auto result=mailbox->receive(2000,request);
                if(result==sl3::worker::MessageResult::closed)return 0;
                if(result!=sl3::worker::MessageResult::ok)return 11;
                if(mode==L"--mailbox-die")return 42;
                if(mode==L"--mailbox-hang")Sleep(INFINITE);
                if(mode==L"--mailbox-late"){
                    const std::wstring name=argv[2];
                    const auto ready=OpenEventW(EVENT_MODIFY_STATE,FALSE,(name+L"-test-ready").c_str());
                    const auto release=OpenEventW(SYNCHRONIZE,FALSE,(name+L"-test-release").c_str());
                    if(!ready || !release){if(ready)CloseHandle(ready);if(release)CloseHandle(release);return 16;}
                    SetEvent(ready);const auto wait=WaitForSingleObject(release,2000);CloseHandle(ready);CloseHandle(release);
                    if(wait!=WAIT_OBJECT_0)return 17;
                    return mailbox->respond(0,nullptr,0)?44:43;
                }
                if(mode==L"--mailbox-corrupt" && argc==4){
                    const std::wstring name=argv[2],fault=argv[3];
                    const auto map=OpenFileMappingW(FILE_MAP_ALL_ACCESS,FALSE,(name+L"-map").c_str());
                    auto* value=static_cast<sl3::worker::wire::Shared*>(MapViewOfFile(map,FILE_MAP_ALL_ACCESS,0,0,sizeof(sl3::worker::wire::Shared)));
                    if(!value){if(map)CloseHandle(map);return 12;}
                    value->reply_sequence=request.sequence;value->reply_bytes=0;value->status=0;
                    if(fault==L"sequence")++value->reply_sequence;
                    else if(fault==L"length")value->reply_bytes=sl3::worker::wire::capacity+1;
                    else if(fault==L"version")++value->version_value;
                    else if(fault==L"opcode")++value->opcode;
                    else return 13;
                    InterlockedExchange(&value->phase,sl3::worker::wire::reply);
                    const auto event=OpenEventW(EVENT_MODIFY_STATE,FALSE,(name+L"-reply").c_str());
                    if(event){SetEvent(event);CloseHandle(event);}
                    UnmapViewOfFile(value);CloseHandle(map);return 0;
                }
                if(request.opcode==2){mailbox->respond(0,nullptr,0);return 0;}
                if(!mailbox->respond(1234,request.bytes.data(),request.bytes.size()))return 14;
            }
        }catch(...){return 15;}
    }
    if(mode==L"--exit" && argc==3)return std::stoi(argv[2]);
    if(mode==L"--hang" && argc==2){Sleep(INFINITE);return 9;}
    if(mode==L"--argv" && argc==9){
        const std::array<std::wstring,7> expected{{L"",L"spaces here",L"tail\\",L"embedded\"quote",L"slash\\\"quote",L"\u042e\u30cb\u30b3\u30fc\u30c9",L"two\\\\"}};
        for(int i=2;i<argc;++i)if(argv[i]!=expected[std::size_t(i-2)])return 4;
        return 0;
    }
    if(mode==L"--signal-handle" && argc==3){
        SetEvent(reinterpret_cast<HANDLE>(std::stoull(argv[2])));return 0;
    }
    if((mode==L"--spawn-exit" || mode==L"--spawn-hang") && argc==2){
        const std::filesystem::path self=argv[0];
        std::wstring line=L"\""+self.native()+L"\" --hang";
        STARTUPINFOW startup{};startup.cb=sizeof(startup);PROCESS_INFORMATION child{};
        if(!CreateProcessW(self.c_str(),line.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,nullptr,&startup,&child))return 5;
        CloseHandle(child.hThread);CloseHandle(child.hProcess);
        if(mode==L"--spawn-hang")Sleep(INFINITE);
        return 39;
    }
    if(mode==L"--abrupt-owner" && argc==3){
        std::string expected;
        for(const auto ch:std::wstring(argv[2]))expected+=char(ch);
        sl3::worker::Process nested;
        nested.launch(std::filesystem::path(argv[0]),expected,{L"--hang"});
        // Bypass C++ destructors: Windows closing the owner's sole job handle
        // must retire the nested worker while the outer observing owner lives.
        TerminateProcess(GetCurrentProcess(),41);return 6;
    }
    return 2;
}
