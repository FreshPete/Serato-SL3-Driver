#include "asio/host_session.hpp"
#include "core/input_recorder.hpp"
#include "windows/diagnostic.hpp"
#include <sddl.h>
#include <atomic>
#include <cmath>
#include <cstring>
#include <map>
#include <vector>

namespace {
using namespace sl3::asio;
using sl3::diagnostic::quote;
void require(bool value,const char* text){if(!value)throw std::runtime_error(text);}
#ifdef SL3_INPUT_RECORD_SIMULATED
constexpr auto kind=sl3::session::Kind::simulated;
#else
constexpr auto kind=sl3::session::Kind::native;
#endif
constexpr unsigned bank_frames=128;
constexpr unsigned marker_start=8192;
constexpr std::array<unsigned,2> marker_hz{997,1301};
using Marker=std::array<std::vector<std::uint8_t>,2>;
Marker make_marker(unsigned rate){
    Marker marker;
    const auto frames=rate*650/1000;
    const auto fade=rate/100;
    for(std::size_t channel=0;channel<marker.size();++channel){
        auto& pcm=marker[channel];pcm.resize(frames*3);
        for(unsigned frame=0;frame<frames;++frame){
            const auto gain=double(std::min({frame,frames-1-frame,fade}))/fade;
            const auto angle=6.283185307179586*marker_hz[channel]*frame/rate;
            const auto sample=std::uint32_t(std::int32_t(265271*gain*std::sin(angle)));
            for(unsigned byte=0;byte<3;++byte)pcm[frame*3+byte]=std::uint8_t(sample>>(8*byte));
        }
    }
    return marker;
}
struct Handle {HANDLE value=INVALID_HANDLE_VALUE;~Handle(){if(value!=INVALID_HANDLE_VALUE && value)CloseHandle(value);}};
void ordinary(){Handle token;require(OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token.value)!=FALSE,"Open diagnostic token");
    TOKEN_ELEVATION elevation{};DWORD count=0;require(GetTokenInformation(token.value,TokenElevation,&elevation,sizeof(elevation),&count) && !elevation.TokenIsElevated,"Ordinary diagnostic token required");}
void local(const std::filesystem::path& p){const auto root=p.root_name().native();const auto text=p.native();
    require(p.is_absolute() && root.size()==2 && root[1]==L':' && text.find(L'\0')==std::wstring::npos && text.find(L':',2)==std::wstring::npos && p.lexically_normal()==p && GetDriveTypeW(p.root_path().c_str())==DRIVE_FIXED,"Absolute canonical fixed-drive path required");}
struct Pin {Handle file;explicit Pin(const std::filesystem::path& path,bool directory=false){local(path);
    file.value=CreateFileW(path.c_str(),GENERIC_READ,directory?FILE_SHARE_READ|FILE_SHARE_WRITE:FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT|(directory?FILE_FLAG_BACKUP_SEMANTICS:0),nullptr);
    BY_HANDLE_FILE_INFORMATION info{};require(file.value!=INVALID_HANDLE_VALUE && GetFileInformationByHandle(file.value,&info) && !(info.dwFileAttributes&FILE_ATTRIBUTE_REPARSE_POINT) && bool(info.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY)==directory && (directory || info.nNumberOfLinks==1),"Pin ordinary non-reparse diagnostic object");
    std::array<wchar_t,32768> name{};const auto n=GetFinalPathNameByHandleW(file.value,name.data(),DWORD(name.size()),FILE_NAME_NORMALIZED|VOLUME_NAME_DOS);
    require(n>4 && n<name.size() && std::wstring(name.data(),4)==L"\\\\?\\" && std::filesystem::path(std::wstring(name.data()+4,n-4))==path,"Diagnostic final path differs");
}};
void write_new(const std::filesystem::path& path,const void* data,std::size_t bytes){require(bytes && bytes<=8*1024*1024,"Bounded diagnostic output required");
    Handle file;file.value=CreateFileW(path.c_str(),GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_WRITE_THROUGH,nullptr);
    require(file.value!=INVALID_HANDLE_VALUE,"Create new diagnostic evidence");DWORD wrote=0;
    require(WriteFile(file.value,data,DWORD(bytes),&wrote,nullptr) && wrote==bytes && FlushFileBuffers(file.value),"Flush exact diagnostic output");}
void write_new(const std::filesystem::path& path,const std::string& text){write_new(path,text.data(),text.size());}
std::string ascii(const std::wstring& value){std::string text;for(auto c:value){require(c>0 && c<128,"ASCII argument required");text+=char(c);}return text;}
bool hash(const std::string& value){return value.size()==64 && value.find_first_not_of("0123456789abcdef")==std::string::npos;}
struct Row {std::uint64_t frame=0,publication=0,ticks=0;unsigned bank=0;};
struct Capture {
    std::vector<std::uint8_t> pcm;sl3::PackedInputRecorder recorder;
    std::vector<Row> rows;std::array<ASIOBufferInfo,12> planes{};
    std::atomic<bool> done{false},bad{false};HostSession* session=nullptr;
    std::uint64_t frequency=0;long previous_bank=-1;
    Marker marker;
    unsigned first_marker_output=0;
    explicit Capture(std::size_t frames):pcm(frames*18),recorder(pcm.data(),frames),rows(frames/bank_frames){
        for(long c=0;c<6;++c){planes[std::size_t(c)]={ASIOTrue,c,{}};planes[std::size_t(c+6)]={ASIOFalse,c,{}};}
    }
};
Capture* current=nullptr;
void callback(long bank,ASIOBool direct) noexcept {
    auto& c=*current;
    if(bank<0 || bank>1 || direct!=ASIOTrue){c.bad=true;return;}
    std::array<const std::uint8_t*,6> inputs{};
    for(unsigned channel=0;channel<6;++channel){
        auto* out=c.planes[channel+6].buffers[bank];inputs[channel]=static_cast<const std::uint8_t*>(c.planes[channel].buffers[bank]);
        if(!out || !inputs[channel]){c.bad=true;return;}
        std::memset(out,0,bank_frames*3);
    }
    if(c.previous_bank==bank){c.bad=true;return;}c.previous_bank=bank;
    const auto observation=c.session->observation();LARGE_INTEGER ticks{};
    if(!observation.valid || observation.bank!=unsigned(bank) || !QueryPerformanceCounter(&ticks) || ticks.QuadPart<=0){c.bad=true;return;}
    const auto recorded=c.recorder.recorded_callbacks();
    if(!c.recorder.append(inputs,bank_frames,observation.first_frame)){c.bad=true;return;}
    if(observation.first_frame>=marker_start){
        const auto offset=(observation.first_frame-marker_start)*3;
        for(std::size_t channel=0;channel<c.marker.size();++channel){
            const auto& pcm=c.marker[channel];
            if(offset<pcm.size()){
                const auto first=std::size_t(offset);
                std::memcpy(c.planes[channel+6+c.first_marker_output].buffers[bank],pcm.data()+first,
                            std::min<std::size_t>(bank_frames*3,pcm.size()-first));
            }
        }
    }
    if(c.recorder.recorded_callbacks()!=recorded){
        if(recorded>=c.rows.size()){c.bad=true;return;}
        c.rows[std::size_t(recorded)]={observation.first_frame,observation.host_observation_ns,std::uint64_t(ticks.QuadPart),unsigned(bank)};
    }
    if(c.recorder.complete())c.done.store(true,std::memory_order_release);
}
int run(WorkerSpec spec,const std::filesystem::path& folder,unsigned expected,bool loopback,unsigned first_marker_output){
    ordinary();local(folder);local(spec.executable);local(spec.helper);
    require(!std::filesystem::exists(folder),"Fresh recording directory required");Pin parent(folder.parent_path(),true);
    require(CreateDirectoryW(folder.c_str(),nullptr)!=FALSE,"Create recording directory");Pin directory(folder,true);
    const auto target=((std::size_t(expected)*3+127)/128)*128;
    Capture capture(target);LARGE_INTEGER frequency{};require(QueryPerformanceFrequency(&frequency) && frequency.QuadPart>0,"Read QPC frequency");capture.frequency=std::uint64_t(frequency.QuadPart);
    if(loopback){capture.marker=make_marker(expected);capture.first_marker_output=first_marker_output;}
    const auto payload=quote(loopback?"bounded stereo markers":"zero PCM only");
    sl3::diagnostic::Watchdog watchdog;current=&capture;HostSession session(spec);capture.session=&session;
    const auto phase=[&](const wchar_t* name){write_new(folder/name,std::string("{\"phase\":")+quote(ascii(name))+",\"audioOutputPayload\":"+payload+"}\n");};
    bool started=false,disposed=false;std::string error;ULONGLONG elapsed=0;
    phase(L"phase-prepared.json");
    try{
        ASIOCallbacks callbacks{};callbacks.bufferSwitch=callback;
        require(session.create_buffers(capture.planes.data(),12,bank_frames,&callbacks)==ASE_OK,"Prepare SDK input/output planes");
        phase(L"phase-starting.json");
        if(loopback){
            require(session.inspect() && session.report().observed_rate_hz==expected,"Retained 44.1 kHz acquisition failed");
            const auto controls=session.inspect_controls();
            require(controls && controls->audio.raw[8]==1,"Expected loopback routing is absent");
        }
        started=loopback?session.start(8):session.start_checked(expected,8);
        require(started,"Single-open checked-rate stream failed");
        const auto begin=GetTickCount64();
        while(!capture.done.load(std::memory_order_acquire) && !capture.bad.load()){
            Sleep(1);const auto state=session.report();elapsed=GetTickCount64()-begin;
            if(!state.running || state.failure!=HostFailure::none || elapsed>6000)throw std::runtime_error("Recording stream failed or exceeded six-second collection deadline");
        }
        elapsed=GetTickCount64()-begin;
    }catch(const std::exception& e){error=e.what();}
    try{phase(L"phase-stopping.json");}catch(...){if(error.empty())error="Recording stop phase could not be saved";}
    const auto stopped=session.stop(5000);
    const auto state=loopback?session.close(5000):stopped;
    const auto& stats=loopback?stopped.device_snapshot.stats:state.worker_snapshot.stats;
    const auto& device=state.device_snapshot;
    const bool stream_stopped=loopback
        ? stopped.device_snapshot.phase==sl3::device_session::Phase::ready && stopped.device_snapshot.failure==sl3::session::Failure::none
        : state.worker_snapshot.phase==sl3::session::Phase::stopped && state.worker_snapshot.failure==sl3::session::Failure::none;
    const bool retired=state.io_retired && state.device_released && state.audio.retired && state.audio.active_callbacks==0 && (!state.process.started || (state.process.process_exited && state.process.job_empty));
    if(!retired){
        // Do not read callback-owned PCM/counters or unwind its storage here.
        try{std::ostringstream failure;failure<<std::boolalpha
            <<"{\"schema\":\"sl3.input-record-unretired.v1\",\"simulated\":"<<(kind==sl3::session::Kind::simulated)
            <<",\"successful\":false,\"error\":"<<quote(error)<<",\"streamStarted\":"<<started
            <<",\"ioRetired\":"<<state.io_retired<<",\"deviceReleased\":"<<state.device_released
            <<",\"audioThreadRetired\":"<<state.audio.retired<<",\"workerExited\":"<<state.process.process_exited
            <<",\"workerJobEmpty\":"<<state.process.job_empty<<",\"forcedTermination\":"<<state.termination_requested
            <<",\"hostFailure\":"<<unsigned(state.failure)<<",\"pcmSaved\":false,\"processContainmentRequired\":true}\n";
            write_new(folder/L"failure.json",failure.str());}catch(...){}
        sl3::diagnostic::fail_stop();
    }
    disposed=session.dispose_buffers()==ASE_OK;current=nullptr;
    bool successful=error.empty() && elapsed<=6000 && started && disposed && capture.done.load() && !capture.bad.load() && capture.recorder.complete()
        && state.failure==HostFailure::none && !state.termination_requested && state.audio.exit==AudioExit::stopped
        && state.audio.callbacks_started==state.audio.callbacks_completed && state.audio.callbacks_completed==capture.recorder.callbacks()
        && stream_stopped && stats.input_frames>=target && stats.output_completions>0 && !stats.pending_mask && !stats.retained_mask
        && state.observed_rate_hz==expected;
    if(!successful && error.empty())error="Stream/callback or complete-prefix contract failed";
    std::string pcm_hash,startup_hash;std::unique_ptr<Pin> pcm_pin,startup_pin;
    if(capture.recorder.frames()){try{
        write_new(folder/L"input.pcm",capture.pcm.data(),capture.recorder.frames()*18);pcm_pin=std::make_unique<Pin>(folder/L"input.pcm");
        pcm_hash=sl3::worker::Process::executable_sha256(folder/L"input.pcm");
    }catch(const std::exception& e){error=e.what();successful=false;}}
    if constexpr(kind==sl3::session::Kind::native){try{
        const auto journal=folder/L"worker-1.tsv";
        if(std::filesystem::exists(journal)){startup_pin=std::make_unique<Pin>(journal);startup_hash=sl3::worker::Process::executable_sha256(journal);}
        if(successful)require(!startup_hash.empty(),"Native startup journal missing");
    }catch(const std::exception& e){error=e.what();successful=false;}}
    std::ostringstream text;text<<std::boolalpha;
    text<<"{\"schema\":"<<quote(loopback?"sl3.host-loopback-probe.v1":"sl3.input-record-probe.v1")<<",\"simulated\":"<<(kind==sl3::session::Kind::simulated)<<",\"successful\":"<<successful
        <<",\"error\":"<<quote(error)<<",\"expectedRateHz\":"<<expected<<",\"observedRateHz\":"<<state.observed_rate_hz
        <<",\"nominalRequestedMilliseconds\":3000,\"collectionElapsedMilliseconds\":"<<elapsed<<",\"bankFrames\":128,\"channels\":6,\"sampleBytes\":3,\"intervals\":8"
        <<",\"targetFrames\":"<<target<<",\"recordedFrames\":"<<capture.recorder.frames()<<",\"recordedCallbacks\":"<<capture.recorder.recorded_callbacks()
        <<",\"trailingCallbacksNotRecorded\":"<<capture.recorder.trailing_callbacks()<<",\"totalCallbacks\":"<<capture.recorder.callbacks()<<",\"recorderFault\":"<<unsigned(capture.recorder.fault())
        <<",\"counterFrequency\":"<<capture.frequency<<",\"pcmSaved\":"<<!pcm_hash.empty()<<",\"pcmSha256\":"<<quote(pcm_hash)<<",\"pcmBytes\":"<<(pcm_hash.empty()?0:capture.recorder.frames()*18)
        <<",\"startupJournalSha256\":"<<quote(startup_hash)<<",\"workerSha256\":"<<quote(spec.sha256)<<",\"workerStarted\":"<<state.process.started<<",\"hostFailure\":"<<unsigned(state.failure)
        <<",\"ioRetired\":"<<state.io_retired<<",\"deviceReleased\":"<<state.device_released<<",\"audioThreadRetired\":"<<state.audio.retired
        <<",\"workerExited\":"<<state.process.process_exited<<",\"workerJobEmpty\":"<<state.process.job_empty<<",\"forcedTermination\":"<<state.termination_requested<<",\"buffersDisposed\":"<<disposed
        <<",\"streamStarted\":"<<started<<",\"workerInputFrames\":"<<stats.input_frames<<",\"outputSubmissions\":"<<stats.output_submissions<<",\"outputCompletions\":"<<stats.output_completions
        <<",\"audioOutputPayload\":"<<payload;
    if(loopback)text<<",\"markerFirstFrame\":"<<marker_start<<",\"markerFrames\":"<<capture.marker[0].size()/3
        <<",\"markerHz\":["<<marker_hz[0]<<','<<marker_hz[1]<<']'
        <<",\"markerOutputChannels\":["<<first_marker_output+1<<','<<first_marker_output+2<<']'
        <<",\"audioExit\":"<<unsigned(state.audio.exit)<<",\"pumpFault\":"<<unsigned(state.audio.pump_failure.cause)
        <<",\"pumpQueueResult\":"<<unsigned(state.audio.pump_failure.queue)<<",\"pumpBridgeStatus\":"<<unsigned(state.audio.pump_failure.bridge)
        <<",\"workerFailure\":"<<unsigned(device.failure)<<",\"workerStreamFault\":"<<unsigned(device.stream_fault)
        <<",\"workerNativeError\":"<<device.native_error<<",\"workerDiagnostic\":"<<quote(device.diagnostic);
    text<<",\"startupFramesDiscarded\":0,\"timingProfileWritten\":false,\"latencyMeasured\":false,\"physicalMappingVerified\":false,\"usbContinuityVerified\":false,\"seratoAdmissionVerified\":false,\"rows\":[";
    const auto count=std::size_t(capture.recorder.recorded_callbacks());for(std::size_t i=0;i<count;++i){if(i)text<<',';const auto& row=capture.rows[i];text<<'['<<row.frame<<','<<row.publication<<','<<row.ticks<<','<<row.bank<<']';}
    text<<"]}\n";write_new(folder/L"result.json",text.str());std::cout<<text.str();return successful?0:1;
}
}
int wmain(int argc,wchar_t** argv){try{
    const std::wstring mode=argc>=2?argv[1]:L"--plan";
    const bool deck1=mode==L"--plan-loopback-deck1" || mode==L"--run-loopback-deck1";
    const unsigned first_marker_output=deck1?2u:0u;
    if(argc==2 && (mode==L"--plan-loopback" || mode==L"--plan-loopback-deck1")){
        if constexpr(kind!=sl3::session::Kind::native)return 2;
        std::cout<<"{\"planOnly\":true,\"deviceAccess\":false,\"expectedRateHz\":44100,"
                   "\"markerHz\":["<<marker_hz[0]<<','<<marker_hz[1]<<"],\"markerFirstFrame\":"<<marker_start
                 <<",\"markerDurationMilliseconds\":650,\"bankFrames\":"<<bank_frames
                 <<",\"markerOutputChannels\":["<<first_marker_output+1<<','<<first_marker_output+2<<"]}\n";
        return 0;
    }
    if(argc==1 || (argc==2 && std::wstring(argv[1])==L"--plan")){
        std::cout<<std::boolalpha<<"{\"planOnly\":true,\"deviceAccess\":false,\"simulated\":"<<(kind==sl3::session::Kind::simulated?"true":"false")<<",\"nominalInputMilliseconds\":3000,\"maximumCollectionMilliseconds\":6000,\"audioOutputPayload\":\"zero PCM only\",\"oneAcquisitionRequested\":true,\"expectedRateRequired\":true,\"timingProfileWritten\":false}\n";return 0;}
    const bool loopback=mode==L"--run-loopback" || mode==L"--run-loopback-deck1";
    if((argc!=12 && argc!=14) || (mode!=L"--run" && !loopback))return 2;
    if(loopback && kind!=sl3::session::Kind::native)return 2;
    if constexpr(kind==sl3::session::Kind::native){if(argc!=12)return 2;}
    std::map<std::wstring,std::wstring> args;
    for(int at=2;at<argc;at+=2)if(!args.emplace(argv[at],argv[at+1]).second)return 2;
    if((args.size()!=5 && args.size()!=6) || !args.count(L"--worker") || !args.count(L"--worker-sha256") || !args.count(L"--helper") || !args.count(L"--output") || !args.count(L"--expected-rate"))return 2;
    const auto rate=args.at(L"--expected-rate");if(rate!=L"44100" && rate!=L"48000")return 2;
    if(loopback && rate!=L"44100")return 2;
    WorkerSpec spec;spec.executable=args.at(L"--worker");spec.helper=args.at(L"--helper");spec.sha256=ascii(args.at(L"--worker-sha256"));spec.kind=kind;
    if(!hash(spec.sha256))return 2;
    std::unique_ptr<Pin> fixture_clock;
    if constexpr(kind==sl3::session::Kind::simulated){
        spec.fixture_mode=L"recording-zero-output";
        if(args.size()==6){if(!args.count(L"--fixture-clock"))return 2;
            const std::filesystem::path clock=args.at(L"--fixture-clock");fixture_clock=std::make_unique<Pin>(clock);spec.fixture_mode=L"clock:"+clock.native();}
    }
    const std::filesystem::path output=args.at(L"--output");
    if constexpr(kind==sl3::session::Kind::native)spec.diagnostic_directory=output;
    if(loopback){
        spec.lifetime=DeviceLifetime::retained;
        spec.diagnostic_playback_keepalive=true;
    }
    return run(spec,output,rate==L"44100"?44100u:48000u,loopback,first_marker_output);
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
