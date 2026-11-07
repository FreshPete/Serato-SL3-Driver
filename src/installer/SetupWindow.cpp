// One-time setup UI. Existing native entry owns all setup/controller operations.
#define SL3_SESSION_WINDOW_TEST
#include "SessionWindow.cpp"
#include "SetupResultPipe.hpp"
#include "SetupUsbPrerequisite.hpp"
#include <shlobj.h>
#include <memory>

namespace sl3::setup_window {
using namespace sl3::launcher;
namespace config=session_window_config;
enum Action {check=101,install=102,restore=104,details=105};
struct Eligibility {bool install=false,restore=false,clean=false,installed=false;};
Eligibility eligibility(const std::wstring& archive,const std::wstring& native,bool running=false,bool usb_ready=true){
    const bool known_archive=archive==L"original" || archive==L"installed" || archive==L"restored" || archive==L"install-staged" || archive==L"rollback-staged";
    const bool known_native=native==L"absent" || native==L"installed" || native==L"unregistered";
    const bool clean=archive==L"original" && native==L"absent",installed=archive==L"installed" && native==L"installed";
    return {usb_ready && !running && known_archive && (archive==L"original" || archive==L"install-staged") && (native==L"absent" || native==L"installed"),
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
struct State:sl3::window::State {
    Eligibility allowed{};bool running=false,usb_ready=false;
    std::wstring launcher=config::launcher,kit=config::kit_root,application=config::application,plan=config::plan,plan_sha=config::plan_sha;
};
void text(HWND item,const wchar_t* value){SetWindowTextW(item,value);}
void enable(State& s){
    EnableWindow(s.check_button,!s.preview && !s.busy);
    EnableWindow(s.start_button,!s.preview && !s.busy && s.allowed.install);
    EnableWindow(s.recover_button,!s.preview && !s.busy && s.allowed.restore);
}
std::vector<std::wstring> arguments(const State& s,const wchar_t* action){return {action,L"--kit",s.kit,L"--app",s.application,
    L"--experiment",s.plan,L"--expected-experiment-sha256",s.plan_sha};}
int select_setup(State& s){
    std::wstring image(32768,L'\0');const auto count=GetModuleFileNameW(nullptr,image.data(),DWORD(image.size()));
    require(count && count<image.size(),"Locate the setup executable");image.resize(count);
    const auto parent=local_path(image).parent_path();
    s.launcher=(parent/L"SL3_Setup_Engineering.exe").native();s.kit=(parent/L"kit").native();
    constexpr GUID program_files{0x905e63b6,0xc1bf,0x494e,{0xb2,0x9c,0x65,0xb7,0x32,0xd3,0xd2,0x1a}};
    PWSTR known=nullptr;checked(SHGetKnownFolderPath(program_files,0,nullptr,&known),"Locate Program Files");
    const std::unique_ptr<wchar_t,decltype(&CoTaskMemFree)> folder(known,CoTaskMemFree);
    s.application=(fs::path(folder.get())/L"Serato/Serato DJ Pro/Serato DJ Pro.exe").native();
    std::vector<Handle> leases;pin(leases,local_path(s.launcher),config::launcher_sha);
    const auto code=sl3::window::execute_child(s,local_path(s.launcher),{L"--select-setup",L"--kit",s.kit,L"--app",s.application},true);
    if(code)return code;
    std::string raw;{std::lock_guard<std::mutex> lock(s.mutex);raw=s.output;}
    const JsonObject result(raw);require(result.text(L"schema")==L"sl3.on-demand-kit-resume.v1","Typed selected setup required");
    const auto plan=local_path(result.text(L"experiment"));const auto sha=result.text(L"experimentSha256");
    require(plan.filename()==L"experiment.json" && equal(plan.parent_path().parent_path().native(),(local_path(s.kit)/L"analysis").native()),
            "Selected setup record must belong to this kit");
    pin(leases,plan,sha,65536);s.plan=plan.native();s.plan_sha=sha;
    {std::lock_guard<std::mutex> lock(s.mutex);s.output.clear();++s.log_revision;}
    return 0;
}
int inspect(State& s,bool retain_prior=false){
    std::string prior;
    {std::lock_guard<std::mutex> lock(s.mutex);if(retain_prior)prior=s.output;s.output.clear();++s.log_revision;}
    s.allowed={};s.running=false;int code=1;
    try{
        if(s.plan.empty()){
            code=select_setup(s);if(code)return code;
        }
        std::vector<Handle> leases;pin(leases,local_path(s.launcher),config::launcher_sha);
        pin(leases,local_path(s.plan),s.plan_sha,65536);
        code=sl3::window::execute_child(s,local_path(s.launcher),arguments(s,L"--check-experiment"),true);
    }
    catch(...){if(retain_prior){std::string failed;{std::lock_guard<std::mutex> lock(s.mutex);failed=s.output;s.output=prior;}
        const auto combined=std::string("\nPost-action observation failed:\n")+failed;s.append(combined.data(),combined.size());}throw;}
    std::string raw;{std::lock_guard<std::mutex> lock(s.mutex);raw=s.output;}
    if(retain_prior){std::lock_guard<std::mutex> lock(s.mutex);s.output=prior;}
    if(retain_prior){const auto combined=std::string("\nPost-action observation:\n")+raw;s.append(combined.data(),combined.size());}
    if(!code){
        const JsonObject result(raw);require(result.text(L"schema")==L"sl3.on-demand-test-action.v1","Typed setup observation required");
        const auto after=result.object(L"after");s.running=serato_running(raw);s.usb_ready=sl3::setup_usb::driver_running();
        s.allowed=eligibility(after.text(L"archive"),after.object(L"native").text(L"state"),s.running,s.usb_ready);}
    return code;
}
struct ActionResult {int code=1;sl3::setup_result::Capture capture;std::string transfer_error;};
ActionResult elevated_action(const State& s,const std::vector<std::wstring>& selected){
    sl3::setup_result::Server server;auto args=selected;
    args.insert(args.end(),{L"--result-pipe",server.name,L"--result-server-pid",std::to_wstring(GetCurrentProcessId())});
    const auto executable=local_path(s.launcher);const auto parameters=command_line(args);const auto directory=executable.parent_path().native();
    SHELLEXECUTEINFOW info{};info.cbSize=sizeof(info);info.fMask=SEE_MASK_NOCLOSEPROCESS|SEE_MASK_NOASYNC;
    info.lpVerb=L"runas";info.lpFile=executable.c_str();info.lpParameters=parameters.c_str();info.lpDirectory=directory.c_str();info.nShow=SW_HIDE;
    if(!ShellExecuteExW(&info))throw WinError("Start approved native setup action");Handle process(info.hProcess);require(process.value!=nullptr,"Launched setup process identity required");
    ActionResult result;
    try{result.capture=server.collect(process.value);}catch(const std::exception& error){result.transfer_error=error.what();}
    server.close(); // If collection fails, release the diagnostic writer; never terminate the transaction.
    require(WaitForSingleObject(process.value,INFINITE)==WAIT_OBJECT_0,"Wait for the actual administrator action");DWORD code=1;
    require(GetExitCodeProcess(process.value,&code)!=FALSE,"Read actual administrator action exit");result.code=int(code);return result;
}
std::string result_text(const State& s,const ActionResult& result){
    return "SL3 setup diagnostic (not a recovery authorization)\nexperiment_sha256="+utf8(s.plan_sha)+
        "\nprocess_exit_code="+std::to_string(result.code)+"\nwriter_authenticated="+(result.capture.authenticated?"true":"false")+
        "\nover_limit="+(result.capture.over_limit?"true":"false")+"\nchannel_error="+std::to_string(result.capture.error)+
        "\ntransfer_error="+result.transfer_error+"\n\nAdministrator output:\n"+result.capture.bytes;
}
fs::path preserve_result(const State& s,const std::string& result){
    const auto directory=local_path(s.plan).parent_path()/(L"ui-action-"+sl3::setup_result::token());
    require(CreateDirectoryW(directory.c_str(),nullptr)!=FALSE,"Create fresh local diagnostic directory");
    const auto path=directory/L"administrator-result.txt";
    Handle file(CreateFileW(path.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_FLAG_OPEN_REPARSE_POINT,nullptr));
    require(file.value!=INVALID_HANDLE_VALUE,"Create new local diagnostic result");DWORD written=0;
    require(result.size()<=1024*1024 && WriteFile(file.value,result.data(),DWORD(result.size()),&written,nullptr) && written==result.size() && FlushFileBuffers(file.value),"Preserve complete local diagnostic result");return path;
}
int apply(State& s,int action){
    auto code=inspect(s);if(code)return code;
    require(action==install?s.allowed.install:s.allowed.restore,"Current setup state does not admit this action");
    std::vector<Handle> leases;pin(leases,local_path(s.launcher),config::launcher_sha);pin(leases,local_path(s.plan),s.plan_sha,65536);
    const auto operation=elevated_action(s,arguments(s,action==install?L"--apply-experiment":L"--restore-experiment"));
    const auto report=result_text(s,operation);std::string persistence_error;
    {std::lock_guard<std::mutex> lock(s.mutex);s.output.clear();++s.log_revision;}s.append(report.data(),report.size());
    try{const auto saved=std::string("\nFull administrator result saved: ")+utf8(preserve_result(s,report).native())+"\n";s.append(saved.data(),saved.size());}
    catch(const std::exception& error){persistence_error=error.what();s.append(persistence_error.data(),persistence_error.size());}
    code=inspect(s,true);if(operation.code)return operation.code;if(code)return code;
    require(operation.capture.authenticated && !operation.capture.over_limit && !operation.capture.error && operation.transfer_error.empty() && persistence_error.empty(),"Administrator result was not completely received and preserved; retain the observed state");
    const JsonObject actual(operation.capture.bytes);require(actual.text(L"schema")==L"sl3.on-demand-test-action.v1" && actual.text(L"action")==std::wstring(action==install?L"setup":L"restore"),"Matching administrator result required");
    require(action==install?s.allowed.installed:s.allowed.clean,"Command finished but observed setup state differs");return 0;
}
void begin(State& s,int action){
    if(s.preview || s.busy || (action==install && !s.allowed.install) || (action==restore && !s.allowed.restore))return;
    if(s.worker.joinable())s.worker.join();s.allowed={};s.busy=true;s.action=action;s.finished=false;s.code=1;
    text(s.progress,action==check?L"Checking your setup…":action==install?L"Installing the compatibility build…":L"Restoring the original setup…");
    text(s.description,action==check?L"This check can prepare local setup files. It does not change Serato or open the SL3.":L"Windows may ask for administrator approval. Keep this window open until the action finishes.");enable(s);
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
        s->instructions=control(L"STATIC",L"Phase and timecode vinyl share the SL3 driver.\r\nDiagnostic audio sessions have a 10-minute limit.\r\nNormal Serato 5.0 startup still needs a live test.",0);
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
            else if(s->action==restore && s->allowed.clean){text(s->progress,L"Original setup restored");text(s->description,L"The compatibility files and temporary driver registration have been removed.");}
            else if(!s->usb_ready){text(s->progress,L"UsbDk is unavailable");text(s->description,L"The UsbDk USB driver must be installed and running.\r\nChoose Check setup again when UsbDk is ready.");}
            else if(s->allowed.installed){text(s->progress,L"Installed — ready for a Serato startup test");text(s->description,L"Open Serato normally to test the SL3.\r\nThis window does not start or control Serato.");}
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
