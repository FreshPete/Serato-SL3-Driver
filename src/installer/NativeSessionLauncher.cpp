// Release-bound native launcher. No audio, USB, registration or firmware API.
#include <windows.h>
#include <shellapi.h>
#include <bcrypt.h>
#include <roapi.h>
#include <windows.data.json.h>
#include <wrl/client.h>
#include <wrl/wrappers/corewrappers.h>
#include <array>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>
#include "launcher_config.hpp"

namespace sl3::launcher {
namespace fs=std::filesystem;
struct WinError:std::runtime_error {
    DWORD code;
    explicit WinError(const char* text):std::runtime_error(text),code(GetLastError()){}
};
void require(bool value,const char* text){if(!value)throw std::runtime_error(text);}
void checked(HRESULT value,const char* text){if(FAILED(value))throw std::runtime_error(text);}
std::string utf8(const std::wstring& value){
    const auto count=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,value.data(),int(value.size()),nullptr,0,nullptr,nullptr);
    require(count>0,"Invalid UTF-16 launcher value");std::string result(std::size_t(count),'\0');
    require(WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,value.data(),int(value.size()),result.data(),count,nullptr,nullptr)==count,"Convert launcher value");return result;
}
std::wstring utf16(const std::string& value){
    const auto count=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,value.data(),int(value.size()),nullptr,0);
    require(count>0,"Invalid UTF-8 session capsule");std::wstring result(std::size_t(count),L'\0');
    require(MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,value.data(),int(value.size()),result.data(),count)==count,"Convert session capsule");return result;
}
class JsonObject {
    Microsoft::WRL::ComPtr<ABI::Windows::Data::Json::IJsonObject> value_;
    JsonObject()=default;
public:
    explicit JsonObject(const std::string& raw){
        Microsoft::WRL::ComPtr<ABI::Windows::Data::Json::IJsonObjectStatics> factory;
        Microsoft::WRL::Wrappers::HStringReference name(L"Windows.Data.Json.JsonObject");
        checked(RoGetActivationFactory(name.Get(),__uuidof(ABI::Windows::Data::Json::IJsonObjectStatics),
                reinterpret_cast<void**>(factory.GetAddressOf())),"Activate Windows JSON parser");
        const auto decoded=utf16(raw);Microsoft::WRL::Wrappers::HString input;
        checked(input.Set(decoded.c_str(),UINT32(decoded.size())),"Create JSON input string");
        checked(factory->Parse(input.Get(),value_.GetAddressOf()),"Parse selected session capsule");
    }
    std::wstring text(const wchar_t* field)const{
        Microsoft::WRL::Wrappers::HString name,result;
        checked(name.Set(field),"Create JSON property name");
        checked(value_->GetNamedString(name.Get(),result.GetAddressOf()),"Read required session string");
        UINT32 size=0;const auto raw=result.GetRawBuffer(&size);return std::wstring(raw,size);
    }
    JsonObject object(const wchar_t* field)const{
        Microsoft::WRL::Wrappers::HString name;checked(name.Set(field),"Create JSON property name");JsonObject result;
        checked(value_->GetNamedObject(name.Get(),result.value_.GetAddressOf()),"Read required session object");return result;
    }
};
struct Handle {
    HANDLE value=nullptr;
    explicit Handle(HANDLE handle=nullptr):value(handle){}
    Handle(const Handle&)=delete;Handle& operator=(const Handle&)=delete;
    Handle(Handle&& other)noexcept:value(std::exchange(other.value,nullptr)){}
    Handle& operator=(Handle&& other)noexcept{reset();value=std::exchange(other.value,nullptr);return *this;}
    ~Handle(){reset();}
    void reset()noexcept{if(value && value!=INVALID_HANDLE_VALUE)CloseHandle(value);value=nullptr;}
};
std::wstring environment(const wchar_t* name){
    const auto size=GetEnvironmentVariableW(name,nullptr,0);if(!size)return {};
    require(size<=32768,"Launcher environment exceeds bound");std::wstring value(size,L'\0');
    const auto copied=GetEnvironmentVariableW(name,value.data(),size);
    require(copied && copied<size,"Launcher environment changed");value.resize(copied);return value;
}
fs::path local_path(const std::wstring& text){
    fs::path value(text);const auto drive=value.root_name().native();
    require(value.is_absolute() && drive.size()==2 && drive[1]==L':' &&
            ((drive[0]>=L'A' && drive[0]<=L'Z') || (drive[0]>=L'a' && drive[0]<=L'z')),"Absolute local path required");
    require(text.find(L':',2)==std::wstring::npos,"Alternate path stream refused");
    for(wchar_t ch:text)require(ch>=32,"Control character in launcher path");
    for(const auto& part:value)require(part!=L"..","Parent traversal in launcher path");
    return value;
}
bool equal(const std::wstring& a,const std::wstring& b){
    return CompareStringOrdinal(a.c_str(),int(a.size()),b.c_str(),int(b.size()),TRUE)==CSTR_EQUAL;
}
fs::path child_path(const fs::path& root,const std::wstring& relative){
    const auto result=(root/fs::path(relative)).lexically_normal();
    auto prefix=root.lexically_normal().native();if(prefix.back()!=L'\\')prefix+=L'\\';
    const auto target=result.native();
    require(target.size()>prefix.size() && equal(target.substr(0,prefix.size()),prefix),"Release file escaped its root");return result;
}
std::wstring quote(const std::wstring& value){
    std::wstring result=L"\"";std::size_t slashes=0;
    for(wchar_t ch:value){
        if(ch==L'\\'){++slashes;continue;}
        result.append(ch==L'"'?slashes*2+1:slashes,L'\\');slashes=0;result+=ch;
    }
    result.append(slashes*2,L'\\');result+=L'"';return result;
}
std::wstring command_line(const std::vector<std::wstring>& values){
    std::wstring command;for(const auto& value:values){if(!command.empty())command+=L' ';command+=quote(value);}return command;
}
void crypto(NTSTATUS value){if(value<0)throw std::runtime_error("Native SHA-256 operation failed");}
std::wstring hash_file(HANDLE file){
    struct Algorithm {BCRYPT_ALG_HANDLE value=nullptr;~Algorithm(){if(value)BCryptCloseAlgorithmProvider(value,0);}} algorithm;
    struct Hash {BCRYPT_HASH_HANDLE value=nullptr;~Hash(){if(value)BCryptDestroyHash(value);}};
    crypto(BCryptOpenAlgorithmProvider(&algorithm.value,BCRYPT_SHA256_ALGORITHM,nullptr,0));
    DWORD length=0,copied=0;
    crypto(BCryptGetProperty(algorithm.value,BCRYPT_OBJECT_LENGTH,reinterpret_cast<PUCHAR>(&length),sizeof(length),&copied,0));
    require(length && length<=65536,"Native hash object bound");std::vector<UCHAR> object(length);Hash hash;
    crypto(BCryptCreateHash(algorithm.value,&hash.value,object.data(),length,nullptr,0,0));
    std::array<UCHAR,65536> buffer{};DWORD count=0;
    while(true){
        if(!ReadFile(file,buffer.data(),DWORD(buffer.size()),&count,nullptr))throw WinError("Read pinned launcher file");
        if(!count)break;crypto(BCryptHashData(hash.value,buffer.data(),count,0));
    }
    std::array<UCHAR,32> digest{};crypto(BCryptFinishHash(hash.value,digest.data(),DWORD(digest.size()),0));
    std::wstring result;const wchar_t* hex=L"0123456789abcdef";
    for(auto value:digest){result+=hex[value>>4];result+=hex[value&15];}
    LARGE_INTEGER zero{};if(!SetFilePointerEx(file,zero,nullptr,FILE_BEGIN))throw WinError("Reset pinned launcher file");return result;
}
HANDLE pin(std::vector<Handle>& leases,const fs::path& path,const std::wstring& expected,LONGLONG maximum=256ll*1024*1024){
    require(expected.size()==64,"Expected SHA-256 binding");
    for(auto ch:expected)require((ch>=L'0' && ch<=L'9') || (ch>=L'a' && ch<=L'f'),"Expected lowercase SHA-256 binding");
    Handle file(CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_FLAG_SEQUENTIAL_SCAN,nullptr));
    if(file.value==INVALID_HANDLE_VALUE)throw WinError("Open pinned launcher file");
    LARGE_INTEGER size{};if(!GetFileSizeEx(file.value,&size))throw WinError("Size pinned launcher file");
    require(size.QuadPart>=0 && size.QuadPart<=maximum,"Pinned launcher file exceeds bound");
    if(hash_file(file.value)!=expected)throw std::runtime_error("Reviewed launcher input differs: "+utf8(path.filename().native()));
    const auto handle=file.value;leases.push_back(std::move(file));return handle;
}
std::string read_capsule(HANDLE file){
    std::string text(65537,'\0');DWORD count=0;
    if(!ReadFile(file,text.data(),DWORD(text.size()),&count,nullptr))throw WinError("Read selected session capsule");
    require(count && count<=65536,"Session capsule exceeds bound");text.resize(count);return text;
}
void drain(HANDLE pipe,std::string& text,DWORD& failure)noexcept{
    std::array<char,8192> buffer{};DWORD count=0;failure=ERROR_SUCCESS;
    while(true){
        if(!ReadFile(pipe,buffer.data(),DWORD(buffer.size()),&count,nullptr)){
            const auto error=GetLastError();if(error!=ERROR_BROKEN_PIPE)failure=error;return;
        }
        if(!count)return;
        if(text.size()+count<=4*1024*1024){try{text.append(buffer.data(),count);}catch(...){failure=ERROR_NOT_ENOUGH_MEMORY;}}
        else failure=ERROR_BUFFER_OVERFLOW; // Keep draining so the child cannot block on its log.
    }
}
struct Pipe {Handle read,write;Pipe(){
    SECURITY_ATTRIBUTES security{sizeof(security),nullptr,TRUE};HANDLE a=nullptr,b=nullptr;
    if(!CreatePipe(&a,&b,&security,0))throw WinError("Create helper output pipe");read=Handle(a);write=Handle(b);
    if(!SetHandleInformation(read.value,HANDLE_FLAG_INHERIT,0))throw WinError("Constrain helper pipe inheritance");
}};
int run_process(const fs::path& executable,const std::vector<std::wstring>& arguments,const fs::path& working_directory,bool elevated){
    const auto parameters=command_line(arguments);const auto directory=working_directory.native();
    if(elevated){
        SHELLEXECUTEINFOW info{};info.cbSize=sizeof(info);info.fMask=SEE_MASK_NOCLOSEPROCESS|SEE_MASK_NOASYNC;
        info.lpVerb=L"runas";info.lpFile=executable.c_str();info.lpParameters=parameters.c_str();info.lpDirectory=directory.c_str();info.nShow=SW_HIDE;
        if(!ShellExecuteExW(&info))throw WinError("Start approved elevated installer");Handle child(info.hProcess);
        require(child.value!=nullptr,"Elevated installer process handle missing");
        // Never terminate a privileged transaction with an unknown commit outcome.
        require(WaitForSingleObject(child.value,INFINITE)==WAIT_OBJECT_0,"Wait elevated installer");
        DWORD code=1;if(!GetExitCodeProcess(child.value,&code))throw WinError("Read installer exit code");return int(code);
    }
    Pipe output,error;SECURITY_ATTRIBUTES security{sizeof(security),nullptr,TRUE};
    Handle input(CreateFileW(L"NUL",GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,&security,OPEN_EXISTING,0,nullptr));
    if(input.value==INVALID_HANDLE_VALUE)throw WinError("Create helper null input");
    STARTUPINFOEXW startup{};startup.StartupInfo.cb=sizeof(startup);startup.StartupInfo.dwFlags=STARTF_USESTDHANDLES|STARTF_USESHOWWINDOW;
    startup.StartupInfo.wShowWindow=SW_HIDE;startup.StartupInfo.hStdInput=input.value;
    startup.StartupInfo.hStdOutput=output.write.value;startup.StartupInfo.hStdError=error.write.value;
    SIZE_T size=0;InitializeProcThreadAttributeList(nullptr,1,0,&size);std::vector<BYTE> attributes(size);
    startup.lpAttributeList=reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(attributes.data());
    if(!InitializeProcThreadAttributeList(startup.lpAttributeList,1,0,&size))throw WinError("Create helper inheritance policy");
    struct Attributes {LPPROC_THREAD_ATTRIBUTE_LIST value;~Attributes(){DeleteProcThreadAttributeList(value);}} guard{startup.lpAttributeList};
    std::array<HANDLE,3> allowed={input.value,output.write.value,error.write.value};
    if(!UpdateProcThreadAttribute(startup.lpAttributeList,0,PROC_THREAD_ATTRIBUTE_HANDLE_LIST,allowed.data(),sizeof(allowed),nullptr,nullptr))
        throw WinError("Set exact helper handle inheritance");
    std::string out,err;DWORD output_error=0,error_error=0;
    std::thread first,second;
    try{first=std::thread([&]{drain(output.read.value,out,output_error);});second=std::thread([&]{drain(error.read.value,err,error_error);});}
    catch(...){output.write.reset();error.write.reset();if(first.joinable())first.join();throw;}
    auto command=quote(executable.native())+L" "+parameters;PROCESS_INFORMATION process{};
    if(!CreateProcessW(executable.c_str(),command.data(),nullptr,nullptr,TRUE,CREATE_NO_WINDOW|EXTENDED_STARTUPINFO_PRESENT,nullptr,directory.c_str(),&startup.StartupInfo,&process)){
        const auto failure=GetLastError();output.write.reset();error.write.reset();first.join();second.join();SetLastError(failure);
        throw WinError("Start verified ordinary helper");
    }
    Handle child(process.hProcess),thread(process.hThread);output.write.reset();error.write.reset();input.reset();
    const auto waited=WaitForSingleObject(child.value,INFINITE);first.join();second.join();
    std::cout<<out;std::cerr<<err;
    require(waited==WAIT_OBJECT_0 && !output_error && !error_error,"Helper wait/output failed; preserve session receipts");
    DWORD code=1;if(!GetExitCodeProcess(child.value,&code))throw WinError("Read helper exit code");return int(code);
}
int run_helper(const fs::path& python,const fs::path& script,const fs::path& capsule,const std::wstring& capsule_hash,
               const std::wstring& action,bool elevated){
    return run_process(python,{L"-I",L"-B",script.native(),action,L"--capsule",capsule.native(),L"--expected-capsule-sha256",capsule_hash},
                       script.parent_path(),elevated);
}
int session_dispatch(wchar_t** argv){
    require(!release::powershell_pins.empty(),"This launcher has no reviewed PowerShell runtime binding");
    const bool plan=std::wstring(argv[1])==L"--plan-session";
    const auto selected=local_path(argv[3]);const std::wstring identity=argv[5];
    const auto powershell=local_path(argv[7]);
    require(powershell.native().find(L';')==std::wstring::npos,
            "PowerShell runtime directory cannot contain a semicolon; choose another location");
    std::vector<Handle> leases;
    const JsonObject record(read_capsule(pin(leases,selected,identity,65536)));
    require(record.text(L"schema")==L"sl3.serato-session-plan.v1","Expected complete session plan");
    const auto root=local_path(record.text(L"projectRoot"));
    // Pin the complete release code closure and both runtimes before starting
    // PowerShell. Its own verifier then checks the selected session data.
    for(const auto& item:release::source_pins)pin(leases,child_path(root,item.first),item.second);
    const auto interpreter=record.object(L"python");const auto python=local_path(interpreter.text(L"path"));
    require(interpreter.text(L"sha256")==release::python_sha,"Release interpreter differs");pin(leases,python,release::python_sha);
    for(const auto& item:release::runtime_pins)pin(leases,child_path(python.parent_path(),item.first),item.second);
    const auto application=record.object(L"application");
    require(application.text(L"sha256")==release::application_sha,"Release application differs");
    pin(leases,local_path(application.text(L"path")),release::application_sha);
    for(const auto& item:release::powershell_pins)pin(leases,child_path(powershell,item.first),item.second);
    const auto action=std::wstring(argv[1]);
    if(action==L"--check-recovery"){
        std::wstring runtime_identity;
        for(const auto& item:release::powershell_pins)if(item.first==L"runtime-manifest.json")runtime_identity=item.second;
        require(!runtime_identity.empty(),"Reviewed PowerShell manifest identity is unavailable");
        return run_process(python,{L"-I",L"-B",(root/L"scripts/inspect-serato-session-recovery.py").native(),L"--session-plan",
                           selected.native(),L"--expected-session-plan-sha256",identity,L"--powershell-directory",
                           powershell.native(),L"--expected-powershell-manifest-sha256",runtime_identity},root,false);
    }
    if(action==L"--status-session"){
        return run_process(python,{L"-I",L"-B",(root/L"scripts/inspect-serato-session-status.py").native(),L"--session-plan",
                           selected.native(),L"--expected-session-plan-sha256",identity,L"--powershell-directory",
                           powershell.native()},root,false);
    }
    if(action==L"--stop-session"){
        return run_process(python,{L"-I",L"-B",(root/L"scripts/serato-session-stop.py").native(),L"--session-plan",
                           selected.native(),L"--expected-session-plan-sha256",identity,L"--powershell-directory",
                           powershell.native(),L"--request"},root,false);
    }
    if(action==L"--prepare-session" || action==L"--start-fresh-session"){
        std::wstring image(32768,L'\0');const auto copied=GetModuleFileNameW(nullptr,image.data(),DWORD(image.size()));
        require(copied && copied<image.size(),"Current launcher path unavailable");image.resize(copied);
        pin(leases,local_path(image),record.object(L"launcher").text(L"sha256"));
        std::vector<std::wstring> arguments={L"-I",L"-B",(root/L"scripts/prepare-fresh-serato-session.py").native(),
                L"--session-plan",selected.native(),L"--expected-session-plan-sha256",identity,
                L"--powershell-directory",powershell.native(),L"--prepare"};
        if(action==L"--start-fresh-session")arguments.push_back(L"--start");
        return run_process(python,arguments,root,false);
    }
    return run_process(powershell/L"pwsh.exe",{L"-NoLogo",L"-NoProfile",L"-NonInteractive",L"-File",
                       (root/L"scripts/serato-session.ps1").native(),L"-Mode",plan?L"Plan":L"Run",
                       L"-SessionPlan",selected.native(),L"-ExpectedPlanSha256",identity},root,false);
}
int kit_dispatch(wchar_t** argv){
    require(!release::powershell_pins.empty(),"This launcher has no reviewed kit runtime binding");
    const auto manifest=local_path(argv[3]);const std::wstring identity=argv[5];
    const auto application=local_path(argv[7]);const auto root=manifest.parent_path();
    require(manifest.filename()==L"kit-manifest.json","Expected kit manifest filename");
    require(root.native().find(L';')==std::wstring::npos,"Kit directory cannot contain a semicolon; choose another location");
    std::vector<Handle> leases;
    const JsonObject record(read_capsule(pin(leases,manifest,identity,65536)));
    require(record.text(L"schema")==L"sl3.portable-serato-kit.v1","Unsupported kit manifest");
    pin(leases,root/L"kit-inventory.json",record.text(L"inventorySha256"),1024*1024);
    for(const auto& item:release::source_pins)pin(leases,child_path(root,item.first),item.second);
    const auto python=root/L"runtime/python/python.exe";pin(leases,python,release::python_sha);
    for(const auto& item:release::runtime_pins)pin(leases,child_path(python.parent_path(),item.first),item.second);
    const auto powershell=root/L"runtime/powershell";
    for(const auto& item:release::powershell_pins)pin(leases,child_path(powershell,item.first),item.second);
    std::wstring image(32768,L'\0');const auto copied=GetModuleFileNameW(nullptr,image.data(),DWORD(image.size()));
    require(copied && copied<image.size(),"Current launcher path unavailable");image.resize(copied);
    pin(leases,local_path(image),record.text(L"launcherSha256"));
    pin(leases,root/L"SL3_Rebuild_Development_x64.exe",record.text(L"launcherSha256"));
    pin(leases,application,release::application_sha);
    std::vector<std::wstring> arguments={L"-I",L"-B",(root/L"scripts/prepare-portable-serato-kit.py").native(),
            L"--kit-manifest",manifest.native(),L"--expected-kit-manifest-sha256",identity,L"--app",application.native()};
    const auto action=std::wstring(argv[1]);
    if(action==L"--check-kit")arguments.push_back(L"--check");
    if(action==L"--prepare-kit" || action==L"--start-kit")arguments.push_back(L"--prepare");
    if(action==L"--start-kit")arguments.push_back(L"--start");
    return run_process(python,arguments,root,false);
}
int dispatch(int argc,wchar_t** argv){
    if(argc==8 && (std::wstring(argv[1])==L"--plan-kit" || std::wstring(argv[1])==L"--check-kit" || std::wstring(argv[1])==L"--prepare-kit" ||
       std::wstring(argv[1])==L"--start-kit") && std::wstring(argv[2])==L"--kit-manifest" &&
       std::wstring(argv[4])==L"--expected-kit-manifest-sha256" && std::wstring(argv[6])==L"--app")return kit_dispatch(argv);
    if(argc==8 && (std::wstring(argv[1])==L"--plan-session" || std::wstring(argv[1])==L"--start-session" ||
       std::wstring(argv[1])==L"--prepare-session" || std::wstring(argv[1])==L"--start-fresh-session" ||
       std::wstring(argv[1])==L"--stop-session" || std::wstring(argv[1])==L"--status-session" ||
       std::wstring(argv[1])==L"--check-recovery") &&
       std::wstring(argv[2])==L"--session-plan" && std::wstring(argv[4])==L"--expected-session-plan-sha256" &&
       std::wstring(argv[6])==L"--powershell-directory")return session_dispatch(argv);
    const bool plan=argc==6 && std::wstring(argv[1])==L"--plan" && std::wstring(argv[2])==L"--capsule" &&
                    std::wstring(argv[4])==L"--expected-capsule-sha256";
    if(!plan && argc!=1)return 2;
    const auto capsule=local_path(plan?argv[3]:environment(L"SL3_SESSION_CAPSULE"));
    const std::wstring capsule_hash=plan?argv[5]:environment(L"SL3_SESSION_CAPSULE_SHA256");
    require(capsule.filename()==L"session-capsule.json","Expected session capsule filename");
    std::vector<Handle> leases;
    const auto file=pin(leases,capsule,capsule_hash,65536);
    const JsonObject record(read_capsule(file));
    require(record.text(L"schema")==L"sl3.session-capsule.v1","Unsupported session capsule");
    const auto root=local_path(record.text(L"projectRoot"));
    require(equal(record.text(L"sessionDirectory"),capsule.parent_path().native()),"Session capsule directory differs");
    for(const auto& item:release::source_pins)pin(leases,child_path(root,item.first),item.second);
    const auto interpreter=record.object(L"python");const auto python=local_path(interpreter.text(L"path"));
    require(interpreter.text(L"sha256")==release::python_sha,"Release interpreter differs");pin(leases,python,release::python_sha);
    for(const auto& item:release::runtime_pins)pin(leases,child_path(python.parent_path(),item.first),item.second);
    const auto application=record.object(L"application");
    require(application.text(L"sha256")==release::application_sha,"Release application differs");
    pin(leases,local_path(application.text(L"path")),release::application_sha);
    const auto installer=root/L"scripts/serato-session-installer.py";
    const auto installed=run_helper(python,installer,capsule,capsule_hash,plan?L"plan":L"install",!plan);
    if(plan || installed)return installed;
    return run_helper(python,root/L"scripts/serato-session-broker.py",capsule,capsule_hash,L"start",false);
}
}

#ifndef SL3_LAUNCHER_ARGUMENT_TEST
int wmain(int argc,wchar_t** argv){
    try{sl3::launcher::checked(RoInitialize(RO_INIT_SINGLETHREADED),"Initialize Windows JSON runtime");
        struct Apartment{~Apartment(){RoUninitialize();}} apartment;return sl3::launcher::dispatch(argc,argv);}
    catch(const sl3::launcher::WinError& error){std::cerr<<error.what()<<": "<<error.code<<'\n';return error.code==ERROR_CANCELLED?ERROR_CANCELLED:1;}
    catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
#endif
