#pragma once
#include <Windows.h>
#include <unknwn.h>

namespace sl3::asio {
// A new project identity; never reuse the original Rane registration.
inline constexpr CLSID driver_clsid={0x5a551cd0,0xf83e,0x48eb,{0x8b,0x9d,0x86,0x14,0xe0,0x78,0x52,0xfe}};
}
