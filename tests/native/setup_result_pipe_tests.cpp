#define SL3_LAUNCHER_ARGUMENT_TEST
#include "../../src/installer/NativeSessionLauncher.cpp"
#include "../../src/installer/SetupResultPipe.hpp"
#include <iostream>
using namespace sl3::launcher;
namespace result=sl3::setup_result;
namespace {
fs::path image(){std::array<wchar_t,32768> text{};const auto size=GetModuleFileNameW(nullptr,text.data(),DWORD(text.size()));require(size && size<text.size(),"Owned fixture image required");return fs::path(text.data());}
struct Child {Handle process,thread;};
Child spawn(const std::vector<std::wstring>& arguments){auto command=quote(image().native())+L" "+command_line(arguments);STARTUPINFOW startup{};startup.cb=sizeof(startup);PROCESS_INFORMATION child{};
    require(CreateProcessW(image().c_str(),command.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,nullptr,&startup,&child)!=FALSE,"Start only owned result fixture");return {Handle(child.hProcess),Handle(child.hThread)};}
DWORD exited(HANDLE process){require(WaitForSingleObject(process,10000)==WAIT_OBJECT_0,"Owned result fixture must retire");DWORD code=1;require(GetExitCodeProcess(process,&code)!=FALSE,"Read owned result fixture exit");return code;}
}
int wmain(int argc,wchar_t** argv){
    try{
        if(argc==2 && std::wstring(argv[1])==L"--emit"){std::cout<<"fixture-stdout\n"<<std::flush;std::cerr<<"fixture-stderr\n"<<std::flush;return 7;}
        if(argc==2 && std::wstring(argv[1])==L"--empty")return 0;
        if(argc==5 && std::wstring(argv[1])==L"--client"){
            const std::wstring mode=argv[4];if(mode==L"delayed")Sleep(250);
            result::Client client(argv[2],result::process_id(argv[3]));
            if(mode==L"redirect"){client.redirect();return run_process(image(),{L"--emit"},image().parent_path(),false);}
            client.write(mode==L"large"?std::string(600*1024,'x'):mode==L"spoof"?"forged-result":"real-result");return 0;
        }
        require(argc==1,"Known owned-pipe fixture mode required");unsigned cases=0;bool anonymous_observed=false;
        const auto pid=std::to_wstring(GetCurrentProcessId());
        {result::Server server;auto child=spawn({L"--client",server.name,pid,L"good"});const auto capture=server.collect(child.process.value);server.close();
            require(exited(child.process.value)==0 && capture.authenticated && capture.bytes=="real-result" && !capture.error && !capture.over_limit,"Actual owned result delivery");++cases;}
        {result::Server server;auto child=spawn({L"--client",server.name,pid,L"redirect"});const auto capture=server.collect(child.process.value);server.close();
            require(exited(child.process.value)==7 && capture.authenticated && capture.bytes.find("fixture-stdout")!=std::string::npos && capture.bytes.find("fixture-stderr")!=std::string::npos,"Existing helper relay retains both streams and failed exit");++cases;}
        {result::Server server;auto wrong=spawn({L"--client",server.name,pid,L"spoof"});Sleep(50);auto real=spawn({L"--client",server.name,pid,L"delayed"});
            const auto capture=server.collect(real.process.value);server.close();const auto rejected=exited(wrong.process.value);
            require((rejected==0 || rejected==2) && exited(real.process.value)==0 && capture.authenticated && capture.rejected>=1 && capture.bytes=="real-result","Foreign writer cannot forge the expected process result");++cases;}
        {result::Server server;auto child=spawn({L"--empty"});const auto capture=server.collect(child.process.value);server.close();
            require(exited(child.process.value)==0 && capture.bytes.empty(),"Process exit without a report must remain missing evidence");++cases;}
        {result::Server server;auto child=spawn({L"--client",server.name,std::to_wstring(GetCurrentProcessId()+1),L"good"});const auto capture=server.collect(child.process.value);server.close();
            require(exited(child.process.value)==2 && capture.bytes.empty(),"Wrong server identity refuses before diagnostic delivery");++cases;}
        {result::Server server;auto child=spawn({L"--client",server.name,pid,L"large"});const auto capture=server.collect(child.process.value);server.close();
            require(exited(child.process.value)==0 && capture.authenticated && capture.over_limit && capture.bytes.size()==512*1024,"Over-budget diagnostics remain bounded and are fully drained");++cases;}
        require(!result::endpoint(L"C:\\result.txt") && !result::endpoint(L"\\\\other\\pipe\\SL3SetupResult-"+result::token()),"Only fixed local result namespace allowed");++cases;
        {result::Server server;auto child=spawn({L"--client",server.name,pid,L"good"});Handle event(CreateEventW(nullptr,TRUE,FALSE,nullptr));OVERLAPPED operation{};operation.hEvent=event.value;
            if(!ConnectNamedPipe(server.diagnostic_handle(),&operation)){const auto error=GetLastError();require(error==ERROR_IO_PENDING || error==ERROR_PIPE_CONNECTED,"Own anonymous probe connection");if(error==ERROR_IO_PENDING){DWORD ignored=0;require(GetOverlappedResult(server.diagnostic_handle(),&operation,&ignored,TRUE)!=FALSE,"Complete own anonymous probe connection");}}
            char first=0;DWORD read=0;ResetEvent(event.value);operation={};operation.hEvent=event.value;
            if(!ReadFile(server.diagnostic_handle(),&first,1,&read,&operation)){require(GetLastError()==ERROR_IO_PENDING && GetOverlappedResult(server.diagnostic_handle(),&operation,&read,TRUE),"Read own client security-context byte");}
            require(read==1,"Own context probe read required");
            if(ImpersonateNamedPipeClient(server.diagnostic_handle())){
                HANDLE token=nullptr;const auto opened=OpenThreadToken(GetCurrentThread(),TOKEN_QUERY,TRUE,&token);const auto error=GetLastError();
                if(opened){SECURITY_IMPERSONATION_LEVEL level=SecurityDelegation;DWORD size=0;const auto known=GetTokenInformation(token,TokenImpersonationLevel,&level,sizeof(level),&size);CloseHandle(token);RevertToSelf();require(known && level==SecurityAnonymous,"Client must not grant impersonation authority");}
                else{RevertToSelf();require(error==ERROR_CANT_OPEN_ANONYMOUS,"Expected anonymous client token");}
                anonymous_observed=true;
            }else{require(GetLastError()==ERROR_CANNOT_IMPERSONATE,"Expected denial of anonymous impersonation");anonymous_observed=true;}
            const auto capture=server.collect(child.process.value);server.close();require(exited(child.process.value)==0 && capture.bytes=="eal-result","Anonymous client diagnostic completion");++cases;
        }
        std::cout<<"{\"schema\":\"sl3.setup-result-pipe-tests.v1\",\"passed\":true,\"cases\":"<<cases<<",\"anonymousClientObserved\":"<<(anonymous_observed?"true":"false")<<",\"elevatedProcessExecuted\":false,\"seratoLaunched\":false,\"nativeDeviceAccess\":false}\n";return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
