#include "descriptor-reader.hpp"
#include <cstring>

namespace {
constexpr std::size_t inlineCapacity = 15;
constexpr std::size_t stringBytes = 32;
constexpr char descriptorPath[] = "userio/audio/audio_rane_sl3_rebuild.xml";

template<std::size_t N>
bool matches(const unsigned char* storage, const char (&expected)[N]) noexcept {
    std::size_t length = 0, capacity = 0;
    std::memcpy(&length, storage + 16, sizeof(length));
    std::memcpy(&capacity, storage + 24, sizeof(capacity));
    if (length != N - 1 || capacity < length) return false;
    const auto* text = reinterpret_cast<const char*>(storage);
    if (capacity > inlineCapacity) std::memcpy(&text, storage, sizeof(text));
    return text != nullptr && std::memcmp(text, expected, length) == 0;
}
// The exact reader ABI supplies uninitialized result storage. Use Serato's
// own constructor so its native caller can release the result normally.
void* supplyDescriptorText(void* output, const unsigned char* identifier, const DescriptorReadScope& scope) {
    if (!output || !identifier || !scope.xml || !scope.make || scope.identifierBytes > 4096 ||
        scope.pathOffset < stringBytes || scope.pathOffset % alignof(void*) ||
        scope.identifierBytes < stringBytes || scope.pathOffset > scope.identifierBytes - stringBytes ||
        !matches(identifier, "resource") || !matches(identifier + scope.pathOffset, descriptorPath)) return nullptr;
    scope.make(output, scope.xml);
    return output;
}
}

extern "C" void* Sl3SupplyScopedDescriptorText(
    void* output, const unsigned char* identifier, const void* caller, std::uint32_t thread,
    DescriptorReadScope* scope) {
    if (!scope || !caller || !thread || thread != scope->thread) return nullptr;
    if (caller != scope->callers[0] && caller != scope->callers[1]) return nullptr;
    const auto hits = scope->hits;
    scope->hits = UINT32_MAX;
    if (hits >= 2 || caller != scope->callers[hits]) return nullptr;
    const auto supplied = supplyDescriptorText(output, identifier, *scope);
    if (supplied) scope->hits = hits + 1;
    return supplied;
}
