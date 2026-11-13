#include "descriptor-reader.hpp"
#include <array>
#include <cstdio>
#include <cstring>

namespace {
constexpr char path[] = "userio/audio/audio_rane_sl3_rebuild.xml";
constexpr char text[] = "<descriptor/>";
int calls = 0;

void* make(void* output, const char* xml) {
    ++calls;
    std::memcpy(output, xml, sizeof(text));
    return output;
}

void sizeField(unsigned char* storage, std::size_t offset, std::size_t value) {
    std::memcpy(storage + offset, &value, sizeof(value));
}
}

int main() {
    std::array<unsigned char, 232> identifier{};
    std::array<char, 32> output{};
    constexpr std::uint32_t pathOffset = 112;
    auto* pathStorage = identifier.data() + pathOffset;
    const char* pathPointer = path;
    std::memcpy(identifier.data(), "resource", 8);
    sizeField(identifier.data(), 16, 8);
    sizeField(identifier.data(), 24, 15);
    std::memcpy(pathStorage, &pathPointer, sizeof(pathPointer));
    sizeField(pathStorage, 16, sizeof(path) - 1);
    sizeField(pathStorage, 24, sizeof(path) - 1);
    char classification{}, fullParse{}, unrelated{};
    DescriptorReadScope scope{{&classification, &fullParse}, text, make, 42, 0, pathOffset,
                              static_cast<std::uint32_t>(identifier.size())};
    const auto scopedRead = [&](const void* caller, std::uint32_t thread = 42) {
        return Sl3SupplyScopedDescriptorText(output.data(), identifier.data(), caller, thread, &scope);
    };
    if (scopedRead(&unrelated) || scopedRead(&classification, 43) || scope.hits || calls) return 1;
    if (scopedRead(&fullParse) || scope.hits != UINT32_MAX || scopedRead(&classification) || calls) return 2;
    scope.hits = 0;
    if (scopedRead(&classification) != output.data() || scope.hits != 1 || scopedRead(&unrelated) || calls != 1) return 3;
    if (scopedRead(&fullParse) != output.data() || scope.hits != 2 || std::strcmp(output.data(), text) || calls != 2) return 4;
    if (scopedRead(&fullParse) || scope.hits != UINT32_MAX || calls != 2) return 5;

    const auto refusesPath = [&] {
        scope.hits = 0;
        return !scopedRead(&classification) && scope.hits == UINT32_MAX && calls == 2;
    };
    identifier[0] = 'R';
    if (!refusesPath()) return 6;
    identifier[0] = 'r';
    sizeField(pathStorage, 24, 15);
    if (!refusesPath()) return 7;
    sizeField(pathStorage, 24, sizeof(path) - 1);
    const char* wrong = "userio/audio/audio_rane_sl2_rebuild.xml";
    std::memcpy(pathStorage, &wrong, sizeof(wrong));
    if (!refusesPath()) return 8;
    std::memcpy(pathStorage, &pathPointer, sizeof(pathPointer));
    scope.pathOffset = 96;
    if (!refusesPath()) return 9;
    scope.pathOffset = pathOffset;
    scope.identifierBytes = pathOffset + 31;
    if (!refusesPath()) return 10;
    std::puts("Descriptor reader accepted the exact resource and refused unrelated or invalid identifiers.");
}
