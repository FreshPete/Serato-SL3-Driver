"""Plan by default: one cached connection-info query on a selected USB root-hub port.

No SL3 handle, descriptor transfer, reset, cycle, binding, audio or elevation.
Run as a bounded child: the synchronous hub call has no user-mode timeout.
"""
import argparse
import ctypes as c
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
IOCTL=0x220448
HUB_GUID='f18a0e88-c30c-11d0-8815-00a0c906bed8'
STATUS=('NoDeviceConnected','DeviceConnected','DeviceFailedEnumeration','DeviceGeneralFailure',
        'DeviceCausedOvercurrent','DeviceNotEnoughPower','DeviceNotEnoughBandwidth',
        'DeviceHubNestedTooDeeply','DeviceInLegacyHub','DeviceEnumerating','DeviceReset')


class Descriptor(c.LittleEndianStructure):
    _pack_=1
    _fields_=[('length',c.c_uint8),('type',c.c_uint8),('usbBcd',c.c_uint16),('deviceClass',c.c_uint8),
              ('deviceSubClass',c.c_uint8),('deviceProtocol',c.c_uint8),('maximumPacketSize0',c.c_uint8),
              ('vendor',c.c_uint16),('product',c.c_uint16),('deviceBcd',c.c_uint16),
              ('manufacturerIndex',c.c_uint8),('productIndex',c.c_uint8),('serialIndex',c.c_uint8),('configurations',c.c_uint8)]


class Connection(c.LittleEndianStructure):
    _pack_=1
    _fields_=[('index',c.c_uint32),('descriptor',Descriptor),('configuration',c.c_uint8),('speed',c.c_uint8),
              ('isHub',c.c_uint8),('address',c.c_uint16),('openPipes',c.c_uint32),('status',c.c_uint32)]


def require(ok,message):
    if not ok:raise ValueError(message)


def now():return datetime.now(timezone.utc).isoformat()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def layout():
    require(c.sizeof(Descriptor)==18 and c.sizeof(Connection)==35 and Connection.descriptor.offset==4 and
            Connection.configuration.offset==22 and Connection.address.offset==25 and
            Connection.openPipes.offset==27 and Connection.status.offset==31,'USB hub query layout mismatch')


def plan(hub,port):
    require(isinstance(hub,str) and hub.upper().startswith('USB\\ROOT_HUB30\\') and len(hub)<=256 and
            all(ch not in hub for ch in '\0\r\n"'),'Expected one explicit root-hub instance')
    require(type(port) is int and 1<=port<=255,'Invalid physical connection index')
    layout()
    return {'schema':'sl3.hub-port-query.v1','hubInstance':hub,'port':port,'queryIoctl':hex(IOCTL),
            'createFileDesiredAccess':0,'hubOpensRequested':1,'connectionQueriesRequested':1,
            'sl3OpensRequested':0,'usbResetRequests':0,'audioStarts':0,'requestsElevation':False,
            'readinessAdmission':False,'scope':'One cached hub connection observation; no child-device operation',
            'sourceSha256':sha(Path(__file__))}


def decode(raw,returned,port):
    require(type(returned) is int and c.sizeof(Connection)<=returned<=len(raw),'Hub returned a truncated or oversized structure')
    value=Connection.from_buffer_copy(raw)
    require(value.index==port,'Hub response connection index differs')
    require(value.status<len(STATUS),'Unknown hub connection status: '+str(value.status))
    require(value.isHub in (0,1),'Invalid hub boolean: '+str(value.isHub))
    require(value.openPipes<=32,'Hub pipe count exceeds bounded capacity: '+str(value.openPipes))
    require(c.sizeof(Connection)+value.openPipes*11<=len(raw),'Hub pipe list exceeds buffer')
    descriptor=value.descriptor
    require(descriptor.length in (0,18) and (descriptor.length==0 or descriptor.type==1),'Invalid cached device descriptor')
    return {'connectionStatus':int(value.status),'connectionStatusName':STATUS[value.status],
            'speedCode':int(value.speed),'deviceAddress':int(value.address),'currentConfiguration':int(value.configuration),
            'numberOfOpenPipes':int(value.openPipes),'deviceIsHub':bool(value.isHub),'descriptorLength':int(descriptor.length),
            'vendor':int(descriptor.vendor),'product':int(descriptor.product),'deviceRevisionBcd':int(descriptor.deviceBcd),
            'targetDescriptorMatches':descriptor.length==18 and descriptor.vendor==0x1cc5 and descriptor.product==1,
            'readinessAdmission':False}


def own_token():
    spec=importlib.util.spec_from_file_location('hub_port_token',ROOT/'scripts/inspect-loaded-hub.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    return helper.own_token()


def response_evidence(raw,returned):
    """Keep the bounded buffer before parsing, including bytes on failed IOCTLs.

    A header here is uninterpreted evidence, not an accepted connection record.
    bytesReturned remains separate: bytes outside it need not be device data.
    """
    require(len(raw)==c.sizeof(Connection)+32*11,'Unexpected query buffer capacity')
    result={'bufferHex':raw.hex(),'bufferBytes':len(raw),'bytesReturned':returned,
            'returnedLengthWithinBuffer':type(returned) is int and 0<=returned<=len(raw)}
    header=Connection.from_buffer_copy(raw)
    result['unvalidatedHeader']={name:int(getattr(header,name)) for name in
        ('index','configuration','speed','isHub','address','openPipes','status')}
    result['unvalidatedDescriptorHex']=bytes(header.descriptor).hex()
    return result


def enumeration_gap(result):
    """Recognize only the observed zero-index reply, without assigning it to a port."""
    if (result['successful'] is not False or result['error']!='Hub response connection index differs' or
            result['handleClosed'] is not True or result.get('queryWin32Error')!=0):
        return False
    returned=result['bytesReturned']
    evidence=result['responseEvidence']
    raw=bytes.fromhex(evidence['bufferHex'])
    return (returned==c.sizeof(Connection) and evidence==response_evidence(raw,returned) and
            raw[:returned]==bytes(31)+b'\x09\x00\x00\x00')


def run(settings):
    require(os.name=='nt','Windows required')
    token=own_token();require(token['queried'] is True and token['elevated'] is False,'Use a normal user token; no elevated fallback')
    result={**settings,'producerToken':token,'startedUtc':now(),'successful':False,'hubOpenSucceeded':False,
            'queryStarted':False,'queryFinished':False,'handleClosed':False,'error':None}
    kernel=c.WinDLL('kernel32',use_last_error=True);cfg=c.WinDLL('cfgmgr32',use_last_error=True)
    u32=c.c_uint32;ptr=c.c_void_p
    cfg.CM_Get_Device_Interface_List_SizeW.argtypes=[c.POINTER(u32),ptr,c.c_wchar_p,u32]
    cfg.CM_Get_Device_Interface_List_SizeW.restype=u32
    cfg.CM_Get_Device_Interface_ListW.argtypes=[ptr,c.c_wchar_p,ptr,u32,u32]
    cfg.CM_Get_Device_Interface_ListW.restype=u32
    kernel.CreateFileW.argtypes=[c.c_wchar_p,u32,u32,ptr,u32,u32,ptr];kernel.CreateFileW.restype=ptr
    kernel.DeviceIoControl.argtypes=[ptr,u32,ptr,u32,ptr,u32,c.POINTER(u32),ptr];kernel.DeviceIoControl.restype=c.c_int32
    kernel.CloseHandle.argtypes=[ptr];kernel.CloseHandle.restype=c.c_int32
    guid=(c.c_ubyte*16).from_buffer_copy(uuid.UUID(HUB_GUID).bytes_le);size=u32()
    handle=None
    try:
        status=cfg.CM_Get_Device_Interface_List_SizeW(c.byref(size),c.byref(guid),settings['hubInstance'],0)
        require(status==0 and 2<=size.value<=32768,'Hub interface-list size query failed or empty: '+str(status))
        names=c.create_unicode_buffer(size.value)
        status=cfg.CM_Get_Device_Interface_ListW(c.byref(guid),settings['hubInstance'],names,size,0)
        require(status==0,'Hub interface-list query failed: '+str(status))
        paths=[p for p in names[:].split('\0') if p]
        require(len(paths)==1 and paths[0].startswith('\\\\?\\'),'Expected exactly one active interface for this root hub')
        result['hubInterface']=paths[0]
        handle=kernel.CreateFileW(paths[0],0,3,None,3,0,None)
        if handle==c.c_void_p(-1).value:
            handle=None;raise OSError(c.get_last_error(),'Opening hub with zero desired access failed')
        result['hubOpenSucceeded']=True
        buffer=(c.c_ubyte*(c.sizeof(Connection)+32*11))();value=Connection.from_buffer(buffer);value.index=settings['port']
        returned=u32();result['queryStarted']=True;result['queryStartedUtc']=now();start=time.perf_counter_ns()
        ok=kernel.DeviceIoControl(handle,IOCTL,buffer,len(buffer),buffer,len(buffer),c.byref(returned),None)
        native_error=c.get_last_error() if not ok else 0
        result['queryElapsedNanoseconds']=str(time.perf_counter_ns()-start)
        result['queryFinishedUtc']=now();result['queryFinished']=True;result['bytesReturned']=int(returned.value)
        result['queryWin32Error']=native_error
        result['responseEvidence']=response_evidence(bytes(buffer),int(returned.value))
        if not ok:raise OSError(native_error,'Cached hub connection query failed')
        result['connection']=decode(bytes(buffer),int(returned.value),settings['port']);result['successful']=True
    except Exception as error:
        result['error']=str(error)
    finally:
        if handle is not None:
            result['handleClosed']=bool(kernel.CloseHandle(handle))
            if not result['handleClosed']:result['successful']=False;result['closeError']=c.get_last_error()
        result['completedUtc']=now()
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hub-instance',required=True);parser.add_argument('--port',type=int,required=True)
    parser.add_argument('--run',action='store_true');parser.add_argument('--output',type=Path)
    args=parser.parse_args();settings=plan(args.hub_instance,args.port)
    require(not args.run or args.output is not None,'A live query requires a fresh output record')
    if args.output:require(not args.output.exists() and args.output.parent.is_dir(),'Choose a fresh output record')
    result=run(settings) if args.run else settings
    if args.output:
        with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,indent=2))
    raise SystemExit(int(args.run and not result['successful']))
