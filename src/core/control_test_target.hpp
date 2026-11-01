#pragma once
#include "core/audio_control_selection_wire.hpp"
#include <string>
#include <string_view>

namespace sl3::control {
inline selection_wire::Target parse_control_test_target(std::wstring_view text){
    AudioControlSetting setting;
    if(text.substr(0,12)==L"sensitivity:"){setting=AudioControlSetting::sensitivity;text.remove_prefix(12);}
    else if(text.substr(0,8)==L"through:"){setting=AudioControlSetting::through;text.remove_prefix(8);}
    else throw std::invalid_argument("Expected sensitivity:GROUP:VALUE or through:GROUP:VALUE");
    if(text.size()<3 || text[0]<L'0' || text[0]>L'2' || text[1]!=L':')throw std::invalid_argument("Invalid control group");
    const unsigned group=unsigned(text[0]-L'0');text.remove_prefix(2);
    unsigned value=0;
    if(text.size()==1 && text[0]>=L'0' && text[0]<=L'9')value=unsigned(text[0]-L'0');
    else if(text.size()==2 && text[0]==L'1' && text[1]>=L'0' && text[1]<=L'5')value=10+unsigned(text[1]-L'0');
    else throw std::invalid_argument("Invalid canonical control value");
    selection_wire::Target target{setting,group,value};selection_wire::encode_request(target);return target;
}
inline std::wstring format_control_test_target(selection_wire::Target target){
    selection_wire::encode_request(target);
    return std::wstring(target.setting==AudioControlSetting::through?L"through:":L"sensitivity:")+
        std::to_wstring(target.group)+L":"+std::to_wstring(target.value);
}
}
