#include "windows/worker_process.hpp"
#include <chrono>
#include <iostream>
#include <stdexcept>
#include <thread>

using sl3::worker::Process;
static void require(bool condition,const char* text){if(!condition)throw std::runtime_error(text);}
template<class F>static void rejected(F operation,const char* text){
    bool failed=false;try{operation();}catch(const std::exception&){failed=true;}require(failed,text);
}
static bool wait_count(Process& process,DWORD count){
    const auto start=GetTickCount64();
    do{if(process.observe().associated_processes==count)return true;Sleep(5);}while(GetTickCount64()-start<2000);
    return false;
}
static void stopped(Process& process){
    const auto stop=process.terminate_and_wait();
    require(stop.state.process_exited && stop.state.job_empty && stop.state.exit_code_known,"Confirm entire owned job terminated");
}
struct PrivateCopy {
    std::filesystem::path directory,file;
    bool copied=false;
    explicit PrivateCopy(const std::filesystem::path& source){
        directory=std::filesystem::temp_directory_path()/(L"sl3-worker-"+std::to_wstring(GetCurrentProcessId())+L"-"+
            std::to_wstring(GetTickCount64())+L" space \u30cb\u30b3");
        require(CreateDirectoryW(directory.c_str(),nullptr)!=FALSE,"Create fresh private path test directory");
        file=directory/L"worker space \u042e.exe";
        copied=CopyFileW(source.c_str(),file.c_str(),TRUE)!=FALSE;
        if(!copied){RemoveDirectoryW(directory.c_str());throw std::runtime_error("Copy private fixture without overwrite");}
    }
    ~PrivateCopy(){if(copied)DeleteFileW(file.c_str());RemoveDirectoryW(directory.c_str());}
};
int wmain(int argc,wchar_t** argv){
    try{
        require(argc==2,"Test fixture path required");
        const std::filesystem::path fixture=argv[1];
        const auto original_error_mode=GetThreadErrorMode();
        const auto hash=Process::executable_sha256(fixture);
        Process empty;
        require(!empty.observe().started && !empty.process_handle(),"No implicit process launch");
        require(!empty.terminate_and_wait().state.started,"Empty stop is harmless");
        rejected([&]{empty.terminate_and_wait(INFINITE);},"No unbounded termination waits");
        rejected([&]{empty.launch(L"relative.exe",hash,{});},"Reject relative executable");
        rejected([&]{empty.launch(fixture,"",{});},"Require expected executable identity");
        rejected([&]{empty.launch(fixture,std::string(64,'0'),{});},"Reject changed executable identity");
        rejected([&]{empty.launch(fixture,hash,{std::wstring(L"a\0b",3)});},"Reject embedded argument NUL");
        rejected([&]{empty.launch(fixture,hash,{std::wstring(32767,L'x')});},"Reject oversized command line");
        require(!empty.observe().started,"Rejected launches create no worker");
        Process normal;normal.launch(fixture,hash,{L"--exit",L"37"});
        require(normal.wait_for_exit(2000) && wait_count(normal,0),"Normal child exit");
        require(GetThreadErrorMode()==original_error_mode,"Successful launch restores caller thread error mode");
        auto state=normal.observe();
        require(state.job_assigned && state.exit_code_known && state.exit_code==37 && state.job_empty,"Actual exit code and empty assigned job");
        rejected([&]{normal.launch(fixture,hash,{L"--hang"});},"Do not restart an existing owner");
        rejected([&]{normal.wait_for_exit(INFINITE);},"No unbounded waits");
        Process exit259;exit259.launch(fixture,hash,{L"--exit",L"259"});
        require(exit259.wait_for_exit(2000) && exit259.observe().exit_code_known && exit259.observe().exit_code==259,"Exit 259 is not mistaken for a live process");
        Process args;args.launch(fixture,hash,{L"--argv",L"",L"spaces here",L"tail\\",L"embedded\"quote",L"slash\\\"quote",L"\u042e\u30cb\u30b3\u30fc\u30c9",L"two\\\\"});
        require(args.wait_for_exit(2000) && args.observe().exit_code==0,"Exact Unicode/empty/quoted/trailing-slash arguments");
        {
            PrivateCopy copy(fixture);
            Process copied;copied.launch(copy.file,hash,{L"--hang"});
            const auto writer=CreateFileW(copy.file.c_str(),GENERIC_WRITE,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
            if(writer!=INVALID_HANDLE_VALUE)CloseHandle(writer);
            require(writer==INVALID_HANDLE_VALUE,"Worker bytes pinned against writes during process life");
            require(!DeleteFileW(copy.file.c_str()),"Worker bytes pinned against deletion during process life");
            stopped(copied);
        }
        {
            std::cerr<<"worker test: malformed image creation\n";
            PrivateCopy malformed(fixture);
            HANDLE file=CreateFileW(malformed.file.c_str(),GENERIC_WRITE,0,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
            require(file!=INVALID_HANDLE_VALUE,"Open only the private malformed-image fixture");
            DWORD written=0;const char marker[]="??";
            const auto wrote=WriteFile(file,marker,2,&written,nullptr);CloseHandle(file);
            require(wrote && written==2,"Invalidate private fixture image header");
            const auto malformed_hash=Process::executable_sha256(malformed.file);
            Process bad;
            rejected([&]{bad.launch(malformed.file,malformed_hash,{});},"CreateProcess rejects malformed image even with matching hash");
            require(!bad.observe().started && !bad.process_handle(),"Failed process creation owns no child");
            require(GetThreadErrorMode()==original_error_mode,"Rejected launch restores caller thread error mode");
            std::cerr<<"worker test: malformed image rejected\n";
        }
        SECURITY_ATTRIBUTES security{sizeof(security),nullptr,TRUE};
        HANDLE sentinel=CreateEventW(&security,TRUE,FALSE,nullptr);
        require(sentinel!=nullptr,"Create inheritable sentinel");
        Process inheritance;inheritance.launch(fixture,hash,{L"--signal-handle",std::to_wstring(reinterpret_cast<std::uintptr_t>(sentinel))});
        require(inheritance.wait_for_exit(2000) && inheritance.observe().exit_code==0,"No-inheritance fixture exited");
        const auto inherited=WaitForSingleObject(sentinel,0)==WAIT_OBJECT_0;CloseHandle(sentinel);
        require(!inherited,"Inheritable parent handle was not passed to child");
        Process sentry;sentry.launch(fixture,hash,{L"--hang"});
        Process hung;hung.launch(fixture,hash,{L"--spawn-hang"});
        const auto descendants_started=GetTickCount64();
        while(hung.observe().associated_processes<2 && !hung.observe().process_exited && GetTickCount64()-descendants_started<2000)Sleep(5);
        if(hung.observe().associated_processes<2 || hung.observe().process_exited){
            const auto observed=hung.observe();
            throw std::runtime_error("Child and descendant job state: associated="+std::to_string(observed.associated_processes)+
                ", exited="+std::to_string(observed.process_exited)+", exit="+std::to_string(observed.exit_code));
        }
        require(!hung.wait_for_exit(30) && !hung.observe().process_exited,"A wait timeout is still a live process");
        const auto immediate=hung.terminate_and_wait(0);
        require(immediate.termination_requested,"Zero-wait stop requests only owned job termination");
        require(immediate.state.process_exited || !immediate.state.exit_code_known,"Pending stop never invents exit code");
        stopped(hung);
        require(!sentry.observe().process_exited,"Terminating one job does not touch another worker");
        stopped(sentry);
        Process orphan;orphan.launch(fixture,hash,{L"--spawn-exit"});
        const auto orphan_exited=orphan.wait_for_exit(2000);
        if(!orphan_exited || orphan.observe().associated_processes<1){
            const auto observed=orphan.observe();
            throw std::runtime_error("Exited root with live descendant remains incomplete: exited="+std::to_string(orphan_exited)+
                ", associated="+std::to_string(observed.associated_processes)+", exit="+std::to_string(observed.exit_code));
        }
        require(!orphan.observe().job_empty && orphan.observe().exit_code==39,"Root exit is not job cleanup");
        stopped(orphan);
        HANDLE observer=nullptr;
        {
            Process scope;scope.launch(fixture,hash,{L"--hang"});
            require(DuplicateHandle(GetCurrentProcess(),scope.process_handle(),GetCurrentProcess(),&observer,SYNCHRONIZE,FALSE,0)!=FALSE,"Retain an observation handle");
        }
        const auto closed=WaitForSingleObject(observer,2000);CloseHandle(observer);
        require(closed==WAIT_OBJECT_0,"Owner destruction closes job and kills child");
        Process abrupt;
        std::wstring wide_hash(hash.begin(),hash.end());
        abrupt.launch(fixture,hash,{L"--abrupt-owner",wide_hash});
        require(abrupt.wait_for_exit(2000) && wait_count(abrupt,0) && abrupt.observe().exit_code==41,"Abrupt nested owner exit retires its descendant without C++ cleanup");
        std::cout<<"Worker process identity, argument, timeout, job containment and owner-death tests passed; no USB or ASIO access\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
