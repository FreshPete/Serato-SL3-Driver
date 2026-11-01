#include "windows/startup_journal.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
void require(bool value){if(!value)throw std::runtime_error("Startup journal invariant failed");}
int main(){
    try{
        sl3::diagnostic::StartupJournal disabled({});
        SetLastError(1234);disabled.mark("disabled");require(GetLastError()==1234);
        const auto path=std::filesystem::temp_directory_path()/(L"sl3-journal-"+std::to_wstring(GetCurrentProcessId())+L"-"+std::to_wstring(GetTickCount64())+L".tsv");
        {
            sl3::diagnostic::StartupJournal journal(path);
            SetLastError(4321);journal.mark("redirect_start.enter");require(GetLastError()==4321);
            HANDLE reader=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,0,nullptr);
            require(reader!=INVALID_HANDLE_VALUE);char buffer[256]{};DWORD read=0;
            const bool ok=ReadFile(reader,buffer,sizeof(buffer)-1,&read,nullptr)!=FALSE;CloseHandle(reader);
            require(ok && read && std::string(buffer,read).find("\tredirect_start.enter\n")!=std::string::npos);
            bool rejected=false;try{sl3::diagnostic::StartupJournal duplicate(path);}catch(...){rejected=true;}
            require(rejected);journal.mark("redirect_start.return");
        }
        std::ifstream input(path);std::string first,second,extra;require(bool(std::getline(input,first)) && bool(std::getline(input,second)) && !std::getline(input,extra));
        require(first.find("redirect_start.enter")!=std::string::npos && second.find("redirect_start.return")!=std::string::npos);
        input.close();require(std::filesystem::remove(path));
        bool rejected=false;try{sl3::diagnostic::StartupJournal relative(L"relative.tsv");}catch(...){rejected=true;}require(rejected);
        std::cout<<"Disabled logging, durable readable entry markers, error preservation and no overwrite passed\n";return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
