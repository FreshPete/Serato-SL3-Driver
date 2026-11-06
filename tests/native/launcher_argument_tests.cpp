#define SL3_LAUNCHER_ARGUMENT_TEST
#include "../../src/installer/NativeSessionLauncher.cpp"
int wmain(){
    const std::vector<std::wstring> values={L"fixture.exe",L"",L"plain",L"two words",L"trailing\\",L"embedded\"quote",
        L"slashes\\\\\"quote",L"C:\\with spaces; dollar$(literal) 会话\\session.json"};
    int count=0;const auto command=sl3::launcher::command_line(values);auto decoded=CommandLineToArgvW(command.c_str(),&count);
    if(!decoded || count!=int(values.size()))return 1;
    bool equal=true;for(int i=0;i<count;++i)equal=equal && values[std::size_t(i)]==decoded[i];LocalFree(decoded);
    std::cout<<"Native Windows argument round-trip: "<<values.size()<<" cases\n";return equal?0:1;
}
