#include "asio/buffer_set.hpp"
#include <array>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <new>
#include <stdexcept>
#if defined(_MSC_VER) && defined(_DEBUG)
#include <crtdbg.h>
#endif

static bool fail_next_allocation=false;
static const char* test_stage="startup";
void* operator new(std::size_t size){
    if(fail_next_allocation){fail_next_allocation=false;throw std::bad_alloc();}
    if(void* p=std::malloc(size?size:1))return p;
    throw std::bad_alloc();
}
void* operator new[](std::size_t size){return ::operator new(size);}
void operator delete(void* p) noexcept{std::free(p);}
void operator delete[](void* p) noexcept{std::free(p);}
void operator delete(void* p,std::size_t) noexcept{std::free(p);}
void operator delete[](void* p,std::size_t) noexcept{std::free(p);}
static void require(bool condition,const char* message){if(!condition)throw std::runtime_error(message);}
static std::int32_t value(std::uint64_t frame,unsigned channel){return static_cast<std::int32_t>((frame*7919+channel*104729)%0x1000000)-0x800000;}
static std::int32_t sample(const void* data,std::size_t index){
    const auto* p=static_cast<const std::uint8_t*>(data)+index*3;
    const std::uint32_t bits=p[0]|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16);
    return bits>=0x800000?static_cast<std::int32_t>(bits)-0x1000000:static_cast<std::int32_t>(bits);
}
struct Host {
    sl3::asio::BufferSet buffers;
    // Deliberately shuffled directions and logical channel numbers.
    std::array<ASIOBufferInfo,4> info{{{ASIOFalse,3,{}},{ASIOTrue,5,{}},{ASIOFalse,1,{}},{ASIOTrue,0,{}}}};
    unsigned calls=0,message_calls=0,time_calls=0;
    bool throw_callback=false,defer=false;
    long bank=-1;
};
static Host* current=nullptr;
static void callback(long bank,ASIOBool direct){
    auto& h=*current;
    require(direct==ASIOTrue && bank==long(h.calls%2),"SDK callback arguments changed");
    const auto observation=h.buffers.observation();
    require(observation.valid && observation.first_frame==std::uint64_t(h.calls)*64 && observation.bank==unsigned(bank),"Callback observation/position changed");
    if(h.throw_callback)throw std::runtime_error("SDK host callback fault");
    for(unsigned frame=0;frame<64;++frame){
        require(sample(h.info[1].buffers[bank],frame)==value(observation.first_frame+frame,5),"ASIO input 5 mapping changed");
        require(sample(h.info[3].buffers[bank],frame)==value(observation.first_frame+frame,0),"ASIO input 0 mapping changed");
    }
    require(h.buffers.stop_buffer_flow()==ASE_InvalidMode && h.buffers.dispose()==ASE_InvalidMode,"Callback disposal was allowed");
    h.bank=bank;
    if(!h.defer){
        std::memcpy(h.info[0].buffers[bank],h.info[3].buffers[bank],64*3);
        std::memcpy(h.info[2].buffers[bank],h.info[1].buffers[bank],64*3);
    }
    ++h.calls;
}
static long message(long,long,void*,double*){++current->message_calls;return 1;}
static ASIOTime* time_info(ASIOTime* time,long,ASIOBool){++current->time_calls;return time;}
static ASIOCallbacks callbacks(){ASIOCallbacks result{};result.bufferSwitch=callback;result.asioMessage=message;result.bufferSwitchTimeInfo=time_info;return result;}
static void streaming(bool deferred){
    Host host;host.defer=deferred;current=&host;
    auto cb=callbacks();
    require(host.buffers.create(host.info.data(),4,64,&cb)==ASE_OK,"ASIO buffers could not be prepared");
    cb.bufferSwitch=nullptr; // Driver must own a copy, not retain caller's struct.
    for(const auto& channel:host.info)require(channel.buffers[0] && channel.buffers[1] && channel.buffers[0]!=channel.buffers[1],"Double-bank pointers not published");
    auto* stable=host.info[0].buffers[0];
    require(host.buffers.start_buffer_flow(44100)==ASE_OK,"Buffer flow start failed");
    require(host.buffers.start_buffer_flow(44100)==ASE_InvalidMode,"Duplicate start reset live buffers");
    std::array<sl3::Frame,64> input{};std::array<std::uint32_t,16> lengths{};lengths.fill(72);
    std::array<std::uint8_t,1152> pcm{};std::array<sl3::Packet,16> layout{};
    for(unsigned block=0;block<8;++block){
        for(unsigned frame=0;frame<64;++frame)for(unsigned channel=0;channel<6;++channel)input[frame][channel]=value(std::uint64_t(block)*64+frame,channel);
        require(host.buffers.accept_capture(input.data(),64,std::uint64_t(block)*64,1000+block)==sl3::BridgeStatus::ok,"ASIO callback stream failed");
        if(deferred){
            std::memcpy(host.info[0].buffers[host.bank],host.info[3].buffers[host.bank],64*3);
            std::memcpy(host.info[2].buffers[host.bank],host.info[1].buffers[host.bank],64*3);
        }
        require(host.buffers.render_output(lengths.data(),16,pcm.data(),pcm.size(),layout.data(),16)==sl3::BridgeStatus::ok,"ASIO output render failed");
        for(unsigned frame=0;frame<64;++frame)for(unsigned channel=0;channel<6;++channel){
            const auto expected=block>=2 && (channel==1 || channel==3)?value(std::uint64_t(block-2)*64+frame,channel==1?5:0):0;
            require(sample(pcm.data()+frame*18,channel)==expected,"SDK output-channel mapping or processing window changed");
        }
    }
    require(host.calls==8 && host.message_calls==0 && host.time_calls==0,"Unexpected callback mode negotiation");
    require(host.buffers.stop_buffer_flow()==ASE_OK,"Buffer flow stop failed");
    host.calls=0;
    require(host.buffers.start_buffer_flow(48000)==ASE_OK && host.info[0].buffers[0]==stable,"Restart changed published buffers");
    require(host.buffers.dispose()==ASE_OK && !host.buffers.prepared(),"Dispose did not imply stop/free");
    require(host.buffers.dispose()==ASE_InvalidMode,"Empty disposal incorrectly succeeded");
}
int main(){
    std::set_terminate([]{std::fprintf(stderr,"Unexpected termination in ASIO buffer test (%s)\n",test_stage);std::fflush(stderr);std::_Exit(81);});
#if defined(_MSC_VER) && defined(_DEBUG)
    _CrtSetReportMode(_CRT_ASSERT,_CRTDBG_MODE_FILE);
    _CrtSetReportFile(_CRT_ASSERT,_CRTDBG_FILE_STDERR);
    _CrtSetReportMode(_CRT_ERROR,_CRTDBG_MODE_FILE);
    _CrtSetReportFile(_CRT_ERROR,_CRTDBG_FILE_STDERR);
    _set_abort_behavior(0,_WRITE_ABORT_MSG|_CALL_REPORTFAULT);
#endif
    try{
        test_stage="streaming";
        streaming(false);streaming(true);
        test_stage="validation";
        Host h;current=&h;auto cb=callbacks();
        require(h.buffers.start_buffer_flow(44100)==ASE_InvalidMode,"Unprepared buffer flow started");
        require(h.buffers.create(nullptr,4,64,&cb)==ASE_InvalidParameter,"Null buffer info accepted");
        require(h.buffers.create(h.info.data(),13,64,&cb)==ASE_InvalidParameter,"Excess channels accepted");
        auto no_legacy=cb;no_legacy.bufferSwitch=nullptr;
        require(h.buffers.create(h.info.data(),4,64,&no_legacy)==ASE_InvalidMode,"Time-info-only callback accepted without timestamp contract");
        require(h.buffers.create(h.info.data(),4,65,&cb)==ASE_InvalidMode,"Invalid block size accepted");
        ASIOBufferInfo info[2]{{ASIOTrue,0,{reinterpret_cast<void*>(1),reinterpret_cast<void*>(2)}},{ASIOTrue,0,{reinterpret_cast<void*>(3),reinterpret_cast<void*>(4)}}};
        require(h.buffers.create(info,2,64,&cb)==ASE_InvalidMode && !h.buffers.prepared() && info[0].buffers[0]==reinterpret_cast<void*>(1),"Failed creation partially published pointers");
        test_stage="allocation failure";
        fail_next_allocation=true;
        require(h.buffers.create(h.info.data(),4,64,&cb)==ASE_NoMemory && !h.buffers.prepared(),"Allocation failure not mapped atomically");
        test_stage="metadata and callback faults";
        ASIOChannelInfo channel{};channel.channel=3;channel.isInput=ASIOFalse;
        require(h.buffers.channel_info(&channel)==ASE_OK && channel.type==ASIOSTInt24LSB && !channel.isActive && channel.channelGroup==0,"Unprepared format metadata changed");
        require(h.buffers.create(h.info.data(),4,64,&cb)==ASE_OK,"Valid creation after faults failed");
        require(h.buffers.channel_info(&channel)==ASE_OK && channel.isActive && std::strcmp(channel.name,"SL3 Output 4")==0,"Active channel metadata changed");
        channel.channel=6;require(h.buffers.channel_info(&channel)==ASE_InvalidParameter,"Invalid channel query accepted");
        require(h.buffers.start_buffer_flow(96000)==ASE_NoClock && h.buffers.start_buffer_flow(44100)==ASE_OK,"Rate validation changed buffer state");
        h.throw_callback=true;std::array<sl3::Frame,64> frames{};
        require(h.buffers.accept_capture(frames.data(),64,0,0)==sl3::BridgeStatus::callback_failure,"Throwing SDK callback escaped");
        require(h.buffers.state()==sl3::BridgeState::faulted && h.buffers.dispose()==ASE_OK,"Callback guard did not reset for cleanup");
        std::cout<<"SDK ABI, buffers, deferred callbacks, start/stop/disposal and failure mapping passed\n";
    }catch(const std::exception& error){fail_next_allocation=false;std::cerr<<error.what()<<'\n';return 1;}
}
