"""Enumerate the project SL3 WinUSB interface and query descriptors/pipes only.

Opens one exact VID/PID interface. No vendor/control transfers, alternate-setting
selection, reset, audio transfer, policy changes or firmware operations.
"""
import ctypes as C
from ctypes import wintypes as W
import datetime as dt
import json
from pathlib import Path
import struct
import sys
import uuid

GUID_TEXT = '45dfc124-470c-4c58-ba2b-bff7614a64bc'


def collect(interface_action=None):
    """Query only by default; an explicit internal experiment may use open handles.

    The callback runs after descriptor enumeration and before guaranteed handle
    cleanup. The normal command-line probe never supplies a callback.
    """
    if sys.platform != 'win32' or C.sizeof(C.c_void_p) != 8:
        raise RuntimeError('Requires Windows x64 Python')
    setup = C.WinDLL('setupapi', use_last_error=True)
    kernel = C.WinDLL('kernel32', use_last_error=True)
    winusb = C.WinDLL('winusb', use_last_error=True)

    class GUID(C.Structure):
        _fields_ = [('data', C.c_ubyte * 16)]

    class INTERFACE(C.Structure):
        _fields_ = [('size', W.DWORD), ('guid', GUID), ('flags', W.DWORD), ('reserved', C.c_void_p)]

    class DESCRIPTOR(C.Structure):
        _pack_ = 1
        _fields_ = [('length', C.c_ubyte), ('type', C.c_ubyte), ('number', C.c_ubyte),
                    ('alternate', C.c_ubyte), ('endpoints', C.c_ubyte), ('device_class', C.c_ubyte),
                    ('subclass', C.c_ubyte), ('protocol', C.c_ubyte), ('string', C.c_ubyte)]

    class PIPE(C.Structure):
        _fields_ = [('type', C.c_int), ('id', C.c_ubyte), ('max_packet', W.USHORT),
                    ('interval', C.c_ubyte), ('max_bytes_per_interval', W.ULONG)]

    if (C.sizeof(INTERFACE), C.sizeof(DESCRIPTOR), C.sizeof(PIPE)) != (32, 9, 16):
        raise RuntimeError('Unexpected native structure layout; no device opened')

    guid = GUID((C.c_ubyte * 16).from_buffer_copy(uuid.UUID(GUID_TEXT).bytes_le))
    setup.SetupDiGetClassDevsW.argtypes = [C.POINTER(GUID), W.LPCWSTR, W.HWND, W.DWORD]
    setup.SetupDiGetClassDevsW.restype = W.HANDLE
    setup.SetupDiEnumDeviceInterfaces.argtypes = [W.HANDLE, C.c_void_p, C.POINTER(GUID), W.DWORD, C.POINTER(INTERFACE)]
    setup.SetupDiGetDeviceInterfaceDetailW.argtypes = [W.HANDLE, C.POINTER(INTERFACE), C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p]
    setup.SetupDiDestroyDeviceInfoList.argtypes = [W.HANDLE]
    kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    winusb.WinUsb_Initialize.argtypes = [W.HANDLE, C.POINTER(W.HANDLE)]
    winusb.WinUsb_Free.argtypes = [W.HANDLE]
    winusb.WinUsb_GetAssociatedInterface.argtypes = [W.HANDLE, C.c_ubyte, C.POINTER(W.HANDLE)]
    winusb.WinUsb_QueryInterfaceSettings.argtypes = [W.HANDLE, C.c_ubyte, C.POINTER(DESCRIPTOR)]
    winusb.WinUsb_GetCurrentAlternateSetting.argtypes = [W.HANDLE, C.POINTER(C.c_ubyte)]
    winusb.WinUsb_QueryPipeEx.argtypes = [W.HANDLE, C.c_ubyte, C.c_ubyte, C.POINTER(PIPE)]
    info = setup.SetupDiGetClassDevsW(C.byref(guid), None, None, 0x12)
    invalid = C.c_void_p(-1).value
    if info == invalid:
        raise C.WinError(C.get_last_error())
    paths = []
    try:
        index = 0
        while True:
            interface = INTERFACE(); interface.size = C.sizeof(interface)
            if not setup.SetupDiEnumDeviceInterfaces(info, None, C.byref(guid), index, C.byref(interface)):
                if C.get_last_error() == 259:
                    break
                raise C.WinError(C.get_last_error())
            index += 1
            needed = W.DWORD()
            setup.SetupDiGetDeviceInterfaceDetailW(info, C.byref(interface), None, 0, C.byref(needed), None)
            detail = C.create_string_buffer(needed.value)
            struct.pack_into('<I', detail, 0, 8)
            if not setup.SetupDiGetDeviceInterfaceDetailW(info, C.byref(interface), detail, needed, None, None):
                raise C.WinError(C.get_last_error())
            path = C.wstring_at(C.addressof(detail)+4)
            if 'usb#vid_1cc5&pid_0001#' in path.lower():
                paths.append(path)
    finally:
        setup.SetupDiDestroyDeviceInfoList(info)
    if len(paths) != 1:
        raise RuntimeError(f'Expected one project SL3 interface; found {len(paths)}')
    handle = kernel.CreateFileW(paths[0], 0xc0000000, 3, None, 3, 0x40000000, None)
    if handle == invalid:
        raise C.WinError(C.get_last_error())
    interfaces = []
    active_settings = []
    owned = []
    try:
        primary = W.HANDLE()
        if not winusb.WinUsb_Initialize(handle, C.byref(primary)):
            raise C.WinError(C.get_last_error())
        owned.append(primary)
        for index in range(3):
            associated = W.HANDLE()
            if not winusb.WinUsb_GetAssociatedInterface(primary, index, C.byref(associated)):
                raise C.WinError(C.get_last_error())
            owned.append(associated)
        for usb in owned:
            active = C.c_ubyte()
            if not winusb.WinUsb_GetCurrentAlternateSetting(usb, C.byref(active)):
                raise C.WinError(C.get_last_error())
            current = DESCRIPTOR()
            if not winusb.WinUsb_QueryInterfaceSettings(usb, active.value, C.byref(current)):
                raise C.WinError(C.get_last_error())
            active_settings.append({'number': current.number, 'alternate': active.value})
            for alternate in range(2):
                descriptor = DESCRIPTOR()
                if not winusb.WinUsb_QueryInterfaceSettings(usb, alternate, C.byref(descriptor)):
                    error = C.get_last_error()
                    if error == 259:
                        break
                    raise C.WinError(error)
                pipes = []
                for index in range(descriptor.endpoints):
                    pipe = PIPE()
                    if not winusb.WinUsb_QueryPipeEx(usb, alternate, index, C.byref(pipe)):
                        raise C.WinError(C.get_last_error())
                    pipes.append({'id': hex(pipe.id), 'type': pipe.type, 'max_packet': pipe.max_packet,
                                  'interval': pipe.interval, 'max_bytes_per_interval': pipe.max_bytes_per_interval})
                interfaces.append({'number': descriptor.number, 'alternate': descriptor.alternate,
                                   'class': descriptor.device_class, 'pipes': pipes})
        result = {'utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'interface_guid': GUID_TEXT,
                  'initialized': True, 'active_settings': active_settings, 'interfaces': interfaces, 'scope': __doc__}
        if interface_action is not None:
            interface_action(winusb, owned, DESCRIPTOR, PIPE, result)
        return result
    finally:
        for usb in reversed(owned):
            winusb.WinUsb_Free(usb)
        kernel.CloseHandle(handle)


if __name__ == '__main__':
    output = Path(sys.argv[1] if len(sys.argv) > 1 else 'tests/results/local/winusb-probe.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    success = True
    try:
        result = collect()
    except (OSError, RuntimeError) as error:
        success = False
        result = {'utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'initialized':False,
                  'error':str(error), 'scope':__doc__}
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    sys.exit(0 if success else 1)
