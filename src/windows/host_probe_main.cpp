#include "asio/host_session.hpp"
#include "core/control_test_target.hpp"
#include "core/rate_test_grant.hpp"
#include <algorithm>
#include <array>
#include <atomic>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <thread>

namespace {
using namespace sl3::asio;
constexpr long bank_frames=128;
constexpr unsigned default_interval_count=64;
constexpr ULONGLONG duration_ms=1000;
#ifdef SL3_HOST_PROBE_SIMULATED
constexpr auto kind=sl3::session::Kind::simulated;
#else
constexpr auto kind=sl3::session::Kind::native;
#endif
void require(bool value,const char* reason){if(!value)throw std::runtime_error(reason);}
struct Watchdog {
    HANDLE stop=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    std::thread thread;
    explicit Watchdog(DWORD budget=30000){
        require(stop!=nullptr,"Create probe watchdog event");
        try{thread=std::thread([this,budget]{if(WaitForSingleObject(stop,budget)!=WAIT_OBJECT_0)TerminateProcess(GetCurrentProcess(),3);});}
        catch(...){CloseHandle(stop);throw;}
    }
    ~Watchdog(){SetEvent(stop);thread.join();CloseHandle(stop);}
};
struct Probe {
    struct Timing {std::uint64_t frame=0,publication_ns=0,callback_ticks=0;};
    // Fixed storage: no allocation or file output from the audio callback.
    std::array<Timing,2048> timings{};
    std::atomic<unsigned> timing_count{0};
    std::atomic<std::uint64_t> timing_dropped{0};
    std::uint64_t counter_frequency=0;
    std::array<ASIOBufferInfo,12> planes{};
    std::array<std::atomic<std::uint64_t>,6> nonzero{};
    std::atomic<std::uint64_t> callbacks{0},first_frame{0},last_frame{0};
    std::atomic<bool> bad{false};
    HostSession* session=nullptr;
    Probe(){for(long c=0;c<6;++c){planes[std::size_t(c)]={ASIOTrue,c,{}};planes[std::size_t(c+6)]={ASIOFalse,c,{}};nonzero[std::size_t(c)]=0;}}
};
Probe* current=nullptr;
void buffer_switch(long bank,ASIOBool direct) noexcept {
    auto& p=*current;
    LARGE_INTEGER entered{};
    if(!QueryPerformanceCounter(&entered) || entered.QuadPart<0){p.bad=true;return;}
    if(bank<0 || bank>1 || direct!=ASIOTrue){p.bad=true;return;}
    for(std::size_t channel=0;channel<6;++channel){
        auto* out=static_cast<unsigned char*>(p.planes[channel+6].buffers[bank]);
        const auto* in=static_cast<const unsigned char*>(p.planes[channel].buffers[bank]);
        if(!out || !in){p.bad=true;return;}
        std::memset(out,0,std::size_t(bank_frames)*3);
        std::uint64_t count=0;
        for(std::size_t byte=0;byte<std::size_t(bank_frames)*3;++byte)if(in[byte])++count;
        p.nonzero[channel].fetch_add(count);
    }
    const auto observation=p.session->observation();
    if(!observation.valid || observation.bank!=unsigned(bank)){p.bad=true;return;}
    const auto count=p.callbacks.fetch_add(1);
    if(count==0)p.first_frame=observation.first_frame;
    else if(observation.first_frame!=p.last_frame.load()+std::uint64_t(bank_frames))p.bad=true;
    p.last_frame=observation.first_frame;
    const auto index=p.timing_count.load(std::memory_order_relaxed);
    if(index<p.timings.size()){
        p.timings[index]={observation.first_frame,observation.host_observation_ns,std::uint64_t(entered.QuadPart)};
        p.timing_count.store(index+1,std::memory_order_release);
    }else p.timing_dropped.fetch_add(1,std::memory_order_relaxed);
}
std::string quoted(const std::string& value){
    std::string result="\"";
    constexpr char digits[]="0123456789abcdef";
    for(const auto c:value){const auto byte=static_cast<unsigned char>(c);
        if(c=='"' || c=='\\'){result+='\\';result+=c;}
        else if(byte<32){result+="\\u00";result+=digits[byte>>4];result+=digits[byte&15];}
        else result+=c;
    }
    return result+'"';
}
struct Evidence {
    std::string phase="preparing",error;
    bool inspected=false,started=false,finished=false,success=false,buffers_disposed=false;
    ULONGLONG elapsed=0;
    HostReport host{};
    bool inspect_only=false;
    unsigned completed_inspections=0;
    unsigned single_open_rate=0;
    unsigned initial_observed_rate=0;
    unsigned intervals=default_interval_count;
    bool retained=false;
    unsigned retained_rate=0,stream_index=0;
};
void save(const std::filesystem::path& path,const Evidence& e,const Probe& p){
    const auto& h=e.host;const auto& w=h.worker_snapshot;const auto& d=h.device_snapshot;const auto& s=e.retained?d.stats:w.stats;
    std::ostringstream text;text<<std::boolalpha;
    text<<"{\"schema\":\"sl3.host-probe.v1\",\"phase\":"<<quoted(e.phase)
        <<",\"simulated\":"<<(kind==sl3::session::Kind::simulated)<<",\"inspection_succeeded\":"<<e.inspected
        <<",\"stream_started\":"<<e.started<<",\"finished\":"<<e.finished<<",\"successful\":"<<e.success
        <<",\"inspect_only\":"<<e.inspect_only<<",\"completed_inspections\":"<<e.completed_inspections
        <<",\"single_open\":"<<(e.single_open_rate!=0)<<",\"expected_rate_hz\":"<<(e.retained?e.retained_rate:e.single_open_rate)
        <<",\"retained_device\":"<<e.retained<<",\"stream_index\":"<<e.stream_index<<",\"device_held\":"<<h.device_held
        <<",\"initial_reported_rate_hz\":"<<e.initial_observed_rate
        <<",\"output_payload\":"<<quoted(e.inspect_only?"no audio submitted":"zero PCM only")<<",\"requested_stream_ms\":"<<(e.inspect_only?0:duration_ms)
        <<",\"observed_stream_ms\":"<<e.elapsed<<",\"bank_frames\":"<<bank_frames<<",\"intervals\":"<<e.intervals
        <<",\"reported_rate_hz\":"<<h.observed_rate_hz<<",\"callbacks\":"<<p.callbacks.load()
        <<",\"callback_contract_failed\":"<<p.bad.load()<<",\"first_frame\":"<<p.first_frame.load()<<",\"last_frame\":"<<p.last_frame.load()
        <<",\"host_failure\":"<<unsigned(h.failure)<<",\"audio_exit\":"<<unsigned(h.audio.exit)
        <<",\"audio_thread_retired\":"<<h.audio.retired<<",\"active_callbacks\":"<<h.audio.active_callbacks
        <<",\"callbacks_started\":"<<h.audio.callbacks_started<<",\"callbacks_completed\":"<<h.audio.callbacks_completed
        <<",\"audio_input_frames\":"<<h.audio.input_frames<<",\"published_output_frames\":"<<h.audio.published_frames
        <<",\"io_retired\":"<<h.io_retired<<",\"device_released\":"<<h.device_released
        <<",\"worker_exited\":"<<h.process.process_exited<<",\"private_job_empty\":"<<h.process.job_empty
        <<",\"forced_termination\":"<<h.termination_requested<<",\"buffers_disposed\":"<<e.buffers_disposed
        <<",\"worker_phase\":"<<(e.retained?unsigned(d.phase):unsigned(w.phase))<<",\"worker_failure\":"<<(e.retained?unsigned(d.failure):unsigned(w.failure))
        <<",\"stream_fault\":"<<(e.retained?unsigned(d.stream_fault):unsigned(w.stream_fault))<<",\"native_error\":"<<(e.retained?d.native_error:w.native_error)
        <<",\"input_blocks\":"<<s.input_blocks<<",\"input_frames\":"<<s.input_frames
        <<",\"output_submissions\":"<<s.output_submissions<<",\"output_completions\":"<<s.output_completions
        <<",\"output_frames_submitted\":"<<s.output_frames_submitted<<",\"pending_mask\":"<<s.pending_mask
        <<",\"retained_mask\":"<<s.retained_mask<<",\"worker_diagnostic\":"<<quoted(e.retained?d.diagnostic:w.diagnostic)
        <<",\"analogue_signal_verified\":false,\"latency_measured\":false,\"asio_com_registered\":false"
        <<",\"input_nonzero_bytes\":[";
    for(std::size_t channel=0;channel<6;++channel){if(channel)text<<',';text<<p.nonzero[channel].load();}
    text<<"],\"callback_counter_frequency\":"<<p.counter_frequency
        <<",\"timing_records_dropped\":"<<p.timing_dropped.load()<<",\"callback_timings\":[";
    const auto count=p.timing_count.load(std::memory_order_acquire);
    for(unsigned index=0;index<count;++index){
        const auto& timing=p.timings[index];if(index)text<<',';
        text<<"["<<timing.frame<<','<<timing.publication_ns<<','<<timing.callback_ticks<<']';
    }
    text<<"],\"error\":"<<quoted(e.error)<<"}\n";
    std::ofstream output(path,std::ios::binary|std::ios::trunc);output<<text.str();output.flush();
    require(bool(output),"Write probe evidence");
}
bool local_absolute(const std::filesystem::path& path){
    const auto value=path.native();
    return path.is_absolute() && value.rfind(L"\\\\",0)!=0 && value.find_first_of(L"\"\r\n") == std::wstring::npos;
}
int run(WorkerSpec spec,const std::filesystem::path& folder,bool inspect_only,unsigned single_open_rate,unsigned intervals){
    require(!std::filesystem::exists(folder),"Choose a fresh output directory");
    require(std::filesystem::create_directory(folder),"Create probe output directory");
    Probe probe;LARGE_INTEGER frequency{};
    require(QueryPerformanceFrequency(&frequency)!=FALSE && frequency.QuadPart>0,"Read callback counter frequency");
    probe.counter_frequency=std::uint64_t(frequency.QuadPart);
    current=&probe;Evidence evidence;evidence.inspect_only=inspect_only;evidence.single_open_rate=single_open_rate;const auto path=folder/L"probe.json";
    evidence.intervals=intervals;
    if constexpr(kind==sl3::session::Kind::native)spec.diagnostic_directory=folder;
    save(path,evidence,probe);Watchdog watchdog;HostSession session(spec);probe.session=&session;
    try{
        if(!single_open_rate){
            evidence.phase="inspecting";save(path,evidence,probe);
            evidence.inspected=session.inspect();evidence.host=session.report();
            evidence.initial_observed_rate=evidence.host.observed_rate_hz;
            require(evidence.inspected,"Worker clock inspection failed");
            ++evidence.completed_inspections;
        }
        if(inspect_only){
            evidence.phase="reopening";save(path,evidence,probe);
            require(session.inspect(),"Second worker clock inspection failed");
            ++evidence.completed_inspections;
        }else{
        ASIOCallbacks callbacks{};callbacks.bufferSwitch=buffer_switch;
        require(session.create_buffers(probe.planes.data(),12,bank_frames,&callbacks)==ASE_OK,"Prepare SDK planes");
        evidence.phase="starting";save(path,evidence,probe);
        evidence.started=single_open_rate?session.start_checked(single_open_rate,intervals):session.start(intervals);evidence.host=session.report();
        require(evidence.started,"Continuous worker startup failed");
        evidence.phase="streaming";save(path,evidence,probe);
        const auto begin=GetTickCount64();
        do{
            Sleep(5);evidence.host=session.report();evidence.elapsed=GetTickCount64()-begin;
            if(!evidence.host.running || evidence.host.failure!=HostFailure::none || probe.bad.load())break;
        }while(evidence.elapsed<duration_ms);
        }
    }catch(const std::exception& error){evidence.error=error.what();}
    evidence.phase="stopping";
    try{save(path,evidence,probe);}catch(...){if(evidence.error.empty())evidence.error="Progress evidence write failed";}
    evidence.host=session.stop(5000);
    const auto& h=evidence.host;const auto& w=h.worker_snapshot;
    const bool retired=h.io_retired && h.device_released && h.audio.retired && h.audio.active_callbacks==0
        && (!h.process.started || (h.process.process_exited && h.process.job_empty));
    if(retired && !inspect_only)evidence.buffers_disposed=session.dispose_buffers()==ASE_OK;
    evidence.finished=retired;evidence.phase=retired?"finished":"unretired";
    evidence.success=evidence.error.empty() && (evidence.inspected || single_open_rate) && evidence.started && retired && evidence.buffers_disposed
        && !h.termination_requested && h.failure==HostFailure::none && h.audio.exit==AudioExit::stopped
        && !probe.bad.load() && evidence.elapsed>=duration_ms && probe.callbacks.load()>0
        && h.audio.callbacks_started==h.audio.callbacks_completed && h.audio.callbacks_completed==probe.callbacks.load()
        && w.phase==sl3::session::Phase::stopped && w.failure==sl3::session::Failure::none
        && w.stats.input_frames>0 && w.stats.output_completions>0 && w.stats.output_frames_submitted>0
        && !w.stats.pending_mask && !w.stats.retained_mask;
    if(single_open_rate)evidence.success=evidence.success && h.observed_rate_hz==single_open_rate && evidence.completed_inspections==0;
    if(inspect_only)evidence.success=evidence.error.empty() && evidence.completed_inspections==2 && retired
        && !h.termination_requested && h.failure==HostFailure::none && probe.callbacks.load()==0
        && !evidence.started && !w.stats.input_frames && !w.stats.output_submissions;
    try{save(path,evidence,probe);}catch(...){if(!retired){TerminateProcess(GetCurrentProcess(),1);std::abort();}throw;}
    if(!retired){TerminateProcess(GetCurrentProcess(),1);std::abort();}
    current=nullptr;return evidence.success?0:1;
}
struct RetainedEvidence {
    std::string phase="preparing",error;
    std::string worker_sha;
    unsigned expected_rate=0,attempts=0,completed_streams=0,buffer_recreations=0;
    bool acquired=false,finished=false,success=false,keepalive=false;
    HostReport acquisition{},final{};
};
void save_retained(const std::filesystem::path& path,const RetainedEvidence& e,const std::array<Evidence,2>& streams){
    const auto& h=e.final;const auto& a=e.acquisition;
    std::ostringstream text;text<<std::boolalpha;
    text<<"{\"schema\":\"sl3.retained-host-probe.v1\",\"phase\":"<<quoted(e.phase)
        <<",\"simulated\":"<<(kind==sl3::session::Kind::simulated)<<",\"successful\":"<<e.success<<",\"finished\":"<<e.finished
        <<",\"expected_rate_hz\":"<<e.expected_rate<<",\"reported_rate_hz\":"<<a.observed_rate_hz
        <<",\"worker_sha256\":"<<quoted(e.worker_sha)
        <<",\"acquisition_attempts\":"<<e.attempts<<",\"acquisition_verified\":"<<e.acquired
        <<",\"acquisition_io_retired\":"<<a.io_retired<<",\"acquisition_device_held\":"<<a.device_held
        <<",\"acquisition_device_released\":"<<a.device_released<<",\"acquisition_worker_exited\":"<<a.process.process_exited
        <<",\"requested_streams\":2,\"completed_streams\":"<<e.completed_streams<<",\"buffer_recreations\":"<<e.buffer_recreations
        <<",\"requested_stream_ms\":1000,\"bank_frames\":128,\"intervals\":8,\"output_payload\":\"zero PCM only\""
        <<",\"playback_keepalive\":"<<e.keepalive
        <<",\"streams\":[";
    for(unsigned i=0;i<2;++i){if(i)text<<',';text<<"{\"file\":\"stream-"<<i+1<<".json\",\"successful\":"<<streams[i].success
        <<",\"buffers_disposed\":"<<streams[i].buffers_disposed<<'}';}
    text<<"],\"host_failure\":"<<unsigned(h.failure)<<",\"io_retired\":"<<h.io_retired<<",\"device_released\":"<<h.device_released
        <<",\"device_held\":"<<h.device_held<<",\"audio_thread_retired\":"<<h.audio.retired<<",\"active_callbacks\":"<<h.audio.active_callbacks
        <<",\"worker_exited\":"<<h.process.process_exited<<",\"private_job_empty\":"<<h.process.job_empty<<",\"forced_termination\":"<<h.termination_requested
        <<",\"worker_phase\":"<<unsigned(h.device_snapshot.phase)<<",\"worker_failure\":"<<unsigned(h.device_snapshot.failure)
        <<",\"stream_fault\":"<<unsigned(h.device_snapshot.stream_fault)<<",\"native_error\":"<<h.device_snapshot.native_error
        <<",\"analogue_signal_verified\":false,\"latency_measured\":false,\"asio_com_registered\":false,\"error\":"<<quoted(e.error)<<"}\n";
    std::ofstream output(path,std::ios::binary|std::ios::trunc);output<<text.str()<<std::flush;require(bool(output),"Write retained lifecycle evidence");
}
int run_retained(WorkerSpec spec,const std::filesystem::path& folder,unsigned expected){
    require(!std::filesystem::exists(folder),"Choose a fresh output directory");require(std::filesystem::create_directory(folder),"Create retained probe directory");
    std::array<Probe,2> probes;std::array<Evidence,2> streams;RetainedEvidence evidence;evidence.expected_rate=expected;evidence.worker_sha=spec.sha256;
    const auto path=folder/L"probe.json";LARGE_INTEGER frequency{};
    require(QueryPerformanceFrequency(&frequency)!=FALSE && frequency.QuadPart>0,"Read callback counter frequency");
    spec.lifetime=DeviceLifetime::retained;
    evidence.keepalive=spec.diagnostic_playback_keepalive;
    if constexpr(kind==sl3::session::Kind::native)spec.diagnostic_directory=folder;
    save_retained(path,evidence,streams);Watchdog watchdog(45000);HostSession session(spec);
    try{
        evidence.phase="acquiring";++evidence.attempts;save_retained(path,evidence,streams);
        evidence.acquired=session.inspect();evidence.acquisition=session.report();
        require(evidence.acquired,"Retained device acquisition failed");
        require(evidence.acquisition.observed_rate_hz==expected,"Fresh acquired clock differs from explicit expectation; no rate setter or audio start");
        for(unsigned i=0;i<2;++i){
            auto& p=probes[i];auto& e=streams[i];current=&p;p.session=&session;p.counter_frequency=std::uint64_t(frequency.QuadPart);
            e.retained=true;e.retained_rate=expected;e.stream_index=i+1;e.intervals=8;e.initial_observed_rate=evidence.acquisition.observed_rate_hz;
            const auto stream_path=folder/(L"stream-"+std::to_wstring(i+1)+L".json");
            evidence.phase="stream-"+std::to_string(i+1);save_retained(path,evidence,streams);
            ASIOCallbacks callbacks{};callbacks.bufferSwitch=buffer_switch;
            require(session.create_buffers(p.planes.data(),12,bank_frames,&callbacks)==ASE_OK,"Prepare fresh retained-session SDK planes");
            if(i)++evidence.buffer_recreations;
            e.phase="starting";e.host=session.report();save(stream_path,e,p);
            e.started=session.start(8);e.host=session.report();
            if(!e.started)e.error="Retained stream startup failed";
            save(stream_path,e,p);require(e.started,"Retained stream startup failed");
            e.phase="streaming";save(stream_path,e,p);const auto begin=GetTickCount64();
            do{Sleep(5);e.host=session.report();e.elapsed=GetTickCount64()-begin;
                if(!e.host.running || e.host.failure!=HostFailure::none || p.bad.load())break;
            }while(e.elapsed<duration_ms);
            e.phase="stopping";save(stream_path,e,p);e.host=session.stop(5000);
            const auto& h=e.host;const auto& w=h.device_snapshot;
            const bool audio_retired=h.io_retired && h.audio.retired && h.audio.active_callbacks==0;
            if(audio_retired)e.buffers_disposed=session.dispose_buffers()==ASE_OK;
            e.finished=audio_retired;e.phase=audio_retired?"finished":"unretired";
            e.success=e.started && audio_retired && e.buffers_disposed && h.failure==HostFailure::none && h.device_held && !h.device_released
                && h.process.started && !h.process.process_exited && !h.termination_requested && h.audio.exit==AudioExit::stopped
                && h.observed_rate_hz==expected && !p.bad.load() && e.elapsed>=duration_ms && p.callbacks.load()>0 && p.first_frame.load()==0
                && h.audio.callbacks_started==h.audio.callbacks_completed && h.audio.callbacks_completed==p.callbacks.load()
                && w.phase==sl3::device_session::Phase::ready && w.failure==sl3::session::Failure::none && w.stream_fault==sl3::StreamFault::none
                && w.stats.input_frames>0 && w.stats.output_completions>0 && w.stats.output_frames_submitted>0 && !w.stats.pending_mask && !w.stats.retained_mask;
            save(stream_path,e,p);require(e.success,"Retained stream failed its callback/I/O/held-device retirement contract");
            ++evidence.completed_streams;save_retained(path,evidence,streams);
            if(evidence.keepalive && i==0)Sleep(300);
        }
    }catch(const std::exception& error){evidence.error=error.what();}
    evidence.phase="closing";
    try{save_retained(path,evidence,streams);}catch(...){if(evidence.error.empty())evidence.error="Progress evidence write failed";}
    evidence.final=session.close(5000);const auto& h=evidence.final;
    evidence.finished=h.io_retired && h.device_released && !h.device_held && h.audio.retired && !h.audio.active_callbacks &&
        (!h.process.started || (h.process.process_exited && h.process.job_empty));
    evidence.success=evidence.error.empty() && evidence.acquired && evidence.attempts==1 && evidence.completed_streams==2 && evidence.buffer_recreations==1
        && evidence.finished && !h.termination_requested && h.failure==HostFailure::none && h.device_snapshot.phase==sl3::device_session::Phase::closed
        && h.device_snapshot.failure==sl3::session::Failure::none && streams[0].success && streams[1].success;
    evidence.phase=evidence.finished?"finished":"unretired";
    try{save_retained(path,evidence,streams);}catch(...){if(!evidence.finished){TerminateProcess(GetCurrentProcess(),1);std::abort();}throw;}
    if(!evidence.finished){TerminateProcess(GetCurrentProcess(),1);std::abort();}
    current=nullptr;return evidence.success?0:1;
}
void write_control_owner(std::ostream& text,const char* name,const HostReport& h){
        const auto& d=h.device_snapshot;const auto& s=d.stats;
        text<<",\""<<name<<"\":{\"rate_hz\":"<<h.observed_rate_hz<<",\"host_failure\":"<<unsigned(h.failure)
            <<",\"running\":"<<h.running<<",\"io_retired\":"<<h.io_retired<<",\"device_released\":"<<h.device_released<<",\"device_held\":"<<h.device_held
            <<",\"audio_thread_retired\":"<<h.audio.retired<<",\"active_callbacks\":"<<h.audio.active_callbacks
            <<",\"callbacks_started\":"<<h.audio.callbacks_started<<",\"callbacks_completed\":"<<h.audio.callbacks_completed
            <<",\"process_started\":"<<h.process.started<<",\"worker_exited\":"<<h.process.process_exited<<",\"private_job_empty\":"<<h.process.job_empty
            <<",\"forced_termination\":"<<h.termination_requested<<",\"worker_phase\":"<<unsigned(d.phase)<<",\"worker_failure\":"<<unsigned(d.failure)
            <<",\"stream_fault\":"<<unsigned(d.stream_fault)<<",\"native_error\":"<<d.native_error
            <<",\"audio_input_submissions\":"<<s.input_submissions<<",\"audio_input_frames\":"<<s.input_frames
            <<",\"audio_input_blocks\":"<<s.input_blocks<<",\"audio_owner_input_frames\":"<<h.audio.input_frames<<",\"published_output_frames\":"<<h.audio.published_frames
            <<",\"audio_output_submissions\":"<<s.output_submissions<<",\"audio_output_completions\":"<<s.output_completions
            <<",\"audio_output_frames_submitted\":"<<s.output_frames_submitted
            <<",\"pending_mask\":"<<s.pending_mask<<",\"retained_mask\":"<<s.retained_mask<<'}';
}
struct ControlsEvidence {
    std::string phase="preparing",error,worker_sha;
    unsigned acquisitions=0,queries=0;
    bool acquired=false,finished=false,success=false;
    HostReport acquisition{},query{},final{};
    std::optional<sl3::device_session::ControlSample> sample;
};
void save_controls(const std::filesystem::path& path,const ControlsEvidence& e){
    std::ostringstream text;text<<std::boolalpha;
    text<<"{\"schema\":\"sl3.controls-host-probe.v1\",\"phase\":"<<quoted(e.phase)
        <<",\"simulated\":"<<(kind==sl3::session::Kind::simulated)<<",\"worker_sha256\":"<<quoted(e.worker_sha)
        <<",\"device_protocol_version\":"<<sl3::device_session::version<<",\"successful\":"<<e.success<<",\"finished\":"<<e.finished
        <<",\"acquisition_attempts\":"<<e.acquisitions<<",\"acquisition_verified\":"<<e.acquired<<",\"query_attempts\":"<<e.queries
        <<",\"sample_present\":"<<bool(e.sample)<<",\"received_frames\":";
    if(e.sample)text<<e.sample->received_frames;else text<<"null";
    text<<",\"audio_start_attempts\":0,\"audio_buffers_created\":false,\"alternate_changes_requested\":0"
        <<",\"rate_changes\":0,\"control_setters\":0,\"firmware_requests\":0,\"calibration_verified\":false"
        <<",\"analogue_signal_verified\":false,\"asio_com_registered\":false,\"raw_controls\":";
    if(e.sample){
        text<<'[';for(std::size_t i=0;i<e.sample->audio.raw.size();++i){if(i)text<<',';text<<unsigned(e.sample->audio.raw[i]);}text<<']';
    }else text<<"null";
    text<<",\"inputs\":";
    if(e.sample){
        text<<'[';for(std::size_t i=0;i<3;++i){
            if(i)text<<',';const auto state=*e.sample->audio.input(i);const auto mv=state.original_ui_sensitivity_tenths_mv();
            text<<"{\"group\":"<<i<<",\"phono_raw\":"<<unsigned(state.phono_raw)<<",\"phono_nonzero\":"<<state.phono_switch_nonzero()
                <<",\"sensitivity_code\":"<<unsigned(state.sensitivity_raw)<<",\"original_ui_sensitivity_tenths_mv\":";
            if(mv)text<<*mv;else text<<"null";
            text<<",\"through_raw\":"<<unsigned(state.through_raw)<<",\"through_nonzero\":"<<state.through_nonzero()<<'}';
        }text<<']';
    }else text<<"null";
    write_control_owner(text,"acquisition",e.acquisition);write_control_owner(text,"after_query",e.query);write_control_owner(text,"final",e.final);
    text<<",\"error\":"<<quoted(e.error)<<"}\n";
    std::ofstream output(path,std::ios::binary|std::ios::trunc);output<<text.str()<<std::flush;require(bool(output),"Write controls evidence");
}
bool idle_controls_owner(const HostReport& h){
    const auto& s=h.device_snapshot.stats;
    return h.failure==HostFailure::none && !h.running && h.io_retired && h.audio.retired && !h.audio.active_callbacks
        && !h.audio.callbacks_started && !h.audio.callbacks_completed && !s.input_submissions && !s.output_submissions
        && !s.input_frames && !s.input_blocks && !s.output_completions && !s.output_frames_submitted && !h.audio.input_frames && !h.audio.published_frames
        && !s.pending_mask && !s.retained_mask;
}
struct SelectionEvidence {
    std::string phase="preparing",error,worker_sha;
    sl3::control::selection_wire::Target target{sl3::control::AudioControlSetting::through,0,0};
    unsigned acquisitions=0,queries=0,selections=0;
    bool acquired=false,pending=false,finished=false,success=false;
    std::optional<sl3::device_session::ControlSample> baseline;
    std::optional<std::array<std::uint8_t,22>> reviewed_baseline;
    ControlSelectionReport result{};
    HostReport acquisition{},query{},operation{},final{};
};
void save_selection(const std::filesystem::path& path,const SelectionEvidence& e){
    std::ostringstream text;text<<std::boolalpha;
    const bool verified=e.result.outcome && e.result.outcome->selection.error==sl3::control::SelectionIoError::none;
    text<<"{\"schema\":\"sl3.selection-host-probe.v2\",\"phase\":"<<quoted(e.phase)<<",\"simulated\":"<<(kind==sl3::session::Kind::simulated)
        <<",\"worker_sha256\":"<<quoted(e.worker_sha)<<",\"device_protocol_version\":"<<sl3::device_session::version
        <<",\"target\":{\"setting\":"<<quoted(e.target.setting==sl3::control::AudioControlSetting::through?"through":"sensitivity")
        <<",\"group\":"<<e.target.group<<",\"value\":"<<e.target.value<<"},\"successful\":"<<e.success<<",\"finished\":"<<e.finished
        <<",\"acquisition_attempts\":"<<e.acquisitions<<",\"acquisition_verified\":"<<e.acquired<<",\"baseline_query_attempts\":"<<e.queries
        <<",\"selection_attempts\":"<<e.selections<<",\"publication_pending\":"<<e.pending<<",\"command_attempted\":";
    if(e.pending)text<<"null";else text<<e.result.command_attempted;
    text<<",\"outcome_unknown\":"<<e.result.outcome_unknown<<",\"device_may_have_changed\":"<<e.result.device_may_have_changed
        <<",\"operation_verified\":"<<verified<<",\"baseline_received_frames\":";
    if(e.baseline)text<<e.baseline->received_frames;else text<<"null";
    text<<",\"baseline_raw_controls\":";
    if(e.baseline){text<<'[';for(std::size_t i=0;i<e.baseline->audio.raw.size();++i){if(i)text<<',';text<<unsigned(e.baseline->audio.raw[i]);}text<<']';}
    else text<<"null";
    text<<",\"reviewed_baseline_raw_controls\":";
    if(e.reviewed_baseline){text<<'[';for(std::size_t i=0;i<e.reviewed_baseline->size();++i){if(i)text<<',';text<<unsigned((*e.reviewed_baseline)[i]);}text<<']';}
    else text<<"null";
    text<<",\"outcome_wire_hex\":";
    if(e.result.outcome){
        constexpr char hex[]="0123456789abcdef";const auto bytes=sl3::control::selection_wire::encode_reply(*e.result.outcome);
        text<<'"';for(auto byte:bytes)text<<hex[byte>>4]<<hex[byte&15];text<<'"';
    }else text<<"null";
    text<<",\"audio_start_attempts\":0,\"audio_buffers_created\":false,\"alternate_changes_requested\":0,\"rate_changes\":0"
        <<",\"firmware_requests\":0,\"calibration_verified\":false,\"analogue_signal_verified\":false,\"asio_com_registered\":false";
    write_control_owner(text,"acquisition",e.acquisition);write_control_owner(text,"after_baseline",e.query);
    write_control_owner(text,"after_selection",e.operation);write_control_owner(text,"final",e.final);
    text<<",\"error\":"<<quoted(e.error)<<"}\n";
    std::ofstream output(path,std::ios::binary|std::ios::trunc);output<<text.str()<<std::flush;require(bool(output),"Write selection evidence");
}
int run_selection(WorkerSpec spec,const std::filesystem::path& folder,sl3::control::selection_wire::Target target,
                  const std::optional<std::array<std::uint8_t,22>>& reviewed){
    require(!std::filesystem::exists(folder),"Choose a fresh selection output directory");
    require(std::filesystem::create_directory(folder),"Create selection output directory");
    spec.lifetime=DeviceLifetime::retained;
    if constexpr(kind==sl3::session::Kind::native){spec.diagnostic_directory=folder;spec.diagnostic_control_target=target;}
    SelectionEvidence e;e.target=target;e.worker_sha=spec.sha256;e.reviewed_baseline=reviewed;const auto path=folder/L"probe.json";
    // Immutable initial request survives later progress-file truncation/crash.
    // Both writes finish before HostSession can launch/contact a worker.
    save_selection(folder/L"request.json",e);save_selection(path,e);Watchdog watchdog(45000);HostSession session(spec);
    try{
        e.phase="acquiring";e.acquisitions=1;save_selection(path,e);
        e.acquired=session.inspect();e.acquisition=session.report();require(e.acquired,"Selection acquisition failed");
        require(idle_controls_owner(e.acquisition) && e.acquisition.device_held,"Selection needs an idle healthy owner");
        e.phase="baseline";e.queries=1;save_selection(path,e);
        e.baseline=session.inspect_controls();e.query=session.report();require(bool(e.baseline),"Selection baseline failed");
        require(!reviewed || e.baseline->audio.raw==*reviewed,"Fresh table differs from reviewed baseline; no selection attempted");
        require(idle_controls_owner(e.query) && e.query.device_held && e.query.device_snapshot.selection_supported,"Selection capability absent after baseline");
        e.phase="selection_pending";e.selections=1;e.pending=true;
        e.result.outcome_unknown=true;e.result.device_may_have_changed=true;save_selection(path,e);
        e.result=session.select_control(target);e.pending=false;e.operation=session.report();
        require(e.result.command_attempted && !e.result.outcome_unknown && e.result.outcome &&
                e.result.outcome->selection.error==sl3::control::SelectionIoError::none,"Selection did not return a verified outcome");
        require(idle_controls_owner(e.operation) && e.operation.device_held,"Selection did not preserve a retired idle owner");
    }catch(const std::exception& error){e.error=error.what();e.operation=session.report();}
    e.phase="closing";try{save_selection(path,e);}catch(...){if(e.error.empty())e.error="Selection progress write failed";}
    e.final=session.close(5000);const auto& h=e.final;
    e.finished=h.io_retired && h.device_released && !h.device_held && h.audio.retired && !h.audio.active_callbacks &&
        (!h.process.started || (h.process.process_exited && h.process.job_empty));
    e.success=e.error.empty() && e.acquired && e.acquisitions==1 && e.queries==1 && e.selections==1 && e.baseline &&
        !e.pending && e.result.command_attempted && !e.result.outcome_unknown && e.result.outcome &&
        e.result.outcome->selection.error==sl3::control::SelectionIoError::none && e.finished && !h.termination_requested &&
        idle_controls_owner(e.acquisition) && idle_controls_owner(e.query) && idle_controls_owner(e.operation) && idle_controls_owner(h) &&
        h.device_snapshot.phase==sl3::device_session::Phase::closed;
    if(!e.success && e.error.empty())e.error="Selection probe failed its final ownership contract";
    e.phase=e.finished?"finished":"unretired";
    try{save_selection(path,e);}catch(...){if(!e.finished){TerminateProcess(GetCurrentProcess(),1);std::abort();}throw;}
    if(!e.finished){TerminateProcess(GetCurrentProcess(),1);std::abort();}return e.success?0:1;
}
struct RateEvidence {
    std::string phase="preparing",error,worker_sha;
    unsigned target=0,acquisitions=0,selections=0;
    std::optional<unsigned> expected_initial;
    bool acquired=false,pending=false,finished=false,success=false;
    RateSelectionReport result{};
    HostReport acquisition{},operation{},final{};
};
void save_rate(const std::filesystem::path& path,const RateEvidence& e){
    std::ostringstream text;text<<std::boolalpha;
    const bool verified=e.result.outcome && e.result.outcome->observation.error==sl3::control::DiagnosticError::none;
    text<<"{\"schema\":\"sl3.rate-host-probe.v1\",\"phase\":"<<quoted(e.phase)<<",\"simulated\":"<<(kind==sl3::session::Kind::simulated)
        <<",\"worker_sha256\":"<<quoted(e.worker_sha)<<",\"device_protocol_version\":"<<sl3::device_session::version
        <<",\"target_rate_hz\":"<<e.target<<",\"expected_initial_rate_hz\":";
    if(e.expected_initial)text<<*e.expected_initial;else text<<"null";
    text<<",\"successful\":"<<e.success<<",\"finished\":"<<e.finished<<",\"acquisition_attempts\":"<<e.acquisitions
        <<",\"acquisition_verified\":"<<e.acquired<<",\"selection_attempts\":"<<e.selections<<",\"publication_pending\":"<<e.pending
        <<",\"command_attempted\":";
    if(e.pending)text<<"null";else text<<e.result.command_attempted;
    text<<",\"outcome_unknown\":"<<e.result.outcome_unknown<<",\"device_may_have_changed\":"<<e.result.device_may_have_changed
        <<",\"rejected_before_operation\":"<<e.result.rejected_before_operation<<",\"operation_verified\":"<<verified<<",\"outcome_wire_hex\":";
    if(e.result.outcome){
        constexpr char hex[]="0123456789abcdef";const auto bytes=sl3::control::rate_wire::encode_reply(*e.result.outcome);
        text<<'"';for(auto byte:bytes)text<<hex[byte>>4]<<hex[byte&15];text<<'"';
    }else text<<"null";
    text<<",\"audio_start_attempts\":0,\"audio_buffers_created\":false,\"alternate_changes_requested\":0,\"control_setters\":0"
        <<",\"automatic_rollback\":false,\"firmware_requests\":0,\"calibration_verified\":false,\"analogue_signal_verified\":false,\"asio_com_registered\":false";
    write_control_owner(text,"acquisition",e.acquisition);write_control_owner(text,"after_selection",e.operation);write_control_owner(text,"final",e.final);
    text<<",\"error\":"<<quoted(e.error)<<"}\n";
    std::ofstream output(path,std::ios::binary|std::ios::trunc);output<<text.str()<<std::flush;require(bool(output),"Write rate evidence");
}
int run_rate(WorkerSpec spec,const std::filesystem::path& folder,unsigned target,std::optional<unsigned> expected){
    require(!std::filesystem::exists(folder),"Choose a fresh rate output directory");
    require(std::filesystem::create_directory(folder),"Create rate output directory");spec.lifetime=DeviceLifetime::retained;
    if constexpr(kind==sl3::session::Kind::native){spec.diagnostic_directory=folder;spec.diagnostic_rate_target=target;}
    RateEvidence e;e.target=target;e.expected_initial=expected;e.worker_sha=spec.sha256;const auto path=folder/L"probe.json";
    save_rate(folder/L"request.json",e);save_rate(path,e);Watchdog watchdog(45000);HostSession session(spec);
    try{
        e.phase="acquiring";e.acquisitions=1;save_rate(path,e);
        e.acquired=session.inspect();e.acquisition=session.report();require(e.acquired,"Rate acquisition failed");
        require(idle_controls_owner(e.acquisition) && e.acquisition.device_held,"Rate selection requires an idle healthy owner");
        require(!expected || e.acquisition.observed_rate_hz==*expected,"Acquired clock differs from reviewed initial rate; no selection attempted");
        e.phase="selection_pending";e.selections=1;e.pending=true;e.result.outcome_unknown=true;e.result.device_may_have_changed=true;save_rate(path,e);
        e.result=session.select_rate(target);e.pending=false;e.operation=session.report();
        require(e.result.command_attempted && !e.result.outcome_unknown && e.result.outcome &&
            e.result.outcome->observation.error==sl3::control::DiagnosticError::none,"Rate selection did not return a verified outcome");
        require(e.result.outcome->observation.initial_rate_hz==e.acquisition.observed_rate_hz,"Transaction initial getter differs from acquired clock");
        require(idle_controls_owner(e.operation) && e.operation.device_held && e.operation.observed_rate_hz==target,"Rate selection did not preserve a verified idle owner");
    }catch(const std::exception& error){e.error=error.what();e.operation=session.report();}
    e.phase="closing";try{save_rate(path,e);}catch(...){if(e.error.empty())e.error="Rate progress write failed";}
    e.final=session.close(5000);const auto& h=e.final;
    e.finished=h.io_retired && h.device_released && !h.device_held && h.audio.retired && !h.audio.active_callbacks &&
        (!h.process.started || (h.process.process_exited && h.process.job_empty));
    e.success=e.error.empty() && e.acquired && e.acquisitions==1 && e.selections==1 && !e.pending &&
        e.result.command_attempted && !e.result.outcome_unknown && !e.result.rejected_before_operation && e.result.outcome &&
        e.result.outcome->observation.error==sl3::control::DiagnosticError::none && e.finished && !h.termination_requested &&
        idle_controls_owner(e.acquisition) && idle_controls_owner(e.operation) && idle_controls_owner(h) &&
        h.observed_rate_hz==target && h.device_snapshot.phase==sl3::device_session::Phase::closed;
    if(!e.success && e.error.empty())e.error="Rate probe failed its final ownership contract";
    e.phase=e.finished?"finished":"unretired";
    try{save_rate(path,e);}catch(...){if(!e.finished){TerminateProcess(GetCurrentProcess(),1);std::abort();}throw;}
    if(!e.finished){TerminateProcess(GetCurrentProcess(),1);std::abort();}return e.success?0:1;
}
int run_controls(WorkerSpec spec,const std::filesystem::path& folder){
    require(!std::filesystem::exists(folder),"Choose a fresh output directory");
    require(std::filesystem::create_directory(folder),"Create controls output directory");
    spec.lifetime=DeviceLifetime::retained;
    if constexpr(kind==sl3::session::Kind::native)spec.diagnostic_directory=folder;
    ControlsEvidence e;e.worker_sha=spec.sha256;const auto path=folder/L"probe.json";
    save_controls(path,e);Watchdog watchdog;HostSession session(spec);
    try{
        e.phase="acquiring";e.acquisitions=1;save_controls(path,e);
        e.acquired=session.inspect();e.acquisition=session.report();require(e.acquired,"Idle retained acquisition failed");
        require(idle_controls_owner(e.acquisition) && e.acquisition.device_held,"Acquired owner is not idle and healthy");
        e.phase="inspecting_controls";e.queries=1;save_controls(path,e);
        e.sample=session.inspect_controls();e.query=session.report();require(bool(e.sample),"Read-only control inspection failed");
        require(idle_controls_owner(e.query) && e.query.device_held,"Control inspection did not preserve an idle held device");
    }catch(const std::exception& error){e.error=error.what();e.query=session.report();}
    e.phase="closing";try{save_controls(path,e);}catch(...){if(e.error.empty())e.error="Controls progress write failed";}
    e.final=session.close(5000);const auto& h=e.final;
    e.finished=h.io_retired && h.device_released && !h.device_held && h.audio.retired && !h.audio.active_callbacks
        && (!h.process.started || (h.process.process_exited && h.process.job_empty));
    e.success=e.error.empty() && e.acquired && e.acquisitions==1 && e.queries==1 && e.sample && e.sample->received_frames>=1
        && e.sample->received_frames<=4 && idle_controls_owner(e.acquisition) && idle_controls_owner(e.query) && idle_controls_owner(h)
        && e.finished && !h.termination_requested && h.device_snapshot.phase==sl3::device_session::Phase::closed;
    if(!e.success && e.error.empty())e.error="Controls probe failed its final ownership contract";
    e.phase=e.finished?"finished":"unretired";
    try{save_controls(path,e);}catch(...){if(!e.finished){TerminateProcess(GetCurrentProcess(),1);std::abort();}throw;}
    if(!e.finished){TerminateProcess(GetCurrentProcess(),1);std::abort();}return e.success?0:1;
}
}
int wmain(int argc,wchar_t** argv){
    if(argc==1 || (argc==2 && std::wstring(argv[1])==L"--plan")){
        std::cout<<"{\"plan_only\":true,\"device_access\":false,\"output_payload\":\"zero PCM only\",\"stream_ms\":1000,\"bank_frames\":128,\"intervals\":64,\"simulated\":"
                 <<(kind==sl3::session::Kind::simulated?"true":"false")<<",\"supported_single_open_intervals\":[8,64],\"retained_lifecycle\":{\"streams\":2,\"stream_ms\":1000,\"intervals\":8,\"bank_frames\":128},\"controls_inspection\":{\"mode\":\"--controls\",\"audio\":false,\"maximum_reads\":4}}\n";return 0;
    }
    const std::wstring mode=argc>1?argv[1]:L"";
    const unsigned single_open_rate=mode==L"--single-open-44100"?44100u:mode==L"--single-open-48000"?48000u:0u;
    const bool keepalive=mode==L"--retained-keepalive-44100";
    if(keepalive && kind!=sl3::session::Kind::native)return 2;
    const unsigned retained_rate=mode==L"--retained-44100" || keepalive?44100u:mode==L"--retained-48000"?48000u:0u;
    const bool controls=mode==L"--controls",selection=mode==L"--select-control",rate_select=mode==L"--select-rate";
    if((argc!=10 && argc!=12 && !((selection || rate_select) && (argc==14 || argc==16))) || (mode!=L"--run" && mode!=L"--inspect-reopen" && !single_open_rate && !retained_rate && !controls && !selection && !rate_select)){std::cerr<<"Expected explicit probe mode, --worker FILE --worker-sha256 HASH --helper FILE --output NEW_DIRECTORY; selection requires --target KIND:GROUP:VALUE\n";return 2;}
    unsigned intervals=default_interval_count;
    std::wstring fixture_mode=L"normal";
    std::optional<sl3::control::selection_wire::Target> target;
    std::optional<std::array<std::uint8_t,22>> reviewed;
    std::optional<unsigned> rate_target,expected_initial;
    if(rate_select){
        if((argc!=12 && argc!=14 && argc!=16) || std::wstring(argv[10])!=L"--target")return 2;
        try{rate_target=sl3::control::parse_rate_test_target(argv[11]);}catch(...){return 2;}
        if constexpr(kind==sl3::session::Kind::simulated)fixture_mode=L"rate-normal";
        bool fixture_given=false;
        for(int at=12;at<argc;at+=2){
            const std::wstring option=argv[at],value=argv[at+1];
            if(option==L"--expected-initial" && !expected_initial){try{expected_initial=sl3::control::parse_rate_test_target(value);}catch(...){return 2;}}
            else if(option==L"--fixture-mode" && !fixture_given){
                if constexpr(kind!=sl3::session::Kind::simulated){return 2;}else{
                    fixture_given=true;fixture_mode=value;
                    if(fixture_mode!=L"rate-normal" && fixture_mode!=L"normal" && fixture_mode!=L"rate-mismatch" && fixture_mode!=L"rate-transfer"
                       && fixture_mode!=L"rate-transfer-close" && fixture_mode!=L"rate-success-close" && fixture_mode!=L"rate-throw"
                       && fixture_mode!=L"rate-bad" && fixture_mode!=L"rate-hang" && fixture_mode!=L"fail-acquire" && fixture_mode!=L"invalid-clock")return 2;
                }
            }else return 2;
        }
        if constexpr(kind==sl3::session::Kind::native){if(!expected_initial)return 2;}
    }else if(selection){
        if((argc!=12 && argc!=14 && argc!=16) || std::wstring(argv[10])!=L"--target")return 2;
        try{target=sl3::control::parse_control_test_target(argv[11]);}catch(...){return 2;}
        bool fixture_given=false;
        for(int at=12;at<argc;at+=2){
            const std::wstring option=argv[at],value=argv[at+1];
            if(option==L"--baseline-controls" && !reviewed){
                if(value.size()!=44 || !std::all_of(value.begin(),value.end(),[](wchar_t c){return (c>=L'0' && c<=L'9') || (c>=L'a' && c<=L'f');}))return 2;
                const auto digit=[](wchar_t c){return unsigned(c<=L'9'?c-L'0':c-L'a'+10);};
                reviewed.emplace();for(std::size_t i=0;i<22;++i)(*reviewed)[i]=std::uint8_t(16*digit(value[2*i])+digit(value[2*i+1]));
            }else if(option==L"--fixture-mode" && !fixture_given){
                if constexpr(kind!=sl3::session::Kind::simulated){return 2;}else{
                    fixture_given=true;fixture_mode=value;
                    if(fixture_mode!=L"normal" && fixture_mode!=L"selection-noop" && fixture_mode!=L"fail-selection" && fixture_mode!=L"mismatch-selection"
                       && fixture_mode!=L"bad-selection" && fixture_mode!=L"throw-selection" && fixture_mode!=L"hang-selection" && fixture_mode!=L"slow-selection"
                       && fixture_mode!=L"selection-fail-close" && fixture_mode!=L"selection-success-close" && fixture_mode!=L"selection-unsupported"
                       && fixture_mode!=L"fail-controls" && fixture_mode!=L"invalid-clock" && fixture_mode!=L"hang-device-close" && fixture_mode!=L"fail-device-close")return 2;
                }
            }else return 2;
        }
        if constexpr(kind==sl3::session::Kind::native){if(!reviewed)return 2;}
    }else if(argc==12){
        if(controls && kind==sl3::session::Kind::simulated){
            if(std::wstring(argv[10])!=L"--fixture-mode")return 2;fixture_mode=argv[11];
            if(fixture_mode!=L"normal" && fixture_mode!=L"fail-controls" && fixture_mode!=L"bad-controls" && fixture_mode!=L"hang-controls" && fixture_mode!=L"invalid-clock"
               && fixture_mode!=L"hang-device-close" && fixture_mode!=L"fail-device-close")return 2;
        }else{
            if(!single_open_rate || std::wstring(argv[10])!=L"--intervals")return 2;
            const std::wstring shape=argv[11];if(shape!=L"8" && shape!=L"64")return 2;
            intervals=shape==L"8"?8u:64u;
        }
    }
    WorkerSpec spec;spec.kind=kind;spec.fixture_mode=fixture_mode;spec.diagnostic_playback_keepalive=keepalive;
    std::filesystem::path folder;
    if(std::wstring(argv[2])!=L"--worker" || std::wstring(argv[4])!=L"--worker-sha256" ||
       std::wstring(argv[6])!=L"--helper" || std::wstring(argv[8])!=L"--output")return 2;
    spec.executable=argv[3];spec.helper=argv[7];folder=argv[9];
    const std::wstring sha=argv[5];
    if(sha.size()!=64 || !std::all_of(sha.begin(),sha.end(),[](wchar_t c){return (c>=L'0' && c<=L'9')||(c>=L'a' && c<=L'f')||(c>=L'A' && c<=L'F');}) ||
       !local_absolute(spec.executable) || !local_absolute(spec.helper) || !local_absolute(folder))return 2;
    for(const auto ch:sha)spec.sha256.push_back(static_cast<char>(ch));
    try{return rate_select?run_rate(spec,folder,*rate_target,expected_initial):selection?run_selection(spec,folder,*target,reviewed):controls?run_controls(spec,folder):retained_rate?run_retained(spec,folder,retained_rate):run(spec,folder,mode==L"--inspect-reopen",single_open_rate,intervals);}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
