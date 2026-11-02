#pragma once
#include "asio/call_trace.hpp"
#include <evntrace.h>
#include <sddl.h>
#include <objbase.h>
#include <cstddef>
#include <filesystem>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

namespace sl3::asio::trace {
// Explicit per-process opt-in; no controller is created from DllMain or a
// callback. The caller's factory/device leases retire it before COM unload.
class PrivateSession {
    struct Properties {EVENT_TRACE_PROPERTIES p{};wchar_t name[128]{};wchar_t path[32768]{};};
    std::unique_ptr<Properties> properties_=std::make_unique<Properties>();
    TRACEHANDLE handle_=0;
    std::filesystem::path directory_;
    static void need(bool b){if(!b)throw std::runtime_error("Private ASIO trace unavailable");}
    static void plain(const std::filesystem::path& p){
        for(auto at=p;!at.empty();){
            const auto a=GetFileAttributesW(at.c_str());
            need(a!=INVALID_FILE_ATTRIBUTES && (a&FILE_ATTRIBUTE_DIRECTORY) && !(a&FILE_ATTRIBUTE_REPARSE_POINT));
            const auto next=at.parent_path();if(next==at)break;at=next;
        }
    }
    static void make_directory(const std::filesystem::path& p,SECURITY_ATTRIBUTES& sa,bool fresh){
        if(!CreateDirectoryW(p.c_str(),&sa))need(!fresh && GetLastError()==ERROR_ALREADY_EXISTS);
        plain(p);
    }
    void start(){
        struct Token {HANDLE value=nullptr;~Token(){if(value)CloseHandle(value);}} token;
        need(OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token.value)!=FALSE);
        TOKEN_ELEVATION elevation{};DWORD count=0;
        const bool ordinary=GetTokenInformation(token.value,TokenElevation,&elevation,sizeof(elevation),&count) && !elevation.TokenIsElevated;
        need(ordinary);GetTokenInformation(token.value,TokenUser,nullptr,0,&count);
        need(count && count<=65536);
        std::vector<unsigned char> bytes(count);
        need(GetTokenInformation(token.value,TokenUser,bytes.data(),count,&count)!=FALSE);
        struct Sid {LPWSTR value=nullptr;~Sid(){if(value)LocalFree(value);}} sid;
        need(ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(bytes.data())->User.Sid,&sid.value)!=FALSE);
        const std::wstring sddl=L"D:P(A;;FA;;;SY)(A;;FA;;;"+std::wstring(sid.value)+L")";
        PSECURITY_DESCRIPTOR descriptor=nullptr;need(ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl.c_str(),SDDL_REVISION_1,&descriptor,nullptr)!=FALSE);
        struct Descriptor {PSECURITY_DESCRIPTOR p;~Descriptor(){LocalFree(p);}} owned{descriptor};
        SECURITY_ATTRIBUTES sa{sizeof(sa),descriptor,FALSE};
        std::vector<wchar_t> env(32768);const auto n=GetEnvironmentVariableW(L"LOCALAPPDATA",env.data(),DWORD(env.size()));
        need(n>2 && n<env.size());const std::wstring path(env.data(),n);
        need(path[1]==L':' && path.find(L':',2)==std::wstring::npos && path[2]==L'\\');
        auto base=std::filesystem::path(path);need(GetDriveTypeW(base.root_path().c_str())==DRIVE_FIXED);plain(base);
        base/=L"SL3Rebuild";make_directory(base,sa,false);base/=L"AsioTraces";make_directory(base,sa,false);
        GUID id{};wchar_t text[40]{};need(SUCCEEDED(CoCreateGuid(&id)) && StringFromGUID2(id,text,40)>0);
        directory_=base/(L"run-"+std::to_wstring(GetCurrentProcessId())+L"-"+text);make_directory(directory_,sa,true);
        const auto file=(directory_/L"private.etl").native();const auto name=L"SL3-ASIO-owned-"+std::to_wstring(GetCurrentProcessId())+L"-"+text;
        need(file.size()<32768 && name.size()<128);
        auto& s=*properties_;s.p.Wnode.BufferSize=sizeof(Properties);s.p.Wnode.Guid=provider_id;
        s.p.Wnode.ClientContext=1;s.p.Wnode.Flags=WNODE_FLAG_TRACED_GUID;
        s.p.BufferSize=16;s.p.MinimumBuffers=2;s.p.MaximumBuffers=4;s.p.MaximumFileSize=4;s.p.FlushTimer=1;
        s.p.LogFileMode=EVENT_TRACE_FILE_MODE_SEQUENTIAL|EVENT_TRACE_PRIVATE_LOGGER_MODE|EVENT_TRACE_PRIVATE_IN_PROC|EVENT_TRACE_NO_PER_PROCESSOR_BUFFERING;
        s.p.LoggerNameOffset=offsetof(Properties,name);s.p.LogFileNameOffset=offsetof(Properties,path);
        std::wmemcpy(s.name,name.c_str(),name.size()+1);std::wmemcpy(s.path,file.c_str(),file.size()+1);
        TRACEHANDLE created=0;
        need(StartTraceW(&created,s.name,&s.p)==ERROR_SUCCESS);handle_=created;
        need(EnableTraceEx2(handle_,&provider_id,EVENT_CONTROL_CODE_ENABLE_PROVIDER,4,keyword,0,0,nullptr)==ERROR_SUCCESS);
    }
    void stop(bool report) noexcept {
        if(!handle_)return;
        const auto status=ControlTraceW(handle_,properties_->name,&properties_->p,EVENT_TRACE_CONTROL_STOP);handle_=0;
        if(!report || directory_.empty())return;
        try{
            char data[512]{};
            const auto n=_snprintf_s(data,sizeof(data),_TRUNCATE,
                "{\"schema\":\"sl3.asio-owned-session.v1\",\"pid\":%lu,\"stopStatus\":%lu,\"eventsLost\":%lu,\"buffersLost\":%lu,\"complete\":%s,\"hardwareStateAssessed\":false}\n",
                GetCurrentProcessId(),status,properties_->p.EventsLost,properties_->p.LogBuffersLost,status==ERROR_SUCCESS && properties_->p.EventsLost==0 && properties_->p.LogBuffersLost==0?"true":"false");
            if(n<=0)return;
            const auto file=directory_/L"session.json";
            const auto h=CreateFileW(file.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
            if(h!=INVALID_HANDLE_VALUE){DWORD written=0;(void)WriteFile(h,data,DWORD(n),&written,nullptr);CloseHandle(h);}
        }catch(...){}
    }
public:
    PrivateSession(){try{start();}catch(...){stop(false);throw;}}
    ~PrivateSession(){stop(true);}
    PrivateSession(const PrivateSession&)=delete;PrivateSession& operator=(const PrivateSession&)=delete;
};
inline std::shared_ptr<PrivateSession> acquire_private_session() noexcept {
    wchar_t flag[2]{};
    if(GetEnvironmentVariableW(L"SL3_ASIO_PRIVATE_TRACE",flag,2)!=1 || flag[0]!=L'1')return {};
    try{
        struct Manager {std::mutex mutex;std::weak_ptr<PrivateSession> active;unsigned attempts=0;};
        static Manager manager;
        std::lock_guard<std::mutex> guard(manager.mutex);
        if(auto current=manager.active.lock())return current;
        if(manager.attempts>=4 || next_call.load(std::memory_order_relaxed)>maximum_calls)return {};
        ++manager.attempts;
        auto session=std::make_shared<PrivateSession>();manager.active=session;return session;
    }catch(...){return {};}
}
}
