#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <array>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <cwchar>

namespace {
using Address = std::uintptr_t;
using Notice = void (*)(void*, const void*);
using Publish = void (*)(void*, unsigned, void*, unsigned, unsigned, unsigned, unsigned);
constexpr wchar_t serato[] = L"C:\\Program Files\\Serato\\Serato DJ Pro\\Serato DJ Pro.exe";
constexpr char asioName[] = "SL3 Rebuild Development";
constexpr Address commonOffset = 0x738;
constexpr Address noticeRva = 0x213f740;
constexpr Address publishRva = 0x4db170;
constexpr Address slotRva = 0x31c3f60;

HMODULE self = nullptr;
HANDLE journal = INVALID_HANDLE_VALUE;
Address base = 0;
UINT_PTR timer = 0;
ULONGLONG deadline = 0;
std::atomic<Address> observed{};
std::atomic<bool> armed{};
bool timerInitialized = false;

template<class T>
bool read(Address address, T& value) {
    SIZE_T bytes = 0;
    return ReadProcessMemory(GetCurrentProcess(), reinterpret_cast<void*>(address), &value, sizeof value, &bytes)
        && bytes == sizeof value;
}

void report(const char* line) {
    if (journal != INVALID_HANDLE_VALUE) {
        DWORD written = 0;
        WriteFile(journal, line, static_cast<DWORD>(std::strlen(line)), &written, nullptr);
    }
}

bool exact(Address at, const std::array<unsigned char,8>& expected) {
    std::array<unsigned char,8> actual{};
    return read(at, actual) && actual == expected;
}

bool rebuilt(Address common) {
    if (common < commonOffset) return false;
    const auto descriptor = common - commonOffset;
    Address table = 0, name = 0, length = 0, capacity = 0;
    WORD vid = 0, pid = 0, revision = 0;
    std::array<char,sizeof asioName> text{};
    return read(common, table) && table == base + 0x281cbe8 &&
           read(descriptor, table) && table == base + 0x281caa8 &&
           read(descriptor + 0xa8, vid) && vid == 0x1cc5 &&
           read(descriptor + 0xaa, pid) && pid == 1 &&
           read(descriptor + 0xac, revision) && revision == 0 &&
           read(descriptor + 0x3b0, length) && length == sizeof asioName - 1 &&
           read(descriptor + 0x3b8, capacity) && capacity >= length &&
           read(descriptor + 0x3a0, name) && read(name, text) &&
           std::memcmp(text.data(), asioName, text.size()) == 0;
}

bool registered(Address manager, Address descriptor) {
    Address table = 0, begin = 0, end = 0;
    if (!read(manager, table) || table != base + 0x2808488 ||
        !read(manager + 0xd8, begin) || !read(manager + 0xe0, end) ||
        !begin || end < begin || end - begin > 16384 || (end - begin) % 16)
        return false;
    for (auto item = begin; item < end; item += 16) {
        Address entry = 0;
        if (!read(item, entry)) return false;
        if (entry == descriptor) return true;
    }
    return false;
}

bool replaceSlot(Address expected, Address value) {
    auto slot = reinterpret_cast<void* volatile*>(base + slotRva);
    DWORD protection = 0, ignored = 0;
    if (!VirtualProtect(const_cast<void**>(slot), sizeof(void*), PAGE_READWRITE, &protection)) return false;
    const auto before = InterlockedCompareExchangePointer(
        slot, reinterpret_cast<void*>(value), reinterpret_cast<void*>(expected));
    if (!VirtualProtect(const_cast<void**>(slot), sizeof(void*), protection, &ignored))
        report("notice_page_protection_restore_failed\n");
    return before == reinterpret_cast<void*>(expected);
}

void observeNotice(void* receiver, const void* holder) {
    Address common = 0;
    const bool matches = armed.load() && read(reinterpret_cast<Address>(holder), common) && rebuilt(common);
    reinterpret_cast<Notice>(base + noticeRva)(receiver, holder);
    if (matches && armed.load()) {
        Address empty = 0;
        if (observed.compare_exchange_strong(empty, common)) report("matching_installed_notice\n");
    }
}

bool retire() {
    armed.store(false);
    KillTimer(nullptr, timer);
    timer = 0;
    const bool restored = replaceSlot(reinterpret_cast<Address>(&observeNotice), base + noticeRva);
    report(restored ? "notice_observer_retired\n" : "notice_observer_restore_failed\n");
    return restored;
}

void CALLBACK poll(HWND, UINT, UINT_PTR, DWORD) {
    if (!armed.load()) return;
    if (GetTickCount64() >= deadline) {
        report("selection_window_expired\n");
        retire();
        return;
    }
    const auto common = observed.load();
    if (!common) return;
    const auto descriptor = common - commonOffset;
    Address manager = 0, selected = 0, gate = 0, bus = 0, busTable = 0;
    unsigned char blocked = 0;
    if (!read(base + 0x3eac1d0, manager) || !registered(manager, descriptor) || !rebuilt(common) ||
        !read(manager + 0xf0, selected) || selected ||
        !read(base + 0x3eac1f8, gate) || !gate ||
        !read(gate + 0x319, blocked) || blocked ||
        !read(base + 0x3eac9c8, bus) || !read(bus, busTable) || busTable != base + 0x2f520d8)
        return;
    if (!retire()) return;
    report("selection_requested\n");
    reinterpret_cast<Publish>(base + publishRva)(
        reinterpret_cast<void*>(bus), 0x2ca, reinterpret_cast<void*>(descriptor), 0, 7, 0, 0);
    report("selection_publisher_returned\n");
}

DWORD initializeObserver() {
    wchar_t path[MAX_PATH]{};
    if (!GetModuleFileNameW(nullptr, path, MAX_PATH) || _wcsicmp(path, serato) != 0) return 2;
    if (!GetModuleFileNameW(self, path, MAX_PATH)) return 2;
    auto tail = std::wcsrchr(path, L'\\');
    if (!tail) return 2;
    const auto remaining = MAX_PATH - static_cast<size_t>(tail + 1 - path);
    if (swprintf_s(tail + 1, remaining, L"notice-hook-%lu.log", GetCurrentProcessId()) < 0) return 2;
    journal = CreateFileW(path, FILE_APPEND_DATA, FILE_SHARE_READ, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (journal == INVALID_HANDLE_VALUE) return 2;
    base = reinterpret_cast<Address>(GetModuleHandleW(nullptr));
    if (IsDebuggerPresent() ||
        !exact(base + noticeRva, {0x48,0x89,0x5c,0x24,0x08,0x48,0x89,0x54}) ||
        !exact(base + publishRva, {0x48,0x89,0x5c,0x24,0x10,0x48,0x89,0x6c}) ||
        !exact(base + 0x5b0c48, {0xe8,0x23,0xa5,0xf2,0xff,0x90,0x48,0x8b})) {
        report("image_or_debugger_guard_refused\n");
        return 2;
    }
    HMODULE pinned = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
            reinterpret_cast<LPCWSTR>(&observeNotice), &pinned)) {
        report("notice_observer_pin_failed\n");
        return 2;
    }
    deadline = GetTickCount64() + 45000;
    armed.store(true);
    if (!replaceSlot(base + noticeRva, reinterpret_cast<Address>(&observeNotice))) {
        armed.store(false);
        report("notice_observer_install_failed\n");
        return 2;
    }
    report("notice_observer_armed\n");
    return 0;
}
}

extern "C" __declspec(dllexport) DWORD WINAPI Sl3ObserveEarly(void*) {
    return initializeObserver();
}

extern "C" __declspec(dllexport) LRESULT CALLBACK Sl3GetMessage(int code, WPARAM wparam, LPARAM lparam) {
    if (code == HC_ACTION && wparam == PM_REMOVE && armed.load() && !timerInitialized) {
        timerInitialized = true;
        timer = SetTimer(nullptr, 0, 100, &poll);
        if (timer) report("selection_ui_timer_armed\n");
        else {
            report("selection_timer_failed\n");
            retire();
        }
    }
    return CallNextHookEx(nullptr, code, wparam, lparam);
}

BOOL WINAPI DllMain(HINSTANCE module, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) self = module;
    return TRUE;
}
