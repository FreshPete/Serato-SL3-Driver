#pragma once
// One-way diagnostic channel. No commands, impersonation or arbitrary file path.
#include <sddl.h>

namespace sl3::setup_result {
using namespace sl3::launcher;
inline std::wstring token(){
    GUID value{};checked(CoCreateGuid(&value),"Create setup result identity");std::array<wchar_t,40> text{};
    require(StringFromGUID2(value,text.data(),int(text.size()))>0,"Format setup result identity");std::wstring result;
    for(auto c:text){if(c>=L'0' && c<=L'9')result+=c;else if(c>=L'a' && c<=L'f')result+=c;else if(c>=L'A' && c<=L'F')result+=wchar_t(c-L'A'+L'a');}
    require(result.size()==32,"Canonical setup result identity");return result;
}
inline bool endpoint(const std::wstring& name){
    const std::wstring prefix=L"\\\\.\\pipe\\SL3SetupResult-";
    return name.size()==prefix.size()+32 && name.compare(0,prefix.size(),prefix)==0 &&
        std::all_of(name.begin()+prefix.size(),name.end(),[](wchar_t c){return (c>=L'0' && c<=L'9') || (c>=L'a' && c<=L'f');});
}
inline std::vector<BYTE> user(HANDLE process){
    Handle access;require(OpenProcessToken(process,TOKEN_QUERY,&access.value)!=FALSE,"Read result-channel identity");DWORD bytes=0;
    GetTokenInformation(access.value,TokenUser,nullptr,0,&bytes);require(bytes && bytes<=65536,"Bounded result-channel identity");
    std::vector<BYTE> result(bytes);require(GetTokenInformation(access.value,TokenUser,result.data(),bytes,&bytes)!=FALSE,"Read result-channel user");return result;
}
inline std::wstring own_sid(){
    auto identity=user(GetCurrentProcess());LPWSTR value=nullptr;
    require(ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(identity.data())->User.Sid,&value)!=FALSE,"Format result-channel user");
    std::wstring result=value;LocalFree(value);return result;
}
struct Capture {bool authenticated=false,over_limit=false;DWORD rejected=0,error=0;std::string bytes;};
class Server {
    Handle pipe_;
    struct Pending {
        HANDLE pipe;Handle event;OVERLAPPED operation{};bool pending=false;
        explicit Pending(HANDLE value):pipe(value),event(CreateEventW(nullptr,TRUE,FALSE,nullptr)){
            require(event.value!=nullptr,"Create result-channel wait event");operation.hEvent=event.value;
        }
        ~Pending(){if(pending){CancelIoEx(pipe,&operation);DWORD ignored=0;(void)GetOverlappedResult(pipe,&operation,&ignored,TRUE);}}
        DWORD finish(HANDLE process,DWORD& bytes){
            pending=true;std::array<HANDLE,2> handles={event.value,process};const auto ready=WaitForMultipleObjects(2,handles.data(),FALSE,INFINITE);
            if(ready==WAIT_OBJECT_0+1 && WaitForSingleObject(event.value,1000)!=WAIT_OBJECT_0)return ERROR_BROKEN_PIPE;
            if(ready!=WAIT_OBJECT_0 && ready!=WAIT_OBJECT_0+1)return GetLastError();
            if(!GetOverlappedResult(pipe,&operation,&bytes,FALSE))return GetLastError();pending=false;return ERROR_SUCCESS;
        }
    };
public:
    const std::wstring name=L"\\\\.\\pipe\\SL3SetupResult-"+token();
    HANDLE diagnostic_handle()const noexcept{return pipe_.value;}
    void close()noexcept{pipe_.reset();}
    Server(){
        const auto policy=L"D:P(A;;GA;;;SY)(A;;GA;;;"+own_sid()+L")";PSECURITY_DESCRIPTOR descriptor=nullptr;
        require(ConvertStringSecurityDescriptorToSecurityDescriptorW(policy.c_str(),SDDL_REVISION_1,&descriptor,nullptr)!=FALSE,"Create private result-channel policy");
        SECURITY_ATTRIBUTES attributes{sizeof(attributes),descriptor,FALSE};
        pipe_=Handle(CreateNamedPipeW(name.c_str(),PIPE_ACCESS_INBOUND|FILE_FLAG_OVERLAPPED|FILE_FLAG_FIRST_PIPE_INSTANCE,
            PIPE_TYPE_BYTE|PIPE_READMODE_BYTE|PIPE_WAIT|PIPE_REJECT_REMOTE_CLIENTS,1,65536,65536,0,&attributes));LocalFree(descriptor);
        require(pipe_.value!=INVALID_HANDLE_VALUE,"Create private result channel");
    }
    Capture collect(HANDLE process){
        Capture result;const auto expected=GetProcessId(process);require(expected!=0,"Exact launched result-writer process required");
        for(unsigned attempt=0;attempt<8;++attempt){
            Pending connection(pipe_.value);DWORD ignored=0;
            if(!ConnectNamedPipe(pipe_.value,&connection.operation)){
                const auto error=GetLastError();if(error==ERROR_IO_PENDING){result.error=connection.finish(process,ignored);if(result.error)return result;}
                else if(error!=ERROR_PIPE_CONNECTED){result.error=error;return result;}
            }
            ULONG writer=0;
            if(!GetNamedPipeClientProcessId(pipe_.value,&writer) || writer!=expected || WaitForSingleObject(process,0)!=WAIT_TIMEOUT){
                ++result.rejected;DisconnectNamedPipe(pipe_.value);if(WaitForSingleObject(process,0)==WAIT_OBJECT_0)return result;continue;
            }
            result.authenticated=true;constexpr std::size_t limit=512*1024;
            for(;;){
                std::array<char,8192> buffer{};DWORD count=0;Pending read(pipe_.value);
                if(!ReadFile(pipe_.value,buffer.data(),DWORD(buffer.size()),&count,&read.operation)){
                    const auto error=GetLastError();if(error==ERROR_IO_PENDING){result.error=read.finish(process,count);}
                    else result.error=error;
                    if(result.error==ERROR_BROKEN_PIPE){result.error=0;return result;}if(result.error)return result;
                }
                if(!count)return result;const auto retained=(std::min)(std::size_t(count),limit-result.bytes.size());
                result.bytes.append(buffer.data(),retained);if(retained<count)result.over_limit=true;
                // Keep draining even over budget so a completed privileged
                // transaction is never blocked by discarded diagnostic bytes.
            }
        }
        result.error=ERROR_ACCESS_DENIED;return result;
    }
};
class Client {
    Handle pipe_;HANDLE old_output_=nullptr,old_error_=nullptr;bool redirected_=false;
public:
    Client(const std::wstring& name,DWORD expected_server){
        require(endpoint(name) && expected_server,"Scoped result channel and server identity required");const auto began=GetTickCount64();
        for(;;){
            // Anonymous SQOS prevents the ordinary server from impersonating
            // this client, including when it is the elevated setup process.
            pipe_=Handle(CreateFileW(name.c_str(),GENERIC_WRITE,0,nullptr,OPEN_EXISTING,SECURITY_SQOS_PRESENT|SECURITY_ANONYMOUS,nullptr));
            if(pipe_.value!=INVALID_HANDLE_VALUE)break;const auto error=GetLastError();
            require((error==ERROR_PIPE_BUSY || error==ERROR_FILE_NOT_FOUND) && GetTickCount64()-began<5000,"Result channel is unavailable");WaitNamedPipeW(name.c_str(),50);Sleep(2);
        }
        ULONG server=0;require(GetNamedPipeServerProcessId(pipe_.value,&server)!=FALSE && server==expected_server,"Result server process differs");
        Handle process(OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,server));require(process.value!=nullptr,"Read result server process");
        auto own=user(GetCurrentProcess()),peer=user(process.value);DWORD own_session=0,peer_session=0;
        require(EqualSid(reinterpret_cast<TOKEN_USER*>(own.data())->User.Sid,reinterpret_cast<TOKEN_USER*>(peer.data())->User.Sid) &&
            ProcessIdToSessionId(GetCurrentProcessId(),&own_session) && ProcessIdToSessionId(server,&peer_session) && own_session==peer_session,"Result server user/session differs");
    }
    ~Client(){if(redirected_){SetStdHandle(STD_OUTPUT_HANDLE,old_output_);SetStdHandle(STD_ERROR_HANDLE,old_error_);}if(pipe_.value && pipe_.value!=INVALID_HANDLE_VALUE)(void)FlushFileBuffers(pipe_.value);}
    void redirect(){old_output_=GetStdHandle(STD_OUTPUT_HANDLE);old_error_=GetStdHandle(STD_ERROR_HANDLE);redirected_=true;
        require(SetStdHandle(STD_OUTPUT_HANDLE,pipe_.value) && SetStdHandle(STD_ERROR_HANDLE,pipe_.value),"Redirect fixed helper diagnostic output");}
    void write(const std::string& text){std::size_t offset=0;while(offset<text.size()){DWORD count=0;
        require(WriteFile(pipe_.value,text.data()+offset,DWORD((std::min)(text.size()-offset,std::size_t(65536))),&count,nullptr)!=FALSE && count,"Write result-channel diagnostics");offset+=count;}}
};
inline DWORD process_id(const std::wstring& text){
    require(!text.empty() && text.size()<=10 && text[0]!=L'0',"Canonical result server PID required");unsigned long long value=0;
    for(auto c:text){require(c>=L'0' && c<=L'9',"Decimal result server PID required");value=value*10+unsigned(c-L'0');}
    require(value && value<=MAXDWORD,"Bounded result server PID required");return DWORD(value);
}
}
