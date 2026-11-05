#include "asio/driver_facade.hpp"
#include <array>
#include <atomic>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>

using namespace sl3::asio;
static void require(bool value,const char* text){if(!value)throw std::runtime_error(text);}
static WorkerSpec spec(const std::filesystem::path& executable,const wchar_t* mode=L"normal"){
    WorkerSpec result;result.executable=executable;result.sha256=sl3::worker::Process::executable_sha256(executable);
    result.kind=sl3::session::Kind::simulated;result.fixture_mode=mode;return result;
}
static std::uint64_t joined(const ASIOSamples& value){return (std::uint64_t(value.hi)<<32)|value.lo;}
struct Host {
    DriverFacade& driver;
    std::array<ASIOBufferInfo,12> buffers{};
    HANDLE entered=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    HANDLE release=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    std::atomic<unsigned> calls{0};std::atomic<bool> bad{false};
    bool block=false;unsigned rate=48000;
    explicit Host(DriverFacade& device):driver(device){require(entered && release,"Host events");for(long i=0;i<6;++i){buffers[std::size_t(i)]={ASIOTrue,i,{}};buffers[std::size_t(i+6)]={ASIOFalse,i,{}};}}
    ~Host(){SetEvent(release);driver.stop();CloseHandle(entered);CloseHandle(release);}
};
static Host* host=nullptr;
static void callback(long bank,ASIOBool direct){
    auto& h=*host;const auto call=h.calls.load();ASIOSamples position{};ASIOTimeStamp time{};ASIOSampleRate rate=0;
    long input=0,output=0;
    if(bank!=long(call%2) || direct!=ASIOTrue || h.driver.getSamplePosition(&position,&time)!=ASE_OK || joined(position)!=std::uint64_t(call)*64 ||
       (!time.hi && !time.lo) || h.driver.getSampleRate(&rate)!=ASE_OK || rate!=h.rate || h.driver.getChannels(&input,&output)!=ASE_OK || input!=6 || output!=6)h.bad=true;
    if(h.driver.stop()!=ASE_InvalidMode || h.driver.start()!=ASE_InvalidMode || h.driver.disposeBuffers()!=ASE_InvalidMode ||
       h.driver.setSampleRate(rate)!=ASE_InvalidMode || h.driver.setClockSource(0)!=ASE_InvalidMode || h.driver.init()!=ASIOFalse)h.bad=true;
    SetEvent(h.entered);if(h.block)WaitForSingleObject(h.release,INFINITE);
    for(unsigned c=0;c<6;++c){auto* out=static_cast<unsigned char*>(h.buffers[c+6].buffers[bank]);
        const auto* in=static_cast<const unsigned char*>(h.buffers[c].buffers[bank]);for(unsigned i=0;i<64*3;++i)out[i]=in[i];}
    h.calls.fetch_add(1);
}
static ASIOCallbacks callbacks(){ASIOCallbacks result{};result.bufferSwitch=callback;return result;}
static void unavailable(DriverFacade& driver){
    long a=71,b=72,c=73,d=74;ASIOSampleRate rate=12345;ASIOSamples position{};position.lo=75;ASIOTimeStamp time{};time.lo=76;
    ASIOChannelInfo info{};info.channel=77;ASIOClockSource clock{};clock.index=78;ASIOBufferInfo buffer{};buffer.channelNum=79;ASIOCallbacks cb{};
    for(auto result:{driver.getChannels(&a,&b),driver.getLatencies(&a,&b),driver.getBufferSize(&a,&b,&c,&d),driver.canSampleRate(44100),
        driver.getSampleRate(&rate),driver.setSampleRate(48000),driver.getClockSources(&clock,&a),driver.setClockSource(0),
        driver.getSamplePosition(&position,&time),driver.getChannelInfo(&info),driver.createBuffers(&buffer,1,64,&cb),driver.disposeBuffers(),
        driver.start(),driver.stop(),driver.controlPanel(),driver.future(kAsioCanTimeInfo,nullptr),driver.outputReady()})require(result==ASE_NotPresent,"Uninitialized methods fail without readiness");
    require(a==71 && b==72 && c==73 && d==74 && rate==12345 && position.lo==75 && time.lo==76 && info.channel==77 && clock.index==78 && buffer.channelNum==79,"Unavailable calls preserve outputs");
}
static void healthy(const WorkerSpec& worker,unsigned expected_rate,LatencyProfile timing){
    DriverFacade driver(worker,timing);unavailable(driver);require(driver.init()==ASIOTrue && driver.init()==ASIOTrue,"Inspection-backed initialization is idempotent");
    long minimum=0,maximum=0,preferred=0,granularity=0;
    require(driver.getBufferSize(&minimum,&maximum,&preferred,&granularity)==ASE_OK && minimum==64 && maximum==1024 && preferred==128 && granularity==-1,"Supported power-of-two buffer range");
    require(driver.getChannels(nullptr,&minimum)==ASE_InvalidParameter && driver.getBufferSize(&minimum,&maximum,&preferred,nullptr)==ASE_InvalidParameter,"Validate pointers before output publication");
    const auto other_rate=expected_rate==48000?44100u:48000u;
    ASIOSampleRate rate=0;require(driver.getSampleRate(&rate)==ASE_OK && rate==expected_rate && driver.canSampleRate(rate)==ASE_OK && driver.setSampleRate(rate)==ASE_OK &&
        driver.canSampleRate(other_rate)==ASE_NoClock && driver.setSampleRate(other_rate)==ASE_NoClock && driver.setSampleRate(0)==ASE_NoClock &&
        driver.canSampleRate(std::numeric_limits<double>::quiet_NaN())==ASE_NoClock,"Observed-rate-only contract, no implicit rate setter");
    long count=0;require(driver.getClockSources(nullptr,&count)==ASE_OK && count==1,"Clock count query with zero capacity");
    std::array<ASIOClockSource,2> clocks{};clocks[1].index=999;count=2;
    require(driver.getClockSources(clocks.data(),&count)==ASE_OK && count==1 && clocks[0].index==0 && clocks[0].isCurrentSource==ASIOTrue && clocks[0].associatedChannel==-1 &&
        clocks[0].associatedGroup==-1 && clocks[1].index==999 && driver.setClockSource(0)==ASE_OK && driver.setClockSource(1)==ASE_InvalidParameter,"Only one device clock, no array overrun or control write");
    Host h(driver);h.rate=expected_rate;host=&h;auto cb=callbacks();
    require(driver.createBuffers(h.buffers.data(),12,64,&cb)==ASE_OK,"Publish actual SDK planes");const auto pointer=h.buffers[0].buffers[0];
    long input=71,output=75;
    const auto latency_status=driver.getLatencies(&input,&output);
    if (timing.report_latency)
        require(latency_status==ASE_OK && input==71 && output==75,"Bridge delay plus synthetic extra delays");
    else
        require(latency_status==ASE_InvalidMode && input==0 && output==0,"Unknown latency clears both outputs and returns an error");
    for(long direction=0;direction<2;++direction)for(long channel=0;channel<6;++channel){ASIOChannelInfo info{};info.channel=channel;info.isInput=direction?ASIOTrue:ASIOFalse;
        require(driver.getChannelInfo(&info)==ASE_OK && info.type==ASIOSTInt24LSB && info.isActive==ASIOTrue && info.channelGroup==0 && std::strstr(info.name,"SL3"),"Logical channels and active buffer selection");}
    ASIOSamples position{};position.lo=77;ASIOTimeStamp time{};time.lo=78;
    require(driver.getSamplePosition(&position,&time)==ASE_SPNotAdvancing && position.lo==77 && time.lo==78,"No invented sample position before callback");
    for(unsigned cycle=0;cycle<2;++cycle){h.calls=0;ResetEvent(h.entered);require(driver.start()==ASE_OK,"Facade starts real simulated process/session");
        require(driver.start()==ASE_InvalidMode,"Duplicate start preserves existing session");
        require(WaitForSingleObject(h.entered,2000)==WAIT_OBJECT_0,"Facade callback sees current-bank position/rate");
        require(driver.stop()==ASE_OK && h.calls>0 && !h.bad && h.buffers[0].buffers[0]==pointer,"Fresh starts reset logical position and retain planes; callback reentry rejected");
        require(driver.getSamplePosition(&position,&time)==ASE_SPNotAdvancing,"Stopped position is explicitly not advancing");}
    require(driver.disposeBuffers()==ASE_OK,"Dispose after normal retirement");ASIOChannelInfo inactive{};inactive.isInput=ASIOTrue;
    require(driver.getChannelInfo(&inactive)==ASE_OK && inactive.isActive==ASIOFalse,"Disposed channel metadata becomes inactive");
    require(driver.controlPanel()==ASE_NotPresent && driver.future(kAsioCanTimeInfo,nullptr)==ASE_NotPresent && driver.outputReady()==ASE_NotPresent,"No unimplemented time-info/output-ready negotiation");
}
static void healthy_44100(const std::filesystem::path& fixture){
    struct ClockFile {
        std::filesystem::path path=std::filesystem::temp_directory_path()/(L"SL3FacadeClock-"+std::to_wstring(GetCurrentProcessId())+L"-"+std::to_wstring(GetTickCount64())+L".txt");
        ~ClockFile(){std::error_code error;std::filesystem::remove(path,error);}
    } clock;
    {std::ofstream file(clock.path);file<<44100;require(bool(file),"Write simulated 44.1 kHz clock");}
    const auto mode=L"clock:"+clock.path.native();
    const auto worker=spec(fixture,mode.c_str());
    healthy(worker,44100,{7,11});
    healthy(worker,44100,{0,0,44100,0,false});
}
static void bound_profile(const std::filesystem::path& fixture){
    DriverFacade wrong_rate(spec(fixture),{7,11,44100,128});require(wrong_rate.init()==ASIOFalse,"Reject observed rate outside timing calibration");
    DriverFacade driver(spec(fixture),{7,11,48000,128});require(driver.init()==ASIOTrue,"Accept observed rate matching bound profile");
    long minimum=0,maximum=0,preferred=0,granularity=7,input=0,output=0;
    require(driver.getBufferSize(&minimum,&maximum,&preferred,&granularity)==ASE_OK && minimum==128 && maximum==128 && preferred==128 && granularity==0 &&
        driver.getLatencies(&input,&output)==ASE_OK && input==135 && output==139,"Bound timing offers one measured bank size and known pre-buffer latency");
    ASIOBufferInfo info{};info.isInput=ASIOTrue;auto cb=callbacks();
    require(driver.createBuffers(&info,1,64,&cb)==ASE_InvalidMode && !info.buffers[0] &&
        driver.createBuffers(&info,1,240,&cb)==ASE_InvalidMode && !info.buffers[0] &&
        driver.createBuffers(&info,1,128,&cb)==ASE_OK &&
        driver.disposeBuffers()==ASE_OK,"No timing extrapolation to unreviewed buffer sizes");
    bool rejected=false;try{DriverFacade invalid(spec(fixture),{0,0,96000,128});}catch(const std::exception&){rejected=true;}
    require(rejected,"Reject invalid calibration rate at construction");
}
static void failures(const std::filesystem::path& fixture,const std::filesystem::path& native){
    DriverFacade rejected(spec(fixture,L"fail-inspect"),{0,0});require(rejected.init()==ASIOFalse,"Failed inspection never initializes facade");unavailable(rejected);
    WorkerSpec real;real.executable=native;real.sha256=sl3::worker::Process::executable_sha256(native);real.helper=L"C:/deliberately-missing-sl3-session-helper.dll";
    require(!std::filesystem::exists(real.helper),"Native negative test helper must be absent");DriverFacade absent(real,{0,0});require(absent.init()==ASIOFalse,"Actual native gate rejects without helper/hardware access");unavailable(absent);
    DriverFacade failed(spec(fixture,L"fail-start"),{0,0});Host h(failed);host=&h;auto cb=callbacks();require(failed.init()==ASIOTrue && failed.createBuffers(h.buffers.data(),12,64,&cb)==ASE_OK,"Prepare failed-start facade");
    require(failed.start()==ASE_HWMalfunction && h.calls==0 && failed.getSampleRate(nullptr)==ASE_NotPresent && failed.disposeBuffers()==ASE_OK,"Failed start invalidates metadata but permits safe plane cleanup");
    char message[124]{};failed.getErrorMessage(message);failed.getErrorMessage(nullptr);require(std::strlen(message)>0 && std::strlen(message)<124,"Bounded error string");
}
int wmain(int argc,wchar_t** argv){
    try{require(argc==3,"Fixture and native worker paths required");healthy(spec(argv[1]),48000,{7,11});healthy_44100(argv[1]);bound_profile(argv[1]);failures(argv[1],argv[2]);
        std::cout<<"ASIO facade clock and callbacks at 44.1/48 kHz, buffer and channel metadata, repeated start/stop and native absent-helper rejection passed; synthetic timing only\n";
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
