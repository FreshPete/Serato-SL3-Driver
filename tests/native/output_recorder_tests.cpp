#include "core/output_recorder.hpp"
#include <array>
#include <cstdlib>
#include <iostream>
#include <new>
#include <stdexcept>
static bool counting=false;static unsigned allocations=0;
void* operator new(std::size_t n){if(counting)++allocations;if(auto* p=std::malloc(n?n:1))return p;throw std::bad_alloc();}
void* operator new[](std::size_t n){return ::operator new(n);}
void operator delete(void* p) noexcept{std::free(p);}void operator delete[](void* p) noexcept{std::free(p);}
void operator delete(void* p,std::size_t) noexcept{std::free(p);}void operator delete[](void* p,std::size_t) noexcept{std::free(p);}
void require(bool value,const char* text){if(!value)throw std::runtime_error(text);}
sl3::AudioBlock block(std::uint64_t first){
    sl3::AudioBlock b;b.first_frame=first;b.reported_rate_hz=44100;b.packet_count=8;
    for(unsigned i=0;i<8;++i)b.frames_per_packet[i]=std::uint8_t(5+i%2);
    for(unsigned i=0;i<b.pcm.size();++i)b.pcm[i]=std::uint8_t(i*37+first);
    return b; // 44 frames, arbitrary byte patterns include signed extrema.
}
int main(){try{
    std::array<std::uint8_t,70*18+2> data{};data.front()=0x5a;data.back()=0xa5;
    auto a=block(12345),b=block(12389);const auto original_a=a.pcm,original_b=b.pcm;
    sl3::PackedOutputRecorder capture(data.data()+1,70,44100);counting=true;
    const bool first=capture.append(a),second=capture.append(b);counting=false;
    require(first && second && !allocations,"Recorder copy allocated or failed");
    require(capture.complete() && capture.frames()==70 && capture.first_frame()==12345 && capture.blocks()==2,"Arbitrary start and final partial block");
    require(data.front()==0x5a && data.back()==0xa5,"Capture exceeded destination bounds");
    require(a.pcm==original_a && b.pcm==original_b,"Source PCM changed");
    for(unsigned i=0;i<70*18;++i)require(data[i+1]==(i<44*18?a.pcm[i]:b.pcm[i-44*18]),"Packed PCM changed");
    const auto saved=data;auto bad=b;bad.reported_rate_hz=0;
    require(capture.append(bad) && data==saved,"Completed clip must remain sealed");
    sl3::PackedOutputRecorder gap(data.data()+1,70,44100);
    require(gap.append(a),"Initial block rejected");bad=block(12390);
    require(!gap.append(bad) && gap.fault()==sl3::OutputRecordFault::position && gap.frames()==44,"Sequence gap accepted");
    require(!gap.append(b),"Failed capture resumed");
    for(unsigned mutation=0;mutation<6;++mutation){
        sl3::PackedOutputRecorder invalid(data.data()+1,70,44100);bad=a;
        if(mutation==0)bad.packet_count=7;if(mutation==1)bad.packet_count=72;
        if(mutation==2)bad.frames_per_packet[0]=0;if(mutation==3)bad.frames_per_packet[0]=8;
        if(mutation==4)bad.frames_per_packet[8]=1;if(mutation==5)bad.reported_rate_hz=48000;
        const auto before=data;require(!invalid.append(bad) && invalid.frames()==0 && before==data,"Invalid metadata partially copied");
    }
    sl3::PackedOutputRecorder overflow(data.data()+1,70,44100);bad=block(UINT64_MAX-43);
    require(!overflow.append(bad),"Position overflow accepted");
    sl3::PackedOutputRecorder null(nullptr,1,44100),zero(data.data()+1,0,44100),large(data.data()+1,240001,48000),rate(data.data()+1,1,96000);
    require(!null.append(a) && !zero.append(a) && !large.append(a) && !rate.append(a),"Invalid configuration accepted");
    std::cout<<"Output clip bounds, continuity, byte preservation and allocation checks passed\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
