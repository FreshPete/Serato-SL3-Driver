// Original bounded diagnostic using the unchanged UsbDk 1.0.22 helper ABI.
// No installer, hide rule, reset or firmware. Rate writes require --select-rate
// or a single-use --rate-test-target in an explicitly journalled device worker.
// Audio OUT is available
// in the explicit bounded --duplex-silence diagnostic (all zero), or after an
// explicit typed start in an isolated --stream-worker or --device-worker mode.
// The latter retains its redirect across successful audio stops. Nothing auto-starts.
#include <windows.h>
#include <cfgmgr32.h>
#include <usb.h>
#include <bcrypt.h>
#include "UsbDkHelper.h"
#include "core/capture.hpp"
#include "core/playback.hpp"
#include "core/duplex.hpp"
#include "core/worker_protocol.hpp"
#include "core/control_frames.hpp"
#include "core/audio_controls_query.hpp"
#include "core/rate_diagnostic.hpp"
#include "core/rate_test_grant.hpp"
#include "core/driver_timer_query.hpp"
#include "windows/redirect_owner.hpp"
#include "core/device_presence.hpp"
#include "windows/mailbox.hpp"
#include "windows/stream_session.hpp"
#include "windows/device_session.hpp"
#include "windows/usbdk_stream.hpp"
#include "windows/diagnostic.hpp"
#include "windows/sl3_fixture.hpp"
#include "windows/startup_journal.hpp"
#include "windows/rate_io_log.hpp"
#include "windows/control_transfer_io.hpp"
#include "windows/control_selection_diagnostic.hpp"
#include "windows/driver_timer_io.hpp"
#include "core/control_test_target.hpp"
#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <memory>
#include <vector>

namespace {
using namespace sl3::diagnostic;
static_assert(sizeof(void*) == 8, "The pinned helper is Windows x64");
static_assert(sizeof(USB_DK_TRANSFER_REQUEST) == 72 && offsetof(USB_DK_TRANSFER_REQUEST, Result) == 48, "UsbDk request ABI mismatch");
static_assert(sizeof(USB_DK_ISO_TRANSFER_RESULT) == 16 && sizeof(USB_DK_DEVICE_INFO) == 848, "UsbDk result/device ABI mismatch");
static_assert(HighSpeed==3,"Typed probe uses the pinned UsbDk speed enumeration");
constexpr unsigned requests=4, intervals=64, bytes_per_request=intervals*126;
constexpr char helper_sha256[]="66bbfe6f99b417f97c7a9e97816e24af7dde0e01b8e535c41e91e1c6c19cfeda";

struct File {
    HANDLE value=INVALID_HANDLE_VALUE;
    ~File(){if(value!=INVALID_HANDLE_VALUE)CloseHandle(value);}
};
std::string sha256(HANDLE file);
void require_running_driver() {
    const auto manager=OpenSCManagerW(nullptr,nullptr,SC_MANAGER_CONNECT);
    if(!manager) failed("Open service manager for query");
    const auto service=OpenServiceW(manager,L"UsbDk",SERVICE_QUERY_STATUS|SERVICE_QUERY_CONFIG);
    const auto open_error=GetLastError();CloseServiceHandle(manager);
    if(!service){SetLastError(open_error);failed("UsbDk must already be installed and running; this program does not install it");}
    SERVICE_STATUS_PROCESS status{};DWORD bytes=0;
    const auto ok=QueryServiceStatusEx(service,SC_STATUS_PROCESS_INFO,reinterpret_cast<LPBYTE>(&status),sizeof(status),&bytes);
    const auto error=GetLastError();
    std::vector<UCHAR> config_data;
    if(ok && status.dwCurrentState==SERVICE_RUNNING){
        DWORD required=0;QueryServiceConfigW(service,nullptr,0,&required);
        if(GetLastError()!=ERROR_INSUFFICIENT_BUFFER || !required){CloseServiceHandle(service);failed("Query driver service configuration size");}
        config_data.resize(required);
        if(!QueryServiceConfigW(service,reinterpret_cast<QUERY_SERVICE_CONFIGW*>(config_data.data()),required,&required)){
            const auto config_error=GetLastError();CloseServiceHandle(service);SetLastError(config_error);failed("Query driver service configuration");
        }
    }
    CloseServiceHandle(service);
    if(!ok){SetLastError(error);failed("Query UsbDk service");}
    if(status.dwCurrentState!=SERVICE_RUNNING)throw std::runtime_error("UsbDk service is not running; no DLL loaded or device redirected");
    const auto* config=reinterpret_cast<const QUERY_SERVICE_CONFIGW*>(config_data.data());
    if(config->dwServiceType!=SERVICE_KERNEL_DRIVER || !config->lpBinaryPathName)throw std::runtime_error("Unexpected UsbDk service type/path");
    std::wstring source(config->lpBinaryPathName);
    if(source.size()>1 && source.front()==L'"' && source.back()==L'"')source=source.substr(1,source.size()-2);
    if(source.compare(0,12,L"\\SystemRoot\\")==0){
        std::array<wchar_t,MAX_PATH> windows{};const auto count=GetWindowsDirectoryW(windows.data(),UINT(windows.size()));
        if(!count || count>=windows.size())failed("Resolve SystemRoot");
        source=std::wstring(windows.data())+L"\\"+source.substr(12);
    }else if(source.compare(0,4,L"\\??\\")==0)source.erase(0,4);
    std::array<wchar_t,32768> expanded{};const auto count=ExpandEnvironmentStringsW(source.c_str(),expanded.data(),DWORD(expanded.size()));
    if(!count || count>expanded.size())failed("Expand driver path");
    const std::filesystem::path driver(expanded.data());
    if(!driver.is_absolute())throw std::runtime_error("UsbDk service image must have an absolute path");
    File file;file.value=CreateFileW(driver.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file.value==INVALID_HANDLE_VALUE)failed("Read installed UsbDk image");
    if(sha256(file.value)!="c92b6c15bd550023312ae4cfe49a39757952a3c2ebdc7d1d143ac5e695f69a63")throw std::runtime_error("UsbDk service image differs from reviewed Windows 10 binary; no DLL loaded");
}
std::string sha256(HANDLE file) {
    struct Hash {
        BCRYPT_ALG_HANDLE algorithm{};BCRYPT_HASH_HANDLE hash{};
        std::vector<UCHAR> object;
        ~Hash(){if(hash)BCryptDestroyHash(hash);if(algorithm)BCryptCloseAlgorithmProvider(algorithm,0);}
    } state;
    auto check=[](NTSTATUS status){if(status<0)throw std::runtime_error("Helper SHA256 verification failed");};
    check(BCryptOpenAlgorithmProvider(&state.algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0));
    DWORD size=0,received=0;
    check(BCryptGetProperty(state.algorithm,BCRYPT_OBJECT_LENGTH,reinterpret_cast<PUCHAR>(&size),sizeof(size),&received,0));
    state.object.resize(size);
    check(BCryptCreateHash(state.algorithm,&state.hash,state.object.data(),size,nullptr,0,0));
    std::array<UCHAR,65536> buffer{};
    for(;;){DWORD count=0;if(!ReadFile(file,buffer.data(),DWORD(buffer.size()),&count,nullptr))failed("Read pinned helper");if(!count)break;check(BCryptHashData(state.hash,buffer.data(),count,0));}
    std::array<UCHAR,32> digest{};check(BCryptFinishHash(state.hash,digest.data(),ULONG(digest.size()),0));
    std::ostringstream out;out<<std::hex<<std::setfill('0');for(auto value:digest)out<<std::setw(2)<<unsigned(value);
    return out.str();
}
struct Api {
    sl3::diagnostic::StartupJournal* journal=nullptr;
    void mark(const char* stage) const noexcept {if(journal)journal->mark(stage);}
    // Holding this file open denies changes/deletion between hashing/loading.
    File helper_file;
    HMODULE module{};
    decltype(&UsbDk_GetDevicesList) list{};
    decltype(&UsbDk_ReleaseDevicesList) release_list{};
    decltype(&UsbDk_GetConfigurationDescriptor) configuration{};
    decltype(&UsbDk_ReleaseConfigurationDescriptor) release_configuration{};
    decltype(&UsbDk_StartRedirect) start{};
    decltype(&UsbDk_StopRedirect) stop{};
    decltype(&UsbDk_GetRedirectorSystemHandle) system_handle{};
    decltype(&UsbDk_ReadPipe) read{};
    decltype(&UsbDk_WritePipe) write{};
    decltype(&UsbDk_SetAltsetting) set_alt{};
    ~Api(){if(module){mark("helper_unload.enter");FreeLibrary(module);mark("helper_unload.return");}}
    template<class T> void resolve(T& target,const char* name) {
        const auto address=GetProcAddress(module,name);
        if(!address)failed("Resolve pinned helper export");
        static_assert(sizeof(target)==sizeof(address),"Function pointer size mismatch");
        std::memcpy(&target,&address,sizeof(target));
    }
    void load(const std::filesystem::path& source) {
        mark("helper_load.enter");
        require_running_driver();
        const auto absolute=std::filesystem::canonical(source);
        helper_file.value=CreateFileW(absolute.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        if(helper_file.value==INVALID_HANDLE_VALUE)failed("Lock pinned helper");
        if(sha256(helper_file.value)!=helper_sha256)throw std::runtime_error("Helper differs from reviewed Windows x64 UsbDk 1.0.22 binary; no DLL loaded");
        module=LoadLibraryExW(absolute.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);
        if(!module)failed("Load pinned helper");
        resolve(list,"UsbDk_GetDevicesList");resolve(release_list,"UsbDk_ReleaseDevicesList");
        resolve(configuration,"UsbDk_GetConfigurationDescriptor");resolve(release_configuration,"UsbDk_ReleaseConfigurationDescriptor");
        resolve(start,"UsbDk_StartRedirect");resolve(stop,"UsbDk_StopRedirect");resolve(system_handle,"UsbDk_GetRedirectorSystemHandle");
        resolve(read,"UsbDk_ReadPipe");resolve(write,"UsbDk_WritePipe");resolve(set_alt,"UsbDk_SetAltsetting");
        mark("helper_load.return");
        // Installation, device/pipe reset and hide-rule exports are not resolved.
    }
    USB_DK_DEVICE_INFO select(unsigned readiness_ms=0) {
        sl3::DevicePresence gate(GetTickCount64(),readiness_ms);
        USB_DK_DEVICE_INFO selected{};
        for(;;) {
            unsigned matches=0;
            {
                PUSB_DK_DEVICE_INFO items=nullptr;ULONG count=0;
                mark("enumerate.enter");const auto listed=list(&items,&count);mark("enumerate.return");
                if(!listed)failed("Enumerate UsbDk devices");
                struct List {Api& api;PUSB_DK_DEVICE_INFO data;~List(){if(data)api.release_list(data);}} lease{*this,items};
                if(count>4096 || (count && !items))throw std::runtime_error("Invalid device list");
                for(ULONG i=0;i<count;++i)if(items[i].DeviceDescriptor.idVendor==0x1cc5 && items[i].DeviceDescriptor.idProduct==1){selected=items[i];++matches;}
            } // Release every enumeration before waiting; no redirection yet.
            const auto state=gate.observe(matches,GetTickCount64());
            if(state==sl3::DevicePresence::State::ready)break;
            if(state!=sl3::DevicePresence::State::waiting)
                throw std::runtime_error("Exactly one SL3 must be ready within the enumeration deadline; no device redirected");
            Sleep(gate.sleep_ms());
        }
        constexpr std::array<UCHAR,18> device_fixture{0x12,0x01,0x00,0x02,0xff,0xff,0xff,0x40,0xc5,0x1c,0x01,0x00,0x00,0x00,0x01,0x02,0x03,0x01};
        if(selected.Speed!=HighSpeed || std::memcmp(&selected.DeviceDescriptor,device_fixture.data(),device_fixture.size()))throw std::runtime_error("SL3 device descriptor/speed differs from recorded fixture");
        USB_DK_CONFIG_DESCRIPTOR_REQUEST request{};request.ID=selected.ID;request.Index=0;
        PUSB_CONFIGURATION_DESCRIPTOR descriptor=nullptr;ULONG length=0;
        mark("configuration.enter");const auto configured=configuration(&request,&descriptor,&length);mark("configuration.return");
        if(!configured)failed("Read UsbDk configuration descriptor");
        struct Config {Api& api;PUSB_CONFIGURATION_DESCRIPTOR data;~Config(){if(data)api.release_configuration(data);}} config{*this,descriptor};
        if(!descriptor || length!=sl3::configuration_fixture.size() || std::memcmp(descriptor,sl3::configuration_fixture.data(),length))throw std::runtime_error("SL3 configuration differs from verified fixture; no device redirected");
        return selected;
    }
};
struct Device {
    sl3::worker::ControlBaselineOwner control_baseline;
    sl3::worker::RedirectOwner redirect_owner;
    Api& api;HANDLE redirect=INVALID_HANDLE_VALUE,system=INVALID_HANDLE_VALUE;
    std::vector<unsigned> attempted;
    explicit Device(Api& source):api(source){}
    ~Device(){if(redirect!=INVALID_HANDLE_VALUE && !close())fail_stop();}
    void open(USB_DK_DEVICE_INFO& selected) {
        api.mark("redirect_owner_acquire.enter");
        if(!redirect_owner.acquire()){SetLastError(redirect_owner.error());failed("Acquire exclusive SL3 redirect owner");}
        api.mark("redirect_owner_acquire.return");
        api.mark("redirect_start.enter");redirect=api.start(&selected.ID);api.mark("redirect_start.return");
        if(redirect==INVALID_HANDLE_VALUE || !redirect){redirect=INVALID_HANDLE_VALUE;failed("Redirect exact SL3");}
        api.mark("system_handle.enter");system=api.system_handle(redirect);api.mark("system_handle.return");
        if(system==INVALID_HANDLE_VALUE || !system)failed("Get redirector system handle");
    }
    void activate() {
        control_baseline.invalidate();
        // A fresh redirect selects the first configuration and default alts.
        // The API has no active-alt getter; report this limitation explicitly.
        for(unsigned i:{1u,2u}){attempted.push_back(i);if(!api.set_alt(redirect,i,1))failed("Select UsbDk audio alternate");}
    }
    bool deactivate() noexcept {
        bool ok=true;
        for(auto i=attempted.rbegin();i!=attempted.rend();++i)if(!api.set_alt(redirect,*i,0))ok=false;
        attempted.clear();
        return ok;
    }
    bool close() noexcept {
        control_baseline.invalidate();
        const auto ok=deactivate();
        if(redirect!=INVALID_HANDLE_VALUE){api.mark("redirect_close.enter");const auto stopped=api.stop(redirect);api.mark("redirect_close.return");if(!stopped)return false;redirect=INVALID_HANDLE_VALUE;system=INVALID_HANDLE_VALUE;}
        return ok && redirect_owner.close();
    }
};
struct Transfer {
    Device& device;
    std::vector<UCHAR> buffer;
    std::vector<ULONG64> lengths;
    std::vector<USB_DK_ISO_TRANSFER_RESULT> results;
    USB_DK_TRANSFER_REQUEST request{};
    OVERLAPPED overlapped{};
    bool pending=false,terminal=false,accepted=false;
    DWORD completion_error=0;
    std::string submitted_utc,completed_utc;
    explicit Transfer(Device& owner):device(owner){}
    ~Transfer(){if(pending)fail_stop();if(overlapped.hEvent)CloseHandle(overlapped.hEvent);}
    void prepare(unsigned endpoint,std::size_t bytes,bool iso) {
        buffer.resize(bytes);overlapped.hEvent=CreateEventW(nullptr,TRUE,FALSE,nullptr);
        if(!overlapped.hEvent)failed("Create UsbDk completion event");
        request.EndpointAddress=endpoint;request.Buffer=buffer.data();request.BufferLength=buffer.size();
        request.TransferType=iso?IsochronousTransferType:InterruptTransferType;
        if(iso){lengths.assign(intervals,126);results.resize(intervals);request.IsochronousPacketsArraySize=lengths.size();request.IsochronousPacketsArray=lengths.data();request.Result.IsochronousResultsArray=results.data();}
    }
    void submit(bool output=false) {
        submitted_utc=utc_now();
        const auto status=output?device.api.write(device.redirect,&request,&overlapped):device.api.read(device.redirect,&request,&overlapped);
        if(status==TransferFailure){
            completion_error=GetLastError();if(!completion_error)completion_error=ERROR_GEN_FAILURE;
            pending=false;terminal=true;completed_utc=utc_now();
            SetLastError(completion_error);failed("Submit UsbDk transfer");
        }
        if(status!=TransferSuccess && status!=TransferSuccessAsync)fail_stop();
        accepted=true;pending=status==TransferSuccessAsync;terminal=!pending;
        if(terminal)completed_utc=utc_now();
    }
    sl3::Completion wait(DWORD timeout) {
        if(pending){
            const auto status=WaitForSingleObject(overlapped.hEvent,timeout);
            if(status==WAIT_TIMEOUT)return sl3::Completion::pending;
            if(status!=WAIT_OBJECT_0)failed("Wait UsbDk completion");
            DWORD transferred=0;
            if(!GetOverlappedResult(device.system,&overlapped,&transferred,FALSE)){
                completion_error=GetLastError();
                if(completion_error==ERROR_IO_INCOMPLETE)return sl3::Completion::pending;
            }
            pending=false;terminal=true;completed_utc=utc_now();
        }
        if(!terminal)throw std::runtime_error("UsbDk transfer was never submitted");
        return completion_error || request.Result.GenResult.UsbdStatus?sl3::Completion::failure:sl3::Completion::success;
    }
    void cancel(){if(pending && !CancelIoEx(device.system,&overlapped) && GetLastError()!=ERROR_NOT_FOUND)failed("Cancel UsbDk transfer");}
    void bounded(bool output,DWORD timeout) {
        submit(output);
        try {
            const auto status=wait(timeout);
            if(status==sl3::Completion::success)return;
            if(status==sl3::Completion::failure)throw std::runtime_error("UsbDk interrupt transfer failed");
        } catch (...) {
            try{cancel();}catch(...){}
            try{if(wait(2000)==sl3::Completion::pending)fail_stop();}catch(...){if(pending)fail_stop();}
            throw;
        }
        try{cancel();}catch(...){}
        try{if(wait(2000)==sl3::Completion::pending)fail_stop();}catch(...){if(pending)fail_stop();}
        throw std::runtime_error("UsbDk interrupt deadline elapsed");
    }
};
struct NativeRateIo final:sl3::control::RateIo {
    Device& device;std::ofstream& report;const std::filesystem::path& output;unsigned target;
    sl3::diagnostic::RateIoLog log;sl3::diagnostic::RateNativeFacts facts{};
    std::array<sl3::control::RateIoObservation,15> observations{};unsigned observed_count=0,saved_decisions=0;
    bool transaction_seen=false,transaction_done=false,transaction_saved=false;
    std::uint64_t transaction_start=0,transaction_finish=0;unsigned transaction_budget=0;
    sl3::control::DiagnosticError transaction_error=sl3::control::DiagnosticError::none;
    bool possible=false,retired=true;unsigned transfers=0,setter_attempts=0;std::array<char,512> error{};
    NativeRateIo(Device& d,std::ofstream& r,const std::filesystem::path& p,unsigned hz):device(d),report(r),output(p),target(hz),log(p/L"rate-io.jsonl",hz,utc_now()){}
    std::uint64_t now_ms() noexcept override{return GetTickCount64();}
    bool cancelled() noexcept override{return false;} // Parent watchdog contains the entire process.
    void save(const char* phase,const sl3::control::RateDiagnosticResult* result=nullptr,bool closed=false){
        if(result && result->setter_attempts!=setter_attempts)throw std::runtime_error("Rate setter attempt accounting differs");
        if(result){
            if(observed_count!=transfers)throw std::runtime_error("Rate observation count differs");
            if(transaction_seen && !transaction_saved){
                if(!transaction_done || transaction_error!=result->error)throw std::runtime_error("Rate transaction recording differs");
                log.transaction(transaction_start,transaction_budget,transaction_finish,transaction_error);transaction_saved=true;
            }
            for(;saved_decisions<observed_count;++saved_decisions)log.decided(observations[saved_decisions]);
        }
        report.close();report.open(output/L"rate.json",std::ios::trunc);
        report<<"{\"schema\":\"sl3.rate-diagnostic.v2\",\"phase\":"<<quote(phase)<<",\"utc\":"<<quote(utc_now())
              <<",\"target_rate_hz\":"<<target<<",\"device_may_have_changed\":"<<(possible?"true":"false")
              <<",\"last_io_retired\":"<<(retired?"true":"false")<<",\"control_transfer_attempts\":"<<transfers
              <<",\"redirect_closed\":"<<(closed?"true":"false")<<",\"audio_submissions\":0,\"alternate_changes\":0,\"automatic_rollback\":false"
              <<",\"rate_io_schema\":\"sl3.rate-io.v2\",\"rate_io_file\":\"rate-io.jsonl\""
              <<",\"setter_attempts\":"<<setter_attempts;
        if(result)report<<",\"diagnostic_error\":"<<unsigned(result->error)<<",\"transaction_error\":"<<unsigned(result->transaction_error)
                        <<",\"exchange_error\":"<<unsigned(result->exchange_error)<<",\"initial_rate_hz\":"<<result->initial_rate_hz
                        <<",\"verified_rate_hz\":"<<result->verified_rate_hz<<",\"write_attempts\":"<<result->write_attempts
                        <<",\"read_attempts\":"<<result->read_attempts<<",\"readback_rate_hz\":"<<result->readback_rate_hz
                        <<",\"acknowledgement_received\":"<<(result->acknowledgement_received?"true":"false");
        report<<",\"error\":"<<quote(error.data())<<"}\n"<<std::flush;
        if(!report)throw std::runtime_error("Cannot persist rate-test state");
    }
    void observed(const sl3::control::RateIoObservation& observation) noexcept override{
        if(observed_count>=observations.size() || observation.sequence!=observed_count)fail_stop();
        observations[observed_count++]=observation; // Fixed storage only; no I/O on the decision boundary.
    }
    void transaction_started(std::uint64_t tick,unsigned budget) noexcept override{
        if(transaction_seen)fail_stop();transaction_seen=true;transaction_start=tick;transaction_budget=budget;
    }
    void transaction_finished(std::uint64_t tick,sl3::control::DiagnosticError error_code) noexcept override{
        if(!transaction_seen || transaction_done)fail_stop();transaction_done=true;transaction_finish=tick;transaction_error=error_code;
    }
    bool transfer(bool output_frame,sl3::control::Frame& frame,unsigned timeout,std::size_t& bytes) noexcept override{
        Transfer request(device);facts={};facts.invoked=true;const auto started=GetTickCount64();
        const auto capture=[&]() noexcept{
            bytes=std::size_t(request.request.Result.GenResult.BytesTransferred);
            facts.api_attempted=!request.submitted_utc.empty();facts.api_accepted=request.accepted;facts.terminal=request.terminal;
            facts.completion_error=request.completion_error;facts.usbd_status=request.request.Result.GenResult.UsbdStatus;
            strncpy_s(facts.submitted_utc.data(),facts.submitted_utc.size(),request.submitted_utc.c_str(),_TRUNCATE);
            strncpy_s(facts.completed_utc.data(),facts.completed_utc.size(),request.completed_utc.c_str(),_TRUNCATE);
            if(!output_frame){frame.fill(0);std::copy_n(request.buffer.begin(),std::min({bytes,frame.size(),request.buffer.size()}),frame.begin());}
        };
        const auto finish=[&](bool success) noexcept{
            log.end({transfers-1,output_frame,timeout,started,GetTickCount64(),success,bytes,frame,
                sl3::control::RateIoDecision::transfer_failure},facts);
        };
        try{
            if(output_frame && frame[0]==0x31){possible=true;++setter_attempts;}
            ++transfers;retired=false;save(output_frame?"before control write":"before control read");
            log.begin(output_frame,timeout,started,frame);
            request.prepare(output_frame?0x01:0x81,64,false);
            if(output_frame)std::copy(frame.begin(),frame.end(),request.buffer.begin());
            const auto elapsed=GetTickCount64()-started;
            if(elapsed>=timeout){retired=true;capture();strcpy_s(error.data(),error.size(),"Rate transfer budget expired before submission");finish(false);return false;}
            facts.adapter_timeout_ms=timeout-DWORD(elapsed);
            request.bounded(output_frame,facts.adapter_timeout_ms); // Retains storage through cancellation/drain or fail-stops.
            retired=true;capture();
            save("control transfer retired");finish(true);return true;
        }catch(const std::exception& e){
            // Transfer's destructor cannot return with pending I/O.
            retired=true;capture();strncpy_s(error.data(),error.size(),e.what(),_TRUNCATE);finish(false);return false;
        }catch(...){retired=true;capture();strcpy_s(error.data(),error.size(),"Unexpected rate transfer failure");finish(false);return false;}
    }
};
int run_rate_diagnostic(Api& api,USB_DK_DEVICE_INFO& selected,const std::filesystem::path& output,std::ofstream& report,unsigned target){
    Device device(api);NativeRateIo io(device,report,output,target);sl3::control::RateDiagnosticResult result;
    bool opened=false;
    try{
        io.save("before idle redirect");device.open(selected);opened=true;
        // Fresh redirect only: no audio alternate activation or ISO request.
        result=sl3::control::diagnose_rate(target,io);
    }catch(const std::exception& e){strncpy_s(io.error.data(),io.error.size(),e.what(),_TRUNCATE);result.error=sl3::control::DiagnosticError::transfer;}
    const auto closed=device.close();io.possible=io.possible || result.device_may_have_changed;
    io.save(opened?"finished":"failed before usable redirect",&result,closed);
    if(!closed)fail_stop();
    return opened && result.error==sl3::control::DiagnosticError::none?0:1;
}
unsigned read_rate(Device& device) {
    sl3::control::Exchange exchange(sl3::control::rate_query());
    Transfer query(device);query.prepare(0x01,64,false);
    const auto& frame=exchange.query().frame();std::copy(frame.begin(),frame.end(),query.buffer.begin());
    query.bounded(true,100);
    if(query.request.Result.GenResult.BytesTransferred!=64)throw std::runtime_error("Incomplete rate query write");
    for(std::size_t i=0;i<sl3::control::maximum_received_frames;++i){
        Transfer reply(device);reply.prepare(0x81,64,false);reply.bounded(false,300);
        if(reply.request.Result.GenResult.BytesTransferred!=64)throw std::runtime_error("Incomplete status frame");
        const auto event=exchange.accept(reply.buffer.data(),reply.buffer.size());
        if(event.outcome==sl3::control::Outcome::reply)return exchange.rate_hz();
        if(event.outcome==sl3::control::Outcome::failed)throw std::runtime_error(sl3::control::error_message(event.error));
    }
    throw std::runtime_error("No rate reply within four status frames");
}
std::string timer_hex(const sl3::control::Challenge& bytes){
    constexpr char alphabet[]="0123456789abcdef";std::string text;
    for(const auto byte:bytes){text+=alphabet[byte>>4];text+=alphabet[byte&15];}return text;
}
class CadenceAudioPeer final:public sl3::ContinuousPeer {
    std::array<sl3::AudioBlock,4> pending_{};
    unsigned read_=0,write_=0,count_=0;
    const std::atomic<bool>& tone_enabled_;
    unsigned tone_frames_=0;
public:
    explicit CadenceAudioPeer(const std::atomic<bool>& tone_enabled):tone_enabled_(tone_enabled){}
    unsigned tone_frames() const noexcept{return tone_frames_;}
    sl3::StreamExchange publish_input(const sl3::AudioBlock& input) noexcept override {
        if(count_==pending_.size())return sl3::StreamExchange::full;
        auto& output=pending_[write_];
        output.first_frame=input.first_frame;output.host_observation_ns=input.host_observation_ns;
        output.reported_rate_hz=input.reported_rate_hz;output.packet_count=input.packet_count;
        output.frames_per_packet=input.frames_per_packet;
        output.pcm.fill(0);
        if(tone_enabled_){
            const auto rate=input.reported_rate_hz;
            const unsigned length=rate*65/100,fade=rate/100;
            unsigned frames=0;
            for(unsigned packet=0;packet<input.packet_count;++packet)frames+=input.frames_per_packet[packet];
            for(unsigned frame=0;frame<frames && tone_frames_<length;++frame,++tone_frames_){
                const auto ramp=std::min({tone_frames_,length-1-tone_frames_,fade})/double(fade);
                const auto sample=static_cast<std::uint32_t>(static_cast<std::int32_t>(265271.0*ramp*
                    std::sin(tone_frames_*(6.283185307179586*997.0/rate))));
                for(unsigned channel=0;channel<2;++channel)
                    for(unsigned byte=0;byte<3;++byte)
                        output.pcm[frame*18+channel*3+byte]=std::uint8_t(sample>>(8*byte));
            }
        }
        write_=(write_+1)%4;++count_;
        return sl3::StreamExchange::ok;
    }
    sl3::StreamExchange receive_output(sl3::AudioBlock& output) noexcept override {
        if(!count_)return sl3::StreamExchange::empty;
        output=pending_[read_];read_=(read_+1)%4;--count_;
        return sl3::StreamExchange::ok;
    }
};

int run_timer_diagnostic(Api& api,USB_DK_DEVICE_INFO& selected,const std::filesystem::path& output,
                         std::ofstream& report,sl3::control::Challenge challenge,bool cadence,bool silent_stream,bool tone){
    Device device(api);sl3::control::DriverTimerResult result;
    unsigned writes=0,reads=0;DWORD native_error=0;
    bool redirect_attempted=false,opened=false,closed=false,io_retired=true;std::string error;
    const auto seed=challenge;
    std::ostringstream exchanges;
    unsigned completed=0;
    sl3::StreamStats stream_stats{};
    sl3::StreamFault stream_fault=sl3::StreamFault::none;
    sl3::StreamStats retired_stats{};
    sl3::StreamFault retired_fault=sl3::StreamFault::none;
    unsigned rate=0;
    unsigned alternate_attempts=0;
    const bool with_stream=silent_stream || tone;
    std::atomic<bool> streaming{false},stream_finished{false},stop_audio{false},tone_enabled{false};
    std::atomic<std::uint64_t> observed_output_completions{0};
    std::thread audio;
    unsigned tone_frames=0,retired_tone_frames=0;
    std::optional<sl3::control::AudioControlsSnapshot> controls_before,controls_after;
    auto save=[&](const char* phase){
        report.close();report.open(output/L"timer.json",std::ios::trunc);
        report<<"{\"schema\":\"sl3.driver-timer-diagnostic.v1\",\"phase\":"<<quote(phase)<<",\"utc\":"<<quote(utc_now())
              <<",\"challenge_hex\":"<<quote(timer_hex(seed))<<",\"redirect_attempted\":"<<(redirect_attempted?"true":"false")
              <<",\"redirect_opened\":"<<(opened?"true":"false")<<",\"last_io_retired\":"<<(io_retired?"true":"false")
              <<",\"redirect_closed\":"<<(closed?"true":"false")<<",\"write_attempts\":"<<writes<<",\"read_attempts\":"<<reads
              <<",\"diagnostic_error\":"<<unsigned(result.error)<<",\"exchange_error\":"<<unsigned(result.exchange_error)
              <<",\"native_error\":"<<native_error<<",\"response_parsed\":"<<(result.response?"true":"false")
              <<",\"response_verified\":false,\"serato_admission_verified\":false,\"reopen_ready_verified\":false,\"rate_changes\":0";
        if(!with_stream)report<<",\"audio_submissions\":0,\"alternate_changes\":0";
        if(result.response)report<<",\"response_hex\":"<<quote(timer_hex(*result.response));
        if(cadence)report<<",\"cadence_ms\":100,\"completed_exchanges\":"<<completed<<",\"exchanges\":["<<exchanges.str()<<']';
        if(with_stream)report<<",\"silent_stream\":"<<(silent_stream?"true":"false")<<",\"observed_rate_hz\":"<<rate
            <<",\"audio_submissions_known\":"<<(audio.joinable()?"false":"true")
            <<",\"audio_submissions\":"<<stream_stats.output_submissions<<",\"alternate_activation_attempts\":"<<alternate_attempts
            <<",\"stream_fault\":"<<unsigned(stream_fault)<<",\"input_frames\":"<<stream_stats.input_frames
            <<",\"output_completions\":"<<stream_stats.output_completions
            <<",\"output_payload\":"<<quote(tone?"997 Hz on stream channels 1 and 2":"zero PCM only");
        if(tone){
            report<<",\"tone_frames_staged\":"<<tone_frames<<",\"routing_setters\":0";
            auto write_table=[&](const char* name,const std::optional<sl3::control::AudioControlsSnapshot>& controls){
                report<<','<<quote(name)<<':';
                if(!controls){report<<"null";return;}
                report<<'[';
                for(unsigned i=0;i<controls->raw.size();++i){if(i)report<<',';report<<unsigned(controls->raw[i]);}
                report<<']';
            };
            write_table("controls_before",controls_before);
            write_table("controls_after",controls_after);
        }
        report<<",\"error\":"<<quote(error)<<"}\n"<<std::flush;
        if(!report)throw std::runtime_error("Cannot persist timer diagnostic");
    };
    try{
        redirect_attempted=true;save("before idle redirect");device.open(selected);opened=true;
        if(with_stream){
            rate=read_rate(device);
            if(tone){
                sl3::worker::NativeControlsIo<Device,Transfer> io(device);
                controls_before=sl3::control::inspect_audio_controls(io).controls;
                if(!controls_before || controls_before->raw[8]!=1)
                    throw std::runtime_error("Original control byte 8 does not match the playback hypothesis");
            }
            device.activate();
            alternate_attempts=static_cast<unsigned>(device.attempted.size());
            audio=std::thread([&]{
                sl3::worker::UsbDkStreamBackend backend({api.read,api.write},device.redirect,device.system);
                CadenceAudioPeer peer(tone_enabled);
                sl3::ContinuousStream stream(backend,peer);
                if(stream.start({rate,8})){
                    while(!stop_audio && stream.step()==sl3::StreamState::running){
                        const auto completions=stream.stats().output_completions;
                        observed_output_completions=completions;
                        if(completions)streaming=true;
                        std::this_thread::yield();
                    }
                }
                stream.stop();
                while(stream.step()==sl3::StreamState::draining)std::this_thread::yield();
                if(stream.state()==sl3::StreamState::retained)fail_stop();
                retired_tone_frames=peer.tone_frames();
                retired_stats=stream.stats();retired_fault=stream.fault();stream_finished=true;
            });
            const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(1);
            while(!streaming && !stream_finished && std::chrono::steady_clock::now()<deadline)Sleep(1);
            if(!streaming || stream_finished)throw std::runtime_error("Silent stream did not start");
        }
        const auto origin=std::chrono::steady_clock::now();
        for(unsigned index=0;index<(cadence?10u:1u);++index){
            const auto due=origin+std::chrono::milliseconds(index*100);
            if(index)std::this_thread::sleep_until(due);
            if(stream_finished)throw std::runtime_error("Silent stream ended during cadence");
            if(cadence){io_retired=false;save("before cadence exchange");}
            const auto start=std::chrono::steady_clock::now();
            if(cadence && start-due>std::chrono::milliseconds(20)){
                io_retired=true;throw std::runtime_error("Timer cadence missed its start window");
            }
            challenge.back()=std::uint8_t(seed.back()+index);
            using Io=sl3::worker::NativeDriverTimerIo<Device,Transfer>;
            Io* active=nullptr;
            Io io(device,challenge,[&](const char* phase){
                io_retired=std::string_view(phase)=="timer transfer retired";
                if(!cadence){
                    if(active){writes=active->writes;reads=active->reads;}
                    save(phase);
                }
            });active=&io;
            const auto outputs_before=observed_output_completions.load();
            result=sl3::control::inspect_driver_timer(challenge,io,cadence?80u:sl3::control::driver_timer_budget_ms);
            const auto outputs_after=observed_output_completions.load();
            io_retired=true;native_error=io.error;
            if(!cadence){writes=io.writes;reads=io.reads;break;}
            writes+=io.writes;reads+=io.reads;
            const auto end=std::chrono::steady_clock::now();
            if(index)exchanges<<',';
            exchanges<<"{\"start_us\":"<<std::chrono::duration_cast<std::chrono::microseconds>(start-origin).count()
                     <<",\"end_us\":"<<std::chrono::duration_cast<std::chrono::microseconds>(end-origin).count()
                     <<",\"writes\":"<<io.writes<<",\"reads\":"<<io.reads;
            if(with_stream)exchanges<<",\"output_completions_before\":"<<outputs_before
                                      <<",\"output_completions_after\":"<<outputs_after;
            exchanges<<'}';
            if(result.error!=sl3::control::DriverTimerError::none || !result.response)break;
            if(end>=due+std::chrono::milliseconds(100))throw std::runtime_error("Timer cadence missed its completion window");
            ++completed;
            if(tone)tone_enabled=true;
        }
        if(!with_stream)save("before redirect release");
    }catch(const std::exception& exception){error=exception.what();result.error=sl3::control::DriverTimerError::transfer;}
    if(audio.joinable()){
        stop_audio=true;audio.join();
        if(retired_fault!=sl3::StreamFault::none && error.empty()){
            error="Silent stream faulted";result.error=sl3::control::DriverTimerError::transfer;
        }
    }
    stream_stats=retired_stats;stream_fault=retired_fault;
    tone_frames=retired_tone_frames;
    alternate_attempts=static_cast<unsigned>(device.attempted.size());
    if(tone && controls_before){
        if(!device.deactivate())fail_stop();
        sl3::worker::NativeControlsIo<Device,Transfer> io(device);
        controls_after=sl3::control::inspect_audio_controls(io).controls;
        if(!controls_after || controls_before->raw!=controls_after->raw || tone_frames!=rate*65/100){
            if(error.empty())error="Tone prefix incomplete or original control table could not be confirmed";
            result.error=sl3::control::DriverTimerError::transfer;
        }
    }
    if(with_stream)save("before redirect release");
    closed=device.close();save(opened?"finished":"failed before usable redirect");
    if(!closed)fail_stop();
    return opened && result.error==sl3::control::DriverTimerError::none && result.response && (!cadence || completed==10)?0:1;
}
using NativeControlDiagnostic=sl3::worker::ControlSelectionDiagnostic<Device,Transfer>;
struct Capture final:sl3::CaptureBackend {
    Device& device;
    std::array<std::unique_ptr<Transfer>,requests> slots;
    unsigned submitted=0,completed=0;
    std::array<bool,requests> counted{};
    explicit Capture(Device& source):device(source){}
    void prepare(std::size_t i) override {
        auto request=std::make_unique<Transfer>(device);request->prepare(0x82,bytes_per_request,true);slots.at(i)=std::move(request);
    }
    void submit(std::size_t i,bool) override {slots.at(i)->submit();++submitted;}
    sl3::Completion wait(std::size_t i,std::uint32_t timeout) override {
        const auto result=slots.at(i)->wait(timeout);
        if(result!=sl3::Completion::pending && !counted.at(i)){++completed;counted.at(i)=true;}
        return result;
    }
    void cancel(std::size_t i) override {slots.at(i)->cancel();}
    void release(std::size_t i) override {
        auto& t=*slots.at(i);if(t.pending)throw std::runtime_error("Attempt to release pending UsbDk memory");
        if(t.overlapped.hEvent){CloseHandle(t.overlapped.hEvent);t.overlapped.hEvent=nullptr;}
    }
    std::uint64_t now_ms() const override {return GetTickCount64();}
};
struct Duplex final:sl3::DuplexBackend {
    Device& device;
    std::array<std::unique_ptr<Transfer>,requests*2> slots;
    std::array<bool,requests*2> counted{},staged{};
    unsigned submitted_input=0,submitted_output=0,completed_input=0,completed_output=0;
    unsigned output_attempts=0;
    std::uint64_t output_bytes_requested=0,output_bytes_accepted=0;
    explicit Duplex(Device& source):device(source){}
    void prepare(std::size_t slot) override {
        auto transfer=std::make_unique<Transfer>(device);
        transfer->prepare(slot%2?0x06:0x82,bytes_per_request,true);slots.at(slot)=std::move(transfer);
    }
    void stage_output(std::size_t input,std::size_t output) override {
        const auto& in=*slots.at(input);auto& out=*slots.at(output);
        if(input%2 || output!=input+1 || !in.terminal || in.pending || in.completion_error || in.request.Result.GenResult.UsbdStatus)
            throw std::runtime_error("IN request is not successful and terminal before OUT staging");
        if(in.results.size()!=intervals || out.lengths.size()!=intervals)throw std::runtime_error("Unexpected isochronous packet count");
        std::array<sl3::PacketResult64,intervals> input_results{};
        for(std::size_t i=0;i<intervals;++i)input_results[i]={in.results[i].ActualLength,in.results[i].TransferResult};
        const auto layout=sl3::stage_silent_output(input_results.data(),input_results.size(),out.lengths.data(),out.lengths.size(),out.buffer.data(),out.buffer.size());
        if(layout.status!=sl3::SilentStageStatus::ok)throw std::runtime_error("Invalid input packet or OUT capacity; corresponding OUT was not submitted");
        out.request.BufferLength=layout.bytes;staged[output]=true;
    }
    void submit(std::size_t slot,bool) override {
        if(slot%2 && !staged.at(slot))throw std::runtime_error("OUT layout was not validated");
        if(slot%2){++output_attempts;output_bytes_requested+=slots[slot]->request.BufferLength;}
        slots.at(slot)->submit(slot%2!=0);
        if(slot%2){++submitted_output;output_bytes_accepted+=slots[slot]->request.BufferLength;}else ++submitted_input;
    }
    sl3::Completion wait(std::size_t slot,std::uint32_t timeout) override {
        auto result=slots.at(slot)->wait(timeout);
        if(result!=sl3::Completion::pending && !counted.at(slot)){
            if(slot%2)++completed_output;else ++completed_input;counted[slot]=true;
        }
        // OUT packet Length is not an actual-byte-count contract. Check its
        // status, preserving the returned length only as uninterpreted evidence.
        if(result==sl3::Completion::success && slot%2)
            for(const auto& packet:slots[slot]->results)if(packet.TransferResult)return sl3::Completion::failure;
        return result;
    }
    void cancel(std::size_t slot) override {slots.at(slot)->cancel();}
    void release(std::size_t slot) override {
        auto& transfer=*slots.at(slot);
        if(transfer.pending)throw std::runtime_error("Attempt to free pending duplex memory");
        if(transfer.overlapped.hEvent){CloseHandle(transfer.overlapped.hEvent);transfer.overlapped.hEvent=nullptr;}
    }
    std::uint64_t now_ms() const override{return GetTickCount64();}
};

int run_duplex_silence(Api& api,USB_DK_DEVICE_INFO& selected,const std::filesystem::path& output,std::ofstream& report){
    Device device(api);unsigned rate=0,in_submitted=0,out_submitted=0,in_completed=0,out_completed=0;
    unsigned out_attempts=0;std::uint64_t bytes_requested=0,bytes_accepted=0;bool success=false,transfers=false,closed=false;std::string error;
    const auto started=utc_now();std::ostringstream metadata;metadata<<'[';bool first=true;
    auto progress=[&](const char* phase,bool output_count_known){
        report.close();report.open(output/L"duplex.json",std::ios::trunc);
        report<<"{\"mode\":\"duplex-silence\",\"phase\":"<<quote(phase)<<",\"audio_output_submissions_known\":"<<(output_count_known?"true":"false");
        if(output_count_known)report<<",\"audio_output_submissions\":0";
        report<<"}\n"<<std::flush;if(!report)throw std::runtime_error("Cannot save duplex progress");
    };
    try{
        progress("verified exact SL3; before redirect",true);device.open(selected);
        progress("redirected; before clock getter",true);rate=read_rate(device);
        progress("clock read; before audio alternates",true);device.activate();
        progress("before bounded IN/OUT pipeline; all OUT payloads are zero",false);
        Duplex backend(device);const auto result=sl3::duplex_transaction(backend);
        in_submitted=backend.submitted_input;out_submitted=backend.submitted_output;
        in_completed=backend.completed_input;out_completed=backend.completed_output;bytes_requested=backend.output_bytes_requested;
        out_attempts=backend.output_attempts;bytes_accepted=backend.output_bytes_accepted;
        transfers=result.transfers_succeeded;
        if(!result.cleanup_complete){
            report.close();report.open(output/L"duplex.json",std::ios::trunc);
            report<<"{\"cleanup_complete\":false,\"process_teardown_required\":true,\"audio_output_submissions_known\":true,\"audio_output_submissions\":"<<out_attempts<<",\"accepted_output_requests\":"<<out_submitted<<",\"retained_slots\":[";
            bool comma=false;for(auto slot:result.retained_slots){if(comma)report<<',';comma=true;report<<slot;}
            report<<"]}\n"<<std::flush;fail_stop();
        }
        for(std::size_t i=0;i<backend.slots.size();++i)if(backend.slots[i]){
            const auto& slot=*backend.slots[i];const bool is_output=i%2!=0;
            std::ofstream raw(output/(L"registered-"+std::to_wstring(i)+L".bin"),std::ios::binary);
            raw.write(reinterpret_cast<const char*>(slot.buffer.data()),std::streamsize(slot.buffer.size()));if(!raw)throw std::runtime_error("Cannot save duplex buffer");
            std::uint64_t offset=0;
            for(std::size_t packet=0;packet<slot.results.size();++packet){const auto& value=slot.results[packet];
                if(!first)metadata<<',';first=false;
                metadata<<"{\"slot\":"<<i<<",\"pair\":"<<i/2<<",\"direction\":"<<quote(is_output?"OUT":"IN")<<",\"packet\":"<<packet<<",\"offset\":"<<offset
                 <<",\"requested_length\":"<<slot.lengths[packet]<<",\"returned_length\":"<<value.ActualLength<<",\"status\":"<<value.TransferResult
                 <<",\"output_layout_staged\":"<<(backend.staged[is_output?i:i+1]?"true":"false")<<",\"request_attempted\":"<<(!slot.submitted_utc.empty()?"true":"false")
                 <<",\"request_submitted\":"<<(slot.accepted?"true":"false")
                 <<",\"request_terminal\":"<<(slot.terminal?"true":"false")<<",\"completion_win32_error\":"<<slot.completion_error
                 <<",\"request_usbd_status\":"<<slot.request.Result.GenResult.UsbdStatus<<",\"reported_request_bytes\":"<<slot.request.Result.GenResult.BytesTransferred
                 <<",\"submitted_utc\":"<<quote(slot.submitted_utc)<<",\"completed_utc\":"<<quote(slot.completed_utc)<<'}';
                offset+=slot.lengths[packet];
            }
        }
        if(!result.transfers_succeeded)throw std::runtime_error(result.error);
        success=true;
    }catch(const std::exception& exception){error=exception.what();}
    closed=device.close();metadata<<']';
    report.close();report.open(output/L"duplex.json",std::ios::trunc);
    report<<"{\"mode\":\"duplex-silence\",\"transport\":\"UsbDk 1.0.22\",\"started_utc\":"<<quote(started)<<",\"completed_utc\":"<<quote(utc_now())
     <<",\"duplex_succeeded\":"<<(success?"true":"false")<<",\"transfers_succeeded\":"<<(transfers?"true":"false")<<",\"buffer_cleanup_complete\":true"
     <<",\"redirect_and_alternates_cleanup_succeeded\":"<<(closed?"true":"false")<<",\"reported_rate_hz\":"<<rate
     <<",\"planned_input_intervals\":256,\"planned_output_intervals\":256,\"planned_ms_per_direction\":32"
     <<",\"submitted_input_requests\":"<<in_submitted<<",\"submitted_output_requests\":"<<out_submitted
     <<",\"completed_input_requests\":"<<in_completed<<",\"completed_output_requests\":"<<out_completed
     <<",\"audio_output_submissions_known\":true,\"audio_output_submissions\":"<<out_attempts<<",\"output_request_attempts\":"<<out_attempts
     <<",\"output_bytes_requested\":"<<bytes_requested<<",\"output_bytes_accepted_by_api\":"<<bytes_accepted
     <<",\"output_payload\":\"zero PCM only\",\"out_returned_lengths_interpreted\":false,\"continuity_verified\":false,\"alternate_readback_available\":false"
     <<",\"sample_clock_validated\":false,\"analog_output_verified\":false"
     <<",\"error\":"<<quote(error)<<",\"packets\":"<<metadata.str()<<"}\n"<<std::flush;
    if(!closed)fail_stop();return success && report?0:1;
}
std::vector<std::uint8_t> worker_capture(const std::filesystem::path& helper){
    Api api;api.load(helper);auto selected=api.select();Device device(api);device.open(selected);
    sl3::protocol::CaptureBatch batch;batch.reported_rate_hz=read_rate(device);device.activate();
    Capture backend(device);const auto result=sl3::capture_transaction(backend);
    if(!result.cleanup_complete)fail_stop();
    if(!result.transfers_succeeded)throw std::runtime_error(result.error);
    batch.frames_per_packet.reserve(256);batch.pcm.reserve(256*126);
    for(const auto& item:backend.slots){
        if(!item || item->results.size()!=64 || item->buffer.size()!=64*126)throw std::runtime_error("Unexpected completed capture storage");
        for(std::size_t index=0;index<64;++index){
            const auto& packet=item->results[index];
            if(packet.TransferResult || !packet.ActualLength || packet.ActualLength>126 || packet.ActualLength%18)
                throw std::runtime_error("Invalid completed input packet; no replacement or narrowing");
            batch.frames_per_packet.push_back(std::uint8_t(packet.ActualLength/18));
            const auto first=item->buffer.begin()+static_cast<std::ptrdiff_t>(index*126);
            batch.pcm.insert(batch.pcm.end(),first,first+static_cast<std::ptrdiff_t>(packet.ActualLength));
        }
    }
    if(!device.close())fail_stop();
    return sl3::protocol::encode_capture(batch);
}
int serve_worker(const std::wstring& channel,const std::filesystem::path& helper){
    using sl3::protocol::Command;using sl3::protocol::Status;
    auto mailbox=sl3::worker::Mailbox::open(channel);bool greeted=false;
    // This is a bounded diagnostic worker, not the continuous ASIO session.
    for(unsigned count=0;count<64;++count){
        sl3::worker::Message request;
        const auto received=mailbox->receive(5000,request);
        if(received==sl3::worker::MessageResult::closed || received==sl3::worker::MessageResult::timeout)return 0;
        if(received!=sl3::worker::MessageResult::ok)return 1;
        auto status=Status::ok;std::vector<std::uint8_t> payload;bool quit=false;
        const auto command=static_cast<Command>(request.opcode);
        try{
            if(!request.bytes.empty())status=Status::bad_request;
            else if(command==Command::quit)quit=true;
            else if(command==Command::hello){
                if(greeted)status=Status::bad_state;
                else{payload=sl3::protocol::encode_hello();greeted=true;}
            }else if(!greeted)status=Status::bad_state;
            else if(command==Command::probe){
                Watchdog watchdog;Api api;api.load(helper);api.select();payload=sl3::protocol::encode_probe();
            }else if(command==Command::capture_input){
                Watchdog watchdog;payload=worker_capture(helper);
            }else status=Status::bad_request;
        }catch(const std::exception& error){
            status=Status::operation_failed;const std::string text=error.what();
            payload.assign(text.begin(),text.begin()+static_cast<std::ptrdiff_t>(std::min<std::size_t>(text.size(),512)));
        }
        if(!mailbox->respond(static_cast<std::uint32_t>(status),payload.data(),payload.size()))return 1;
        if(quit)return 0;
    }
    // Preserve the 64th published reply through peer exit, just like quit.
    return 0;
}
class NativeStreamTarget final:public sl3::worker::SessionTarget {
    Api api_;Device device_{api_};std::unique_ptr<sl3::worker::UsbDkStreamBackend> backend_;
    bool closed_=false;DWORD error_=0;
public:
    NativeStreamTarget(const std::filesystem::path& helper,sl3::StreamConfig config,sl3::diagnostic::StartupJournal& journal){
        api_.journal=&journal;
        api_.load(helper);auto selected=api_.select(2000);device_.open(selected);
        api_.mark("clock_getter.enter");const auto reported=read_rate(device_);api_.mark("clock_getter.return");
        if(reported!=config.rate_hz)throw std::runtime_error("SL3 rate differs from requested metadata; no rate setter or audio submission");
        device_.activate();
        backend_=std::make_unique<sl3::worker::UsbDkStreamBackend>(sl3::worker::UsbDkStreamApi{api_.read,api_.write},device_.redirect,device_.system);
        if(!backend_->valid())throw std::runtime_error("Invalid native continuous backend");
    }
    ~NativeStreamTarget(){if(!closed_ && !close())fail_stop();}
    sl3::ContinuousBackend& backend() noexcept override {return *backend_;}
    bool close() noexcept override {
        if(closed_)return true;
        if(backend_){error_=backend_->last_error();backend_.reset();}
        if(!device_.close()){error_=GetLastError();return false;}
        closed_=true;return true;
    }
    DWORD native_error() const noexcept override {return backend_?backend_->last_error():error_;}
    bool wait_for_work(sl3::worker::Mailbox& mailbox,unsigned pending,DWORD timeout) noexcept override {
        if(backend_->immediate_poll())return true;
        std::array<HANDLE,10> events{};DWORD count=0;
        events[count++]=mailbox.request_event();events[count++]=mailbox.output_event();
        for(unsigned i=0;i<8;++i)if(pending&(1u<<i)){const auto event=backend_->pending_event(i);if(event)events[count++]=event;}
        const auto waited=WaitForMultipleObjects(count,events.data(),FALSE,timeout);
        return waited==WAIT_TIMEOUT || waited<WAIT_OBJECT_0+count;
    }
};
class NativeHeldTarget final:public sl3::worker::SessionTarget {
    Device& device_;bool& active_;std::unique_ptr<sl3::worker::UsbDkStreamBackend> backend_;
    bool closed_=false;DWORD error_=0;
public:
    NativeHeldTarget(Device& device,bool& active):device_(device),active_(active){
        try{
            device_.activate();
            backend_=std::make_unique<sl3::worker::UsbDkStreamBackend>(sl3::worker::UsbDkStreamApi{device_.api.read,device_.api.write},device_.redirect,device_.system);
            if(!backend_->valid())throw std::runtime_error("Invalid held-device native backend");
            active_=true;
        }catch(...){if(!device_.deactivate())fail_stop();throw;}
    }
    ~NativeHeldTarget(){if(!closed_ && !close())fail_stop();}
    sl3::ContinuousBackend& backend() noexcept override{return *backend_;}
    bool close() noexcept override{
        if(closed_)return true;
        if(backend_){error_=backend_->last_error();backend_.reset();}
        if(!device_.deactivate()){error_=GetLastError();return false;}
        active_=false;closed_=true;return true;
    }
    DWORD native_error() const noexcept override{return backend_?backend_->last_error():error_;}
    bool wait_for_work(sl3::worker::Mailbox& audio,unsigned pending,DWORD timeout) noexcept override{
        if(backend_->immediate_poll())return true;
        std::array<HANDLE,10> events{};DWORD count=0;
        events[count++]=audio.request_event();events[count++]=audio.output_event();
        for(unsigned i=0;i<8;++i)if(pending&(1u<<i)){const auto event=backend_->pending_event(i);if(event)events[count++]=event;}
        const auto waited=WaitForMultipleObjects(count,events.data(),FALSE,timeout);
        return waited==WAIT_TIMEOUT || waited<WAIT_OBJECT_0+count;
    }
};
class NativeHeldDevice final:public sl3::worker::SessionDevice {
    Api api_;Device device_{api_};bool active_=false,closed_=false;DWORD error_=0;
    NativeControlDiagnostic controls_;
    sl3::control::RateTestGrant rate_grant_;
    std::filesystem::path rate_directory_;
public:
    NativeHeldDevice(const std::filesystem::path& helper,sl3::diagnostic::StartupJournal& journal,
                     std::optional<sl3::control::selection_wire::Target> target,std::optional<unsigned> rate_target,
                     const std::filesystem::path& log):controls_(device_,target),rate_grant_(rate_target),rate_directory_(log.native()+L".rate"){
        api_.journal=&journal;
        if(target){
            api_.mark(target->setting==sl3::control::AudioControlSetting::through?"control_target_through.enter":"control_target_sensitivity.enter");
            api_.mark(target->group==0?"control_group_zero.enter":target->group==1?"control_group_one.enter":"control_group_two.enter");
            constexpr const char* values[]={"control_value_zero.enter","control_value_one.enter","control_value_two.enter","control_value_three.enter",
                "control_value_four.enter","control_value_five.enter","control_value_six.enter","control_value_seven.enter",
                "control_value_eight.enter","control_value_nine.enter","control_value_ten.enter","control_value_eleven.enter",
                "control_value_twelve.enter","control_value_thirteen.enter","control_value_fourteen.enter","control_value_fifteen.enter"};
            api_.mark(values[target->value]);
        }
        api_.load(helper);auto selected=api_.select(2000);device_.open(selected);
    }
    ~NativeHeldDevice(){if(!closed_ && !close())fail_stop();}
    unsigned read_rate() override{
        if(active_ || closed_)throw std::runtime_error("Held clock inspection requires idle device");
        api_.mark("clock_getter.enter");const auto rate=::read_rate(device_);api_.mark("clock_getter.return");return rate;
    }
    sl3::device_session::ControlSample read_controls() override{
        if(active_ || closed_)throw std::runtime_error("Held control inspection requires idle device");
        api_.mark("audio_controls.enter");const auto result=controls_.inspect();error_=controls_.native_error();
        if(result.error!=sl3::control::ControlsError::none || !result.controls){
            SetLastError(error_);
            throw std::runtime_error("Bounded audio-control query failed ("+std::to_string(unsigned(result.error))+", "+
                                     std::to_string(unsigned(result.exchange_error))+")");
        }
        api_.mark("audio_controls.return");return {*result.controls,result.read_attempts};
    }
    bool supports_selection() const noexcept override{return !active_ && !closed_ && controls_.supported();}
    sl3::control::selection_wire::Reply select_control(sl3::control::selection_wire::Target target) override{
        if(active_ || closed_)throw std::runtime_error("Native control test requires an idle held device");
        const auto result=controls_.select(target);error_=controls_.native_error();return result;
    }
    bool supports_rate_selection() const noexcept override{return !active_ && !closed_ && rate_grant_.available();}
    sl3::control::rate_wire::Reply select_rate(unsigned target) override{
        if(active_ || closed_ || !rate_grant_.consume(target))throw std::runtime_error("Native rate test requires its unused idle target grant");
        api_.mark(target==44100?"rate_target_44100.enter":"rate_target_48000.enter");
        // The journal is already CREATE_NEW on a local fixed drive. Never reuse
        // another operation's record directory; device_ keeps its sole redirect.
        if(!std::filesystem::create_directory(rate_directory_))throw std::runtime_error("Held rate record directory already exists");
        std::ofstream report;
        NativeRateIo io(device_,report,rate_directory_,target);io.save("before held rate transaction");
        api_.mark("rate_selection.enter");
        const auto result=sl3::control::diagnose_rate(target,io);
        // This observation precedes final device release. It deliberately does
        // not claim redirect_closed; later cleanup has separate owner evidence.
        io.save("finished",&result,false);api_.mark("rate_selection.return");error_=0;
        return {target,result,0}; // No independently captured Win32 status.
    }
    std::unique_ptr<sl3::worker::SessionTarget> begin(sl3::StreamConfig) override{
        if(controls_.enabled() || rate_grant_.enabled())throw std::runtime_error("Control/rate-test device cannot start audio");
        if(active_ || closed_)throw std::runtime_error("Held device is not available for activation");
        return std::make_unique<NativeHeldTarget>(device_,active_);
    }
    bool close() noexcept override{
        controls_.invalidate();
        if(closed_)return true;
        if(active_){error_=ERROR_BUSY;return false;}
        if(!device_.close()){error_=GetLastError();return false;}
        closed_=true;return true;
    }
    DWORD native_error() const noexcept override{return error_;}
};
int serve_native_device(const std::wstring& channel,const std::filesystem::path& helper,const std::filesystem::path& log,
                        std::optional<sl3::control::selection_wire::Target> target,std::optional<unsigned> rate_target){
    sl3::diagnostic::StartupJournal journal(log);journal.mark("worker.enter");
    auto mailbox=sl3::worker::Mailbox::open(channel);
    return sl3::worker::serve_device_session(*mailbox,sl3::session::Kind::native,
        [helper,&journal,target,rate_target,log]{return std::make_unique<NativeHeldDevice>(helper,journal,target,rate_target,log);});
}
int serve_native_stream(const std::wstring& channel,const std::filesystem::path& helper,const std::filesystem::path& log){
    sl3::diagnostic::StartupJournal journal(log);journal.mark("worker.enter");
    auto mailbox=sl3::worker::Mailbox::open(channel);
    return sl3::worker::serve_stream_session(*mailbox,sl3::session::Kind::native,
        [helper,&journal](sl3::StreamConfig config){return std::make_unique<NativeStreamTarget>(helper,config,journal);},
        [helper,&journal]{
            Api api;api.journal=&journal;Device device(api);api.load(helper);auto selected=api.select(2000);device.open(selected);
            api.mark("clock_getter.enter");const auto rate=read_rate(device);api.mark("clock_getter.return");
            // No alternate activation, ISO requests, rate setter or device reset.
            if(!device.close())fail_stop();return rate;
        });
}
}

int wmain(int argc,wchar_t** argv) {
    bool capture=false,list=false,plan=false,duplex=false,worker=false,stream_worker=false,device_worker=false,timer_query=false;
    unsigned rate_target=0;
    std::optional<sl3::control::selection_wire::Target> control_target;
    std::optional<unsigned> held_rate_target;
    std::optional<sl3::control::Challenge> timer_challenge;
    bool timer_cadence=false,timer_silent_stream=false,timer_tone=false;
    std::wstring channel;
    std::filesystem::path helper,output,startup_log;
    for(int i=1;i<argc;++i){const std::wstring arg=argv[i];
        if(arg==L"--capture")capture=true;else if(arg==L"--list")list=true;else if(arg==L"--plan")plan=true;
        else if(arg==L"--duplex-silence")duplex=true;
        else if(arg==L"--worker")worker=true;
        else if(arg==L"--stream-worker")stream_worker=true;
        else if(arg==L"--device-worker")device_worker=true;
        else if(arg==L"--timer-query")timer_query=true;
        else if(arg==L"--timer-cadence" && !timer_cadence)timer_cadence=true;
        else if(arg==L"--timer-silent-stream" && !timer_silent_stream)timer_silent_stream=true;
        else if(arg==L"--timer-tone" && !timer_tone)timer_tone=true;
        else if(arg==L"--challenge" && i+1<argc && !timer_challenge){
            try{timer_challenge=sl3::control::parse_driver_timer_challenge(argv[++i]);}
            catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
        }
        else if(arg==L"--control-test-target" && i+1<argc && !control_target){
            try{control_target=sl3::control::parse_control_test_target(argv[++i]);}
            catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
        }
        else if(arg==L"--rate-test-target" && i+1<argc && !held_rate_target){
            try{held_rate_target=sl3::control::parse_rate_test_target(argv[++i]);}
            catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
        }
        else if(arg==L"--select-rate" && i+1<argc && !rate_target){
            const std::wstring value=argv[++i];
            if(value==L"44100")rate_target=44100;else if(value==L"48000")rate_target=48000;
            else{std::cerr<<"Rate test target must be exactly 44100 or 48000\n";return 2;}
        }
        else if(arg==L"--channel" && i+1<argc)channel=argv[++i];
        else if(arg==L"--startup-log" && i+1<argc && startup_log.empty())startup_log=argv[++i];
        else if(arg==L"--helper" && i+1<argc)helper=argv[++i];else if(arg==L"--output" && i+1<argc)output=argv[++i];
        else{std::cerr<<"Usage: sl3_usbdk [--plan [--challenge HEX16] | --list --helper FILE | --timer-query --challenge HEX16 --helper FILE --output NEW_DIRECTORY | --capture/--duplex-silence/--select-rate HZ --helper FILE --output NEW_DIRECTORY | --worker/--stream-worker/--device-worker --channel LOCAL_NAME --helper FILE]\n";return 2;}
    }
    if(unsigned(capture)+unsigned(list)+unsigned(plan)+unsigned(duplex)+unsigned(worker)+unsigned(stream_worker)+unsigned(device_worker)+unsigned(rate_target!=0)+unsigned(timer_query)>1 || ((!capture && !duplex && !rate_target && !timer_query) && !output.empty()) || ((!capture && !list && !duplex && !worker && !stream_worker && !device_worker && !rate_target && !timer_query) && !helper.empty()) || (!worker && !stream_worker && !device_worker && !channel.empty()) || ((worker || stream_worker || device_worker) && (channel.empty() || helper.empty())) || (rate_target && output.empty()) || (timer_query && (!timer_challenge || output.empty())) || (timer_challenge && !timer_query && !plan)){std::cerr<<"Conflicting, missing or unused arguments\n";return 2;}
    if(timer_cadence && (!timer_challenge || (!timer_query && !plan))){std::cerr<<"Timer cadence requires a timer query or plan and challenge\n";return 2;}
    if(timer_silent_stream && !timer_cadence){std::cerr<<"Timer silent stream requires explicit cadence mode\n";return 2;}
    if(timer_tone && (!timer_cadence || timer_silent_stream)){std::cerr<<"Timer tone requires cadence and excludes silent stream mode\n";return 2;}
    if(!startup_log.empty() && !stream_worker && !device_worker){std::cerr<<"Startup journal is only valid for an isolated audio worker\n";return 2;}
    if(control_target && (!device_worker || startup_log.empty())){std::cerr<<"Control-test target requires an isolated device worker and explicit fresh startup journal\n";return 2;}
    if(held_rate_target && (!device_worker || startup_log.empty() || control_target)){
        std::cerr<<"Rate-test target requires a separate isolated device worker and explicit fresh startup journal\n";return 2;
    }
    if(plan && timer_challenge){
        std::cout<<"{\"plan_only\":true,\"helper_loaded\":false,\"device_access\":false,\"driver_changes\":false,\"timer_command\":\"0x37\"";
        if(timer_cadence)std::cout<<",\"maximum_writes\":10,\"maximum_reads\":40,\"budget_ms\":80,\"cadence_ms\":100";
        else std::cout<<",\"maximum_writes\":1,\"maximum_reads\":4,\"budget_ms\":1500";
        if(timer_silent_stream)std::cout<<",\"silent_stream\":true";
        if(timer_tone)std::cout<<",\"tone_hz\":997,\"tone_duration_ms\":650,\"routing_setters\":0";
        std::cout<<",\"audio_submissions\":0,\"response_verified\":false,\"challenge_hex\":"<<quote(timer_hex(*timer_challenge))<<"}\n";return 0;
    }
    if(device_worker){try{return serve_native_device(channel,helper,startup_log,control_target,held_rate_target);}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}}
    if(stream_worker){try{return serve_native_stream(channel,helper,startup_log);}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}}
    if(worker){try{return serve_worker(channel,helper);}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}}
    if(!capture && !list && !duplex && !rate_target && !timer_query){std::cout<<"{\"plan_only\":true,\"helper_loaded\":false,\"driver_changes\":false,\"scheduled_ms\":32,\"audio_output_submissions\":0,\"silent_duplex_requires_explicit_mode\":true,\"rate_test_requires_explicit_target\":true,\"scheduling\":\"UsbDk ASAP; continuity not verified\"}\n";return 0;}
    if(helper.empty()){std::cerr<<"An explicit pinned helper path is required\n";return 2;}
    std::ofstream report;bool timer_started=false;
    try{
        if(capture || duplex || rate_target || timer_query){
            if(output.empty() || std::filesystem::exists(output))throw std::runtime_error("A fresh output directory is required");
            if(!output.parent_path().empty())std::filesystem::create_directories(output.parent_path());
            if(!std::filesystem::create_directory(output))throw std::runtime_error("Output directory appeared concurrently");
            report.open(output/(timer_query?L"timer.json":rate_target?L"rate.json":duplex?L"duplex.json":L"capture.json"));if(!report)throw std::runtime_error("Cannot create result record");
            report<<"{\"phase\":\"before service query or helper load\",\"audio_output_submissions\":0}\n"<<std::flush;
        }
        Watchdog watchdog;Api api;api.load(helper);auto selected=api.select();
        if(list){std::cout<<"{\"matched_sl3\":1,\"descriptor_fixture_matches\":true,\"high_speed\":true,\"device_redirected\":false}\n";return 0;}
        if(timer_query){timer_started=true;return run_timer_diagnostic(api,selected,output,report,*timer_challenge,timer_cadence,timer_silent_stream,timer_tone);}
        if(rate_target)return run_rate_diagnostic(api,selected,output,report,rate_target);
        if(duplex)return run_duplex_silence(api,selected,output,report);
        Device device(api);unsigned rate=0;bool captured=false,closed=false,transfers=false;unsigned submitted=0,completed=0;
        std::size_t frames=0,zero_packets=0;bool layout_valid=false,maximum_shape=false;std::string error;
        const auto started=utc_now();std::ostringstream metadata;metadata<<'[';bool first=true;
        auto progress=[&](const char* phase){
            report.close();report.open(output/L"capture.json",std::ios::trunc);
            report<<"{\"phase\":"<<quote(phase)<<",\"audio_output_submissions\":0}\n"<<std::flush;
            if(!report)throw std::runtime_error("Cannot save capture progress record");
        };
        try{
            progress("verified dependency files and SL3 descriptor fixture; before redirect");
            device.open(selected);progress("redirected exact SL3; before clock getter");
            rate=read_rate(device);progress("clock getter complete; before audio alternates");
            device.activate();progress("audio alternates selected; before bounded IN capture");Capture backend(device);
            const auto result=sl3::capture_transaction(backend);submitted=backend.submitted;completed=backend.completed;transfers=result.transfers_succeeded;
            if(!result.cleanup_complete){report.close();report.open(output/L"capture.json",std::ios::trunc);report<<"{\"cleanup_complete\":false,\"process_teardown_required\":true,\"audio_output_submissions\":0}\n"<<std::flush;fail_stop();}
            std::vector<sl3::Frame> decoded_frames;std::vector<std::uint32_t> packet_lengths;
            for(std::size_t i=0;i<backend.slots.size();++i)if(backend.slots[i]){
                const auto& slot=*backend.slots[i];
                std::ofstream raw(output/(L"registered-"+std::to_wstring(i)+L".bin"),std::ios::binary);
                raw.write(reinterpret_cast<const char*>(slot.buffer.data()),std::streamsize(slot.buffer.size()));if(!raw)throw std::runtime_error("Cannot save registered buffer");
                for(std::size_t j=0;j<slot.results.size();++j){const auto& p=slot.results[j];
                    if(!first)metadata<<',';first=false;
                    metadata<<"{\"request\":"<<i<<",\"packet\":"<<j<<",\"offset\":"<<j*126<<",\"length\":"<<p.ActualLength<<",\"status\":"<<p.TransferResult
                     <<",\"request_attempted\":"<<(!slot.submitted_utc.empty()?"true":"false")<<",\"request_submitted\":"<<(slot.accepted?"true":"false")<<",\"request_terminal\":"<<(slot.terminal?"true":"false")
                     <<",\"completion_win32_error\":"<<slot.completion_error<<",\"request_usbd_status\":"<<slot.request.Result.GenResult.UsbdStatus
                     <<",\"submitted_utc\":"<<quote(slot.submitted_utc)<<",\"completed_utc\":"<<quote(slot.completed_utc)<<'}';
                }
            }
            if(!transfers)throw std::runtime_error(result.error);
            for(const auto& pointer:backend.slots){const auto& slot=*pointer;std::vector<sl3::Packet> packets;
                for(std::size_t j=0;j<slot.results.size();++j){const auto& p=slot.results[j];
                    if(p.TransferResult || p.ActualLength>126)throw std::runtime_error("Invalid UsbDk packet result; no truncation or recovery substitution");
                    packets.push_back({std::uint32_t(j*126),std::uint32_t(p.ActualLength),0});packet_lengths.push_back(std::uint32_t(p.ActualLength));
                }
                const auto decoded=sl3::decode_capture(slot.buffer,packets);frames+=decoded.frames.size();zero_packets+=decoded.zero_packets;
                decoded_frames.insert(decoded_frames.end(),decoded.frames.begin(),decoded.frames.end());
            }
            if(zero_packets || !frames)throw std::runtime_error("Empty packets observed; do not claim valid audio");
            const auto layout=sl3::make_playback_layout(packet_lengths,decoded_frames);layout_valid=true;maximum_shape=layout.winusb_maximum_packet_shape;
            std::ofstream pcm(output/L"capture.pcm",std::ios::binary);pcm.write(reinterpret_cast<const char*>(layout.packed_pcm.data()),std::streamsize(layout.packed_pcm.size()));if(!pcm)throw std::runtime_error("Cannot save PCM evidence");
            captured=true;
        }catch(const std::exception& e){error=e.what();}
        closed=device.close();metadata<<']';
        report.close();report.open(output/L"capture.json",std::ios::trunc);
        report<<"{\"transport\":\"UsbDk 1.0.22\",\"started_utc\":"<<quote(started)<<",\"completed_utc\":"<<quote(utc_now())
         <<",\"capture_succeeded\":"<<(captured?"true":"false")<<",\"transfers_succeeded\":"<<(transfers?"true":"false")<<",\"buffer_cleanup_complete\":true"
         <<",\"redirect_and_alternates_cleanup_succeeded\":"<<(closed?"true":"false")<<",\"alternate_readback_available\":false,\"continuity_verified\":false"
         <<",\"reported_rate_hz\":"<<rate<<",\"planned_intervals\":256,\"planned_ms\":32,\"submitted_requests\":"<<submitted<<",\"completed_requests\":"<<completed
         <<",\"frames\":"<<frames<<",\"zero_packets\":"<<zero_packets<<",\"offline_playback_layout_validated\":"<<(layout_valid?"true":"false")
         <<",\"winusb_maximum_packet_shape\":"<<(maximum_shape?"true":"false")<<",\"audio_output_submissions\":0,\"error\":"<<quote(error)<<",\"packets\":"<<metadata.str()<<"}\n"<<std::flush;
        if(!closed)fail_stop();
        return captured && report?0:1;
    }catch(const std::exception& e){
        if(report.is_open() && timer_query && !timer_started){
            report.close();report.open(output/L"timer.json",std::ios::trunc);
            report<<"{\"schema\":\"sl3.driver-timer-diagnostic.v1\",\"phase\":\"failed before timer diagnostic\",\"utc\":"<<quote(utc_now())
                  <<",\"challenge_hex\":"<<quote(timer_hex(*timer_challenge))<<",\"redirect_attempted\":false,\"write_attempts\":0,\"read_attempts\":0"
                  <<",\"response_parsed\":false,\"response_verified\":false,\"serato_admission_verified\":false,\"reopen_ready_verified\":false,\"audio_submissions\":0,\"error\":"<<quote(e.what())<<"}\n"<<std::flush;
        }
        if(report.is_open() && !rate_target && !timer_query){report.close();report.open(output/(duplex?L"duplex.json":L"capture.json"),std::ios::trunc);report<<"{\"capture_succeeded\":false,\"duplex_succeeded\":false,\"device_redirected\":false,\"submitted_requests\":0,\"completed_requests\":0,\"error\":"<<quote(e.what())<<",\"audio_output_submissions\":0}\n";}
        // Rate diagnostics preserve their last durable progress record on
        // unexpected outer failure; do not replace possible effects with zero.
        std::cerr<<e.what()<<'\n';return 1;
    }
}
