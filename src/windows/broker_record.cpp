#include "windows/broker_record.hpp"
#include <algorithm>
#include <charconv>
#include <array>
#include <cstdint>
#include <stdexcept>

namespace sl3::worker {
namespace {
void require(bool good,const char* text){if(!good)throw std::runtime_error(text);}
bool hash(const std::string& s){return s.size()==64 && std::all_of(s.begin(),s.end(),[](char c){return (c>='0' && c<='9') || (c>='a' && c<='f');});}
void local(const std::filesystem::path& p){
    const auto drive=p.root_name().native();const auto& name=p.native();
    require(p.is_absolute() && name.find(L'\0')==std::wstring::npos && drive.size()==2 && drive[1]==L':' &&
        ((drive[0]>=L'A' && drive[0]<=L'Z') || (drive[0]>=L'a' && drive[0]<=L'z')) &&
        name.find(L':',2)==std::wstring::npos && GetDriveTypeW(p.root_path().c_str())==DRIVE_FIXED,"Broker record/image must be on a local fixed drive");
}
struct File {
    HANDLE value=INVALID_HANDLE_VALUE;LONGLONG size=0;
    File(const std::filesystem::path& p,DWORD maximum){
        local(p);value=CreateFileW(p.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        require(value!=INVALID_HANDLE_VALUE,"Broker record/image is missing or not readable");
        try{
            LARGE_INTEGER bytes{};require(GetFileType(value)==FILE_TYPE_DISK && GetFileSizeEx(value,&bytes) && bytes.QuadPart>0 && bytes.QuadPart<=maximum,"Invalid broker record/image size/type");size=bytes.QuadPart;
            std::array<wchar_t,32768> final{};const auto n=GetFinalPathNameByHandleW(value,final.data(),DWORD(final.size()),FILE_NAME_NORMALIZED|VOLUME_NAME_DOS);
            require(n>4 && n<final.size(),"Cannot resolve broker file path");const std::wstring name(final.data(),n);
            require(name.compare(0,4,L"\\\\?\\")==0,"Unexpected broker final path");local(std::filesystem::path(name.substr(4)));
        }catch(...){CloseHandle(value);value=INVALID_HANDLE_VALUE;throw;}
    }
    ~File(){if(value!=INVALID_HANDLE_VALUE)CloseHandle(value);}
    File(const File&)=delete;File& operator=(const File&)=delete;
    std::string text(){std::string result(std::size_t(size),'\0');DWORD bytes=0;require(ReadFile(value,result.data(),DWORD(result.size()),&bytes,nullptr) && bytes==result.size(),"Read complete broker record");return result;}
};
struct Files {std::vector<std::unique_ptr<File>> entries;};
struct Handle {HANDLE value=nullptr;~Handle(){if(value)CloseHandle(value);}};
std::uint64_t created(HANDLE process){
    FILETIME start{},end{},kernel{},user{};require(GetProcessTimes(process,&start,&end,&kernel,&user)!=FALSE,"Read exact broker creation time");
    return (std::uint64_t(start.dwHighDateTime)<<32)|start.dwLowDateTime;
}
bool endpoint(const std::wstring& s){const std::wstring prefix=L"\\\\.\\pipe\\SL3Broker-";
    return s.size()==prefix.size()+32 && s.compare(0,prefix.size(),prefix)==0 &&
        std::all_of(s.begin()+std::ptrdiff_t(prefix.size()),s.end(),[](wchar_t c){return (c>=L'0' && c<=L'9') || (c>=L'a' && c<=L'f');});}
std::uint64_t number(const std::string& s){
    require(!s.empty() && s[0]!='0',"Noncanonical broker process identity");std::uint64_t value=0;
    const auto result=std::from_chars(s.data(),s.data()+s.size(),value);require(result.ec==std::errc{} && result.ptr==s.data()+s.size() && value,"Invalid broker process identity");return value;
}
std::vector<std::string> parse(const std::string& bytes,bool keepalive){
    require(!bytes.empty() && bytes.back()=='\n' && bytes.find('\0')==std::string::npos,"Incomplete broker session record");
    std::vector<std::string> values;std::size_t offset=0;
    const auto field=[&](const char* key){
        const auto end=bytes.find('\n',offset);require(end!=std::string::npos,"Missing broker session field");
        auto line=bytes.substr(offset,end-offset);if(!line.empty() && line.back()=='\r')line.pop_back();
        const std::string prefix(key);require(line.find('\r')==std::string::npos && line.compare(0,prefix.size(),prefix)==0,"Unexpected broker session field/order");values.push_back(line.substr(prefix.size()));offset=end+1;
    };
    field(keepalive?"SL3-BROKER-SESSION-2":"SL3-BROKER-SESSION-1");
    for(const auto key:{"endpoint=","server_pid=","server_created=","worker_sha256="})field(key);
    if(keepalive)field("keepalive_timing_sha256=");
    require(values[0].empty() && offset==bytes.size(),"Unknown/trailing broker session record fields");return values;
}
bool same_file(HANDLE a,HANDLE b){
    BY_HANDLE_FILE_INFORMATION first{},second{};require(GetFileInformationByHandle(a,&first) && GetFileInformationByHandle(b,&second),"Read broker image file identity");
    return first.dwVolumeSerialNumber==second.dwVolumeSerialNumber && first.nFileIndexHigh==second.nFileIndexHigh && first.nFileIndexLow==second.nFileIndexLow;
}
}
std::string broker_record_text(const std::wstring& name,const std::string& worker,const std::string& keepalive_timing){
    require(endpoint(name) && hash(worker),"Invalid broker record endpoint/worker hash");std::string ascii;for(auto c:name)ascii+=static_cast<char>(c);
    const bool keepalive=!keepalive_timing.empty();
    require(!keepalive || hash(keepalive_timing),"Invalid keepalive timing hash");
    auto result=std::string(keepalive?"SL3-BROKER-SESSION-2":"SL3-BROKER-SESSION-1")+"\nendpoint="+ascii+"\nserver_pid="+std::to_string(GetCurrentProcessId())+
        "\nserver_created="+std::to_string(created(GetCurrentProcess()))+"\nworker_sha256="+worker+"\n";
    if(keepalive)result+="keepalive_timing_sha256="+keepalive_timing+"\n";
    return result;
}
BrokerBinding bind_broker_record(const std::filesystem::path& record,const std::string& record_hash,
                               const std::filesystem::path& image,const std::string& image_hash,const std::string& worker_hash,
                               const std::string& keepalive_timing){
    require(hash(record_hash) && hash(image_hash) && hash(worker_hash),"Broker binding requires lowercase SHA256 pins");
    const bool keepalive=!keepalive_timing.empty();
    require(!keepalive || hash(keepalive_timing),"Invalid expected keepalive timing hash");
    auto files=std::make_shared<Files>();auto input=std::make_unique<File>(record,4096);
    require(Process::executable_sha256(record)==record_hash,"Broker session record hash mismatch");const auto values=parse(input->text(),keepalive);files->entries.push_back(std::move(input));
    require(values[4]==worker_hash,"Broker session worker hash differs from reviewed configuration");
    require(!keepalive || values[5]==keepalive_timing,"Broker keepalive timing differs from reviewed configuration");
    const std::wstring name(values[1].begin(),values[1].end());require(endpoint(name),"Invalid broker session endpoint");
    const auto pid=number(values[2]),time=number(values[3]);require(pid<=MAXDWORD,"Broker PID overflow");
    Handle process;process.value=OpenProcess(SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,DWORD(pid));
    require(process.value && WaitForSingleObject(process.value,0)==WAIT_TIMEOUT && created(process.value)==time,"Broker process is stale or creation identity differs");
    auto expected=std::make_unique<File>(image,256*1024*1024);require(Process::executable_sha256(image)==image_hash,"Broker executable hash mismatch");
    std::array<wchar_t,32768> buffer{};DWORD count=DWORD(buffer.size());require(QueryFullProcessImageNameW(process.value,0,buffer.data(),&count) && count>0 && count<buffer.size(),"Read broker process image path");
    auto actual=std::make_unique<File>(std::filesystem::path(std::wstring(buffer.data(),count)),256*1024*1024);
    require(same_file(expected->value,actual->value),"Broker process image differs from pinned executable");
    files->entries.push_back(std::move(expected));files->entries.push_back(std::move(actual));
    require(WaitForSingleObject(process.value,0)==WAIT_TIMEOUT && created(process.value)==time,"Broker ended during binding");
    return {name,ProcessWait::duplicate(process.value,files),files};
}
}
