#include "windows/redirect_owner.hpp"
#include "windows/worker_process.hpp"
#include <aclapi.h>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using sl3::worker::RedirectOwner;
using sl3::worker::Process;
void check(bool value,const char* message){if(!value)throw std::runtime_error(message);}
struct Handle {
    HANDLE value=nullptr;
    ~Handle(){if(value)CloseHandle(value);}
};
std::wstring unique_name(){
    static unsigned sequence=0;
    return L"Global\\SL3Rebuild.Redirect.Test."+std::to_wstring(GetCurrentProcessId())+L"."+
        std::to_wstring(GetTickCount64())+L"."+std::to_wstring(++sequence);
}
void retired(Process& child,DWORD expected){
    check(child.wait_for_exit(3000),"Private guard child did not exit");
    const auto entered=GetTickCount64();
    while(!child.observe().job_empty && GetTickCount64()-entered<2000)Sleep(1);
    const auto state=child.observe();
    check(state.process_exited && state.job_empty && state.exit_code_known && state.exit_code==expected,
          "Private guard child exit/job mismatch");
}
int wmain(int argc,wchar_t** argv){try{
    if(argc>=3){
        RedirectOwner owner;
        if(std::wstring(argv[1])==L"--try")return owner.acquire(argv[2])?0:owner.error()==ERROR_BUSY?20:21;
        if(argc==4 && std::wstring(argv[1])==L"--hold"){
            if(!owner.acquire(argv[2]))return 22;
            Handle ready;ready.value=OpenEventW(EVENT_MODIFY_STATE,FALSE,argv[3]);
            if(!ready.value || !SetEvent(ready.value))return 23;
            Sleep(10000);return 24;
        }
        return 25;
    }
    check(argc==1,"Unexpected test arguments");
    wchar_t self[MAX_PATH]{};check(GetModuleFileNameW(nullptr,self,MAX_PATH)>0,"Find guard test executable");
    const auto hash=Process::executable_sha256(self);
    auto peer=[&](const std::wstring& name,DWORD code){Process child;child.launch(self,hash,{L"--try",name});retired(child,code);};
    {const auto name=unique_name();RedirectOwner owner;
        check(owner.acquire(name.c_str()),"Ordinary token could not create global guard");
        RedirectOwner recursive;check(!recursive.acquire(name.c_str()) && recursive.error()==ERROR_BUSY,
                                      "Same-thread second owner was admitted");
        check(!owner.acquire(name.c_str()) && owner.error()==ERROR_INVALID_STATE,"Owner reused itself");
        peer(name,20);
        // The creator is allowed implicit READ_CONTROL/WRITE_DAC as owner,
        // but authenticated-user access must not permit event signalling.
        Handle modify;SetLastError(ERROR_SUCCESS);modify.value=OpenEventW(EVENT_MODIFY_STATE,FALSE,name.c_str());
        check(!modify.value && GetLastError()==ERROR_ACCESS_DENIED,"Guard unexpectedly permits signalling");
        check(owner.close(),"Close ordinary owner");peer(name,0);
        check(!owner.acquire(name.c_str()),"Closed owner was revived");}
    {const auto name=unique_name();
        {RedirectOwner owner;check(owner.acquire(name.c_str()),"Create destructor fixture");}
        peer(name,0);}
    {const auto name=unique_name();Handle wrong;
        wrong.value=CreateMutexW(nullptr,FALSE,name.c_str());check(wrong.value!=nullptr,"Create wrong-type fixture");
        RedirectOwner owner;check(!owner.acquire(name.c_str()) && owner.error()==ERROR_INVALID_HANDLE,"Wrong-type collision admitted");}
    {const auto name=unique_name();Handle denied;
        denied.value=CreateEventW(nullptr,FALSE,FALSE,name.c_str());check(denied.value!=nullptr,"Create denied fixture");
        ACL empty{};check(InitializeAcl(&empty,sizeof(empty),ACL_REVISION)!=FALSE,"Initialize empty private DACL");
        check(SetSecurityInfo(denied.value,SE_KERNEL_OBJECT,DACL_SECURITY_INFORMATION|PROTECTED_DACL_SECURITY_INFORMATION,
                              nullptr,nullptr,&empty,nullptr)==ERROR_SUCCESS,"Set private denied fixture DACL");
        RedirectOwner owner;check(!owner.acquire(name.c_str()) && owner.error()==ERROR_ACCESS_DENIED,"Access denial bypassed");}
    {RedirectOwner invalid;check(!invalid.acquire(L"") && invalid.error()==ERROR_INVALID_NAME,"Empty guard name admitted");}
    {const auto name=unique_name(),ready_name=name+L".ready";Handle ready;
        ready.value=CreateEventW(nullptr,TRUE,FALSE,ready_name.c_str());check(ready.value!=nullptr,"Create private readiness event");
        Process holder;holder.launch(self,hash,{L"--hold",name,ready_name});
        check(WaitForSingleObject(ready.value,2000)==WAIT_OBJECT_0,"Private holder did not become ready");
        peer(name,20);
        const auto stopped=holder.terminate_and_wait(3000);
        check(stopped.state.process_exited && stopped.state.job_empty,"Private holder did not retire");
        peer(name,0); // Kernel-object cleanup only: no USB I/O occurred.
    }
    std::cout<<"Redirect guard same-thread/process exclusion, collisions, DACL and owner-exit cleanup passed; private objects only, no USB\n";
    return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}}
