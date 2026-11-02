#include "asio/call_trace.hpp"
#include "asio/com_identity.hpp"
#include "iasiodrv.h"
#include <evntrace.h>
#include <evntcons.h>
#include <array>
#include <cstddef>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <fstream>
#include <iterator>
#include <memory>
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
struct Properties {EVENT_TRACE_PROPERTIES p{};wchar_t name[128]{};wchar_t path[32768]{};};
class Session {
    TRACEHANDLE handle_=0;bool stopped_=false;
public:
    std::unique_ptr<Properties> properties=std::make_unique<Properties>();
    Session(const fs::path& file){
        const auto name=L"SL3-ASIO-private-"+std::to_wstring(GetCurrentProcessId());
        require(name.size()<128 && file.native().size()<32768,"Bounded session paths");
        auto& s=*properties;s.p.Wnode.BufferSize=sizeof(Properties);s.p.Wnode.Guid=t::provider_id;
        s.p.Wnode.ClientContext=1;s.p.Wnode.Flags=WNODE_FLAG_TRACED_GUID;
        s.p.BufferSize=16;s.p.MinimumBuffers=2;s.p.MaximumBuffers=4;s.p.MaximumFileSize=4;
        s.p.LogFileMode=EVENT_TRACE_FILE_MODE_SEQUENTIAL|EVENT_TRACE_PRIVATE_LOGGER_MODE|EVENT_TRACE_PRIVATE_IN_PROC|EVENT_TRACE_NO_PER_PROCESSOR_BUFFERING;
        s.p.LoggerNameOffset=offsetof(Properties,name);s.p.LogFileNameOffset=offsetof(Properties,path);
        std::wmemcpy(s.name,name.c_str(),name.size()+1);std::wmemcpy(s.path,file.c_str(),file.native().size()+1);
        check(StartTraceW(&handle_,s.name,&s.p),"Start own private in-process session");
    }
    ~Session(){if(handle_ && !stopped_){stopped_=true;(void)ControlTraceW(handle_,properties->name,&properties->p,EVENT_TRACE_CONTROL_STOP);}}
    void enable(){check(EnableTraceEx2(handle_,&t::provider_id,EVENT_CONTROL_CODE_ENABLE_PROVIDER,4,1,0,0,nullptr),"Enable own provider");}
    void stop(){stopped_=true;check(ControlTraceW(handle_,properties->name,&properties->p,EVENT_TRACE_CONTROL_STOP),"Stop own session");}
};
struct Module {
    HMODULE h=nullptr;
    explicit Module(const fs::path& p){h=LoadLibraryExW(p.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);require(h!=nullptr,"Load isolated own DLL");}
    ~Module(){if(h)FreeLibrary(h);}
    void unload(){require(h && FreeLibrary(h),"Unload own DLL");h=nullptr;}
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
    require(!result.failed && result.count>0 && log.EventsLost==0 && log.LogfileHeader.BuffersLost==0,"Complete provider decode without reported losses");
    return result.count;
}
static void probe(const fs::path& dll){
    require(dll.filename()==L"sl3_asio.dll" && fs::is_regular_file(dll) && !fs::exists(dll.parent_path()/L"sl3-asio.conf"),"Isolated production DLL without configuration required");
    std::size_t files=0;for(const auto& entry:fs::directory_iterator(dll.parent_path())){require(entry.path()==dll,"Only copied DLL may exist beside it");++files;}
    require(files==1,"Exactly one isolated DLL required");
    Module library(dll);
    using Get=HRESULT(__stdcall*)(REFCLSID,REFIID,void**);using Unload=HRESULT(__stdcall*)();
    const auto get=reinterpret_cast<Get>(GetProcAddress(library.h,"DllGetClassObject"));
    const auto unload=reinterpret_cast<Unload>(GetProcAddress(library.h,"DllCanUnloadNow"));
    require(get && unload && !GetProcAddress(library.h,"sl3_test_configure"),"Production-only COM DLL required");
    IClassFactory* factory=nullptr;check(ULONG(get(sl3::asio::driver_clsid,IID_IClassFactory,reinterpret_cast<void**>(&factory))),"Own class factory");
    IASIO* device=nullptr;const auto created=factory->CreateInstance(nullptr,sl3::asio::driver_clsid,reinterpret_cast<void**>(&device));factory->Release();
    require(created==S_OK && device,"Own ASIO instance");
    try{
        char name[32]{};device->getDriverName(name);require(std::strcmp(name,"SL3 Rebuild Development")==0,"Exact driver identity");
        require(device->getDriverVersion()==1 && device->init(nullptr)==ASIOFalse,"Honest unavailable driver; no configuration/worker");
        long in=73,out=74;require(device->getChannels(&in,&out)==ASE_NotPresent && in==73 && out==74,"Unavailable channels preserve caller outputs");
        long a=1,b=2,c=3,d=4;require(device->getBufferSize(&a,&b,&c,&d)==ASE_NotPresent && a==1 && b==2 && c==3 && d==4,"Unavailable bank metadata preserves outputs");
        ASIOSampleRate rate=123;require(device->getSampleRate(&rate)==ASE_NotPresent && rate==123,"Unavailable rate preserves output");
        char message[124]{};device->getErrorMessage(message);
    }catch(...){device->Release();throw;}
    require(device->Release()==0 && unload()==S_OK,"Full object/module retirement");
    library.unload();require(GetModuleHandleW(dll.c_str())==nullptr,"Own DLL mapping fully retired");
}
int wmain(int argc,wchar_t** argv){
    try{
        if(argc==1 || (argc==2 && std::wstring(argv[1])==L"--plan")){
            std::cout<<"{\"schema\":\"sl3.asio-private-trace-plan.v1\",\"defaultPlanOnly\":true,\"deviceAccess\":false,\"seratoExecuted\":false}\n";return 0;
        }
        const bool owned=argc==4 && std::wstring(argv[1])==L"--self-capture";
        const bool disabled=argc==4 && std::wstring(argv[1])==L"--self-disabled";
        const bool refused=argc==4 && std::wstring(argv[1])==L"--self-refused";
        require(argc==4 && (owned || disabled || refused || std::wstring(argv[1])==L"--capture"),"Explicit --capture or --self-capture NEW_DIRECTORY ISOLATED_DLL required");
        HANDLE token=nullptr;require(OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token)!=FALSE,"Read own token");TOKEN_ELEVATION elevation{};DWORD count=0;
        const bool queried=GetTokenInformation(token,TokenElevation,&elevation,sizeof(elevation),&count)!=FALSE;CloseHandle(token);
        require(queried && !elevation.TokenIsElevated,"Ordinary non-elevated fixture required");
        const auto directory=fs::absolute(argv[2]),dll=fs::absolute(argv[3]);require(!fs::exists(directory) && fs::create_directory(directory),"Fresh capture directory required");
        if(disabled || refused){
            const auto profile=directory/L"profile";
            if(disabled)require(fs::create_directory(profile),"Fresh disabled profile");
            require(SetEnvironmentVariableW(L"LOCALAPPDATA",profile.c_str()) &&
                SetEnvironmentVariableW(L"SL3_ASIO_PRIVATE_TRACE",refused?L"1":nullptr),"Own fallback environment");
            probe(dll);
            require(!fs::exists(profile/L"SL3Rebuild"),"Disabled/refused logger has no trace side effects");
            File result(directory/L"fallback.json");result.write("{\"schema\":\"sl3.asio-owned-fallback.v1\",\"ordinaryResultsPreserved\":true,\"dllUnloaded\":true,\"traceDirectoryCreated\":false,\"deviceAccess\":false,\"seratoExecuted\":false}\n");
            std::cout<<"Optional logger fallback preserved unavailable ASIO results\n";return 0;
        }
        const auto etl=directory/L"private.etl";ULONG lost=0,buffers_lost=0;
        if(owned){
            const auto profile=directory/L"profile";require(fs::create_directory(profile),"Fresh isolated profile");
            require(SetEnvironmentVariableW(L"LOCALAPPDATA",profile.c_str()) && SetEnvironmentVariableW(L"SL3_ASIO_PRIVATE_TRACE",L"1"),"Own process opt-in environment");
            probe(dll); // Factory released before device calls; final device release must stop logger.
            const auto traces=profile/L"SL3Rebuild"/L"AsioTraces";
            fs::path run;unsigned runs=0;for(const auto& entry:fs::directory_iterator(traces)){require(entry.is_directory(),"Only own run directory");run=entry.path();++runs;}
            require(runs==1,"Exactly one driver-owned session");
            std::ifstream marker(run/L"session.json",std::ios::binary);require(bool(marker),"Driver-owned stop marker required");
            const std::string text((std::istreambuf_iterator<char>(marker)),std::istreambuf_iterator<char>());
            const auto expected=std::string("{\"schema\":\"sl3.asio-owned-session.v1\",\"pid\":")+std::to_string(GetCurrentProcessId())+
                ",\"stopStatus\":0,\"eventsLost\":0,\"buffersLost\":0,\"complete\":true,\"hardwareStateAssessed\":false}\n";
            require(text==expected,"Driver-owned logger stopped without reported losses");
            File copy(directory/L"session.json");copy.write(text);
            unsigned found=0;for(const auto& entry:fs::directory_iterator(run))if(entry.path().filename().native().find(L"private.etl")==0){
                require(fs::copy_file(entry.path(),etl),"Preserve completed driver-owned ETL");++found;}
            require(found==1,"Exactly one driver-owned ETL");
        }else{
            require(SetEnvironmentVariableW(L"SL3_ASIO_PRIVATE_TRACE",nullptr)!=FALSE,"Disable own-DLL controller for external fixture");
            Session session(etl);session.enable();probe(dll);session.stop();lost=session.properties->p.EventsLost;buffers_lost=session.properties->p.LogBuffersLost;
            require(lost==0 && buffers_lost==0,"Private session reported loss");
        }
        fs::path actual;unsigned matches=0;
        for(const auto& entry:fs::directory_iterator(directory))if(entry.path().filename().native().find(L"private.etl")==0){actual=entry.path();++matches;}
        require(matches==1,"Exactly one private ETL (optional process suffix) required");
        const auto events=decode(actual,directory/L"events.jsonl",GetCurrentProcessId());
        File summary(directory/L"capture.json");summary.write(std::string("{\"schema\":\"sl3.asio-private-capture.v1\",\"pid\":")+std::to_string(GetCurrentProcessId())+
            ",\"decodedEvents\":"+std::to_string(events)+",\"eventsLost\":"+std::to_string(lost)+",\"buffersLost\":"+std::to_string(buffers_lost)+
            ",\"sessionStopped\":true,\"dllUnloaded\":true,\"ordinaryToken\":true,\"unavailableProductionDll\":true,\"deviceAccess\":false,\"seratoExecuted\":false}\n");
        std::cout<<"Private ETW capture decoded "<<events<<" real provider events; no device or Serato\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
