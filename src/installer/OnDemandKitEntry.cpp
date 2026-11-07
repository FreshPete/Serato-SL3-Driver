// Native verification before fixed setup-only dispatch; no automatic elevation.
#define SL3_LAUNCHER_ARGUMENT_TEST
#include "NativeSessionLauncher.cpp"
#include "setup_config.hpp"
#include "SetupResultPipe.hpp"
#include <set>

namespace sl3::setup {
using namespace sl3::launcher;
void token_requirement(bool administrator){
    Handle token;require(OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token.value)!=FALSE,"Read setup token");
    TOKEN_ELEVATION elevation{};DWORD size=0;
    require(GetTokenInformation(token.value,TokenElevation,&elevation,sizeof(elevation),&size)!=FALSE,"Read setup elevation state");
    require(bool(elevation.TokenIsElevated)==administrator,administrator?
            "Run this exact reviewed setup/restore entry as administrator; no automatic prompt is requested":
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
constexpr ULONGLONG dynamic_size=~ULONGLONG(0);
HANDLE pin_input(std::vector<Handle>& leases,std::set<fs::path>& directories,const fs::path& path,const std::wstring& hash,ULONGLONG bytes){
    pin_directory(leases,directories,path.parent_path());
    Handle file(CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_SEQUENTIAL_SCAN,nullptr));
    require(file.value!=INVALID_HANDLE_VALUE,"Open reviewed setup input");BY_HANDLE_FILE_INFORMATION info{};LARGE_INTEGER length{};
    require(GetFileInformationByHandle(file.value,&info)!=FALSE && !(info.dwFileAttributes&(FILE_ATTRIBUTE_REPARSE_POINT|FILE_ATTRIBUTE_DIRECTORY)) &&
            GetFileType(file.value)==FILE_TYPE_DISK && GetFileSizeEx(file.value,&length)!=FALSE && length.QuadPart>=0 &&
            (bytes==dynamic_size?length.QuadPart<=16ll*1024*1024:ULONGLONG(length.QuadPart)==bytes),
            "Setup input size or file type differs");
    require(hash_file(file.value)==hash,"Reviewed setup input hash differs before helper execution");const auto result=file.value;leases.push_back(std::move(file));return result;
}
bool identity_hash(const std::wstring& value){return value.size()==64 && std::all_of(value.begin(),value.end(),[](wchar_t c){return (c>=L'0' && c<=L'9') || (c>=L'a' && c<=L'f');});}
void local_state(const fs::path& root,const fs::path& directory,const std::wstring& prefix){
    require(equal(directory.parent_path().native(),(root/L"analysis").native()),"Prepared state must belong to this kit");
    const auto name=directory.filename().native();require(name.size()==prefix.size()+32 && name.compare(0,prefix.size(),prefix)==0 &&
        std::all_of(name.begin()+prefix.size(),name.end(),[](wchar_t c){return (c>=L'0' && c<=L'9') || (c>=L'a' && c<=L'f');}),"Generated prepared state identity required");
}
int dispatch(int argc,wchar_t** argv){
    if(argc==1 || (argc==2 && std::wstring(argv[1])==L"--help")){
        std::cout<<"SL3 setup engineering entry: --verify|--plan|--prepare --kit ABSOLUTE_DIRECTORY --app ABSOLUTE_SERATO_EXE\n"
                 <<"Prepared actions: --check-experiment|--apply-experiment|--restore-experiment with --experiment PATH --expected-experiment-sha256 SHA256.\n"
                 <<"Apply/restore require an already elevated process. No automatic approval prompt or Serato launch.\n";return 0;
    }
    const std::wstring action=argv[1];const bool experiment=action==L"--check-experiment" || action==L"--apply-experiment" || action==L"--restore-experiment";
    require((argc==(experiment?10:6)) && std::wstring(argv[2])==L"--kit" && std::wstring(argv[4])==L"--app" &&
            (!experiment || (std::wstring(argv[6])==L"--experiment" && std::wstring(argv[8])==L"--expected-experiment-sha256")),"Exact reviewed setup arguments required");
    require(experiment || action==L"--verify" || action==L"--plan" || action==L"--prepare","Known setup entry action required");
    token_requirement(action==L"--apply-experiment" || action==L"--restore-experiment");
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
    if(experiment){
        const auto selected=local_path(argv[7]).lexically_normal();const std::wstring identity=argv[9];
        require(selected.filename()==L"experiment.json" && identity_hash(identity),"Reviewed experiment filename/hash required");
        local_state(root,selected.parent_path(),L"sl3-on-demand-test-");
        checked(RoInitialize(RO_INIT_SINGLETHREADED),"Initialize prepared-record JSON parser");struct Apartment{~Apartment(){RoUninitialize();}} apartment;
        const JsonObject record(read_capsule(pin_input(leases,directories,selected,identity,dynamic_size)));
        require(record.text(L"schema")==L"sl3.on-demand-normal-start-test.v1" && equal(record.text(L"projectRoot"),root.native()) &&
                equal(record.text(L"application"),application.native()) && record.text(L"applicationSha256")==release::application_sha,
                "Prepared experiment root/application differs");
        const auto python=record.object(L"python");
        require(equal(local_path(python.text(L"path")).lexically_normal().native(),(root/L"runtime/python/python.exe").lexically_normal().native()) &&
                python.text(L"sha256")==sl3::launcher::release::python_sha &&
                python.text(L"manifestSha256")==release::python_manifest_sha,"Prepared interpreter differs from the reviewed kit");
        const auto powershell=record.object(L"powershell");
        require(equal(local_path(powershell.text(L"directory")).lexically_normal().native(),(root/L"runtime/powershell").lexically_normal().native()) &&
                powershell.text(L"manifestSha256")==release::powershell_manifest_sha,"Prepared PowerShell differs from the reviewed kit");
        const auto assets=record.object(L"assets");
        for(const auto& name:std::vector<std::wstring>{L"archive/candidate-userio_resources.bin",L"archive/serato-archive-file-transaction.ps1",L"archive/deployment-plan.json",L"archive/archive-test.ps1",L"archive/action-child.ps1"})
            pin_input(leases,directories,child_path(selected.parent_path(),name),assets.text(name.c_str()),dynamic_size);
        const auto bundle=record.object(L"bundle");const auto destination=local_path(bundle.text(L"directory")).lexically_normal();local_state(root,destination,L"sl3-deployment-rebound-");
        const JsonObject native(read_capsule(pin_input(leases,directories,destination/L"bundle-manifest.json",bundle.text(L"sha256"),dynamic_size)));
        require(native.text(L"schema")==L"sl3.deployment-bundle.v2","Prepared on-demand bundle required");const auto payload=native.object(L"files");
        std::set<std::wstring> bundle_names={L"bundle-manifest.json"};
        for(const auto& item:release::files){
            const std::wstring prefix=L"native-package/";if(item.name.compare(0,prefix.size(),prefix)!=0)continue;
            const auto name=item.name.substr(prefix.size());if(name==L"bundle-manifest.json")continue;bundle_names.insert(name);
            const auto expected_hash=payload.object(name.c_str()).text(L"sha256");
            if(name==L"sl3_asio.dll" || name==L"sl3_broker_controller.exe" || name==L"sl3_usbdk.exe" || name==L"UsbDkHelper.dll")require(expected_hash==item.sha,"Prepared native binary differs from compiled kit");
            pin_input(leases,directories,child_path(destination,name),expected_hash,dynamic_size);
        }
        std::set<std::wstring> actual_bundle;for(const auto& child:fs::directory_iterator(destination))actual_bundle.insert(child.path().filename().native());
        require(actual_bundle==bundle_names,"Unexpected prepared native bundle payload");
        const auto operation=action==L"--apply-experiment"?L"setup":action==L"--restore-experiment"?L"restore":L"plan";
        return run_process(root/L"runtime/python/python.exe",{L"-I",L"-B",(root/L"scripts/serato-on-demand-test.py").native(),operation,
            L"--experiment",selected.native(),L"--expected-experiment-sha256",identity},root,false);
    }
    std::vector<std::wstring> arguments={L"-I",L"-B",(root/L"scripts/prepare-on-demand-kit.py").native(),L"--manifest",(root/L"kit-manifest.json").native(),
        L"--expected-manifest-sha256",release::kit_manifest_sha,L"--application",application.native()};
    if(action==L"--prepare")arguments.push_back(L"--prepare");
    return run_process(root/L"runtime/python/python.exe",arguments,root,false);
}
}
int wmain(int argc,wchar_t** argv){
    try{
        if(argc==14 && std::wstring(argv[10])==L"--result-pipe" && std::wstring(argv[12])==L"--result-server-pid"){
            const std::wstring action=argv[1];sl3::launcher::require(action==L"--apply-experiment" || action==L"--restore-experiment","Result channel applies only to setup/restore");
            sl3::setup::token_requirement(true);
            sl3::setup_result::Client result(argv[11],sl3::setup_result::process_id(argv[13]));result.redirect();
            try{return sl3::setup::dispatch(10,argv);}
            catch(const std::exception& error){result.write(std::string("SL3 setup entry refused: ")+error.what()+"\n");return 1;}
        }
        return sl3::setup::dispatch(argc,argv);
    }
    catch(const std::exception& error){std::cerr<<"SL3 setup entry refused: "<<error.what()<<'\n';return 1;}
}
