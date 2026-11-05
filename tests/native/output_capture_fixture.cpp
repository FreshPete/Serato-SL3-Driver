#include "windows/output_capture.hpp"
#include "windows/continuous_peer.hpp"
#include "windows/diagnostic.hpp"
#include <filesystem>
#include <fstream>
using namespace sl3;using namespace sl3::worker;
void require(bool value,const char* text){if(!value)throw std::runtime_error(text);}
int wmain(int argc,wchar_t** argv){try{
    require(argc==3,"Expected fresh directory and success/partial/invalid-arm/existing mode");
    const std::filesystem::path directory(argv[1]);const std::wstring mode(argv[2]);
    const unsigned rate=mode==L"rate-44100"?44100:48000;
    SetEnvironmentVariableW(L"SL3_OUTPUT_CAPTURE_DIRECTORY",nullptr);
    require(!SoftwareOutputCapture::from_environment(48000),"Capture must be disabled by default");
    SetEnvironmentVariableW(L"SL3_OUTPUT_CAPTURE_DIRECTORY",directory.c_str());
    if(mode==L"existing"){
        bool refused=false;try{auto capture=SoftwareOutputCapture::from_environment(48000);}catch(const std::exception&){refused=true;}
        require(refused,"Existing output directory not refused");return 0;
    }
    {
        auto capture=SoftwareOutputCapture::from_environment(rate);
        SetEnvironmentVariableW(L"SL3_OUTPUT_CAPTURE_DIRECTORY",nullptr);
        require(bool(capture) && !capture->is_armed(),"Unexpected automatic capture");
        AudioBlock ignored;capture->append(ignored); // Disabled prefix is never parsed/copied.
        if(mode==L"invalid-arm"){
            std::filesystem::create_directory(directory/L"arm.txt");
            const auto deadline=GetTickCount64()+3000;
            while(!std::filesystem::exists(directory/L"capture-error.json") && GetTickCount64()<deadline)Sleep(5);
            require(std::filesystem::exists(directory/L"capture-error.json"),"Bad arm did not report failure");return 0;
        }
        {std::ofstream marker(directory/L"arm.txt");require(bool(marker),"Cannot arm test capture");}
        const auto deadline=GetTickCount64()+3000;
        while(!capture->is_armed() && GetTickCount64()<deadline)Sleep(5);
        require(capture->is_armed(),"Capture did not arm");
        if(mode==L"write-failure"){std::ofstream sentinel(directory/L"capture.pcm");sentinel<<"preserve";}
        auto host=Mailbox::create();auto worker=Mailbox::open(host->name());MailboxStreamPeer peer(*worker,capture.get());
        AudioBlock block;block.packet_count=8;block.reported_rate_hz=rate;
        const unsigned frames_per_block=rate==44100?44:48;
        for(unsigned i=0;i<8;++i)block.frames_per_packet[i]=std::uint8_t(rate==44100?5+i%2:6);
        for(unsigned frame=0;frame<frames_per_block;++frame)for(unsigned channel=0;channel<6;++channel){
            const auto offset=frame*18+channel*3;
            block.pcm[offset]=std::uint8_t(channel+1);block.pcm[offset+1]=0x80;block.pcm[offset+2]=0xff;
        }
        const unsigned blocks=mode==L"partial"?1:(rate*5+frames_per_block-1)/frames_per_block;
        for(unsigned i=0;i<blocks;++i){
            block.first_frame=std::uint64_t(i)*frames_per_block;
            require(host->try_push_audio(AudioDirection::output,block)==AudioResult::ok,"Host queue push failed");
            AudioBlock received;require(peer.receive_output(received)==StreamExchange::ok,"Worker queue pop failed");
            require(received.pcm==block.pcm && received.first_frame==block.first_frame,"Capture changed stream data");
        }
        AudioBlock empty;require(peer.receive_output(empty)==StreamExchange::empty,"Empty dequeue changed semantics");
        capture->retire(); // Complete clip survives retirement; partial clip is refused.
    }
    require(std::filesystem::exists(directory/((mode==L"partial" || mode==L"write-failure")?L"capture-error.json":L"capture.json")),"Expected terminal capture record missing");
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
