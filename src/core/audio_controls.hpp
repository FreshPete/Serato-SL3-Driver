#pragma once
#include "core/control_frames.hpp"
#include <optional>

namespace sl3::control {
// Original control-panel table consumers, not inferred physical jack order.
struct InputControlIndexes {std::size_t phono,sensitivity,through;};
inline constexpr std::array<InputControlIndexes,3> input_control_indexes{{
    {0,3,8},{1,9,14},{2,15,20}
}};

struct InputControlState {
    std::uint8_t phono_raw=0,sensitivity_raw=0,through_raw=0;
    bool phono_switch_nonzero() const noexcept{return phono_raw!=0;}
    bool through_nonzero() const noexcept{return through_raw!=0;}
    // The original UI offers codes 0..15, displayed as 2.5 + 0.5*code mV.
    // This is its display scale, not measured gain, clipping or calibration.
    std::optional<unsigned> original_ui_sensitivity_tenths_mv() const noexcept {
        if(sensitivity_raw>15)return std::nullopt;
        return 25u+5u*sensitivity_raw;
    }
};

struct AudioControlsSnapshot {
    std::array<std::uint8_t,22> raw{}; // Includes every still-uninterpreted table byte.
    std::optional<InputControlState> input(std::size_t index) const noexcept {
        if(index>=input_control_indexes.size())return std::nullopt;
        const auto fields=input_control_indexes[index];
        return InputControlState{raw[fields.phono],raw[fields.sensitivity],raw[fields.through]};
    }
};

inline std::optional<AudioControlsSnapshot> audio_controls_snapshot(const Event& event) noexcept {
    if(event.outcome!=Outcome::reply || event.error!=Error::none || event.command!=0x32 || event.payload_bytes!=22)
        return std::nullopt;
    return AudioControlsSnapshot{event.payload};
}

enum class SwitchKind {phono,through};
struct SwitchNotification {
    SwitchKind kind=SwitchKind::phono;
    std::array<std::uint8_t,3> raw{};
    // The original through callback forwards four bytes; its UI reads three.
    // Preserve the extra byte without inventing a fourth channel/status bit.
    std::optional<std::uint8_t> extra;
};
inline std::optional<SwitchNotification> switch_notification(const Event& event) noexcept {
    if(event.outcome!=Outcome::notification || event.error!=Error::none)return std::nullopt;
    if(!((event.command==0x38 && event.payload_bytes==3) || (event.command==0x39 && event.payload_bytes==4)))
        return std::nullopt;
    SwitchNotification result;
    result.kind=event.command==0x38?SwitchKind::phono:SwitchKind::through;
    for(std::size_t i=0;i<result.raw.size();++i)result.raw[i]=event.payload[i];
    if(result.kind==SwitchKind::through)result.extra=event.payload[3];
    return result;
}
}
