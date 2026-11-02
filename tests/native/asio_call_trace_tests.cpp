#include "asio/call_trace.hpp"
#include <array>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <thread>
#include <type_traits>
#include <vector>

namespace t=sl3::asio::trace;
namespace {
std::array<t::Record,8192> records{};
std::size_t stored=0,writes=0,clock_reads=0,frequency_reads=0;
bool enabled=true,drop=false;
std::uint64_t tick=100,hz=10000000;
bool is_enabled() noexcept{return enabled;}
void write(const t::Record& r) noexcept{++writes;if(!drop && stored<records.size())records[stored++]=r;}
std::uint64_t now() noexcept{++clock_reads;return tick;}
std::uint64_t frequency() noexcept{++frequency_reads;return hz;}
const t::Backend sink{is_enabled,write,now,frequency};
std::array<t::Record,256> parallel_records{};
std::atomic<std::size_t> parallel_count{0};
void parallel_write(const t::Record& r) noexcept {
    const auto n=parallel_count.fetch_add(1);
    if(n<parallel_records.size())parallel_records[n]=r;
}
const t::Backend parallel_sink{[]() noexcept{return true;},parallel_write,
    []() noexcept{return std::uint64_t{100};},[]() noexcept{return std::uint64_t{10000000};}};
void require(bool value,const char* text){if(!value)throw std::runtime_error(text);}
void reset(){stored=writes=clock_reads=frequency_reads=0;tick=100;hz=10000000;enabled=true;drop=false;}
}
int main(){
    try{
        {t::Provider actual;require(actual.registered(),"Register and unregister real user-mode ETW provider without starting a session");}
        reset();enabled=false;const auto initial=t::next_call.load();
        {t::Call call(t::Operation::init,1,0,0,sink);require(call.finish(false)==false,"Disabled Boolean result preserved");}
        require(!stored && !writes && !clock_reads && !frequency_reads && t::next_call.load()==initial,"Disabled trace does not read clock, consume budget or emit");
        reset();
        {t::Call call(t::Operation::create_buffers,7,6,128,sink);
            static_assert(std::is_same_v<decltype(call.finish(HRESULT{})),HRESULT>);
            tick=145;require(call.finish(E_FAIL)==E_FAIL,"Negative HRESULT returned unchanged");}
        require(stored==2 && records[0].phase==t::Phase::begin && records[1].phase==t::Phase::end,"Begin/end pair");
        require(records[0].call==records[1].call && records[0].instance==7 && records[1].argument0==6 && records[1].argument1==128,"Pair identity and integer arguments");
        require(records[1].result==E_FAIL && records[1].qpc==100 && records[1].elapsed==45 && records[1].frequency==10000000,"Result and raw host timing");
        reset();{t::Call call(t::Operation::init,8,0,0,sink);}
        require(stored==2 && records[1].phase==t::Phase::abandoned,"Unfinished scope is not a successful end");
        reset();{t::Call call(t::Operation::stop,9,0,0,sink);call.finish(0L);call.finish(1L);}
        require(stored==2 && records[1].result==0,"Finish emits once");
        reset();drop=true;
        {t::Call call(t::Operation::start,9,0,0,sink);require(call.finish(-999L)==-999,"Dropped backend write cannot change driver result");}
        require(!stored && writes==2,"Dropped records remain unobserved");
        reset();hz=0;
        {t::Call call(t::Operation::channels,10,0,0,sink);tick=99;call.finish(0L);}
        require(records[1].elapsed==0 && records[1].frequency==0,"Regressing/failed timing is not unsigned elapsed underflow");
        wchar_t text[512]{};
        const t::Record extremes{t::Phase::end,t::Operation::create_buffers,
            std::numeric_limits<std::uint64_t>::max(),std::numeric_limits<std::uint64_t>::max(),
            std::numeric_limits<std::int64_t>::min(),std::numeric_limits<std::int64_t>::min(),std::numeric_limits<std::int64_t>::max(),
            std::numeric_limits<std::uint64_t>::max(),std::numeric_limits<std::uint64_t>::max(),std::numeric_limits<std::uint64_t>::max()};
        require(t::format(extremes,text,512),"Fixed payload fits worst-case integer widths");
        const std::wstring formatted=text;
        require(formatted.find(L"\"schema\":\"sl3.asio-call.v1\"")!=std::wstring::npos &&
            formatted.find(L"\"phase\":\"end\"")!=std::wstring::npos &&
            formatted.find(L"18446744073709551615")!=std::wstring::npos &&
            formatted.find(L"-9223372036854775808")!=std::wstring::npos,"Stable string schema and full-width signed/unsigned values");
        wchar_t short_buffer[2]{};
        require(!t::format(extremes,short_buffer,2) && !t::format(extremes,nullptr,0),"Truncated/absent output is refused");
        std::atomic<bool> parallel_results{true};
        std::vector<std::thread> threads;
        for(unsigned worker=0;worker<8;++worker)threads.emplace_back([worker,&parallel_results]{
            for(unsigned n=0;n<16;++n){
                t::Call call(t::Operation::set_clock,worker,n,0,parallel_sink);
                if(n%3 && call.finish(E_FAIL)!=E_FAIL)parallel_results=false;
            }
        });
        for(auto& thread:threads)thread.join();
        require(parallel_results && parallel_count.load()==256,"Concurrent call results and bounded record count");
        std::map<std::uint64_t,std::pair<unsigned,unsigned>> pairs;
        for(const auto& r:parallel_records){auto& pair=pairs[r.call];if(r.phase==t::Phase::begin)++pair.first;else ++pair.second;}
        require(pairs.size()==128,"Concurrent calls receive unique IDs");
        for(const auto& pair:pairs)require(pair.second.first==1 && pair.second.second==1,"Concurrent begin/terminal pairing");
        reset();
        for(std::uint64_t n=0;n<t::maximum_calls+10;++n){t::Call call(t::Operation::name,n,0,0,sink);require(call.finish(123L)==123,"Budget exhaustion preserves API result");}
        require(stored<=2*t::maximum_calls && stored%2==0 && t::next_call.load()==t::maximum_calls+1,"Per-module call budget saturates and cannot wrap/reopen");
        for(std::size_t n=0;n<stored;n+=2)require(records[n].phase==t::Phase::begin && records[n+1].phase==t::Phase::end &&
            records[n].call==records[n+1].call && (!n || records[n].call>records[n-2].call),"Budgeted records stay paired and ordered");
        const auto count=writes;{t::Call call(t::Operation::init,42,0,0,sink);call.finish(0L);}
        require(writes==count,"No writes after saturation");
        std::cout<<"ASIO trace format, disabled/drop semantics, scope pairing and saturation passed; no ETW capture or device\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
