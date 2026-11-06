#define SL3_SETUP_WINDOW_TEST
#include "../../src/installer/SetupWindow.cpp"
#include <iostream>
int main(){
    using namespace sl3::setup_window;
    try{
        unsigned cases=0;
        const auto clean=eligibility(L"original",L"absent");require(clean.clean && clean.install && !clean.restore && !clean.installed,"Clean setup eligibility");++cases;
        const auto installed=eligibility(L"installed",L"installed");require(installed.installed && installed.restore && !installed.install,"Installed setup eligibility");++cases;
        const auto partial=eligibility(L"original",L"installed");require(partial.install && partial.restore && !partial.clean,"Partial install retry/recovery eligibility");++cases;
        const auto running=eligibility(L"original",L"absent",true);require(!running.install && !running.restore,"Running Serato must disable install/restore");++cases;
        checked(RoInitialize(RO_INIT_SINGLETHREADED),"Initialize own result-parser test");
        require(serato_running("{\"after\":{\"seratoRunning\":true}}") && !serato_running("{\"after\":{\"seratoRunning\":false}}"),"Typed running-state parsing");RoUninitialize();++cases;
        for(const auto& pair:std::vector<std::pair<std::wstring,std::wstring>>{{L"conflict",L"absent"},{L"original",L"conflict"},{L"unknown",L"installed"}}){
            const auto state=eligibility(pair.first,pair.second);require(!state.install && !state.restore,"Unrecognized state must not offer privileged action");++cases;}
        State preview;preview.preview=true;const auto window=create(preview,GetModuleHandleW(nullptr));
        require(!preview.busy && !preview.worker.joinable() && !IsWindowEnabled(preview.start_button) && !IsWindowEnabled(preview.recover_button),"Opening preview is inert");++cases;
        begin(preview,install);begin(preview,restore);begin(preview,check);require(!preview.busy && !preview.worker.joinable(),"Preview cannot dispatch any command");++cases;
        message(window,WM_CLOSE,0,0);require(!IsWindow(window),"Idle preview closes");++cases;
        State live;const auto live_window=create(live,GetModuleHandleW(nullptr));require(!live.busy && !live.worker.joinable() && IsWindowEnabled(live.check_button) && !IsWindowEnabled(live.start_button),"Opening ordinary setup does not run a command");++cases;
        auto font_face=[&](HWND control){const auto dc=GetDC(live_window);require(dc!=nullptr,"Read own window font metrics");
            const auto previous=SelectObject(dc,reinterpret_cast<HFONT>(SendMessageW(control,WM_GETFONT,0,0)));std::array<wchar_t,LF_FACESIZE> name{};
            const auto count=GetTextFaceW(dc,int(name.size()),name.data());SelectObject(dc,previous);ReleaseDC(live_window,dc);require(count>0,"Resolve actual own control font");return std::wstring(name.data());};
        const auto body_face=font_face(live.description),title_face=font_face(live.heading);
        std::cout<<"Resolved fonts: body="<<utf8(body_face)<<", title="<<utf8(title_face)<<'\n';
        begin(live,check);require(live.busy && !IsWindowEnabled(live.check_button) && !IsWindowEnabled(live.start_button),"Busy state disables commands");++cases;
        message(live_window,WM_CLOSE,0,0);require(IsWindow(live_window),"Closing cannot interrupt an active check");++cases;
        const auto began=GetTickCount64();while(live.busy){message(live_window,WM_TIMER,0,0);require(GetTickCount64()-began<30000,"Read-only setup check deadline");Sleep(10);}
        require(live.code==0 && live.allowed.clean && live.allowed.install && !live.allowed.restore && IsWindowEnabled(live.start_button),"Actual native read-only check produces install eligibility");++cases;
        {ActionResult observed;observed.code=1;observed.capture.authenticated=true;observed.capture.bytes="fixture failure report";
            const auto report=result_text(observed);const auto saved=preserve_result(report);std::vector<Handle> leases;
            Handle read(CreateFileW(saved.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,0,nullptr));require(read.value!=INVALID_HANDLE_VALUE,"Read owned diagnostic result");
            require(read_capsule(read.value)==report,"Saved ordinary-user result preserves exact diagnostic bytes");++cases;
            const std::string previous="retained administrator failure\n";live.append(previous.data(),previous.size());
            checked(RoInitialize(RO_INIT_SINGLETHREADED),"Initialize retained-result parser");const auto code=inspect(live,true);RoUninitialize();
            require(code==0 && live.output.find(previous)!=std::string::npos && live.output.find("Post-action observation:")!=std::string::npos,"Postcheck must not erase the administrator diagnostic");++cases;}
        message(live_window,WM_CLOSE,0,0);require(!IsWindow(live_window),"Completed window closes normally");++cases;
        std::cout<<"{\"schema\":\"sl3.setup-window-tests.v1\",\"passed\":true,\"cases\":"<<cases<<",\"privilegedActionsExecuted\":false,\"seratoLaunched\":false,\"nativeDeviceAccess\":false}\n";return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
