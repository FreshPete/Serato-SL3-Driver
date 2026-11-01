#include <windows.h>
#include <usbioctl.h>
#include <cstddef>
static_assert(sizeof(USB_DEVICE_DESCRIPTOR)==18);
static_assert(sizeof(USB_NODE_CONNECTION_INFORMATION_EX)==35);
static_assert(offsetof(USB_NODE_CONNECTION_INFORMATION_EX, DeviceDescriptor)==4);
static_assert(offsetof(USB_NODE_CONNECTION_INFORMATION_EX, CurrentConfigurationValue)==22);
static_assert(offsetof(USB_NODE_CONNECTION_INFORMATION_EX, DeviceAddress)==25);
static_assert(offsetof(USB_NODE_CONNECTION_INFORMATION_EX, NumberOfOpenPipes)==27);
static_assert(offsetof(USB_NODE_CONNECTION_INFORMATION_EX, ConnectionStatus)==31);
static_assert(sizeof(USB_PIPE_INFO)==11);
static_assert(IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX==0x220448);
