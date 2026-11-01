"""Read SL3 descriptors through Windows USB hub IOCTLs, with no driver rebinding.

Only GET_NODE_INFORMATION, GET_NODE_CONNECTION_INFORMATION_EX and standard
GET_DESCRIPTOR are issued. No vendor requests, reset, firmware or audio writes.
Requires Windows x64. Descriptor reads may require an elevated terminal.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import datetime as dt
import json
from pathlib import Path
import struct
import sys
import uuid

def parse_configuration(data):
    rows = []
    offset = 0
    while offset < len(data):
        if len(data)-offset < 2:
            raise ValueError('Truncated descriptor header')
        size, kind = data[offset:offset+2]
        if size < 2 or offset+size > len(data):
            raise ValueError(f'Invalid descriptor length {size} at {offset}')
        raw = data[offset:offset+size]
        row = dict(offset=offset, type=kind, hex=raw.hex())
        if kind == 2 and size >= 9:
            row.update(total_length=int.from_bytes(raw[2:4], 'little'),interfaces=raw[4],configuration=raw[5])
        elif kind == 4 and size >= 9:
            row.update(interface=raw[2],alternate=raw[3],endpoints=raw[4],interface_class=raw[5],subclass=raw[6],protocol=raw[7])
        elif kind == 5 and size >= 7:
            row.update(endpoint=hex(raw[2]),direction='in' if raw[2]&128 else 'out',
                       transfer=['control','isochronous','bulk','interrupt'][raw[3]&3],
                       attributes=raw[3],max_packet=int.from_bytes(raw[4:6], 'little'),interval=raw[6])
        rows.append(row)
        offset += size
    return rows

def collect():
    if sys.platform != 'win32' or C.sizeof(C.c_void_p) != 8:
        raise RuntimeError('Requires Windows x64 Python')
    setup = C.WinDLL('setupapi', use_last_error=True)
    kernel = C.WinDLL('kernel32', use_last_error=True)
    class GUID(C.Structure):
        _fields_ = [('bytes', C.c_ubyte*16)]
    class INTERFACE(C.Structure):
        _fields_ = [('cbSize', W.DWORD),('guid', GUID),('flags',W.DWORD),('reserved',C.c_void_p)]
    guid = GUID((C.c_ubyte*16).from_buffer_copy(uuid.UUID('f18a0e88-c30c-11d0-8815-00a0c906bed8').bytes_le))
    setup.SetupDiGetClassDevsW.argtypes = [C.POINTER(GUID),W.LPCWSTR,W.HWND,W.DWORD]
    setup.SetupDiGetClassDevsW.restype = W.HANDLE
    setup.SetupDiEnumDeviceInterfaces.argtypes = [W.HANDLE,C.c_void_p,C.POINTER(GUID),W.DWORD,C.POINTER(INTERFACE)]
    setup.SetupDiGetDeviceInterfaceDetailW.argtypes = [W.HANDLE,C.POINTER(INTERFACE),C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p]
    setup.SetupDiDestroyDeviceInfoList.argtypes = [W.HANDLE]
    kernel.CreateFileW.argtypes = [W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.DeviceIoControl.argtypes = [W.HANDLE,W.DWORD,C.c_void_p,W.DWORD,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p]
    kernel.CloseHandle.argtypes = [W.HANDLE]
    invalid = C.c_void_p(-1).value
    errors, devices = [], []
    info = setup.SetupDiGetClassDevsW(C.byref(guid),None,None,0x12)
    if info == invalid:
        raise C.WinError(C.get_last_error())
    def ioctl(handle, code, request, length=4096):
        buffer = C.create_string_buffer(length)
        C.memmove(buffer, request, len(request))
        returned = W.DWORD()
        if not kernel.DeviceIoControl(handle,code,buffer,len(request),buffer,length,C.byref(returned),None):
            raise C.WinError(C.get_last_error())
        return buffer.raw[:returned.value]
    try:
        index = 0
        while True:
            interface = INTERFACE(); interface.cbSize = C.sizeof(INTERFACE)
            if not setup.SetupDiEnumDeviceInterfaces(info,None,C.byref(guid),index,C.byref(interface)):
                if C.get_last_error() == 259:
                    break
                raise C.WinError(C.get_last_error())
            index += 1
            needed = W.DWORD()
            setup.SetupDiGetDeviceInterfaceDetailW(info,C.byref(interface),None,0,C.byref(needed),None)
            detail = C.create_string_buffer(needed.value)
            struct.pack_into('<I', detail,0,8)
            if not setup.SetupDiGetDeviceInterfaceDetailW(info,C.byref(interface),detail,needed,None,None):
                raise C.WinError(C.get_last_error())
            path = C.wstring_at(C.addressof(detail)+4)
            handle = kernel.CreateFileW(path,0,3,None,3,0,None)
            if handle == invalid:
                errors.append(dict(hub_index=index-1,operation='open hub',winerror=C.get_last_error()))
                continue
            try:
                hub = ioctl(handle,0x220408,bytes(76),76)
                if len(hub) < 7:
                    raise ValueError('Short hub information')
                for port in range(1,hub[6]+1):
                    try:
                        # usbioctl.h is packed to one byte: address at 25,
                        # pipe count at 27, status at 31, header length 35.
                        connection = ioctl(handle,0x220448,struct.pack('<I',port)+bytes(4092))
                        if len(connection)<35:
                            continue
                        vendor,product = struct.unpack_from('<HH',connection,12)
                        if (vendor,product) != (0x1cc5,1):
                            continue
                        request = struct.pack('<IBBHHH',port,0x80,6,0x0200,0,4096)
                        config = ioctl(handle,0x220410,request,4108)[12:]
                        total = int.from_bytes(config[2:4],'little') if len(config)>=4 else 0
                        if not total or len(config)<total:
                            raise ValueError('Incomplete configuration descriptor')
                        config = config[:total]
                        devices.append(dict(hub_index=index-1,port=port,device_descriptor_hex=connection[4:22].hex(),
                            speed=connection[23],configuration=connection[22],connection_status=int.from_bytes(connection[31:35],'little'),
                            configuration_descriptor_hex=config.hex(),descriptors=parse_configuration(config)))
                    except (OSError,ValueError) as error:
                        errors.append(dict(hub_index=index-1,port=port,error=str(error)))
            except (OSError,ValueError) as error:
                errors.append(dict(hub_index=index-1,error=str(error)))
            finally:
                kernel.CloseHandle(handle)
    finally:
        setup.SetupDiDestroyDeviceInfoList(info)
    return dict(collected_utc=dt.datetime.now(dt.timezone.utc).isoformat(),devices=devices,errors=errors)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output')
    args = parser.parse_args()
    result = collect()
    out = Path(args.output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
