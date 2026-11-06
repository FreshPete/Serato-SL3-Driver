// One-time setup UI. Existing native entry owns all setup/controller operations.
#define SL3_SESSION_WINDOW_TEST
#include "SessionWindow.cpp"

namespace sl3::setup_window {
using namespace sl3::launcher;
namespace config=session_window_config;
enum Action {check=101,install=102,restore=104,details=105};
struct Eligibility {bool install=false,restore=false,clean=false,installed=false;};
Eligibility eligibility(const std::wstring& archive,const std::wstring& native,bool running=false){
    const bool known_archive=archive==L"original" || archive==L"installed" || archive==L"restored" || archive==L"install-staged" || archive==L"rollback-staged";
    const bool known_native=native==L"absent" || native==L"installed" || native==L"unregistered";
    const bool clean=archive==L"original" && native==L"absent",installed=archive==L"installed" && native==L"installed";
    return {!running && known_archive && (archive==L"original" || archive==L"install-staged") && (native==L"absent" || native==L"installed"),
            !running && known_archive && known_native && !clean,clean,installed};
}
bool serato_running(const std::string& raw){
    Microsoft::WRL::ComPtr<ABI::Windows::Data::Json::IJsonObjectStatics> factory;
    Microsoft::WRL::Wrappers::HStringReference type(L"Windows.Data.Json.JsonObject");
    checked(RoGetActivationFactory(type.Get(),__uuidof(ABI::Windows::Data::Json::IJsonObjectStatics),reinterpret_cast<void**>(factory.GetAddressOf())),"Activate typed setup parser");
    Microsoft::WRL::Wrappers::HString input;const auto decoded=utf16(raw);checked(input.Set(decoded.c_str(),UINT32(decoded.size())),"Read setup result text");
    Microsoft::WRL::ComPtr<ABI::Windows::Data::Json::IJsonObject> object,after;checked(factory->Parse(input.Get(),object.GetAddressOf()),"Parse setup result");
    checked(object->GetNamedObject(Microsoft::WRL::Wrappers::HStringReference(L"after").Get(),after.GetAddressOf()),"Read observed setup state");
    boolean running=false;checked(after->GetNamedBoolean(Microsoft::WRL::Wrappers::HStringReference(L"seratoRunning").Get(),&running),"Typed running-state result required");return running!=false;
}
struct State:sl3::window::State {Eligibility allowed{};bool running=false;};
void text(HWND item,const wchar_t* value){SetWindowTextW(item,value);}
void enable(State& s){
    EnableWindow(s.check_button,!s.preview && !s.busy);
    EnableWindow(s.start_button,!s.preview && !s.busy && s.allowed.install);
    EnableWindow(s.recover_button,!s.preview && !s.busy && s.allowed.restore);
}
std::vector<std::wstring> arguments(const wchar_t* action){return {action,L"--kit",config::kit_root,L"--app",config::application,
    L"--experiment",config::plan,L"--expected-experiment-sha256",config::plan_sha};}
int inspect(State& s){
    {std::lock_guard<std::mutex> lock(s.mutex);s.output.clear();++s.log_revision;}
    const auto code=sl3::window::execute(s,arguments(L"--check-experiment"),true);s.allowed={};s.running=false;
    if(!code){std::string raw;{std::lock_guard<std::mutex> lock(s.mutex);raw=s.output;}
        const JsonObject result(raw);require(result.text(L"schema")==L"sl3.on-demand-test-action.v1","Typed setup observation required");
        const auto after=result.object(L"after");s.running=serato_running(raw);s.allowed=eligibility(after.text(L"archive"),after.object(L"native").text(L"state"),s.running);}
    return code;
}
int apply(State& s,int action){
    auto code=inspect(s);if(code)return code;
    require(action==install?s.allowed.install:s.allowed.restore,"Current setup state does not admit this action");
    std::vector<Handle> leases;pin(leases,local_path(config::launcher),config::launcher_sha);pin(leases,local_path(config::plan),config::plan_sha,65536);
    const auto operation=run_process(local_path(config::launcher),arguments(action==install?L"--apply-experiment":L"--restore-experiment"),
                                     local_path(config::launcher).parent_path(),true);
    code=inspect(s);if(operation)return operation;if(code)return code;
    require(action==install?s.allowed.installed:s.allowed.clean,"Command finished but observed setup state differs");return 0;
}
void begin(State& s,int action){
    if(s.preview || s.busy || (action==install && !s.allowed.install) || (action==restore && !s.allowed.restore))return;
    if(s.worker.joinable())s.worker.join();s.allowed={};s.busy=true;s.action=action;s.finished=false;s.code=1;
    text(s.progress,action==check?L"Checking your setup…":action==install?L"Installing the compatibility build…":L"Restoring the original setup…");
    text(s.description,action==check?L"This check does not change Serato or open the SL3.":L"Windows may ask for administrator approval. Keep this window open until the action finishes.");enable(s);
    try{s.worker=std::thread([&s,action]{
        bool initialized=false;
        try{checked(RoInitialize(RO_INIT_SINGLETHREADED),"Initialize setup result parser");initialized=true;s.code=action==check?inspect(s):apply(s,action);}
        catch(const WinError& error){s.append(error.what(),std::strlen(error.what()));s.code=int(error.code?error.code:1);}
        catch(const std::exception& error){s.append(error.what(),std::strlen(error.what()));s.code=1;}
        if(initialized)RoUninitialize();s.finished.store(true,std::memory_order_release);
    });}catch(...){s.busy=false;enable(s);throw;}
}
void layout(State& s){
    RECT box{};GetClientRect(s.window,&box);const auto dpi=int(GetDpiForWindow(s.window));auto px=[dpi](int n){return MulDiv(n,dpi,96);};
    const auto margin=px(28),width=int(box.right)-2*margin;
    auto place=[&](HWND item,int x,int y,int w,int h){MoveWindow(item,margin+px(x),px(y),w?px(w):width,px(h),TRUE);};
    place(s.heading,0,24,0,38);place(s.progress,0,78,0,28);place(s.description,0,116,0,56);place(s.instructions,0,188,0,56);
    place(s.check_button,0,264,154,38);place(s.start_button,166,264,154,38);place(s.recover_button,0,318,224,36);place(s.detail_button,0,372,0,30);
    MoveWindow(s.log,margin,px(414),width,std::max(px(70),int(box.bottom)-px(440)),TRUE);ShowWindow(s.log,s.expanded?SW_SHOW:SW_HIDE);
}
LRESULT message(HWND window,UINT message,WPARAM wparam,LPARAM lparam){
    auto* s=reinterpret_cast<State*>(GetWindowLongPtrW(window,GWLP_USERDATA));
    if(message==WM_NCCREATE){s=static_cast<State*>(reinterpret_cast<CREATESTRUCTW*>(lparam)->lpCreateParams);s->window=window;SetWindowLongPtrW(window,GWLP_USERDATA,LONG_PTR(s));}
    if(!s)return DefWindowProcW(window,message,wparam,lparam);
    switch(message){
    case WM_CREATE:{
        sl3::window::fonts(*s);auto control=[&](const wchar_t* kind,const wchar_t* label,DWORD style,int id=0){return sl3::window::control(*s,kind,label,style,id);};
        s->heading=control(L"STATIC",L"Set up your SL3",0);SendMessageW(s->heading,WM_SETFONT,WPARAM(s->title),TRUE);
        s->progress=control(L"STATIC",s->preview?L"Preview — actions are disabled":L"Check this setup to begin",0);
        s->description=control(L"STATIC",L"Install this compatibility build once, then open Serato normally.\r\nClose Serato before installing or restoring.",0);
        s->instructions=control(L"STATIC",L"Phase and timecode vinyl use the same SL3 audio driver.\r\nExperimental build for Serato 5.0. Normal startup still needs a live test.",0);
        s->check_button=control(L"BUTTON",L"&Check setup",BS_DEFPUSHBUTTON|WS_TABSTOP,check);
        s->start_button=control(L"BUTTON",L"&Install",WS_TABSTOP,install);
        s->recover_button=control(L"BUTTON",L"&Restore original setup",WS_TABSTOP,restore);
        s->detail_button=control(L"BUTTON",L"Show diagnostic &details",BS_AUTOCHECKBOX|WS_TABSTOP,details);
        s->log=control(L"EDIT",L"",ES_MULTILINE|ES_READONLY|ES_AUTOVSCROLL|WS_VSCROLL|WS_TABSTOP);SendMessageW(s->log,EM_SETLIMITTEXT,65536,0);
        enable(*s);SetTimer(window,1,200,nullptr);layout(*s);return 0;
    }
    case WM_COMMAND:
        if(HIWORD(wparam)==BN_CLICKED){const int action=LOWORD(wparam);
            if(action==details){s->expanded=SendMessageW(s->detail_button,BM_GETCHECK,0,0)==BST_CHECKED;RECT bounds{};GetWindowRect(window,&bounds);
                const auto addition=MulDiv(220,int(GetDpiForWindow(window)),96);SetWindowPos(window,nullptr,0,0,bounds.right-bounds.left,bounds.bottom-bounds.top+(s->expanded?addition:-addition),SWP_NOMOVE|SWP_NOZORDER);layout(*s);}
            else if(action==check || action==install || action==restore)begin(*s,action);}
        return 0;
    case WM_TIMER:
        if(s->expanded){std::lock_guard<std::mutex> lock(s->mutex);if(s->displayed_revision!=s->log_revision){
            const auto count=MultiByteToWideChar(CP_UTF8,0,s->output.data(),int(s->output.size()),nullptr,0);std::wstring shown(std::size_t(count),L'\0');
            if(count)MultiByteToWideChar(CP_UTF8,0,s->output.data(),int(s->output.size()),shown.data(),count);text(s->log,shown.c_str());s->displayed_revision=s->log_revision;}}
        if(s->busy && s->finished.load(std::memory_order_acquire)){
            s->worker.join();s->busy=false;
            if(s->code){text(s->progress,s->code==ERROR_CANCELLED?L"Action cancelled":L"Setup needs attention");text(s->description,L"Open diagnostic details for the result. No further action will start automatically.");}
            else if(s->running){text(s->progress,L"Close Serato before continuing");text(s->description,L"Close Serato normally, then choose Check setup again.\r\nInstall and restore are disabled while it is running.");}
            else if(s->allowed.installed){text(s->progress,L"Installed — ready for a Serato startup test");text(s->description,L"Open Serato normally to test the SL3.\r\nThis window does not start or control Serato.");}
            else if(s->action==restore && s->allowed.clean){text(s->progress,L"Original setup restored");text(s->description,L"The compatibility files and temporary driver registration have been removed.");}
            else{text(s->progress,s->allowed.install?L"Ready to install this development build":L"Setup needs review");text(s->description,s->allowed.install?
                L"Install will ask Windows for administrator approval.\r\nYou will not need this window for normal Serato use after validation.":L"Open diagnostic details. Keep the prepared records for reviewed recovery.");}
            enable(*s);
        }return 0;
    case WM_SIZE:layout(*s);return 0;
    case WM_GETMINMAXINFO:{auto* limits=reinterpret_cast<MINMAXINFO*>(lparam);const auto dpi=int(GetDpiForWindow(window));limits->ptMinTrackSize={MulDiv(660,dpi,96),MulDiv(s->expanded?720:500,dpi,96)};return 0;}
    case WM_DPICHANGED:{const auto* bounds=reinterpret_cast<RECT*>(lparam);SetWindowPos(window,nullptr,bounds->left,bounds->top,bounds->right-bounds->left,bounds->bottom-bounds->top,SWP_NOZORDER|SWP_NOACTIVATE);sl3::window::fonts(*s);return 0;}
    case WM_CTLCOLORSTATIC:{const auto dc=reinterpret_cast<HDC>(wparam);SetBkColor(dc,GetSysColor(COLOR_WINDOW));SetTextColor(dc,GetSysColor(COLOR_WINDOWTEXT));return reinterpret_cast<LRESULT>(GetSysColorBrush(COLOR_WINDOW));}
    case WM_CLOSE:if(s->busy){text(s->description,L"An action is running. Wait for its result before closing; setup will not be interrupted.");return 0;}DestroyWindow(window);return 0;
    case WM_DESTROY:KillTimer(window,1);PostQuitMessage(0);return 0;
    default:return DefWindowProcW(window,message,wparam,lparam);
    }
}
LRESULT CALLBACK procedure(HWND window,UINT code,WPARAM wparam,LPARAM lparam) noexcept {
    try{return message(window,code,wparam,lparam);}catch(...){if(code==WM_CREATE)return -1;
        const auto* state=reinterpret_cast<State*>(GetWindowLongPtrW(window,GWLP_USERDATA));
        if(state && state->progress)text(state->progress,L"The window could not complete that action. Keep the prepared records.");return 0;}
}
HWND create(State& state,HINSTANCE instance){
    WNDCLASSW kind{};kind.lpfnWndProc=procedure;kind.hInstance=instance;kind.lpszClassName=L"SL3OneTimeSetupWindow";kind.hCursor=LoadCursorW(nullptr,IDC_ARROW);kind.hbrBackground=GetSysColorBrush(COLOR_WINDOW);
    require(RegisterClassW(&kind)!=0 || GetLastError()==ERROR_CLASS_ALREADY_EXISTS,"Register setup window");
    const auto window=CreateWindowExW(WS_EX_CONTROLPARENT,kind.lpszClassName,L"SL3 compatibility setup",WS_OVERLAPPEDWINDOW,CW_USEDEFAULT,CW_USEDEFAULT,780,530,nullptr,nullptr,instance,&state);
    require(window!=nullptr,"Create setup window");return window;
}
}
#ifndef SL3_SETUP_WINDOW_TEST
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE,PWSTR arguments,int show){
    using namespace sl3::setup_window;
    try{State state;const std::wstring selection=arguments;require(selection.empty() || selection==L"--preview","Unexpected setup window arguments");state.preview=!selection.empty();
        SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);const auto window=create(state,instance);ShowWindow(window,show);
        MSG item{};BOOL result=0;while((result=GetMessageW(&item,nullptr,0,0))>0){if(!IsDialogMessageW(window,&item)){TranslateMessage(&item);DispatchMessageW(&item);}}require(result==0,"Read setup window messages");return 0;
    }catch(const std::exception& error){MessageBoxA(nullptr,error.what(),"SL3 setup could not open",MB_OK|MB_ICONERROR);return 1;}
}
#endif
