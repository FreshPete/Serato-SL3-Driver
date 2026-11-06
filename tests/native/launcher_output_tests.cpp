// Real relay/child process fixture. No application, registry, elevation or USB.
#define SL3_LAUNCHER_ARGUMENT_TEST
#include "../../src/installer/NativeSessionLauncher.cpp"

int wmain(int argc,wchar_t** argv){
    try{
        if(argc==3 && std::wstring(argv[1])==L"--emit"){
            std::cout<<"child-first\n"<<std::flush;
            std::cerr<<"child-error-first\n"<<std::flush;
            const auto deadline=GetTickCount64()+15000;
            while(GetFileAttributesW(argv[2])==INVALID_FILE_ATTRIBUTES){
                if(GetTickCount64()>=deadline)return 4;
                Sleep(10);
            }
            std::cout<<"child-last\n"<<std::flush;
            std::cerr<<"child-error-last\n"<<std::flush;return 7;
        }
        if(argc==2 && std::wstring(argv[1])==L"--overflow-child"){
            const std::string block(8192,'x');
            for(int i=0;i<520;++i)std::cout.write(block.data(),block.size());
            std::cout.flush();std::cerr<<"overflow-child-finished\n"<<std::flush;return 0;
        }
        if(argc==2 && std::wstring(argv[1])==L"--no-console-child"){
            std::cout<<"unattached-output\n"<<std::flush;
            std::cerr<<"unattached-error\n"<<std::flush;return 9;
        }
        if(argc==2 && std::wstring(argv[1])==L"--no-console"){
            std::wstring image(32768,L'\0');auto length=GetModuleFileNameW(nullptr,image.data(),DWORD(image.size()));
            sl3::launcher::require(length && length<image.size(),"Fixture image unavailable");image.resize(length);
            sl3::launcher::require(SetStdHandle(STD_OUTPUT_HANDLE,nullptr)!=FALSE,"Detach fixture stdout");
            sl3::launcher::require(SetStdHandle(STD_ERROR_HANDLE,INVALID_HANDLE_VALUE)!=FALSE,"Detach fixture stderr");
            return sl3::launcher::run_process(image,{L"--no-console-child"},std::filesystem::current_path(),false);
        }
        if(argc==3 && std::wstring(argv[1])==L"--relay"){
            std::wstring image(32768,L'\0');auto length=GetModuleFileNameW(nullptr,image.data(),DWORD(image.size()));
            sl3::launcher::require(length && length<image.size(),"Fixture image unavailable");image.resize(length);
            return sl3::launcher::run_process(image,{L"--emit",argv[2]},std::filesystem::current_path(),false);
        }
        if(argc==2 && std::wstring(argv[1])==L"--overflow"){
            std::wstring image(32768,L'\0');auto length=GetModuleFileNameW(nullptr,image.data(),DWORD(image.size()));
            sl3::launcher::require(length && length<image.size(),"Fixture image unavailable");image.resize(length);
            return sl3::launcher::run_process(image,{L"--overflow-child"},std::filesystem::current_path(),false);
        }
        return 2;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
