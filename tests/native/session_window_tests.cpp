#define SL3_SESSION_WINDOW_TEST
#include "../../src/installer/SessionWindow.cpp"
#include <fstream>

namespace {
using namespace sl3::window;
void pump(State& state){
    MSG message{};
    while(PeekMessageW(&message,nullptr,0,0,PM_REMOVE)){
        if(message.message!=WM_QUIT){TranslateMessage(&message);DispatchMessageW(&message);}
    }
    if(state.window && IsWindow(state.window))SendMessageW(state.window,WM_TIMER,1,0);
}
void wait(State& state){
    const auto began=GetTickCount64();
    while(state.busy){pump(state);require(GetTickCount64()-began<60000,"Read-only GUI fixture deadline");Sleep(25);}
    require(state.code==0,"Read-only GUI action failed");
}
HWND create(State& state){
    const auto window=CreateWindowExW(WS_EX_CONTROLPARENT,L"SL3WindowFixture",L"SL3 window read-only fixture",
        WS_OVERLAPPEDWINDOW,0,0,780,500,nullptr,nullptr,GetModuleHandleW(nullptr),&state);
    require(window!=nullptr,"Create fixture window");return window;
}
void check_bounds(State& state){
    RECT client{};GetClientRect(state.window,&client);
    for(const auto item:{state.heading,state.progress,state.description,state.instructions,state.check_button,
                         state.start_button,state.status_button,state.recover_button,state.detail_button}){
        RECT bounds{};require(GetWindowRect(item,&bounds)!=FALSE,"Read control bounds");
        MapWindowPoints(nullptr,state.window,reinterpret_cast<POINT*>(&bounds),2);
        require(bounds.left>=0 && bounds.top>=0 && bounds.right<=client.right && bounds.bottom<=client.bottom,
                "Control escaped the client area");
    }
}
void capture(State& state,const sl3::launcher::fs::path& path){
    require(!sl3::launcher::fs::exists(path),"New screenshot file required");
    RECT bounds{};GetClientRect(state.window,&bounds);const int width=bounds.right,height=bounds.bottom;
    const auto screen=GetDC(state.window);const auto memory=CreateCompatibleDC(screen);
    BITMAPINFO info{};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biWidth=width;info.bmiHeader.biHeight=-height;
    info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=BI_RGB;
    void* pixels=nullptr;const auto bitmap=CreateDIBSection(screen,&info,DIB_RGB_COLORS,&pixels,nullptr,0);
    require(memory && bitmap && pixels,"Create fixture capture");const auto previous=SelectObject(memory,bitmap);
    // Ask this fixture and its standard controls to paint their own client.
    // This does not read a screen or another application's pixels.
    SendMessageW(state.window,WM_PRINT,WPARAM(memory),PRF_CLIENT|PRF_CHILDREN|PRF_ERASEBKGND);
    const auto* colours=static_cast<const DWORD*>(pixels);bool captured=false;
    for(int index=1;index<width*height;++index)if(colours[index]!=colours[0]){captured=true;break;}
    BITMAPFILEHEADER file{};file.bfType=0x4d42;file.bfOffBits=sizeof(file)+sizeof(BITMAPINFOHEADER);
    file.bfSize=file.bfOffBits+DWORD(width*height*4);
    if(captured){std::ofstream stream(path,std::ios::binary);stream.write(reinterpret_cast<const char*>(&file),sizeof(file));
        stream.write(reinterpret_cast<const char*>(&info.bmiHeader),sizeof(info.bmiHeader));
        stream.write(static_cast<const char*>(pixels),std::streamsize(width)*height*4);require(stream.good(),"Write fixture screenshot");}
    SelectObject(memory,previous);DeleteObject(bitmap);DeleteDC(memory);ReleaseDC(state.window,screen);
    require(captured,"Render fixture screenshot");
}
}
int wmain(int argc,wchar_t** argv){
    using namespace sl3::window;
    try{
        require(argc==2,"Fresh screenshot output prefix required");
        SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
        WNDCLASSW kind{};kind.lpfnWndProc=procedure;kind.hInstance=GetModuleHandleW(nullptr);kind.lpszClassName=L"SL3WindowFixture";
        kind.hCursor=LoadCursorW(nullptr,IDC_ARROW);kind.hbrBackground=GetSysColorBrush(COLOR_WINDOW);
        require(RegisterClassW(&kind)!=0,"Register fixture window");
        State preview;preview.preview=true;create(preview);
        require(!IsWindowEnabled(preview.check_button) && !IsWindowEnabled(preview.start_button),"Preview actions must be disabled");
        begin(preview,check);require(!preview.busy,"Preview must not start a command");DestroyWindow(preview.window);
        State state;create(state);pump(state);check_bounds(state);
        require(!state.ready && !IsWindowEnabled(state.start_button),"Start requires setup check");
        begin(state,start);require(!state.busy && !state.used,"Unchecked start must be refused");
        capture(state,std::wstring(argv[1])+L"-initial.bmp");
        begin(state,check);require(state.busy && !IsWindowEnabled(state.check_button),"Actions must be disabled during work");
        SendMessageW(state.window,WM_CLOSE,0,0);require(IsWindow(state.window)!=FALSE,"Busy window close must be refused");
        wait(state);require(state.ready && IsWindowEnabled(state.start_button),"Passing check enables start");
        capture(state,std::wstring(argv[1])+L"-ready.bmp");
        begin(state,status);wait(state);require(state.ready,"Status should preserve checked state");
        // A consumed prepared session cannot start twice, even after rechecking.
        state.used=true;enable(state);require(!IsWindowEnabled(state.start_button),"Consumed start disabled");
        begin(state,start);require(!state.busy,"Consumed start handler must refuse");
        begin(state,check);wait(state);require(!state.ready && !IsWindowEnabled(state.start_button),"Recheck cannot renew a consumed session");
        wchar_t description[512]{};GetWindowTextW(state.description,description,512);
        require(std::wstring(description).find(L"already been used")!=std::wstring::npos,"Consumed recheck must explain the new-session requirement");
        capture(state,std::wstring(argv[1])+L"-consumed.bmp");
        SendMessageW(state.detail_button,BM_SETCHECK,BST_CHECKED,0);
        SendMessageW(state.window,WM_COMMAND,MAKEWPARAM(details,BN_CLICKED),0);pump(state);check_bounds(state);
        require(state.expanded && !state.output.empty(),"Diagnostic details must be available");
        capture(state,std::wstring(argv[1])+L"-details.bmp");
        SendMessageW(state.detail_button,BM_SETCHECK,BST_UNCHECKED,0);
        SendMessageW(state.window,WM_COMMAND,MAKEWPARAM(details,BN_CLICKED),0);pump(state);check_bounds(state);
        SendMessageW(state.window,WM_CLOSE,0,0);require(!IsWindow(state.window),"Idle window closes normally");
        std::cout<<"{\"schema\":\"sl3.session-window-tests.v1\",\"passed\":true,\"readOnlyActions\":3,"
                   "\"previewDisarmed\":true,\"uncheckedAndConsumedStartRefused\":true,\"busyCloseRefused\":true,"
                   "\"layoutBoundsChecked\":true,\"fixtureWindowRendered\":true,\"seratoStarted\":false,\"deviceOpened\":false}\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
