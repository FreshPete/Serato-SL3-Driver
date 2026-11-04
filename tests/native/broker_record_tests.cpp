#include "windows/broker_record.hpp"
#include "windows/broker_pipe.hpp"
#include <fstream>
#include <iostream>

using namespace sl3::worker;
static void require(bool good,const char* text){if(!good)throw std::runtime_error(text);}
template<class F>static void rejects(F f){bool bad=false;try{f();}catch(const std::exception&){bad=true;}require(bad,"Invalid broker session binding accepted");}
static void write(const std::filesystem::path& p,const std::string& s){std::ofstream out(p,std::ios::binary);out<<s;require(bool(out),"Write synthetic broker record");}
static std::string change(std::string text,const std::string& key,const std::string& value){const auto start=text.find(key);require(start!=std::string::npos,"Mutation key");const auto at=start+key.size(),end=text.find('\n',at);text.replace(at,end-at,value);return text;}
struct Temp {
    BrokerListener listener;std::filesystem::path folder=std::filesystem::temp_directory_path()/listener.name().substr(listener.name().size()-32);
    std::filesystem::path record=folder/L"session.txt",other=folder/L"other.exe";
    Temp(){require(std::filesystem::create_directory(folder),"Fresh broker record folder");}
    ~Temp(){std::error_code ec;for(const auto& p:{record,other})std::filesystem::remove(p,ec);std::filesystem::remove(folder,ec);}
};
static void run(const std::filesystem::path& self){
    Temp t;const auto worker=std::string(64,'a'),image=Process::executable_sha256(self),text=broker_record_text(t.listener.name(),worker);write(t.record,text);
    const auto record_hash=Process::executable_sha256(t.record);
    {
        auto binding=bind_broker_record(t.record,record_hash,self,image,worker);
        require(binding.endpoint==t.listener.name() && GetProcessId(binding.server->handle())==GetCurrentProcessId() && WaitForSingleObject(binding.server->handle(),0)==WAIT_TIMEOUT,"Actual live process/image/record binding");
        const auto handle=CreateFileW(t.record.c_str(),GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,0,nullptr);
        require(handle==INVALID_HANDLE_VALUE && GetLastError()==ERROR_SHARING_VIOLATION,"Session record stays write locked");
        require(!DeleteFileW(t.record.c_str()) && GetLastError()==ERROR_SHARING_VIOLATION,"Session record stays delete locked");
        binding.files.reset();require(!DeleteFileW(t.record.c_str()),"Wait reference itself retains record/image leases");
    }
    const auto timing=std::string(64,'c');
    rejects([&]{bind_broker_record(t.record,record_hash,self,image,worker,timing);});
    write(t.record,broker_record_text(t.listener.name(),worker,timing)); // Prior leases have retired.
    const auto keepalive_hash=Process::executable_sha256(t.record);
    require(bind_broker_record(t.record,keepalive_hash,self,image,worker,timing).endpoint==t.listener.name(),"Exact keepalive timing record binds");
    rejects([&]{bind_broker_record(t.record,keepalive_hash,self,image,worker);});
    rejects([&]{bind_broker_record(t.record,keepalive_hash,self,image,worker,std::string(64,'d'));});
    write(t.record,text);
    rejects([&]{bind_broker_record(t.record,std::string(64,'0'),self,image,worker);});
    rejects([&]{bind_broker_record(t.record,record_hash,self,std::string(64,'0'),worker);});
    rejects([&]{bind_broker_record(t.record,record_hash,self,image,std::string(64,'b'));});
    rejects([&]{bind_broker_record(t.record,std::string(64,'A'),self,image,worker);});
    require(std::filesystem::copy_file(self,t.other),"Copy same bytes into a different file object");
    rejects([&]{bind_broker_record(t.record,record_hash,t.other,image,worker);});
    for(const auto& bad:std::vector<std::string>{text+"extra=1\n",text.substr(0,text.size()-1),std::string("\xef\xbb\xbf")+text,text+std::string(1,'\0'),
        change(text,"server_pid=","0"),change(text,"server_pid=","01"),change(text,"server_pid=","4294967296"),change(text,"server_created=","1"),
        change(text,"server_created=","18446744073709551616"),change(text,"endpoint=","\\\\server\\pipe\\bad"),change(text,"worker_sha256=",std::string(64,'b'))}){
        write(t.record,bad);rejects([&]{bind_broker_record(t.record,Process::executable_sha256(t.record),self,image,worker);});
    }
    write(t.record,std::string(4097,'x'));rejects([&]{bind_broker_record(t.record,Process::executable_sha256(t.record),self,image,worker);});
    Process exited;exited.launch(self,image,{L"--exit"});require(exited.wait_for_exit(5000),"Exact child process exited");
    FILETIME start{},end{},kernel{},user{};require(GetProcessTimes(exited.process_handle(),&start,&end,&kernel,&user)!=FALSE,"Read retired process identity");
    auto stale=change(text,"server_pid=",std::to_string(GetProcessId(exited.process_handle())));
    stale=change(stale,"server_created=",std::to_string((std::uint64_t(start.dwHighDateTime)<<32)|start.dwLowDateTime));write(t.record,stale);
    rejects([&]{bind_broker_record(t.record,Process::executable_sha256(t.record),self,image,worker);});
    rejects([&]{broker_record_text(L"wrong-endpoint",worker);});
    std::cout<<"Broker record pins, actual process creation/image identity, stale/malformed refusal and file leases passed; no device acquisition\n";
}
int wmain(int argc,wchar_t** argv){try{if(argc==2 && std::wstring(argv[1])==L"--exit")return 0;require(argc==1,"No native/device arguments accepted");run(std::filesystem::absolute(argv[0]));return 0;}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
