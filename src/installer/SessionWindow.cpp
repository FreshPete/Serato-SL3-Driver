// A host-bound native front end. All session operations stay in the pinned CLI.
#define SL3_LAUNCHER_ARGUMENT_TEST
#include "NativeSessionLauncher.cpp"
#include "session_window_config.hpp"
#include <atomic>
#include <cstring>
#include <mutex>
#pragma comment(linker, "\"/manifestdependency:type='win32' name='Microsoft.Windows.Common-Controls' version='6.0.0.0' processorArchitecture='*' publicKeyToken='6595b64144ccf1df' language='*'\"")

namespace sl3::window {
using namespace sl3::launcher;
namespace config = session_window_config;
enum Action {check=101,start,status,recover,details};
struct State {
    HWND window=nullptr,heading=nullptr,description=nullptr,progress=nullptr,instructions=nullptr;
    HWND check_button=nullptr,start_button=nullptr,status_button=nullptr,recover_button=nullptr,detail_button=nullptr,log=nullptr;
    HFONT body=nullptr,title=nullptr;
    std::thread worker;
    std::mutex mutex;
    std::string output;
    std::atomic<bool> finished{false};
    bool busy=false,ready=false,used=false,expanded=false,preview=false;
    int action=0,code=1;
    unsigned log_revision=0,displayed_revision=0;
    ~State(){if(worker.joinable())worker.join();if(body)DeleteObject(body);if(title)DeleteObject(title);}
    void append(const char* data,std::size_t size){
        std::lock_guard<std::mutex> lock(mutex);
        output.append(data,size);
        constexpr std::size_t limit=65536;
        if(output.size()>limit)output.erase(0,output.size()-limit);
        ++log_revision;
    }
};
void text(HWND item,const wchar_t* value){SetWindowTextW(item,value);}
void enable(State& s){
    EnableWindow(s.check_button,!s.busy && !s.preview);
    EnableWindow(s.start_button,!s.busy && s.ready && !s.used && !s.preview);
    EnableWindow(s.status_button,!s.busy && !s.preview);
    EnableWindow(s.recover_button,!s.busy && !s.preview);
}
std::vector<std::wstring> session_arguments(const wchar_t* action){
    return {action,L"--session-plan",config::plan,L"--expected-session-plan-sha256",config::plan_sha,
            L"--powershell-directory",config::powershell};
}
int execute(State& s,const std::vector<std::wstring>& args,bool readonly){
    std::vector<Handle> leases;
    const auto executable=local_path(config::launcher);
    pin(leases,executable,config::launcher_sha);
    pin(leases,local_path(config::plan),config::plan_sha,65536);
    // Deny replacement of the reviewed inputs while their CLI executes.
    Pipe output;SECURITY_ATTRIBUTES security{sizeof(security),nullptr,TRUE};
    Handle input(CreateFileW(L"NUL",GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,&security,OPEN_EXISTING,0,nullptr));
    if(input.value==INVALID_HANDLE_VALUE)throw WinError("Open session input");
    STARTUPINFOEXW startup{};startup.StartupInfo.cb=sizeof(startup);
    startup.StartupInfo.dwFlags=STARTF_USESTDHANDLES|STARTF_USESHOWWINDOW;startup.StartupInfo.wShowWindow=SW_HIDE;
    startup.StartupInfo.hStdInput=input.value;startup.StartupInfo.hStdOutput=output.write.value;startup.StartupInfo.hStdError=output.write.value;
    SIZE_T size=0;InitializeProcThreadAttributeList(nullptr,1,0,&size);std::vector<BYTE> buffer(size);
    startup.lpAttributeList=reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(buffer.data());
    if(!InitializeProcThreadAttributeList(startup.lpAttributeList,1,0,&size))throw WinError("Create session inheritance policy");
    struct Guard {LPPROC_THREAD_ATTRIBUTE_LIST value;~Guard(){DeleteProcThreadAttributeList(value);}} guard{startup.lpAttributeList};
    std::array<HANDLE,2> allowed{input.value,output.write.value};
    if(!UpdateProcThreadAttribute(startup.lpAttributeList,0,PROC_THREAD_ATTRIBUTE_HANDLE_LIST,allowed.data(),sizeof(allowed),nullptr,nullptr))
        throw WinError("Restrict session handles");
    auto command=quote(executable.native());for(const auto& argument:args)command+=L" "+quote(argument);
    Handle job;
    if(readonly){
        job=Handle(CreateJobObjectW(nullptr,nullptr));require(job.value!=nullptr,"Create read-only check job");
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        require(SetInformationJobObject(job.value,JobObjectExtendedLimitInformation,&limits,sizeof(limits))!=FALSE,"Bound read-only check job");
    }
    PROCESS_INFORMATION child{};
    if(!CreateProcessW(executable.c_str(),command.data(),nullptr,nullptr,TRUE,CREATE_SUSPENDED|CREATE_NO_WINDOW|EXTENDED_STARTUPINFO_PRESENT,
                       nullptr,executable.parent_path().c_str(),&startup.StartupInfo,&child))throw WinError("Start verified session command");
    Handle process(child.hProcess),thread(child.hThread);output.write.reset();input.reset();
    if((readonly && !AssignProcessToJobObject(job.value,process.value)) || ResumeThread(thread.value)==DWORD(-1)){
        // The owned child has never run user code on this failure path.
        (void)TerminateProcess(process.value,1);(void)WaitForSingleObject(process.value,5000);
        throw std::runtime_error("Could not resume the bounded session command");
    }
    struct Retirement {
        HANDLE process;
        // Even an output error must not orphan an active protected session.
        ~Retirement(){(void)WaitForSingleObject(process,INFINITE);}
    } retirement{process.value};
    const auto began=GetTickCount64();bool exited=false;ULONGLONG retired=0;
    for(;;){
        DWORD available=0;
        if(!PeekNamedPipe(output.read.value,nullptr,0,nullptr,&available,nullptr)){
            if(GetLastError()!=ERROR_BROKEN_PIPE)throw WinError("Read session progress");
            available=0;
        }
        if(available){
            std::array<char,4096> bytes{};DWORD read=0;
            if(!ReadFile(output.read.value,bytes.data(),std::min<DWORD>(available,DWORD(bytes.size())),&read,nullptr))
                throw WinError("Read session details");
            s.append(bytes.data(),read);
        }
        const auto wait=WaitForSingleObject(process.value,available?0:25);
        require(wait==WAIT_OBJECT_0 || wait==WAIT_TIMEOUT,"Session process wait failed");
        if(wait==WAIT_OBJECT_0 && !exited){exited=true;retired=GetTickCount64();}
        if(exited && !available)break;
        // Do not wait forever for an inherited writer after the CLI has exited.
        require(!exited || GetTickCount64()-retired<2000,"Session output did not retire; retain saved reports");
        if(readonly && !exited && GetTickCount64()-began>120000){
            // Only this owned read-only CLI may be terminated here. Never kill a
            // running session or an elevated helper from the window.
            require(TerminateJobObject(job.value,1)!=FALSE,"Stop timed-out read-only check job");
            require(WaitForSingleObject(process.value,5000)==WAIT_OBJECT_0,"Read-only check did not retire");
            throw std::runtime_error("Read-only check timed out; session was not started");
        }
    }
    DWORD result=1;if(!GetExitCodeProcess(process.value,&result))throw WinError("Read session result");
    return int(result);
}
void begin(State& s,int action){
    if(s.preview || s.busy || (action==start && (!s.ready || s.used)))return;
    if(s.worker.joinable())s.worker.join();
    s.action=action;s.busy=true;s.finished=false;
    if(action==recover)s.ready=false;
    if(action==start){s.used=true;s.ready=false;}
    {std::lock_guard<std::mutex> lock(s.mutex);s.output.clear();++s.log_revision;}
    text(s.progress,action==check?L"Checking the prepared setup…":action==start?L"Starting the session…":
                    action==status?L"Reading session status…":L"Checking whether recovery is needed…");
    text(s.description,action==start?L"Accept the Windows prompts. In Serato, click Download Driver when asked. Close Serato normally when finished.":
                          L"This window stays responsive while the verified launcher works.");
    enable(s);
    try{s.worker=std::thread([&s,action]{
        try{
            if(action==check){
                s.code=execute(s,session_arguments(L"--plan-session"),true);
                if(!s.code)s.code=execute(s,{L"--check-kit",L"--kit-manifest",config::kit,L"--expected-kit-manifest-sha256",
                                           config::kit_sha,L"--app",config::application},true);
                if(!s.code)s.code=execute(s,session_arguments(L"--check-recovery"),true);
            }else s.code=execute(s,session_arguments(action==start?L"--start-session":action==status?L"--status-session":L"--recover-session"),action==status);
        }catch(const std::exception& error){s.append(error.what(),std::strlen(error.what()));s.code=1;}
        s.finished.store(true,std::memory_order_release);
    });}catch(...){s.busy=false;enable(s);throw;}
}
void layout(State& s){
    RECT box{};GetClientRect(s.window,&box);
    const auto dpi=GetDpiForWindow(s.window);
    auto px=[dpi](int n){return MulDiv(n,int(dpi),96);};
    const int margin=px(28),width=box.right-2*margin;
    auto place=[&](HWND item,int x,int y,int w,int h){MoveWindow(item,margin+px(x),px(y),w<0?width:px(w),px(h),TRUE);};
    place(s.heading,0,24,-1,38);place(s.progress,0,78,-1,28);
    place(s.description,0,114,-1,56);place(s.instructions,0,184,-1,60);
    place(s.check_button,0,258,142,38);place(s.start_button,154,258,142,38);
    place(s.status_button,0,310,142,34);place(s.recover_button,154,310,142,34);
    place(s.detail_button,0,364,-1,30);
    MoveWindow(s.log,margin,px(406),width,std::max(px(60),int(box.bottom)-px(430)),TRUE);
    ShowWindow(s.log,s.expanded?SW_SHOW:SW_HIDE);
}
HWND control(State& s,const wchar_t* kind,const wchar_t* label,DWORD style,int id=0){
    auto child=CreateWindowExW(0,kind,label,WS_CHILD|WS_VISIBLE|style,0,0,0,0,s.window,
                              reinterpret_cast<HMENU>(INT_PTR(id)),GetModuleHandleW(nullptr),nullptr);
    require(child!=nullptr,"Create session window control");SendMessageW(child,WM_SETFONT,WPARAM(s.body),TRUE);return child;
}
void fonts(State& s){
    const int dpi=int(GetDpiForWindow(s.window));
    const auto body=CreateFontW(-MulDiv(11,dpi,72),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Segoe UI");
    const auto title=CreateFontW(-MulDiv(21,dpi,72),0,0,0,FW_SEMIBOLD,FALSE,FALSE,FALSE,DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Segoe UI");
    if(!body || !title){if(body)DeleteObject(body);if(title)DeleteObject(title);throw std::runtime_error("Create session window fonts");}
    for(const auto item:{s.heading,s.description,s.progress,s.instructions,s.check_button,s.start_button,s.status_button,s.recover_button,s.detail_button,s.log})
        if(item)SendMessageW(item,WM_SETFONT,WPARAM(item==s.heading?title:body),TRUE);
    if(s.body)DeleteObject(s.body);if(s.title)DeleteObject(s.title);s.body=body;s.title=title;
}
LRESULT handle_message(HWND window,UINT message,WPARAM wparam,LPARAM lparam){
    auto* s=reinterpret_cast<State*>(GetWindowLongPtrW(window,GWLP_USERDATA));
    if(message==WM_NCCREATE){s=static_cast<State*>(reinterpret_cast<CREATESTRUCTW*>(lparam)->lpCreateParams);
        s->window=window;SetWindowLongPtrW(window,GWLP_USERDATA,LONG_PTR(s));}
    if(!s)return DefWindowProcW(window,message,wparam,lparam);
    switch(message){
    case WM_CREATE:{
        fonts(*s);
        s->heading=control(*s,L"STATIC",L"SL3 for Serato",0);SendMessageW(s->heading,WM_SETFONT,WPARAM(s->title),TRUE);
        s->progress=control(*s,L"STATIC",s->preview?L"Preview — session actions are disabled":L"Check setup to begin",0);
        s->description=control(*s,L"STATIC",L"Prepared development session for Serato DJ Pro 5.0.\r\nClose any existing Serato window before checking setup.",0);
        s->instructions=control(*s,L"STATIC",L"Phase A → SL3 inputs 3/4 · Phase B → inputs 5/6 · LINE\r\nExperimental software. Keep this window open until the session finishes.",0);
        s->check_button=control(*s,L"BUTTON",L"&Check setup",BS_DEFPUSHBUTTON|WS_TABSTOP,check);
        s->start_button=control(*s,L"BUTTON",L"&Start session",WS_TABSTOP,start);
        s->status_button=control(*s,L"BUTTON",L"Session s&tatus",WS_TABSTOP,status);
        s->recover_button=control(*s,L"BUTTON",L"&Recovery",WS_TABSTOP,recover);
        s->detail_button=control(*s,L"BUTTON",L"Show diagnostic &details",BS_AUTOCHECKBOX|WS_TABSTOP,details);
        s->log=control(*s,L"EDIT",L"",ES_MULTILINE|ES_READONLY|ES_AUTOVSCROLL|WS_VSCROLL|WS_TABSTOP);
        SendMessageW(s->log,EM_SETLIMITTEXT,65536,0);enable(*s);SetTimer(window,1,200,nullptr);layout(*s);return 0;
    }
    case WM_COMMAND:
        if(HIWORD(wparam)==BN_CLICKED){const int id=LOWORD(wparam);
            if(id==details){s->expanded=SendMessageW(s->detail_button,BM_GETCHECK,0,0)==BST_CHECKED;
                RECT bounds{};GetWindowRect(window,&bounds);const int addition=MulDiv(220,int(GetDpiForWindow(window)),96);
                SetWindowPos(window,nullptr,0,0,bounds.right-bounds.left,bounds.bottom-bounds.top+(s->expanded?addition:-addition),SWP_NOMOVE|SWP_NOZORDER);layout(*s);}
            else if(id>=check && id<=recover)begin(*s,id);}
        return 0;
    case WM_TIMER:{
        if(s->expanded){std::lock_guard<std::mutex> lock(s->mutex);if(s->displayed_revision!=s->log_revision){
            const auto& raw=s->output;const int count=MultiByteToWideChar(CP_UTF8,0,raw.data(),int(raw.size()),nullptr,0);
            std::wstring shown(std::size_t(count),L'\0');if(count)MultiByteToWideChar(CP_UTF8,0,raw.data(),int(raw.size()),shown.data(),count);
            text(s->log,shown.c_str());s->displayed_revision=s->log_revision;}}
        if(s->busy && s->finished.load(std::memory_order_acquire)){
            s->worker.join();s->busy=false;if(s->action==check)s->ready=s->code==0 && !s->used;
            text(s->progress,s->code?L"Action needs attention":s->action==check?L"Setup checks passed":
                 s->action==start?L"Session command finished":s->action==status?L"Status report is available":L"Recovery check finished");
            text(s->description,s->code?L"Open diagnostic details for the result. No further action will start automatically.":
                 s->action==check?(s->used?L"This prepared session has already been used. Prepare a new session before starting again.":
                                  L"You can start this prepared session. Windows will ask for administrator approval."):
                 s->action==start?L"Use Session status to inspect the saved result. A new session must be prepared before another start.":
                 L"Open diagnostic details to review the result. Clean setup does not prove a clean Serato shutdown.");
            enable(*s);
        }return 0;
    }
    case WM_SIZE:layout(*s);return 0;
    case WM_GETMINMAXINFO:{auto* limits=reinterpret_cast<MINMAXINFO*>(lparam);const auto dpi=int(GetDpiForWindow(window));
        limits->ptMinTrackSize={MulDiv(660,dpi,96),MulDiv(s->expanded?700:480,dpi,96)};return 0;}
    case WM_DPICHANGED:{auto* bounds=reinterpret_cast<RECT*>(lparam);SetWindowPos(window,nullptr,bounds->left,bounds->top,
        bounds->right-bounds->left,bounds->bottom-bounds->top,SWP_NOZORDER|SWP_NOACTIVATE);fonts(*s);return 0;}
    case WM_CTLCOLORSTATIC:{const auto dc=reinterpret_cast<HDC>(wparam);SetBkColor(dc,GetSysColor(COLOR_WINDOW));
        SetTextColor(dc,GetSysColor(COLOR_WINDOWTEXT));return reinterpret_cast<LRESULT>(GetSysColorBrush(COLOR_WINDOW));}
    case WM_CLOSE:if(s->busy){text(s->description,L"An action is still running. Close Serato normally and wait for the session to finish before closing this window.");return 0;}
        DestroyWindow(window);return 0;
    case WM_DESTROY:KillTimer(window,1);PostQuitMessage(0);return 0;
    default:return DefWindowProcW(window,message,wparam,lparam);
    }
}
LRESULT CALLBACK procedure(HWND window,UINT message,WPARAM wparam,LPARAM lparam) noexcept {
    try{return handle_message(window,message,wparam,lparam);}
    catch(const std::exception&){
        if(message==WM_CREATE)return -1;
        const auto* s=reinterpret_cast<State*>(GetWindowLongPtrW(window,GWLP_USERDATA));
        if(s && s->progress)text(s->progress,L"The window could not complete that action. Retain the saved reports.");
        return 0;
    }
}
}
#ifndef SL3_SESSION_WINDOW_TEST
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE,PWSTR arguments,int show){
    using namespace sl3::window;
    try{
        // No arguments run a bound session window. Preview never runs a command.
        State state;const std::wstring selected=arguments;
        require(selected.empty() || selected==L"--preview","Unexpected session window arguments");state.preview=!selected.empty();
        SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
        WNDCLASSW kind{};kind.lpfnWndProc=procedure;kind.hInstance=instance;kind.lpszClassName=L"SL3PreparedSessionWindow";
        kind.hCursor=LoadCursorW(nullptr,IDC_ARROW);kind.hbrBackground=GetSysColorBrush(COLOR_WINDOW);
        require(RegisterClassW(&kind)!=0,"Register session window");
        const auto window=CreateWindowExW(WS_EX_CONTROLPARENT,kind.lpszClassName,L"SL3 development session",WS_OVERLAPPEDWINDOW,
            CW_USEDEFAULT,CW_USEDEFAULT,780,500,nullptr,nullptr,instance,&state);
        require(window!=nullptr,"Create session window");ShowWindow(window,show);
        MSG message{};BOOL result=0;
        while((result=GetMessageW(&message,nullptr,0,0))>0){if(!IsDialogMessageW(window,&message)){TranslateMessage(&message);DispatchMessageW(&message);}}
        require(result==0,"Read session window messages");return 0;
    }catch(const std::exception& error){MessageBoxA(nullptr,error.what(),"SL3 window could not open",MB_OK|MB_ICONERROR);return 1;}
}
#endif
