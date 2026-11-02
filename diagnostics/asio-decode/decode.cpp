#include "asio/call_trace.hpp"
#include <evntrace.h>
#include <evntcons.h>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
namespace fs=std::filesystem;
namespace t=sl3::asio::trace;
static void require(bool b,const char* why){if(!b)throw std::runtime_error(why);}
static void check(ULONG status,const char* why){if(status!=ERROR_SUCCESS)throw std::runtime_error(std::string(why)+": "+std::to_string(status));}
struct File {
    HANDLE h=INVALID_HANDLE_VALUE;
    explicit File(const fs::path& p){h=CreateFileW(p.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);require(h!=INVALID_HANDLE_VALUE,"Create new result file");}
    ~File(){if(h!=INVALID_HANDLE_VALUE)CloseHandle(h);}
    void write(const std::string& s){DWORD n=0;require(s.size()<65536 && WriteFile(h,s.data(),DWORD(s.size()),&n,nullptr) && n==s.size(),"Write complete result");}
};
struct Decoded {File* output;DWORD pid;std::size_t count=0;bool failed=false;};
static VOID WINAPI receive(EVENT_RECORD* event){
    auto& d=*static_cast<Decoded*>(event->UserContext);
    if(event->EventHeader.ProviderId!=t::provider_id)return;
    try{
        require(event->EventHeader.ProcessId==d.pid,"Private event process identity");
        require((event->EventHeader.Flags&EVENT_HEADER_FLAG_STRING_ONLY)!=0 && event->UserData &&
            event->UserDataLength>=2 && event->UserDataLength<=1024 && event->UserDataLength%2==0,"Bounded UTF-16 string event required");
        const auto chars=event->UserDataLength/sizeof(wchar_t);const auto* text=static_cast<const wchar_t*>(event->UserData);
        require(text[chars-1]==0 && d.count<8192,"Terminated bounded provider payload");
        std::string payload;payload.reserve(chars);
        for(std::size_t n=0;n+1<chars;++n){require(text[n]>=32 && text[n]<=126,"Only original ASCII JSON payload accepted");payload.push_back(char(text[n]));}
        const auto row=std::string("{\"schema\":\"sl3.asio-etw-record.v1\",\"pid\":")+std::to_string(d.pid)+
            ",\"tid\":"+std::to_string(event->EventHeader.ThreadId)+",\"timestampFileTime\":\""+
            std::to_string(event->EventHeader.TimeStamp.QuadPart)+"\",\"payload\":"+payload+"}\n";
        d.output->write(row);++d.count;
    }catch(...){d.failed=true;}
}
static std::size_t decode(const fs::path& etl,const fs::path& output,DWORD pid){
    require(fs::file_size(etl)>0 && fs::file_size(etl)<=8*1024*1024,"Bounded complete private ETL required");
    File records(output);Decoded result{&records,pid};
    auto name=etl.native();EVENT_TRACE_LOGFILEW log{};log.LogFileName=name.data();
    log.ProcessTraceMode=PROCESS_TRACE_MODE_EVENT_RECORD;log.EventRecordCallback=receive;log.Context=&result;
    auto handle=OpenTraceW(&log);require(handle!=INVALID_PROCESSTRACE_HANDLE,"Open completed private ETL");
    const auto status=ProcessTrace(&handle,1,nullptr,nullptr);const auto closed=CloseTrace(handle);
    check(status,"Read private ETL");check(closed,"Close private ETL");
    require(!result.failed && log.EventsLost==0 && log.LogfileHeader.BuffersLost==0,"Complete provider decode without reported losses");
    return result.count;
}
int wmain(int argc,wchar_t** argv){
    try{
        if(argc==1 || (argc==2 && std::wstring(argv[1])==L"--plan")){
            std::cout<<"{\"schema\":\"sl3.asio-etl-decoder-plan.v1\",\"readOnlyInput\":true,\"traceControllerStarted\":false,\"deviceAccess\":false,\"seratoExecuted\":false}\n";return 0;
        }
        require(argc==5 && std::wstring(argv[1])==L"--decode","Explicit --decode COMPLETED_ETL NEW_JSONL EXPECTED_PID required");
        const std::wstring text(argv[4]);require(!text.empty() && text.size()<=10 && text.find_first_not_of(L"0123456789")==std::wstring::npos,"Decimal PID required");
        const auto pid=std::stoull(text);require(pid>0 && pid<=MAXDWORD,"Bounded nonzero PID");
        const auto input=fs::absolute(argv[2]),output=fs::absolute(argv[3]);
        require(input!=output && !fs::exists(output),"New independent output required");
        const auto attributes=GetFileAttributesW(input.c_str());
        require(attributes!=INVALID_FILE_ATTRIBUTES && !(attributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT)),"Regular ETL input required");
        struct Lease {HANDLE h=INVALID_HANDLE_VALUE;~Lease(){if(h!=INVALID_HANDLE_VALUE)CloseHandle(h);}} lease;
        lease.h=CreateFileW(input.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        require(lease.h!=INVALID_HANDLE_VALUE,"Lock completed input against writes/deletion");
        const auto events=decode(input,output,DWORD(pid));
        std::cout<<"{\"schema\":\"sl3.asio-etl-decode.v1\",\"pid\":"<<pid<<",\"decodedEvents\":"<<events<<",\"readerReportedLosses\":0,\"traceControllerStarted\":false,\"deviceAccess\":false,\"seratoExecuted\":false}\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
