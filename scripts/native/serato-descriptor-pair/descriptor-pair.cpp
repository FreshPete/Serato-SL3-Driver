#include <Windows.h>
#include <cstdint>
#include <intrin.h>

namespace {
bool alignedPair(const LONG64* pair) noexcept {
    return pair != nullptr && (reinterpret_cast<std::uintptr_t>(pair) & 15) == 0;
}
}

// Each pair already owns a reference. After publication, the private scratch
// pair owns the retired reference and is released by Serato's vector cleanup.
extern "C" __declspec(dllexport) int Sl3ExchangeOwnedDescriptorPair(
    LONG64* published, LONG64* scratch, const LONG64* expected) noexcept {
    if (!IsProcessorFeaturePresent(PF_COMPARE_EXCHANGE128) ||
        !alignedPair(published) || !alignedPair(scratch) || !alignedPair(expected) ||
        published == scratch || published == expected || scratch == expected) {
        return -1;
    }
    if (expected[0] == 0 || expected[1] == 0 || scratch[0] == 0 || scratch[1] == 0 ||
        expected[0] == scratch[0] || expected[1] == scratch[1]) {
        return -1;
    }

    alignas(16) LONG64 comparand[] = {expected[0], expected[1]};
    if (!_InterlockedCompareExchange128(published, scratch[1], scratch[0], comparand)) {
        return 0;
    }
    scratch[0] = comparand[0];
    scratch[1] = comparand[1];
    return 1;
}
