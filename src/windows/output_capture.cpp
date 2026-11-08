#include "windows/output_capture.hpp"
#include "windows/diagnostic.hpp"
#include "core/output_recorder.hpp"
#include <bcrypt.h>
#include <atomic>
#include <filesystem>
#include <optional>
#include <vector>

namespace sl3::worker {
namespace {
enum Phase:unsigned {waiting,armed,complete,failed,retired};
static_assert(std::atomic<unsigned>::is_always_lock_free,"Capture state must not lock the stream thread");
void write_new(const std::filesystem::path& path,const void* data,DWORD size){
    HANDLE file=CreateFileW(path.c_str(),GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_NEW,
                           FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
    if(file==INVALID_HANDLE_VALUE)throw std::runtime_error("Cannot create output capture file");
    DWORD written=0;const bool ok=WriteFile(file,data,size,&written,nullptr)!=FALSE && written==size;
    CloseHandle(file);if(!ok)throw std::runtime_error("Cannot write output capture file");
}
void text_new(const std::filesystem::path& path,const std::string& text){write_new(path,text.data(),static_cast<DWORD>(text.size()));}
std::string hash_pcm(const std::vector<std::uint8_t>& pcm){
    BCRYPT_ALG_HANDLE algorithm=nullptr;
    if(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)<0)throw std::runtime_error("Capture hash unavailable");
    std::array<UCHAR,32> digest{};
    BCRYPT_HASH_HANDLE hash=nullptr;
    auto status=BCryptCreateHash(algorithm,&hash,nullptr,0,nullptr,0,0);
    if(status>=0)status=BCryptHashData(hash,const_cast<PUCHAR>(pcm.data()),static_cast<ULONG>(pcm.size()),0);
    if(status>=0)status=BCryptFinishHash(hash,digest.data(),32,0);
    if(hash)BCryptDestroyHash(hash);
    BCryptCloseAlgorithmProvider(algorithm,0);
    if(status<0)throw std::runtime_error("Capture hash failed");
    std::ostringstream result;result<<std::hex<<std::setfill('0');
    for(auto byte:digest)result<<std::setw(2)<<unsigned(byte);return result.str();
}
void validate_destination(const std::filesystem::path& path){
    if(!path.is_absolute() || !path.has_root_name() || path.root_name().wstring().size()!=2 ||
       GetDriveTypeW(path.root_path().c_str())!=DRIVE_FIXED)throw std::invalid_argument("Capture needs an absolute local fixed-drive path");
    for(const auto& part:path)if(part==L".." || part==L".")throw std::invalid_argument("Capture path traversal refused");
    for(auto parent=path.parent_path();!parent.empty();){
        const DWORD flags=GetFileAttributesW(parent.c_str());
        if(flags==INVALID_FILE_ATTRIBUTES || !(flags&FILE_ATTRIBUTE_DIRECTORY) || (flags&FILE_ATTRIBUTE_REPARSE_POINT))
            throw std::invalid_argument("Capture parent must exist without reparse points");
        const auto next=parent.parent_path();if(next==parent)break;parent=next;
    }
}
}
struct SoftwareOutputCapture::State {
    std::filesystem::path directory;std::vector<std::uint8_t> pcm;
    PackedOutputRecorder recorder;
    std::vector<std::uint8_t> input_pcm;
    std::optional<PackedOutputRecorder> input;
    std::atomic<unsigned> phase{waiting};std::atomic<bool> stop{false};std::thread writer;
    State(std::filesystem::path path,unsigned rate,bool loopback):directory(std::move(path)),
        pcm(std::size_t(rate)*5*18),recorder(pcm.data(),std::size_t(rate)*5,rate){
        if(recorder.fault()!=OutputRecordFault::none)throw std::invalid_argument("Unsupported output capture rate");
        if(loopback){
            input_pcm.resize(pcm.size());
            input.emplace(input_pcm.data(),std::size_t(rate)*5,rate);
        }
        validate_destination(directory);
        if(!std::filesystem::create_directory(directory))throw std::invalid_argument("Output capture directory already exists");
        text_new(directory/L"ready.json",loopback?
            "{\"schema\":1,\"state\":\"awaiting-arm\",\"seconds\":5,\"source\":\"worker-dequeued-output-pcm\",\"loopbackInput\":true}\n":
            "{\"schema\":1,\"state\":\"awaiting-arm\",\"seconds\":5,\"source\":\"worker-dequeued-output-pcm\"}\n");
        writer=std::thread([this]{run();});
    }
    ~State(){stop.store(true,std::memory_order_release);if(writer.joinable())writer.join();}
    void append(PackedOutputRecorder& destination,const AudioBlock& block) noexcept {
        if(phase.load(std::memory_order_acquire)!=armed)return;
        if(!destination.append(block))phase.store(failed,std::memory_order_release);
        else if(recorder.complete() && (!input || input->complete()))phase.store(complete,std::memory_order_release);
    }
    void run() noexcept {
        try{
            for(;;){
                const auto value=phase.load(std::memory_order_acquire);
                if(value==complete){
                    const auto digest=hash_pcm(pcm);
                    write_new(directory/L"capture.pcm",pcm.data(),static_cast<DWORD>(pcm.size()));
                    auto text=std::string("{\"schema\":1,\"source\":\"worker-dequeued-output-pcm\",\"complete\":true,\"rateHz\":")+
                        std::to_string(recorder.rate())+",\"frames\":"+std::to_string(recorder.frames())+
                        ",\"firstFrame\":"+std::to_string(recorder.first_frame())+",\"pcmSha256\":\""+digest+"\"";
                    if(input){
                        const auto input_digest=hash_pcm(input_pcm);
                        write_new(directory/L"input.pcm",input_pcm.data(),static_cast<DWORD>(input_pcm.size()));
                        text+=",\"input\":{\"source\":\"worker-published-input-pcm\",\"frames\":"+std::to_string(input->frames())+
                            ",\"firstFrame\":"+std::to_string(input->first_frame())+",\"pcmSha256\":\""+input_digest+"\"}";
                    }
                    text_new(directory/L"capture.json",text+"}\n");return; // Completion is published last.
                }
                if(value==failed || value==retired || stop.load(std::memory_order_acquire)){
                    // The writer may have read 'armed' immediately before the
                    // stream published completion and its owner began joining.
                    if(phase.load(std::memory_order_acquire)==complete)continue;
                    text_new(directory/L"capture-error.json","{\"schema\":1,\"complete\":false,\"reason\":\"clip-not-completed\"}\n");return;
                }
                if(value==waiting){
                    const auto flags=GetFileAttributesW((directory/L"arm.txt").c_str());
                    if(flags!=INVALID_FILE_ATTRIBUTES){
                        if(flags&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT))throw std::runtime_error("Invalid capture arm marker");
                        unsigned expected=waiting;phase.compare_exchange_strong(expected,armed,std::memory_order_release,std::memory_order_relaxed);
                    }
                }
                Sleep(25); // Background control/writer only, never the stream owner.
            }
        }catch(...){
            // Recording failure never changes device/stream state or claims a clip.
            phase.store(failed,std::memory_order_release);
            try{text_new(directory/L"capture-error.json","{\"schema\":1,\"complete\":false,\"reason\":\"capture-file-failure\"}\n");}catch(...){}
        }
    }
};
SoftwareOutputCapture::SoftwareOutputCapture(std::unique_ptr<State> state):state_(std::move(state)){}
SoftwareOutputCapture::~SoftwareOutputCapture()=default;
std::unique_ptr<SoftwareOutputCapture> SoftwareOutputCapture::from_environment(unsigned rate){
    const DWORD size=GetEnvironmentVariableW(L"SL3_OUTPUT_CAPTURE_DIRECTORY",nullptr,0);
    if(!size)return {};
    if(size>32767)throw std::invalid_argument("Output capture path too long");
    std::vector<wchar_t> path(size);const auto copied=GetEnvironmentVariableW(L"SL3_OUTPUT_CAPTURE_DIRECTORY",path.data(),size);
    if(!copied || copied>=size)throw std::invalid_argument("Output capture environment changed");
    wchar_t input_flag[2]{};
    const auto length=GetEnvironmentVariableW(L"SL3_LOOPBACK_CAPTURE",input_flag,2);
    if(length && (length!=1 || input_flag[0]!=L'1'))throw std::invalid_argument("Loopback capture flag must be 1");
    return std::unique_ptr<SoftwareOutputCapture>(new SoftwareOutputCapture(std::make_unique<State>(std::filesystem::path(path.data()),rate,length==1)));
}
void SoftwareOutputCapture::append(const AudioBlock& block) noexcept {
    state_->append(state_->recorder,block);
}
void SoftwareOutputCapture::append_input(const AudioBlock& block) noexcept {
    if(state_->input)state_->append(*state_->input,block);
}
bool SoftwareOutputCapture::is_armed() const noexcept{return state_->phase.load(std::memory_order_acquire)==armed;}
void SoftwareOutputCapture::retire() noexcept {
    const auto value=state_->phase.load(std::memory_order_acquire);
    if(value==waiting || value==armed)state_->phase.store(retired,std::memory_order_release);
}
}
