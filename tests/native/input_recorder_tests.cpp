#include "core/input_recorder.hpp"
#include <cstdlib>
#include <iostream>
#include <new>
#include <stdexcept>
static bool counting=false;static unsigned allocations=0;
void* operator new(std::size_t n){if(counting)++allocations;if(auto* p=std::malloc(n?n:1))return p;throw std::bad_alloc();}
void* operator new[](std::size_t n){return ::operator new(n);}
void operator delete(void* p) noexcept{std::free(p);}void operator delete[](void* p) noexcept{std::free(p);}
void operator delete(void* p,std::size_t) noexcept{std::free(p);}void operator delete[](void* p,std::size_t) noexcept{std::free(p);}
void require(bool v,const char* text){if(!v)throw std::runtime_error(text);}
int main(){try{
    std::array<std::array<std::uint8_t,384>,6> planes{};
    std::array<const std::uint8_t*,6> pointers{};
    for(unsigned c=0;c<6;++c){pointers[c]=planes[c].data();for(unsigned b=0;b<384;++b)planes[c][b]=std::uint8_t(c*43+b);}
    planes[0][0]=0;planes[0][1]=0;planes[0][2]=0x80;
    planes[5][0]=0xff;planes[5][1]=0xff;planes[5][2]=0x7f;
    std::array<std::uint8_t,256*18+2> data{};data.front()=0x5a;data.back()=0xa5;
    sl3::PackedInputRecorder capture(data.data()+1,256);counting=true;
    const auto a=capture.append(pointers,128,0),b=capture.append(pointers,128,128),c=capture.append(pointers,128,256);
    counting=false;require(a && b && c && !allocations,"Complete prefix/trailing callback must not allocate");
    require(capture.complete() && capture.frames()==256 && capture.recorded_callbacks()==2 && capture.trailing_callbacks()==1 && capture.callbacks()==3,"Exact whole-bank prefix and explicit suffix accounting");
    require(data.front()==0x5a && data.back()==0xa5,"Recorder crossed storage bounds");
    for(unsigned f=0;f<256;++f)for(unsigned ch=0;ch<6;++ch)for(unsigned k=0;k<3;++k)
        require(data[1+f*18+ch*3+k]==planes[ch][(f%128)*3+k],"Packed channel bytes/polarity/container bits changed");
    auto original=data;require(!capture.append(pointers,128,512) && data==original,"Sequence discontinuity must seal without modifying prefix");
    require(!capture.append(pointers,128,384),"A failed recorder must stay sealed");
    sl3::PackedInputRecorder missing(data.data()+1,256);auto nulls=pointers;nulls[5]=nullptr;
    require(!missing.append(nulls,128,0) && missing.frames()==0,"Null final plane must not partially copy");
    sl3::PackedInputRecorder partial(data.data()+1,1);require(!partial.append(pointers,2,0) && partial.frames()==0,"No partial bank truncation");
    sl3::PackedInputRecorder position(data.data()+1,256);require(!position.append(pointers,128,1),"First logical frame must be zero");
    sl3::PackedInputRecorder zero(data.data()+1,256);require(!zero.append(pointers,0,0),"Empty callback rejected");
    sl3::PackedInputRecorder huge(data.data()+1,256);require(!huge.append(pointers,129,0),"Oversized bank rejected");
    sl3::PackedInputRecorder invalid(nullptr,256);require(!invalid.append(pointers,128,0),"Null destination rejected");
    std::cout<<"Input PCM prefix, allocation, bounds and failure guards passed\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
