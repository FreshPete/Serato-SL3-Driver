#pragma once
// Test-only registration-free activation. Never writes a registry key or installs a DLL.
#include <Windows.h>
#include <objbase.h>
#include <filesystem>
#include <stdexcept>
#include <string>

namespace sl3::test {
class ComApartment {
public:
    explicit ComApartment(DWORD model){
        if(FAILED(CoInitializeEx(nullptr,model)))throw std::runtime_error("COM apartment initialization");
    }
    ~ComApartment(){CoUninitialize();}
    ComApartment(const ComApartment&)=delete;
    ComApartment& operator=(const ComApartment&)=delete;
};
class ComActivation {
    std::filesystem::path manifest_;
    HANDLE context_=INVALID_HANDLE_VALUE;
    ULONG_PTR cookie_=0;
public:
    explicit ComActivation(const std::filesystem::path& library){
        // Fixed test DLL names only: do not interpolate arbitrary XML/path text.
        const auto name=library.filename().string();
        if(name.empty() || name.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")!=std::string::npos)
            throw std::runtime_error("Activation fixture DLL name");
        GUID id{};wchar_t guid[40]{};
        if(FAILED(CoCreateGuid(&id)) || !StringFromGUID2(id,guid,40))throw std::runtime_error("Activation fixture identity");
        // The root manifest's file entries resolve beside the manifest. A
        // separate temp folder plus lpAssemblyDirectory did not resolve this
        // root assembly on the tested host (CoCreateInstance: 0x8007007e).
        manifest_=library.parent_path()/(std::wstring(L"sl3-com-")+guid+L".manifest");
        const std::string xml="<assembly xmlns=\"urn:schemas-microsoft-com:asm.v1\" manifestVersion=\"1.0\">"
            "<assemblyIdentity name=\"SL3.ActivationFixture\" version=\"1.0.0.0\" type=\"win32\" processorArchitecture=\"amd64\"/>"
            "<file name=\""+name+"\"><comClass clsid=\"{5A551CD0-F83E-48EB-8B9D-8614E07852FE}\" threadingModel=\"Both\"/></file></assembly>";
        HANDLE file=CreateFileW(manifest_.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
        if(file==INVALID_HANDLE_VALUE)throw std::runtime_error("Create new activation manifest");
        DWORD written=0;const bool good=WriteFile(file,xml.data(),DWORD(xml.size()),&written,nullptr) && written==xml.size();
        CloseHandle(file);
        if(!good){std::filesystem::remove(manifest_);throw std::runtime_error("Write activation manifest");}
        const auto directory=library.parent_path().native();
        ACTCTXW spec{};spec.cbSize=sizeof(spec);spec.lpSource=manifest_.c_str();
        spec.dwFlags=ACTCTX_FLAG_ASSEMBLY_DIRECTORY_VALID;spec.lpAssemblyDirectory=directory.c_str();
        context_=CreateActCtxW(&spec);
        if(context_==INVALID_HANDLE_VALUE || !ActivateActCtx(context_,&cookie_)){
            if(context_!=INVALID_HANDLE_VALUE)ReleaseActCtx(context_);
            std::filesystem::remove(manifest_);throw std::runtime_error("Create/activate registration-free COM context");
        }
    }
    ~ComActivation(){
        if(cookie_)DeactivateActCtx(0,cookie_);
        if(context_!=INVALID_HANDLE_VALUE)ReleaseActCtx(context_);
        std::error_code error;std::filesystem::remove(manifest_,error);
    }
    ComActivation(const ComActivation&)=delete;
    ComActivation& operator=(const ComActivation&)=delete;
};
}
