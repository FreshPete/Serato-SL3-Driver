#include <windows.h>
#include <evntrace.h>
#include <evntcons.h>
#include <tdh.h>
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>

namespace {
constexpr GUID hub{0xac52ad17,0xcc01,0x4f85,{0x8d,0xf5,0x4d,0xce,0x43,0x33,0xc9,0x9b}};
void require(bool ok,const char* text){if(!ok)throw std::runtime_error(text);}
bool local(const std::filesystem::path& path){
    const auto text=path.wstring();
    return path.is_absolute() && text.rfind(L"\\\\",0)!=0 && text.find_first_of(L"\"\r\n")==std::wstring::npos &&
        GetDriveTypeW(path.root_path().c_str())==DRIVE_FIXED;
}
struct File {
    HANDLE value=INVALID_HANDLE_VALUE;
    ~File(){if(value && value!=INVALID_HANDLE_VALUE)CloseHandle(value);}
    void write(const std::string& text){
        require(text.size()<=65536,"Oversized observation record");DWORD bytes{};
        require(WriteFile(value,text.data(),static_cast<DWORD>(text.size()),&bytes,nullptr) && bytes==text.size(),"Write observation record");
    }
};
struct Observer {
    File file;std::atomic<TRACEHANDLE> handle{INVALID_PROCESSTRACE_HANDLE};
    std::atomic<ULONG> close_status{ERROR_SUCCESS};std::atomic<bool> deadline{false};
    std::uint64_t seen{},states{};ULONG lost{},buffers_lost{};std::string error;
    void close(){
        const auto owned=handle.exchange(INVALID_PROCESSTRACE_HANDLE);
        if(owned!=INVALID_PROCESSTRACE_HANDLE)close_status=CloseTrace(owned);
    }
    ~Observer(){close();}
    std::uint64_t property(PEVENT_RECORD event,const wchar_t* name,ULONG expected){
        PROPERTY_DATA_DESCRIPTOR descriptor{};descriptor.PropertyName=reinterpret_cast<ULONGLONG>(name);descriptor.ArrayIndex=ULONG_MAX;
        ULONG size{};require(TdhGetPropertySize(event,0,nullptr,1,&descriptor,&size)==ERROR_SUCCESS && size==expected,"State property missing or wrong width");
        std::uint64_t value{};require(TdhGetProperty(event,0,nullptr,1,&descriptor,size,reinterpret_cast<PBYTE>(&value))==ERROR_SUCCESS,"Read state property");return value;
    }
    static void WINAPI event(PEVENT_RECORD event){
        auto& self=*static_cast<Observer*>(event->UserContext);
        if(!self.error.empty())return;
        try{
            require(++self.seen<=2000000,"Event count exceeds bound");
            if(!IsEqualGUID(event->EventHeader.ProviderId,hub) || (event->EventHeader.EventDescriptor.Id!=110 && event->EventHeader.EventDescriptor.Id!=111))return;
            require(++self.states<=50000,"State record count exceeds bound");
            require(event->EventHeader.TimeStamp.QuadPart>=0,"Negative normalized timestamp");
            const auto device=self.property(event,L"fid_UsbDevice",8),context=self.property(event,L"fid_Context",8);
            const auto index=self.property(event,L"fid_StartIndex",4),state=self.property(event,L"fid_State",4);
            const auto value=self.property(event,L"fid_Event",4),depth=self.property(event,L"fid_Depth",4);
            std::ostringstream text;text<<"{\"record\":\"state\",\"eventId\":"<<event->EventHeader.EventDescriptor.Id
                <<",\"task\":"<<event->EventHeader.EventDescriptor.Task<<",\"pid\":"<<event->EventHeader.ProcessId
                <<",\"timestampFileTime\":\""<<event->EventHeader.TimeStamp.QuadPart<<"\",\"device\":\""<<device
                <<"\",\"context\":\""<<context<<"\",\"startIndex\":"<<index<<",\"state\":"<<state<<",\"event\":"<<value<<",\"depth\":"<<depth<<"}\n";
            self.file.write(text.str());
        }catch(const std::exception& problem){self.error=problem.what();}
    }
    static ULONG WINAPI buffer(PEVENT_TRACE_LOGFILEW log){
        auto& self=*static_cast<Observer*>(log->Context);
        self.lost=std::max(self.lost,log->LogfileHeader.EventsLost);self.buffers_lost=std::max(self.buffers_lost,log->LogfileHeader.BuffersLost);
        return self.error.empty()?TRUE:FALSE;
    }
};
}

int wmain(int argc,wchar_t** argv){
    if(argc==1 || (argc==2 && std::wstring(argv[1])==L"--plan")){
        std::cout<<"{\"planOnly\":true,\"deviceAccess\":false,\"startsTraceSession\":false,\"stopsSourceSession\":false,\"selfElevates\":false,\"readinessAdmission\":false,\"liveConsumerImplemented\":true,\"liveConsumerPhysicallyValidated\":false}\n";return 0;
    }
    try{
        std::wstring etl,session;std::filesystem::path output;unsigned seconds{};
        require(argc==5 || argc==7,"Expected --etl FILE --output NEW_FILE or --session NAME --seconds N --output NEW_FILE");
        for(int at=1;at+1<argc;at+=2){
            const std::wstring key=argv[at],value=argv[at+1];
            if(key==L"--etl" && etl.empty())etl=value;
            else if(key==L"--session" && session.empty())session=value;
            else if(key==L"--output" && output.empty())output=value;
            else if(key==L"--seconds" && !seconds){
                require(!value.empty() && value.size()<=2 && value[0]!=L'0' && std::all_of(value.begin(),value.end(),[](wchar_t c){return c>=L'0' && c<=L'9';}),"Invalid bounded duration");
                seconds=static_cast<unsigned>(std::stoul(value));require(seconds<=60,"Duration exceeds limit");
            }else throw std::runtime_error("Duplicate or unknown option");
        }
        const bool live=!session.empty();
        require(local(output) && (live?etl.empty() && seconds>0:!etl.empty() && !seconds && local(etl)),"Local paths and exactly one input mode required");
        require(GetFileAttributesW(output.c_str())==INVALID_FILE_ATTRIBUTES,"Choose a new output file");
        if(live){
            require(session.size()==43 && session.substr(0,11)==L"SL3Startup-" &&
                    std::all_of(session.begin()+11,session.end(),[](wchar_t c){return (c>=L'0' && c<=L'9') || (c>=L'a' && c<=L'f');}),"Only an explicitly named SL3Startup session may be observed");
        }else{
            WIN32_FILE_ATTRIBUTE_DATA info{};require(GetFileAttributesExW(etl.c_str(),GetFileExInfoStandard,&info) &&
                !info.nFileSizeHigh && info.nFileSizeLow>0 && info.nFileSizeLow<=64*1024*1024,"Expected bounded local ETL file");
        }
        File token;TOKEN_ELEVATION elevation{};TOKEN_ELEVATION_TYPE elevation_type{};DWORD token_bytes{};
        require(OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token.value) &&
            GetTokenInformation(token.value,TokenElevation,&elevation,sizeof(elevation),&token_bytes) &&
            GetTokenInformation(token.value,TokenElevationType,&elevation_type,sizeof(elevation_type),&token_bytes),"Query observer token");
        Observer observer;EVENT_TRACE_LOGFILEW log{};
        if(live)log.LoggerName=session.data();else log.LogFileName=etl.data();
        log.ProcessTraceMode=PROCESS_TRACE_MODE_EVENT_RECORD|(live?PROCESS_TRACE_MODE_REAL_TIME:0);
        log.EventRecordCallback=Observer::event;log.BufferCallback=Observer::buffer;log.Context=&observer;
        const auto opened=OpenTraceW(&log);require(opened!=INVALID_PROCESSTRACE_HANDLE,"Open owned trace consumer");observer.handle=opened;
        observer.lost=log.LogfileHeader.EventsLost;observer.buffers_lost=log.LogfileHeader.BuffersLost;
        observer.file.value=CreateFileW(output.c_str(),GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
        require(observer.file.value!=INVALID_HANDLE_VALUE,"Create new observation file");
        std::ostringstream header;header<<"{\"record\":\"header\",\"schema\":\"sl3.usb-state-observer.v1\",\"mode\":\""<<(live?"session":"etl")
            <<"\",\"deviceAccess\":false,\"startsTraceSession\":false,\"stopsSourceSession\":false,\"readinessAdmission\":false,\"sourceImageEvidenceRequired\":true,\"opaqueValuesAsStrings\":true"
            <<",\"sourceSession\":";
        if(live){header<<'"';for(auto letter:session)header<<static_cast<char>(letter);header<<'"';}else header<<"null";
        header<<",\"requestedSeconds\":"<<seconds<<",\"pid\":"<<GetCurrentProcessId()<<",\"tokenQueried\":true,\"elevated\":"<<(elevation.TokenIsElevated?"true":"false")
            <<",\"elevationType\":"<<elevation_type<<"}\n";observer.file.write(header.str());
        File done;done.value=CreateEventW(nullptr,TRUE,FALSE,nullptr);require(done.value!=nullptr,"Create observer completion event");
        std::thread timer;
        if(live)timer=std::thread([&]{if(WaitForSingleObject(done.value,seconds*1000)==WAIT_TIMEOUT){observer.deadline=true;observer.close();}});
        auto process_handle=opened;const auto status=ProcessTrace(&process_handle,1,nullptr,nullptr);
        SetEvent(done.value);if(timer.joinable())timer.join();observer.close();
        const auto close=observer.close_status.load();
        const bool successful=observer.error.empty() && (status==ERROR_SUCCESS || (live && observer.deadline && status==ERROR_CANCELLED)) &&
            (close==ERROR_SUCCESS || close==ERROR_CTX_CLOSE_PENDING) && !observer.lost && !observer.buffers_lost;
        std::ostringstream summary;summary<<"{\"record\":\"summary\",\"successful\":"<<(successful?"true":"false")<<",\"eventsSeen\":"<<observer.seen
            <<",\"stateRecords\":"<<observer.states<<",\"eventsLost\":"<<observer.lost<<",\"buffersLost\":"<<observer.buffers_lost
            <<",\"processTraceStatus\":"<<status<<",\"closeTraceStatus\":"<<close<<",\"deadlineExpired\":"<<(observer.deadline?"true":"false")
            <<",\"propertyFailure\":"<<(!observer.error.empty()?"true":"false")<<",\"sourceLossCountersComplete\":"<<(live?"false":"true")
            <<",\"lossScope\":\""<<(live?"header snapshot only":"completed source-file header")<<"\",\"readinessAdmission\":false}\n";
        observer.file.write(summary.str());require(FlushFileBuffers(observer.file.value),"Flush observations");
        if(!observer.error.empty())std::cerr<<observer.error<<'\n';return successful?0:1;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
