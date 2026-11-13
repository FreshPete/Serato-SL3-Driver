#include "notice-startup.cpp"

#include <iostream>
#include <stdexcept>
#include <string>

namespace {
void require(bool condition, const char* reason) {
    if (!condition) throw std::runtime_error(reason);
}

void exerciseRetirement(Address initial, Address expected, const char* terminal) {
    auto image = VirtualAlloc(nullptr, slotRva + sizeof(Address), MEM_RESERVE, PAGE_READWRITE);
    require(image != nullptr, "Reserve the synthetic callback slot");
    base = reinterpret_cast<Address>(image);
    const auto page = reinterpret_cast<void*>((base + slotRva) & ~Address{0xfff});
    auto slot = reinterpret_cast<Address*>(base + slotRva);
    require(VirtualAlloc(page, 4096, MEM_COMMIT, PAGE_READWRITE) == page, "Commit the callback page");
    *slot = initial;
    DWORD previous = 0;
    require(VirtualProtect(page, 4096, PAGE_READONLY, &previous) != FALSE, "Protect the callback page");
    HANDLE log = nullptr;
    require(CreatePipe(&log, &journal, nullptr, 0) != FALSE, "Create the retirement journal");
    armed.store(true);

    const auto cleanup = CreateThreadpoolTimer(&retireWithoutMessagePump, nullptr, nullptr);
    require(cleanup != nullptr, "Allocate the cleanup timer");
    scheduleRetirement(cleanup, 10);
    std::string events;
    const auto until = GetTickCount64() + 2000;
    while (GetTickCount64() < until && events.find(terminal) == std::string::npos) {
        char bytes[256]{};
        DWORD available = 0, received = 0;
        require(PeekNamedPipe(log, nullptr, 0, nullptr, &available, nullptr) != FALSE, "Read journal size");
        if (available) {
            require(available <= sizeof bytes && ReadFile(log, bytes, available, &received, nullptr) != FALSE,
                    "Read the retirement journal");
            events.append(bytes, received);
        }
        Sleep(1);
    }

    MEMORY_BASIC_INFORMATION memory{};
    Address actual = 0;
    require(!armed.load() && read(base + slotRva, actual) && actual == (expected ? expected : base + noticeRva) &&
            VirtualQuery(page, &memory, sizeof memory) == sizeof memory && memory.Protect == PAGE_READONLY,
            "Timer leaves the callback slot restored or preserves a foreign owner");
    require(events == std::string("selection_window_expired\n") + terminal, "One expiry and no selection");
    require(!retire(true), "A second retirement has no work");
    CloseHandle(journal);
    CloseHandle(log);
    journal = INVALID_HANDLE_VALUE;
    VirtualFree(image, 0, MEM_RELEASE);
}
}

int main() {
    try {
        exerciseRetirement(reinterpret_cast<Address>(&observeNotice), 0, "notice_observer_retired\n");
        exerciseRetirement(0x1111, 0x1111, "notice_observer_restore_failed\n");
        std::cout << "Retirement without UI dispatch and foreign ownership passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
