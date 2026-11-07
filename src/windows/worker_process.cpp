#include "windows/worker_process.hpp"
#include <bcrypt.h>
#include <algorithm>
#include <array>
#include <cctype>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace sl3::worker {
namespace {
struct Handle {
    HANDLE value=nullptr;
    Handle()=default;
    Handle(const Handle&)=delete;
    Handle& operator=(const Handle&)=delete;
    ~Handle(){reset();}
    void reset(HANDLE next=nullptr) noexcept {
        if(value && value!=INVALID_HANDLE_VALUE)CloseHandle(value);
        value=next;
    }
};
[[noreturn]] void failed(const char* operation){
    throw std::runtime_error(std::string(operation)+": Win32="+std::to_string(GetLastError()));
}
void valid_path(const std::filesystem::path& path){
    if(!path.is_absolute() || path.native().find(L'\0')!=std::wstring::npos)
        throw std::invalid_argument("Worker executable needs an absolute, NUL-free path");
}
void open_executable(Handle& handle,const std::filesystem::path& path){
    valid_path(path);
    // Keep the original bytes pinned against write/delete through process life.
    handle.reset(CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr));
    if(handle.value==INVALID_HANDLE_VALUE)failed("Open private worker executable");
    LARGE_INTEGER bytes{};
    if(!GetFileSizeEx(handle.value,&bytes))failed("Read worker size");
    if(bytes.QuadPart<=0 || bytes.QuadPart>256*1024*1024)throw std::invalid_argument("Unexpected worker executable size");
}
std::string hash_file(HANDLE file){
    struct Hash {
        BCRYPT_ALG_HANDLE algorithm{};BCRYPT_HASH_HANDLE hash{};
        std::vector<UCHAR> object;
        ~Hash(){if(hash)BCryptDestroyHash(hash);if(algorithm)BCryptCloseAlgorithmProvider(algorithm,0);}
    } state;
    auto check=[](NTSTATUS result){if(result<0)throw std::runtime_error("Worker SHA256 verification failed");};
    check(BCryptOpenAlgorithmProvider(&state.algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0));
    DWORD bytes=0,received=0;
    check(BCryptGetProperty(state.algorithm,BCRYPT_OBJECT_LENGTH,reinterpret_cast<PUCHAR>(&bytes),sizeof(bytes),&received,0));
    state.object.resize(bytes);
    check(BCryptCreateHash(state.algorithm,&state.hash,state.object.data(),bytes,nullptr,0,0));
    std::array<UCHAR,65536> block{};
    for(;;){
        DWORD count=0;
        if(!ReadFile(file,block.data(),DWORD(block.size()),&count,nullptr))failed("Hash worker executable");
        if(!count)break;
        check(BCryptHashData(state.hash,block.data(),count,0));
    }
    std::array<UCHAR,32> digest{};
    check(BCryptFinishHash(state.hash,digest.data(),ULONG(digest.size()),0));
    std::ostringstream out;out<<std::hex<<std::setfill('0');
    for(const auto byte:digest)out<<std::setw(2)<<unsigned(byte);
    return out.str();
}
std::wstring quoted(const std::wstring& text){
    if(text.find(L'\0')!=std::wstring::npos)throw std::invalid_argument("Worker arguments must be NUL-free");
    std::wstring out=L"\"";
    std::size_t slashes=0;
    for(const auto ch:text){
        if(ch==L'\\'){++slashes;continue;}
        if(ch==L'\"')out.append(slashes*2+1,L'\\');else out.append(slashes,L'\\');
        slashes=0;out+=ch;
    }
    out.append(slashes*2,L'\\');out+=L'\"';return out;
}
void valid_timeout(DWORD timeout){
    if(timeout>5000)throw std::invalid_argument("Control-thread waits must be bounded to at most five seconds");
}
struct LaunchErrorMode {
    DWORD previous=0;
    LaunchErrorMode(){
        const auto flags=GetThreadErrorMode()|SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX|SEM_NOOPENFILEERRORBOX;
        if(!SetThreadErrorMode(flags,&previous))failed("Suppress private-launch error dialogs on this control thread");
    }
    ~LaunchErrorMode(){SetThreadErrorMode(previous,nullptr);}
};
struct JobStartupInfo {
    STARTUPINFOEXW startup{};
    std::vector<unsigned char> storage;

    void bind(HANDLE& job){
        SIZE_T size=0;
        InitializeProcThreadAttributeList(nullptr,1,0,&size);
        if(!size)failed("Size controller startup attributes");
        storage.resize(size);
        const auto list=reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(storage.data());
        if(!InitializeProcThreadAttributeList(list,1,0,&size))failed("Initialize controller startup attributes");
        startup.lpAttributeList=list;
        startup.StartupInfo.cb=sizeof(startup);
        if(!UpdateProcThreadAttribute(list,0,PROC_THREAD_ATTRIBUTE_JOB_LIST,&job,sizeof(job),nullptr,nullptr))
            failed("Bind controller job at process creation");
    }

    ~JobStartupInfo(){if(startup.lpAttributeList)DeleteProcThreadAttributeList(startup.lpAttributeList);}
};
}
struct Process::State {
    Handle executable,job,process,thread;
    bool assigned=false;
    ~State(){
        // The job is never inherited. Owner jobs kill remaining child work
        // when closed. An application controller instead watches its bound host.
        // This requests OS teardown; destructor does not claim it has completed.
        if(process.value && !assigned)TerminateProcess(process.value,71);
        job.reset();
    }
};
Process::Process() noexcept=default;
Process::~Process()=default;
std::string Process::executable_sha256(const std::filesystem::path& path){
    Handle file;open_executable(file,path);return hash_file(file.value);
}
void Process::launch(const std::filesystem::path& path,const std::string& expected,const std::vector<std::wstring>& arguments,JobLifetime lifetime){
    if(state_)throw std::logic_error("A worker owner can launch only once; retain its existing process handle");
    if(expected.size()!=64 || !std::all_of(expected.begin(),expected.end(),[](unsigned char c){return std::isxdigit(c)!=0;}))
        throw std::invalid_argument("Expected worker SHA256 is required");
    auto identity=expected;
    for(auto& ch:identity)ch=char(std::tolower(static_cast<unsigned char>(ch)));
    valid_path(path);
    std::wstring command=quoted(path.native());
    for(const auto& arg:arguments){command+=L' ';command+=quoted(arg);}
    if(command.size()>=32767)throw std::invalid_argument("Worker command line exceeds the Windows limit");
    auto candidate=std::make_unique<State>();
    open_executable(candidate->executable,path);
    if(hash_file(candidate->executable.value)!=identity)throw std::runtime_error("Worker executable differs from the expected tested build");
    candidate->job.value=CreateJobObjectW(nullptr,nullptr);
    if(!candidate->job.value)failed("Create private worker job");
    const bool application_controller=lifetime==JobLifetime::application_controller;
    JobStartupInfo controller_startup;
    STARTUPINFOW worker_startup{};worker_startup.cb=sizeof(worker_startup);
    DWORD flags=CREATE_NO_WINDOW;
    if(application_controller){
        // This job survives host exit so the controller can retire its worker.
        // Assign at creation without leaving a suspended child to resume.
        controller_startup.bind(candidate->job.value);
        flags|=EXTENDED_STARTUPINFO_PRESENT;
    }else{
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
        limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if(!SetInformationJobObject(candidate->job.value,JobObjectExtendedLimitInformation,&limits,sizeof(limits)))failed("Configure private worker job");
        flags|=CREATE_SUSPENDED;
    }
    PROCESS_INFORMATION child{};
    BOOL created=FALSE;DWORD creation_error=0;
    {
        LaunchErrorMode error_mode;
        created=CreateProcessW(path.c_str(),command.data(),nullptr,nullptr,FALSE,flags,nullptr,path.parent_path().c_str(),
                               application_controller?&controller_startup.startup.StartupInfo:&worker_startup,&child);
        creation_error=GetLastError();
    }
    if(!created){SetLastError(creation_error);failed("Create private worker suspended");}
    candidate->process.value=child.hProcess;candidate->thread.value=child.hThread;
    if(!application_controller && !AssignProcessToJobObject(candidate->job.value,candidate->process.value)){
        const auto error=GetLastError();
        // Retain the exact handle even on assignment failure. The child has
        // executed no code; terminate only this owned suspended process.
        state_=std::move(candidate);
        const auto stopped=terminate_and_wait(2000);
        throw std::runtime_error("Assign suspended worker failed: Win32="+std::to_string(error)+
            "; process exit confirmed="+std::to_string(stopped.state.process_exited));
    }
    candidate->assigned=true;state_=std::move(candidate);
    if(!application_controller && ResumeThread(state_->thread.value)==DWORD(-1))
        failed("Resume assigned worker; owned handle retained");
    state_->thread.reset();
}
ProcessState Process::observe() const {
    ProcessState result;
    if(!state_)return result;
    result.started=true;
    result.job_assigned=state_->assigned;
    const auto wait=WaitForSingleObject(state_->process.value,0);
    if(wait==WAIT_FAILED)failed("Observe worker process");
    result.process_exited=wait==WAIT_OBJECT_0;
    if(result.process_exited){
        if(!GetExitCodeProcess(state_->process.value,&result.exit_code))failed("Read worker exit code");
        // Exit 259 is legal; signalled process state, not STILL_ACTIVE, decides.
        result.exit_code_known=true;
    }
    JOBOBJECT_BASIC_ACCOUNTING_INFORMATION accounting{};
    if(!QueryInformationJobObject(state_->job.value,JobObjectBasicAccountingInformation,&accounting,sizeof(accounting),nullptr))failed("Observe worker job");
    result.associated_processes=accounting.ActiveProcesses;
    result.job_empty=accounting.ActiveProcesses==0;
    return result;
}
bool Process::wait_for_exit(DWORD timeout) const {
    valid_timeout(timeout);
    if(!state_)throw std::logic_error("No worker process exists");
    const auto wait=WaitForSingleObject(state_->process.value,timeout);
    if(wait==WAIT_FAILED)failed("Wait for worker process");
    return wait==WAIT_OBJECT_0;
}
StopResult Process::terminate_and_wait(DWORD timeout){
    valid_timeout(timeout);
    StopResult result;result.state=observe();
    if(!result.state.started || (result.state.process_exited && result.state.job_empty))return result;
    if(state_->assigned){
        if(!TerminateJobObject(state_->job.value,72))failed("Terminate owned worker job");
    }else if(!result.state.process_exited && !TerminateProcess(state_->process.value,71)){
        failed("Terminate owned unassigned suspended worker");
    }
    result.termination_requested=true;
    const auto started=GetTickCount64();
    do {
        result.state=observe();
        if(result.state.process_exited && result.state.job_empty)break;
        const auto elapsed=GetTickCount64()-started;
        if(elapsed>=timeout)break;
        Sleep(DWORD(std::min<ULONGLONG>(10,timeout-elapsed)));
    }while(true);
    return result;
}
HANDLE Process::process_handle() const noexcept {return state_?state_->process.value:nullptr;}
}
