#pragma once
#include "core/rate_diagnostic.hpp"
#include "windows/diagnostic.hpp"
#include <algorithm>
#include <array>
#include <filesystem>
#include <sstream>

namespace sl3::diagnostic {
struct RateNativeFacts {
    bool invoked=false,api_attempted=false,api_accepted=false,terminal=false;
    unsigned adapter_timeout_ms=0;
    std::uint32_t completion_error=0;
    std::uint64_t usbd_status=0;
    std::array<char,40> submitted_utc{},completed_utc{};
};
// One writer, one fresh bounded diagnostic. Prefixes survive a stalled request;
// an end record describes retired storage. Decisions are persisted separately
// after the transaction, without claiming target verification, device release,
// ETW correlation or physical clock measurement.
class RateIoLog final {
    HANDLE file_=INVALID_HANDLE_VALUE;unsigned attempts_=0,decisions_=0;bool active_=false,output_=false,transaction_=false;
    static const char* decision(control::RateIoDecision d) noexcept {
        switch(d){
        case control::RateIoDecision::write_retired:return "write_retired";
        case control::RateIoDecision::notification:return "notification";
        case control::RateIoDecision::reply:return "reply";
        case control::RateIoDecision::exchange_failure:return "exchange_failure";
        case control::RateIoDecision::cancelled:return "cancelled";
        case control::RateIoDecision::deadline:return "deadline";
        case control::RateIoDecision::transfer_failure:return "transfer_failure";
        }
        fail_stop();
    }
    static void hex(std::ostream& out,const control::Frame& frame,std::size_t bytes){
        constexpr char digits[]="0123456789abcdef";out<<'"';
        for(std::size_t i=0;i<bytes;++i)out<<digits[frame[i]>>4]<<digits[frame[i]&15];out<<'"';
    }
    static void stamp(std::ostream& out,const char* text){
        if(!*text){out<<"null";return;}
        for(const auto* p=text;*p;++p)if(!((*p>='0' && *p<='9') || *p=='T' || *p=='Z' || *p==':' || *p=='.' || *p=='-' || *p=='+'))fail_stop();
        out<<'"'<<text<<'"';
    }
    void append(const std::string& text) noexcept {
        DWORD written=0;
        if(text.size()>2048 || !WriteFile(file_,text.data(),DWORD(text.size()),&written,nullptr) || written!=text.size())fail_stop();
    }
public:
    RateIoLog(const std::filesystem::path& path,unsigned target,const std::string& utc){
        if(target!=44100 && target!=48000)throw std::invalid_argument("Invalid rate recording target");
        file_=CreateFileW(path.c_str(),GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_WRITE_THROUGH,nullptr);
        if(file_==INVALID_HANDLE_VALUE)failed("Create fresh rate I/O recording");
        try{
            std::ostringstream line;line<<"{\"schema\":\"sl3.rate-io.v2\",\"event\":\"header\",\"pid\":"<<GetCurrentProcessId()
                <<",\"target_rate_hz\":"<<target<<",\"utc\":";stamp(line,utc.c_str());line<<"}\n";append(line.str());
        }catch(...){CloseHandle(file_);file_=INVALID_HANDLE_VALUE;throw;}
    }
    ~RateIoLog(){if(file_!=INVALID_HANDLE_VALUE)CloseHandle(file_);}
    RateIoLog(const RateIoLog&)=delete;RateIoLog& operator=(const RateIoLog&)=delete;
    void begin(bool output,unsigned timeout,std::uint64_t tick,const control::Frame& frame) noexcept {
        try{
            if(active_ || attempts_>=15 || !timeout || timeout>(output?100u:300u))fail_stop();
            output_=output;active_=true;
            std::ostringstream line;line<<std::boolalpha<<"{\"event\":\"begin\",\"sequence\":"<<attempts_++<<",\"output\":"<<output
                <<",\"timeout_ms\":"<<timeout<<",\"adapter_started_ms\":"<<tick<<",\"frame_hex\":";
            if(output)hex(line,frame,frame.size());else line<<"null";
            line<<"}\n";append(line.str());
        }catch(...){fail_stop();}
    }
    void end(const control::RateIoObservation& o,const RateNativeFacts& native) noexcept {
        try{
            if(!active_ || o.sequence+1!=attempts_ || o.output!=output_)fail_stop();
            std::ostringstream line;line<<std::boolalpha<<"{\"event\":\"end\",\"sequence\":"<<o.sequence<<",\"output\":"<<o.output
                <<",\"adapter_completed_ms\":"<<o.completed_ms<<",\"io_return_success\":"<<o.transferred
                <<",\"bytes\":"<<o.bytes<<",\"frame_hex\":";
            if(o.output)line<<"null";else hex(line,o.frame,(std::min)(o.bytes,o.frame.size()));
            line<<",\"adapter_invoked\":"<<native.invoked<<",\"api_attempted\":"<<native.api_attempted<<",\"api_accepted\":"<<native.api_accepted
                <<",\"native_terminal\":"<<native.terminal<<",\"adapter_timeout_ms\":"<<native.adapter_timeout_ms
                <<",\"completion_error\":"<<native.completion_error<<",\"usbd_status\":"<<native.usbd_status<<",\"submitted_utc\":";
            stamp(line,native.submitted_utc.data());line<<",\"completed_utc\":";stamp(line,native.completed_utc.data());
            line<<"}\n";append(line.str());active_=false;
        }catch(...){fail_stop();}
    }
    void transaction(std::uint64_t start,unsigned budget,std::uint64_t finished,control::DiagnosticError error) noexcept {
        try{
            if(active_ || transaction_ || decisions_)fail_stop();
            std::ostringstream line;line<<"{\"event\":\"transaction\",\"started_ms\":"<<start<<",\"budget_ms\":"<<budget
                <<",\"finished_ms\":"<<finished<<",\"diagnostic_error\":"<<unsigned(error)<<"}\n";
            append(line.str());transaction_=true;
        }catch(...){fail_stop();}
    }
    void decided(const control::RateIoObservation& o) noexcept {
        try{
            if(active_ || !transaction_ || o.sequence!=decisions_ || decisions_>=attempts_)fail_stop();
            std::ostringstream line;line<<std::boolalpha<<"{\"event\":\"decision\",\"sequence\":"<<decisions_++
                <<",\"output\":"<<o.output<<",\"runner_started_ms\":"<<o.started_ms<<",\"runner_completed_ms\":"<<o.completed_ms
                <<",\"transferred\":"<<o.transferred<<",\"bytes\":"<<o.bytes<<",\"decision\":\""<<decision(o.decision)<<"\"}\n";
            append(line.str());
        }catch(...){fail_stop();}
    }
};
}
