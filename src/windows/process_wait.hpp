#pragma once
#include "windows/worker_process.hpp"
#include <stdexcept>

namespace sl3::worker {
// Shared liveness reference only: no launch, termination or job operations.
// Optional lease retains the original owned Process for the private-worker path.
class ProcessWait final {
public:
    static std::shared_ptr<ProcessWait> duplicate(HANDLE process,std::shared_ptr<const void> lease={}){
        HANDLE copy=nullptr;
        if(!DuplicateHandle(GetCurrentProcess(),process,GetCurrentProcess(),&copy,
            SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,0))throw std::runtime_error("Duplicate wait-only worker reference");
        if(!GetProcessId(copy)){CloseHandle(copy);throw std::invalid_argument("Worker reference is not a process");}
        ProcessWait* result=nullptr;
        try{result=new ProcessWait(copy,std::move(lease));}catch(...){CloseHandle(copy);throw;}
        return std::shared_ptr<ProcessWait>(result);
    }
    static std::shared_ptr<ProcessWait> owned(std::shared_ptr<Process> process){
        if(!process)throw std::invalid_argument("Missing owned worker");
        const auto handle=process->process_handle();return duplicate(handle,std::move(process));
    }
    ~ProcessWait(){CloseHandle(handle_);}
    ProcessWait(const ProcessWait&)=delete;ProcessWait& operator=(const ProcessWait&)=delete;
    HANDLE handle() const noexcept {return handle_;} // Borrowed; do not close.
private:
    HANDLE handle_;std::shared_ptr<const void> lease_;
    ProcessWait(HANDLE handle,std::shared_ptr<const void> lease):handle_(handle),lease_(std::move(lease)){}
};
}
