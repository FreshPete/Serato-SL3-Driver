#pragma once

#include <windows.h>
#include <winsvc.h>

namespace sl3::setup_usb {
inline bool driver_running() noexcept {
    const auto manager = OpenSCManagerW(nullptr, nullptr, SC_MANAGER_CONNECT);
    if (!manager) return false;
    const auto driver = OpenServiceW(manager, L"UsbDk", SERVICE_QUERY_STATUS);
    CloseServiceHandle(manager);
    if (!driver) return false;

    SERVICE_STATUS_PROCESS status{};
    DWORD bytes = 0;
    const bool queried = QueryServiceStatusEx(driver, SC_STATUS_PROCESS_INFO,
        reinterpret_cast<BYTE*>(&status), sizeof(status), &bytes) != FALSE;
    CloseServiceHandle(driver);
    return queried && status.dwServiceType == SERVICE_KERNEL_DRIVER && status.dwCurrentState == SERVICE_RUNNING;
}
} // namespace sl3::setup_usb
