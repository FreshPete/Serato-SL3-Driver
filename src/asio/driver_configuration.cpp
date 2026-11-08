#include "asio/driver_configuration.hpp"
#include "asio/broker_activation.hpp"
#include <algorithm>
#include <array>
#include <charconv>
#include <limits>
#include <stdexcept>
#include "windows/broker_record.hpp"

namespace sl3::asio {
namespace {
void local_path(const std::filesystem::path& path){
    const auto drive=path.root_name().native();const auto& name=path.native();
    if(!path.is_absolute() || name.find(L'\0')!=std::wstring::npos || drive.size()!=2 || drive[1]!=L':' ||
       !((drive[0]>=L'A' && drive[0]<=L'Z') || (drive[0]>=L'a' && drive[0]<=L'z')) || name.find(L':',2)!=std::wstring::npos ||
       GetDriveTypeW(path.root_path().c_str())!=DRIVE_FIXED)
        throw std::invalid_argument("ASIO configuration requires a local fixed-drive file path");
}
struct File {
    HANDLE handle=INVALID_HANDLE_VALUE;
    File(const std::filesystem::path& path,DWORD maximum){
        local_path(path);
        handle=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        if(handle==INVALID_HANDLE_VALUE)throw std::runtime_error("ASIO configuration file is missing or not readable");
        LARGE_INTEGER size{};
        if(GetFileType(handle)!=FILE_TYPE_DISK || !GetFileSizeEx(handle,&size) || size.QuadPart<=0 || size.QuadPart>maximum){
            CloseHandle(handle);handle=INVALID_HANDLE_VALUE;throw std::runtime_error("Invalid ASIO configuration file size/type");
        }
        try{
            std::array<wchar_t,32768> final{};
            const auto n=GetFinalPathNameByHandleW(handle,final.data(),DWORD(final.size()),FILE_NAME_NORMALIZED|VOLUME_NAME_DOS);
            if(n<=4 || n>=final.size() || std::wstring(final.data(),4)!=L"\\\\?\\")throw std::runtime_error("Resolve local ASIO configuration file");
            local_path(std::filesystem::path(std::wstring(final.data()+4,n-4)));
        }catch(...){CloseHandle(handle);handle=INVALID_HANDLE_VALUE;throw;}
    }
    ~File(){if(handle!=INVALID_HANDLE_VALUE)CloseHandle(handle);}
    File(const File&)=delete;File& operator=(const File&)=delete;
    std::string text(){
        LARGE_INTEGER size{};if(!GetFileSizeEx(handle,&size))throw std::runtime_error("Read configuration size");
        std::string bytes(std::size_t(size.QuadPart),'\0');DWORD received=0;
        if(!ReadFile(handle,bytes.data(),DWORD(bytes.size()),&received,nullptr) || received!=bytes.size())throw std::runtime_error("Read complete configuration");
        return bytes;
    }
};
struct Files {std::vector<std::unique_ptr<File>> retained;std::vector<std::shared_ptr<const void>> external;};
std::string locked_text(Files& files,const std::filesystem::path& path){
    auto file=std::make_unique<File>(path,65536);auto text=file->text();files.retained.push_back(std::move(file));return text;
}
void pin_hash(Files& files,const std::filesystem::path& path,const std::string& expected,DWORD maximum){
    auto file=std::make_unique<File>(path,maximum);
    // The first handle denies write/delete while the hash helper opens its own
    // read handle; these locked bytes remain fixed through facade lifetime.
    if(worker::Process::executable_sha256(path)!=expected)throw std::runtime_error("ASIO configured file hash mismatch");
    files.retained.push_back(std::move(file));
}
std::string hash(const std::string& value){
    if(value.size()!=64 || !std::all_of(value.begin(),value.end(),[](char c){return (c>='0' && c<='9') || (c>='a' && c<='f');}))
        throw std::invalid_argument("ASIO hashes must be lowercase SHA256");return value;
}
std::filesystem::path path(const std::string& value){
    if(value.empty() || value.size()>32760 || std::any_of(value.begin(),value.end(),[](unsigned char c){return c<32 || c==127;}))
        throw std::invalid_argument("Invalid ASIO configuration path");
    const auto count=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,value.data(),int(value.size()),nullptr,0);
    if(count<=0)throw std::invalid_argument("ASIO path is not UTF-8");std::wstring wide(std::size_t(count),L'\0');
    if(MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,value.data(),int(value.size()),wide.data(),count)!=count)throw std::runtime_error("Decode ASIO path");
    std::filesystem::path result(wide);if(!result.is_absolute())throw std::invalid_argument("ASIO path is relative");return result;
}
unsigned number(const std::string& text){
    if(text.empty() || (text.size()>1 && text[0]=='0'))throw std::invalid_argument("Noncanonical ASIO frame/rate value");
    unsigned value=0;const auto parsed=std::from_chars(text.data(),text.data()+text.size(),value);
    if(parsed.ec!=std::errc{} || parsed.ptr!=text.data()+text.size())throw std::invalid_argument("Invalid ASIO frame/rate value");return value;
}
std::vector<std::string> record(const std::string& bytes,const std::vector<std::string>& fields){
    if(bytes.empty() || bytes.back()!='\n' || bytes.find('\0')!=std::string::npos)throw std::invalid_argument("Incomplete ASIO record");
    std::vector<std::string> result;std::size_t offset=0;
    for(const auto& field:fields){
        const auto end=bytes.find('\n',offset);if(end==std::string::npos)throw std::invalid_argument("Missing ASIO record field");
        auto line=bytes.substr(offset,end-offset);if(!line.empty() && line.back()=='\r')line.pop_back();
        if(line.find('\r')!=std::string::npos || line.compare(0,field.size(),field)!=0)throw std::invalid_argument("Unexpected ASIO record field/order");
        result.push_back(line.substr(field.size()));offset=end+1;
    }
    if(offset!=bytes.size())throw std::invalid_argument("Trailing ASIO record fields");return result;
}
}
SessionPointer parse_session_pointer(const std::string& bytes){
    if(bytes.size()>65536)throw std::invalid_argument("ASIO session pointer exceeds record limit");
    const auto selected=record(bytes,{"SL3-ASIO-SESSION-POINTER-1","configuration=","configuration_sha256="});
    if(!selected[0].empty())throw std::invalid_argument("Unknown ASIO session pointer version");
    return {path(selected[1]),hash(selected[2])};
}
std::string session_pointer_text(const std::filesystem::path& configuration,const std::string& sha256){
    auto text="SL3-ASIO-SESSION-POINTER-1\nconfiguration="+configuration.u8string()+"\nconfiguration_sha256="+sha256+"\n";
    parse_session_pointer(text);return text;
}
DriverConfiguration load_driver_configuration(const std::filesystem::path& location,TimingPolicy policy){
    auto files=std::make_shared<Files>();
    const auto bytes=locked_text(*files,location);
    const std::string broker_prefix="SL3-ASIO-BROKER-CONFIG-";
    const bool broker=bytes.compare(0,broker_prefix.size(),broker_prefix)==0;
    const auto config=broker?record(bytes,{"SL3-ASIO-BROKER-CONFIG-1","worker=","worker_sha256=","helper=","timing_record=","timing_record_sha256=","broker=","broker_sha256=","session_record=","session_record_sha256="}):
        record(bytes,{"SL3-ASIO-CONFIG-1","worker=","worker_sha256=","helper=","timing_record=","timing_record_sha256="});
    if(!config[0].empty())throw std::invalid_argument("Unknown ASIO configuration version");
    DriverConfiguration result;result.worker.executable=path(config[1]);result.worker.sha256=hash(config[2]);result.worker.helper=path(config[3]);
    result.worker.lifetime=DeviceLifetime::retained;
    const auto timing_path=path(config[4]);const auto timing_hash=hash(config[5]);
    pin_hash(*files,timing_path,timing_hash,65536);
    const auto timing_text=locked_text(*files,timing_path);
    if(policy==TimingPolicy::unmeasured_diagnostic){
        const bool keepalive=timing_text.rfind("SL3-ASIO-DIAGNOSTIC-TIMING-2",0)==0;
        const auto timing=record(timing_text,{keepalive?"SL3-ASIO-DIAGNOSTIC-TIMING-2":"SL3-ASIO-DIAGNOSTIC-TIMING-1",
            "worker_sha256=","helper_sha256=","rate_hz=","buffer_frames="});
        const auto frames=number(timing[4]);
        if(!timing[0].empty() || hash(timing[1])!=result.worker.sha256 || hash(timing[2])!=reviewed_helper_sha256 ||
           timing[3]!="44100" || (frames!=128 && !(keepalive && (frames==32 || frames==64))))
            throw std::invalid_argument("ASIO diagnostic requires 44.1 kHz and 128 frames, or 32/64 frames with playback keepalive");
        if(keepalive)result.keepalive_timing_sha256=timing_hash;
        result.latency={0,0,44100,frames,false};
    }else{
        const bool keepalive=timing_text.rfind("SL3-ASIO-TIMING-2",0)==0;
        const auto timing=record(timing_text,{keepalive?"SL3-ASIO-TIMING-2":"SL3-ASIO-TIMING-1","review=","worker_sha256=","helper_sha256=","rate_hz=","buffer_frames=",
            "intervals=","requests_per_direction=","input_extra_frames=","output_extra_frames=","measurement_file=","measurement_sha256="});
        if(keepalive)result.keepalive_timing_sha256=timing_hash;
        if(!timing[0].empty() || timing[1]!="approved" || hash(timing[2])!=result.worker.sha256 || hash(timing[3])!=reviewed_helper_sha256 ||
           timing[6]!="8" || timing[7]!="4")throw std::invalid_argument("ASIO timing does not bind the reviewed worker/helper/pipeline");
        result.latency={number(timing[8]),number(timing[9]),number(timing[4]),number(timing[5])};
        const auto& latency=result.latency;const auto limit=unsigned(std::numeric_limits<long>::max())-2048u;
        if((latency.rate_hz!=44100 && latency.rate_hz!=48000) || latency.buffer_frames<64 || latency.buffer_frames>1024 ||
           (latency.buffer_frames&(latency.buffer_frames-1)) || latency.input_extra_frames>limit || latency.output_extra_frames>limit)
            throw std::invalid_argument("Invalid bound ASIO timing mode");
        pin_hash(*files,path(timing[10]),hash(timing[11]),1024*1024);
    }
    pin_hash(*files,result.worker.executable,result.worker.sha256,256*1024*1024);
    pin_hash(*files,result.worker.helper,reviewed_helper_sha256,256*1024*1024);
    if(broker){
        auto binding=worker::bind_broker_record(path(config[8]),hash(config[9]),path(config[6]),hash(config[7]),result.worker.sha256,result.keepalive_timing_sha256);
        result.broker=BrokerAttachment{binding.endpoint,std::move(binding.server),session::Kind::native,result.worker.sha256};
        files->external.push_back(std::move(binding.files));
    }
    result.files=std::move(files);return result;
}
DriverConfiguration load_driver_entry_configuration(const std::filesystem::path& location,TimingPolicy policy){
    auto files=std::make_shared<Files>();const auto bytes=locked_text(*files,location);
    const std::string activation_prefix="SL3-ASIO-ACTIVATION-";
    if(bytes.compare(0,activation_prefix.size(),activation_prefix)==0){
        const bool application_bound=bytes.rfind("SL3-ASIO-ACTIVATION-2",0)==0;
        const auto values=record(bytes,{application_bound?"SL3-ASIO-ACTIVATION-2":"SL3-ASIO-ACTIVATION-1","controller=","controller_sha256=","input=","input_sha256=",
                                        "startup_timeout_ms=","startup_failure_grace_ms=","lifetime_ms="});
        if(!values[0].empty())throw std::invalid_argument("Unknown ASIO activation version");
        auto spec=std::make_shared<BrokerActivationSpec>();spec->application_bound=application_bound;
        spec->controller=path(values[1]);spec->controller_sha256=hash(values[2]);
        spec->input=path(values[3]);spec->input_sha256=hash(values[4]);spec->startup_timeout_ms=number(values[5]);
        spec->startup_failure_grace_ms=number(values[6]);spec->lifetime_ms=number(values[7]);spec->timing=policy;
        if(spec->startup_timeout_ms<100 || spec->startup_timeout_ms>30000 || spec->startup_failure_grace_ms>15000 ||
           spec->lifetime_ms<1000 || spec->lifetime_ms>43200000 || (policy==TimingPolicy::unmeasured_diagnostic && spec->lifetime_ms>600000))
            throw std::invalid_argument("Invalid ASIO activation deadlines");
        pin_hash(*files,spec->controller,spec->controller_sha256,256*1024*1024);pin_hash(*files,spec->input,spec->input_sha256,65536);
        auto input=load_driver_configuration(spec->input,policy);
        if(input.broker)throw std::invalid_argument("ASIO activation cannot wrap another broker");
        files->external.push_back(input.files);input.files=files;input.activation=std::move(spec);return input;
    }
    const std::string prefix="SL3-ASIO-LOCATOR-";
    if(bytes.compare(0,prefix.size(),prefix)!=0){
        // Preserve the explicit direct formats. A malformed locator cannot
        // reach this branch or fall back to a private worker configuration.
        auto result=load_driver_configuration(location,policy);
        if(!result.broker && !result.keepalive_timing_sha256.empty())
            throw std::invalid_argument("Keepalive timing requires a controller-owned broker session");
        files->external.push_back(result.files);result.files=files;return result;
    }
    const auto locator=record(bytes,{"SL3-ASIO-LOCATOR-1","session_pointer=","broker=","broker_sha256=","worker_sha256="});
    if(!locator[0].empty())throw std::invalid_argument("Unknown ASIO locator version");
    const auto broker_path=path(locator[2]);const auto broker_hash=hash(locator[3]);const auto worker_hash=hash(locator[4]);
    pin_hash(*files,broker_path,broker_hash,256*1024*1024);
    // Keep the mutable pointer locked only while resolving it. Existing
    // objects retain the selected immutable records and exact process object,
    // so a later pointer replacement cannot redirect an attached client.
    File pointer(path(locator[1]),65536);
    const auto selected=parse_session_pointer(pointer.text());
    const auto configuration=selected.configuration;pin_hash(*files,configuration,selected.sha256,65536);
    const auto config=record(locked_text(*files,configuration),{"SL3-ASIO-BROKER-CONFIG-1","worker=","worker_sha256=","helper=","timing_record=","timing_record_sha256=","broker=","broker_sha256=","session_record=","session_record_sha256="});
    if(!config[0].empty() || hash(config[2])!=worker_hash || hash(config[7])!=broker_hash)
        throw std::invalid_argument("ASIO session does not match locator worker/broker pins");
    File anchor(broker_path,256*1024*1024),actual(path(config[6]),256*1024*1024);
    BY_HANDLE_FILE_INFORMATION first{},second{};
    if(!GetFileInformationByHandle(anchor.handle,&first) || !GetFileInformationByHandle(actual.handle,&second) ||
       first.dwVolumeSerialNumber!=second.dwVolumeSerialNumber || first.nFileIndexHigh!=second.nFileIndexHigh || first.nFileIndexLow!=second.nFileIndexLow)
        throw std::invalid_argument("ASIO session broker differs from locator file identity");
    auto result=load_driver_configuration(configuration,policy);
    if(!result.broker)throw std::invalid_argument("ASIO locator requires a broker session");
    files->external.push_back(result.files);result.files=std::move(files);return result;
}
std::filesystem::path production_configuration_path(){
    HMODULE module=nullptr;
    if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCWSTR>(&production_configuration_path),&module))throw std::runtime_error("Find ASIO configuration module");
    std::vector<wchar_t> buffer(32768);const auto count=GetModuleFileNameW(module,buffer.data(),DWORD(buffer.size()));
    if(!count || count>=buffer.size())throw std::runtime_error("Read ASIO module path");
    return std::filesystem::path(std::wstring(buffer.data(),count)).parent_path()/L"sl3-asio.conf";
}
std::unique_ptr<DriverFacade> make_native_asio_facade(TimingPolicy policy){
    return make_configured_asio_facade(load_driver_entry_configuration(production_configuration_path(),policy),policy);
}
std::unique_ptr<DriverFacade> make_configured_asio_facade(DriverConfiguration config,TimingPolicy policy){
    if(policy==TimingPolicy::unmeasured_diagnostic && !config.broker && !config.activation)
        throw std::invalid_argument("Unmeasured ASIO requires a retained broker");
    if(config.activation)return std::make_unique<DriverFacade>(std::make_shared<DriverOwner>(*config.activation,config.files),config.latency);
    if(config.broker)return std::make_unique<DriverFacade>(*config.broker,config.latency,config.files);
    return std::make_unique<DriverFacade>(config.worker,config.latency,config.files);
}
std::shared_ptr<DriverScope> make_native_asio_scope(TimingPolicy policy){
    return make_configured_asio_scope(load_driver_entry_configuration(production_configuration_path(),policy),policy);
}
std::shared_ptr<DriverScope> make_configured_asio_scope(DriverConfiguration config,TimingPolicy policy){
    if(policy==TimingPolicy::unmeasured_diagnostic && !config.broker && !config.activation)
        throw std::invalid_argument("Unmeasured ASIO requires a retained broker");
    if(config.activation)return std::make_shared<DriverScope>(DriverScope{std::make_shared<DriverOwner>(*config.activation,config.files),config.latency});
    if(config.broker)return std::make_shared<DriverScope>(DriverScope{std::make_shared<DriverOwner>(*config.broker,config.files),config.latency});
    return std::make_shared<DriverScope>(DriverScope{std::make_shared<DriverOwner>(config.worker,config.files),config.latency});
}
}
