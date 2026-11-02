#include "asio/com_identity.hpp"
#include "com_activation_fixture.hpp"
#include "iasiodrv.h"
#include <array>
#include <cstring>
#include <iostream>

static void require(bool value,const char* message){if(!value)throw std::runtime_error(message);}
int wmain(int argc,wchar_t** argv){
    try{
        require(argc==3,"Production DLL and sta|mta required");
        const std::wstring mode=argv[2];require(mode==L"sta" || mode==L"mta","Explicit apartment required");
        const auto library=std::filesystem::absolute(argv[1]);
        require(std::filesystem::is_regular_file(library) && !std::filesystem::exists(library.parent_path()/L"sl3-asio.conf"),
                "Absent adjacent configuration required: no possible hardware access");
        sl3::test::ComApartment apartment(mode==L"sta"?COINIT_APARTMENTTHREADED:COINIT_MULTITHREADED);
        sl3::test::ComActivation activation(library);
        for(unsigned i=0;i<3;++i){
            IASIO* device=nullptr;
            const auto result=CoCreateInstance(sl3::asio::driver_clsid,nullptr,CLSCTX_INPROC_SERVER,
                sl3::asio::driver_clsid,reinterpret_cast<void**>(&device));
            if(result!=S_OK)std::cerr<<"CoCreateInstance HRESULT 0x"<<std::hex<<static_cast<unsigned long>(result)<<std::dec<<"\n";
            require(result==S_OK && device,"Windows CoCreateInstance using ASIO class-as-IID");
            IUnknown* identity=nullptr;
            require(device->QueryInterface(IID_IUnknown,reinterpret_cast<void**>(&identity))==S_OK &&
                    identity==static_cast<IUnknown*>(device),"Canonical COM identity");
            identity->Release();
            // Establish that Windows selected this exact DLL, rather than a registry fallback.
            HMODULE module=nullptr;const auto vtable=*reinterpret_cast<void***>(device);
            require(GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                    reinterpret_cast<const wchar_t*>(vtable[0]),&module)!=FALSE,"Activated implementation module");
            std::array<wchar_t,32768> path{};const auto size=GetModuleFileNameW(module,path.data(),DWORD(path.size()));
            require(size && size<path.size() && std::filesystem::equivalent(library,std::filesystem::path(path.data())),"Exact intended production DLL activated");
            std::array<char,32> name{};device->getDriverName(name.data());
            require(std::strcmp(name.data(),"SL3 Rebuild Development")==0 && device->init(nullptr)==ASIOFalse,"Honest unavailable production device");
            long inputs=73,outputs=74;
            require(device->getChannels(&inputs,&outputs)==ASE_NotPresent && inputs==73 && outputs==74,"Unavailable metadata preserves outputs");
            require(device->Release()==0,"CoCreateInstance object retirement");
        }
        CoFreeUnusedLibrariesEx(0,0);
        std::wcout<<L"CoCreateInstance "<<mode<<L": three production objects; exact DLL; unavailable; no registration or USB\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
