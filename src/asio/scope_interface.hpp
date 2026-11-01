#pragma once
#include "asio/com_identity.hpp"

namespace sl3::asio {
// Project-owned optional factory capability. This is not an IASIO slot or a
// Serato/vendor interface. A control host must retain this factory and use it
// for all scoped CreateInstance calls. Neither method requests elevation.
inline constexpr IID scope_iid={0x0cf4a2e1,0x6610,0x4a5e,{0xa7,0x51,0xe9,0x64,0x31,0xd0,0x8c,0x92}};
struct DeviceScope: IUnknown {
    // Once per factory, before any CreateInstance. Pins reviewed configuration
    // but does not acquire USB. First successful IASIO init acquires the device.
    virtual HRESULT STDMETHODCALLTYPE BeginScope() noexcept=0;
    // S_FALSE while borrowed or already absent; S_OK only after independently
    // checked retirement. Closed/failed factories never revert to private opens.
    virtual HRESULT STDMETHODCALLTYPE EndScope() noexcept=0;
};
}
