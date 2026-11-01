#pragma once
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <sddl.h>

namespace sl3::worker {
// Object existence excludes overlapping cooperating redirect owners. It is
// not a USB recovery barrier, a kernel-detachment proof or an abandoned-owner
// recovery mechanism. No waiting, signalling or ownership handoff is allowed.
class RedirectOwner final {
    HANDLE handle_=nullptr;
    bool attempted_=false;
    DWORD error_=ERROR_SUCCESS;
public:
    inline static constexpr wchar_t device_name[]=L"Global\\SL3Rebuild.Redirect.1cc5.0001.SL3.01.00.v1";
    RedirectOwner()=default;
    RedirectOwner(const RedirectOwner&)=delete;
    RedirectOwner& operator=(const RedirectOwner&)=delete;
    ~RedirectOwner(){close();}
    // The optional name is for private software fixtures. Production always
    // uses the fixed real-device name, never a caller/CLI-supplied name.
    bool acquire(const wchar_t* name=device_name) noexcept {
        if(attempted_){error_=ERROR_INVALID_STATE;return false;}
        attempted_=true;
        if(!name || !*name){error_=ERROR_INVALID_NAME;return false;}
        PSECURITY_DESCRIPTOR descriptor=nullptr;
        // Other authenticated users may open only to observe existence. This
        // grants no event modification, USB access or command channel. An
        // existing inaccessible or wrong-type object is also a hard refusal.
        if(!ConvertStringSecurityDescriptorToSecurityDescriptorW(
               L"D:P(A;;GA;;;SY)(A;;0x00100000;;;AU)",SDDL_REVISION_1,&descriptor,nullptr)){
            error_=GetLastError();return false;
        }
        SECURITY_ATTRIBUTES attributes{sizeof(SECURITY_ATTRIBUTES),descriptor,FALSE};
        SetLastError(ERROR_SUCCESS);
        const auto candidate=CreateEventExW(&attributes,name,0,SYNCHRONIZE);
        const auto status=GetLastError();LocalFree(descriptor);
        if(!candidate){error_=status?status:ERROR_GEN_FAILURE;return false;}
        if(status==ERROR_ALREADY_EXISTS){CloseHandle(candidate);error_=ERROR_BUSY;return false;}
        handle_=candidate;error_=ERROR_SUCCESS;return true;
    }
    bool close() noexcept {
        if(!handle_)return true;
        if(!CloseHandle(handle_)){error_=GetLastError();return false;}
        handle_=nullptr;return true;
    }
    DWORD error() const noexcept{return error_;}
};
}
