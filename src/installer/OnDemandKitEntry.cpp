// Native verification before fixed setup-only Python dispatch. No mutable action.
#define SL3_LAUNCHER_ARGUMENT_TEST
#include "NativeSessionLauncher.cpp"
#include "setup_config.hpp"
#include <set>

namespace sl3::setup {
using namespace sl3::launcher;
void ordinary(){
    Handle token;require(OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token.value)!=FALSE,"Read setup token");
    TOKEN_ELEVATION elevation{};DWORD size=0;
    require(GetTokenInformation(token.value,TokenElevation,&elevation,sizeof(elevation),&size)!=FALSE && !elevation.TokenIsElevated,
            "Verify and prepare this kit as an ordinary user; no approval prompt is requested");
}
void pin_directory(std::vector<Handle>& leases,std::set<fs::path>& seen,const fs::path& directory){
    auto current=directory.root_path();
    for(const auto& part:directory.relative_path()){
        current/=part;if(!seen.insert(current).second)continue;
        Handle handle(CreateFileW(current.c_str(),FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,
                                  FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,nullptr));
        require(handle.value!=INVALID_HANDLE_VALUE,"Retain setup input directory");BY_HANDLE_FILE_INFORMATION info{};
        require(GetFileInformationByHandle(handle.value,&info)!=FALSE && (info.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY) &&
                !(info.dwFileAttributes&FILE_ATTRIBUTE_REPARSE_POINT),"Setup input directories must not redirect");
        leases.push_back(std::move(handle));
    }
}
void pin_input(std::vector<Handle>& leases,std::set<fs::path>& directories,const fs::path& path,const std::wstring& hash,ULONGLONG bytes){
    pin_directory(leases,directories,path.parent_path());
    Handle file(CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_SEQUENTIAL_SCAN,nullptr));
    require(file.value!=INVALID_HANDLE_VALUE,"Open reviewed setup input");BY_HANDLE_FILE_INFORMATION info{};LARGE_INTEGER length{};
    require(GetFileInformationByHandle(file.value,&info)!=FALSE && !(info.dwFileAttributes&(FILE_ATTRIBUTE_REPARSE_POINT|FILE_ATTRIBUTE_DIRECTORY)) &&
            GetFileType(file.value)==FILE_TYPE_DISK && GetFileSizeEx(file.value,&length)!=FALSE && length.QuadPart>=0 && ULONGLONG(length.QuadPart)==bytes,
            "Setup input size or file type differs");
    require(hash_file(file.value)==hash,"Reviewed setup input hash differs before helper execution");leases.push_back(std::move(file));
}
int dispatch(int argc,wchar_t** argv){
    if(argc==1 || (argc==2 && std::wstring(argv[1])==L"--help")){
        std::cout<<"SL3 setup engineering entry: --verify|--plan|--prepare --kit ABSOLUTE_DIRECTORY --app ABSOLUTE_SERATO_EXE\n"
                 <<"No installer, elevation, Serato launch or device operation is exposed.\n";return 0;
    }
    require(argc==6 && std::wstring(argv[2])==L"--kit" && std::wstring(argv[4])==L"--app","Exact reviewed setup arguments required");
    const std::wstring action=argv[1];require(action==L"--verify" || action==L"--plan" || action==L"--prepare","Only verification and offline preparation are supported");ordinary();
    const auto root=local_path(argv[3]).lexically_normal(),application=local_path(argv[5]).lexically_normal();
    require(root.native().find(L';')==std::wstring::npos && GetDriveTypeW(root.root_path().c_str())==DRIVE_FIXED,"Local fixed-drive kit without semicolons required");
    std::vector<Handle> leases;std::set<fs::path> directories;pin_directory(leases,directories,root);
    std::set<std::wstring> expected;
    for(const auto& item:release::files){
        expected.insert(item.name);pin_input(leases,directories,child_path(root,item.name),item.sha,item.bytes);
    }
    std::set<std::wstring> observed;
    for(fs::recursive_directory_iterator it(root),end;it!=end;++it){
        const auto attributes=GetFileAttributesW(it->path().c_str());require(attributes!=INVALID_FILE_ATTRIBUTES && !(attributes&FILE_ATTRIBUTE_REPARSE_POINT),"Unexpected setup redirect");
        const auto name=it->path().lexically_relative(root).generic_wstring();
        if(name==L"analysis"){
            require((attributes&FILE_ATTRIBUTE_DIRECTORY)!=0,"Mutable setup state must be a directory");it.disable_recursion_pending();continue;
        }
        if(attributes&FILE_ATTRIBUTE_DIRECTORY)pin_directory(leases,directories,it->path());else observed.insert(name);
    }
    require(observed==expected,"Unexpected setup payload before helper execution");
    Handle app(CreateFileW(application.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr));
    require(app.value!=INVALID_HANDLE_VALUE,"Original Serato executable required");BY_HANDLE_FILE_INFORMATION info{};
    require(GetFileInformationByHandle(app.value,&info)!=FALSE && !(info.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT)) &&
            hash_file(app.value)==release::application_sha,"Reviewed Serato executable required before helper execution");leases.push_back(std::move(app));
    if(action==L"--verify"){
        std::cout<<"{\"schema\":\"sl3.native-setup-entry-verification.v1\",\"inputsVerified\":true,\"filesPinned\":"<<release::files.size()
                 <<",\"pythonStarted\":false,\"installed\":false,\"seratoLaunched\":false,\"nativeDeviceAccess\":false}\n";return 0;
    }
    std::vector<std::wstring> arguments={L"-I",L"-B",(root/L"scripts/prepare-on-demand-kit.py").native(),L"--manifest",(root/L"kit-manifest.json").native(),
        L"--expected-manifest-sha256",release::kit_manifest_sha,L"--application",application.native()};
    if(action==L"--prepare")arguments.push_back(L"--prepare");
    return run_process(root/L"runtime/python/python.exe",arguments,root,false);
}
}
int wmain(int argc,wchar_t** argv){
    try{return sl3::setup::dispatch(argc,argv);}
    catch(const std::exception& error){std::cerr<<"SL3 setup entry refused: "<<error.what()<<'\n';return 1;}
}
