#pragma once
#include "windows/diagnostic.hpp"
#include <cstdio>
#include <filesystem>

namespace sl3::diagnostic {
// Optional isolated-worker startup/cleanup telemetry, never an audio log.
// One control-thread writer; fixed marker strings only. Each record is written
// through before the operation it describes. Failure contains this worker.
class StartupJournal final {
    HANDLE file_=INVALID_HANDLE_VALUE;
public:
    explicit StartupJournal(const std::filesystem::path& path) {
        if(path.empty())return;
        const auto name=path.native();const auto drive=path.root_name().native();
        if(!path.is_absolute() || drive.size()!=2 || drive[1]!=L':' ||
           name.find_first_of(L"\"\r\n")!=std::wstring::npos || name.find(L'\0')!=std::wstring::npos ||
           name.find(L':',2)!=std::wstring::npos || GetDriveTypeW(path.root_path().c_str())!=DRIVE_FIXED)
            throw std::invalid_argument("Startup journal requires an absolute local fixed-drive path");
        file_=CreateFileW(path.c_str(),GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_NEW,
                         FILE_ATTRIBUTE_NORMAL|FILE_FLAG_WRITE_THROUGH,nullptr);
        if(file_==INVALID_HANDLE_VALUE)failed("Create new startup journal");
    }
    ~StartupJournal(){if(file_!=INVALID_HANDLE_VALUE)CloseHandle(file_);}
    StartupJournal(const StartupJournal&)=delete;
    StartupJournal& operator=(const StartupJournal&)=delete;
    void mark(const char* stage) noexcept {
        if(file_==INVALID_HANDLE_VALUE)return;
        const auto saved=GetLastError();char line[192]{};
        const auto count=std::snprintf(line,sizeof(line),"%llu\t%lu\t%s\n",
            static_cast<unsigned long long>(GetTickCount64()),static_cast<unsigned long>(GetCurrentProcessId()),stage);
        DWORD written=0;
        if(count<=0 || static_cast<std::size_t>(count)>=sizeof(line) ||
           !WriteFile(file_,line,DWORD(count),&written,nullptr) || written!=DWORD(count))fail_stop();
        SetLastError(saved);
    }
};
}
