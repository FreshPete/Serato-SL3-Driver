#include <Windows.h>
#include <array>
#include <atomic>
#include <cstdio>
#include <thread>

extern "C" __declspec(dllimport) int Sl3ExchangeOwnedDescriptorPair(
    LONG64* published, LONG64* scratch, const LONG64* expected) noexcept;

using Pair = std::array<LONG64, 2>;

bool oneConcurrentWinner() {
    alignas(16) Pair published = {101, 102};
    alignas(16) const Pair expected = published;
    alignas(16) Pair first = {201, 202};
    alignas(16) Pair second = {301, 302};
    std::atomic<unsigned> ready{0};
    std::atomic<bool> start{false};
    int firstResult = -1;
    int secondResult = -1;
    const auto attempt = [&](Pair& scratch, int& result) {
        ++ready;
        while (!start.load()) {
            std::this_thread::yield();
        }
        result = Sl3ExchangeOwnedDescriptorPair(published.data(), scratch.data(), expected.data());
    };
    std::thread firstThread([&] { attempt(first, firstResult); });
    std::thread secondThread([&] { attempt(second, secondResult); });
    while (ready.load() != 2) {
        std::this_thread::yield();
    }
    start.store(true);
    firstThread.join();
    secondThread.join();
    return (firstResult == 1 && secondResult == 0 && published == Pair{201, 202} &&
            first == expected && second == Pair{301, 302}) ||
           (secondResult == 1 && firstResult == 0 && published == Pair{301, 302} &&
            second == expected && first == Pair{201, 202});
}

int main() {
    alignas(16) Pair published = {101, 102};
    alignas(16) Pair scratch = {201, 202};
    alignas(16) Pair expected = published;

    if (Sl3ExchangeOwnedDescriptorPair(published.data(), scratch.data(), expected.data()) != 1 ||
        published != Pair{201, 202} || scratch != Pair{101, 102} || expected != Pair{101, 102}) {
        return 1;
    }
    expected = {201, 103};
    if (Sl3ExchangeOwnedDescriptorPair(published.data(), scratch.data(), expected.data()) != 0 ||
        published != Pair{201, 202} || scratch != Pair{101, 102}) {
        return 2;
    }
    expected = {301, 202};
    if (Sl3ExchangeOwnedDescriptorPair(published.data(), scratch.data(), expected.data()) != 0 ||
        published != Pair{201, 202} || scratch != Pair{101, 102}) {
        return 3;
    }
    if (Sl3ExchangeOwnedDescriptorPair(published.data() + 1, scratch.data(), expected.data()) != -1 ||
        Sl3ExchangeOwnedDescriptorPair(published.data(), published.data(), expected.data()) != -1 ||
        Sl3ExchangeOwnedDescriptorPair(published.data(), scratch.data(), nullptr) != -1) {
        return 4;
    }
    expected = {201, 0};
    if (Sl3ExchangeOwnedDescriptorPair(published.data(), scratch.data(), expected.data()) != -1) {
        return 5;
    }
    for (int attempt = 0; attempt < 32; ++attempt) {
        if (!oneConcurrentWinner()) {
            return 6;
        }
    }
    std::puts("Descriptor pair exchange passed the move, both mismatch cases, invalid arguments and 32 competing writes.");
}
