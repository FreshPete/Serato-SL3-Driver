"""Read cached Microsoft USBHUB3 symbols offline; no driver/device access."""
import argparse
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
from pathlib import Path
import struct
import uuid

import capstone
import pefile

ROOT=Path(__file__).resolve().parents[1]
REFERENCE=ROOT/'artifacts/references/windows-usbhub3'
IMAGE_SHA='f93fa3a32037c597fd19ca9d65f59e53a1e337123582ed2479d5c16a4848df16'
PDB_SHA='63c7a9e69445700717fe3f69bc468f6f7a11e6358e5054c1a933388037cc19f5'


def require(ok,reason):
    if not ok:raise ValueError(reason)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def pdb_identity(path):
    require(56<=path.stat().st_size<=64*1024*1024,'PDB size exceeds bound')
    raw=path.read_bytes();require(raw[:32]==b'Microsoft C/C++ MSF 7.00\r\n\x1aDS\0\0\0','Expected MSF 7 PDB')
    block,_,blocks,size,_,block_map=struct.unpack_from('<6I',raw,32)
    require(512<=block<=65536 and not block&(block-1) and blocks*block==len(raw) and size<=len(raw),'Invalid MSF geometry')
    count=(size+block-1)//block
    require((block_map*block+4*count)<=len(raw),'Invalid directory block map')
    indexes=struct.unpack_from(f'<{count}I',raw,block_map*block)
    require(all(i<blocks for i in indexes),'Invalid directory block')
    directory=b''.join(raw[i*block:(i+1)*block] for i in indexes)[:size]
    streams=struct.unpack_from('<I',directory)[0]
    require(4<=streams<=65536 and 4+4*streams<=len(directory),'Invalid stream table')
    sizes=struct.unpack_from(f'<{streams}I',directory,4);at=4+4*streams;info=None;dbi=None
    for n,length in enumerate(sizes):
        if length==0xffffffff:continue
        pages=(length+block-1)//block
        require(length<=len(raw) and at+4*pages<=len(directory),'Invalid stream extent')
        indexes=struct.unpack_from(f'<{pages}I',directory,at);at+=4*pages
        require(all(i<blocks for i in indexes),'Invalid stream block')
        if n==1:info=b''.join(raw[i*block:(i+1)*block] for i in indexes)[:length]
        if n==3:dbi=b''.join(raw[i*block:(i+1)*block] for i in indexes)[:length]
    require(info is not None and len(info)>=28,'Missing PDB info stream')
    require(dbi is not None and len(dbi)>=64 and struct.unpack_from('<2I',dbi)==(0xffffffff,19990903),'Expected modern DBI header')
    return {'guid':uuid.UUID(bytes_le=info[12:28]).hex.upper(),'infoAge':struct.unpack_from('<I',info,8)[0],
            'dbiAge':struct.unpack_from('<I',dbi,8)[0]}


def image_identity(path):
    pe=pefile.PE(str(path));rows=[]
    for item in pe.DIRECTORY_ENTRY_DEBUG:
        raw=pe.get_data(item.struct.AddressOfRawData,item.struct.SizeOfData)
        if raw[:4]==b'RSDS':rows.append({'guid':uuid.UUID(bytes_le=raw[4:20]).hex.upper(),'age':struct.unpack_from('<I',raw,20)[0],
                                        'name':raw[24:].rstrip(b'\0').decode('ascii')})
    require(len(rows)==1,'Expected one image RSDS identity')
    return rows[0]


class Symbol(c.Structure):
    _fields_=[('SizeOfStruct',w.ULONG),('TypeIndex',w.ULONG),('Reserved',c.c_ulonglong*2),('Index',w.ULONG),('Size',w.ULONG),
             ('ModBase',c.c_ulonglong),('Flags',w.ULONG),('Value',c.c_ulonglong),('Address',c.c_ulonglong),('Register',w.ULONG),
             ('Scope',w.ULONG),('Tag',w.ULONG),('NameLen',w.ULONG),('MaxNameLen',w.ULONG),('Name',w.WCHAR*1)]


class VariantValue(c.Union):
    _fields_=[('signed',c.c_longlong),('unsigned',c.c_ulonglong),('bytes',c.c_ubyte*16)]


class Variant(c.Structure):
    _fields_=[('vt',w.WORD),('reserved',w.WORD*3),('value',VariantValue)]


def inspect(image,pdb,*,symbol_masks=(),layout_names=(),enum_names=()):
    identity=image_identity(image);actual=pdb_identity(pdb)
    # Microsoft's PDB1::OpenValidate4 requires matching GUID, PDB age >= image
    # age and matching nonzero DBI age. Public PDB info and DBI ages can differ.
    require(identity['guid']==actual['guid'] and actual['infoAge']>=identity['age'] and actual['dbiAge']==identity['age'],
            'PDB GUID/age does not match image')
    require(sha(image)==IMAGE_SHA and sha(pdb)==PDB_SHA,'Unreviewed image/PDB bytes')
    kernel=c.WinDLL(r'C:\Windows\System32\kernel32.dll',use_last_error=True)
    dbghelp_path=Path(r'C:\Windows\System32\dbghelp.dll');dbg=c.WinDLL(str(dbghelp_path),use_last_error=True)
    kernel.GetCurrentProcess.restype=w.HANDLE;process=kernel.GetCurrentProcess()
    kernel.LocalFree.argtypes=[c.c_void_p];kernel.LocalFree.restype=c.c_void_p
    dbg.SymSetOptions.argtypes=[w.DWORD];dbg.SymSetOptions.restype=w.DWORD
    dbg.SymInitializeW.argtypes=[w.HANDLE,w.LPCWSTR,w.BOOL];dbg.SymInitializeW.restype=w.BOOL
    dbg.SymCleanup.argtypes=[w.HANDLE];dbg.SymCleanup.restype=w.BOOL
    dbg.SymLoadModuleExW.argtypes=[w.HANDLE,w.HANDLE,w.LPCWSTR,w.LPCWSTR,c.c_ulonglong,w.DWORD,c.c_void_p,w.DWORD]
    dbg.SymLoadModuleExW.restype=c.c_ulonglong
    callback=c.WINFUNCTYPE(w.BOOL,c.POINTER(Symbol),w.ULONG,c.c_void_p)
    dbg.SymEnumTypesW.argtypes=[w.HANDLE,c.c_ulonglong,callback,c.c_void_p];dbg.SymEnumTypesW.restype=w.BOOL
    dbg.SymEnumSymbolsW.argtypes=[w.HANDLE,c.c_ulonglong,w.LPCWSTR,callback,c.c_void_p];dbg.SymEnumSymbolsW.restype=w.BOOL
    dbg.SymGetTypeInfo.argtypes=[w.HANDLE,c.c_ulonglong,w.ULONG,c.c_int,c.c_void_p];dbg.SymGetTypeInfo.restype=w.BOOL
    # No network symbol path, source-server execution or target-process invasion.
    dbg.SymSetOptions(0x2|0x4|0x200|0x400|0x80000)
    require(dbg.SymInitializeW(process,str(pdb.parent),False),'Initialize offline symbol handler')
    try:
        base=dbg.SymLoadModuleExW(process,None,str(image),'usbhub3',0x180000000,0,None,0)
        require(base,'Read image symbol metadata')
        types=[];callback_errors=[]
        @callback
        def found(ptr,size,context):
            try:
                symbol=ptr.contents
                require(symbol.NameLen<=4096,'Oversized type name')
                name=c.wstring_at(c.addressof(symbol)+Symbol.Name.offset,symbol.NameLen).rstrip('\0')
                types.append({'name':name,'typeIndex':symbol.TypeIndex,'tag':symbol.Tag});return True
            except Exception as error:callback_errors.append(str(error));return False
        require(dbg.SymEnumTypesW(process,base,found,None) and not callback_errors,'Enumerate type metadata')
        symbols=[]
        @callback
        def symbol_found(ptr,size,context):
            try:
                value=ptr.contents;require(value.NameLen<=4096,'Oversized symbol name')
                name=c.wstring_at(c.addressof(value)+Symbol.Name.offset,value.NameLen).rstrip('\0')
                require(base<=value.Address<base+0x10000000,'Symbol outside image range')
                symbols.append({'name':name,'rva':value.Address-base,'size':value.Size,'tag':value.Tag});return True
            except Exception as error:callback_errors.append(str(error));return False
        for mask in ('*HUBSM*','DSMStateTable','*StateEntryStoppedEnumerated*','*StateEntryResettingPipeInUCXOnClientReset*','HUBDSM_Stopped*',*symbol_masks):
            require(dbg.SymEnumSymbolsW(process,base,mask,symbol_found,None) and not callback_errors,'Enumerate state-machine symbols')
        symbols=list({(x['name'],x['rva']):x for x in symbols}.values())
        def info(index,kind,output):
            require(dbg.SymGetTypeInfo(process,base,index,kind,c.byref(output)),f'Read type {index}/{kind}')
        enums={}
        for name in ('_DSM_STATE','_DSM_EVENT','_DSM_STATE_ETW','_HSM_STATE','_HSM_EVENT','_PSM20_STATE','_PSM30_STATE','_PSM_EVENT',*enum_names):
            matches=[x for x in types if x['name']==name and x['tag']==12]
            require(len(matches)==1,'Expected unique enum: '+name);index=matches[0]['typeIndex'];count=w.ULONG()
            info(index,13,count);require(0<count.value<=4096,'Enum member count exceeds bound')
            class Children(c.Structure):_fields_=[('Count',w.ULONG),('Start',w.ULONG),('ChildId',w.ULONG*count.value)]
            children=Children();children.Count=count.value;info(index,7,children);values=[]
            for child in children.ChildId:
                pointer=c.c_void_p();info(child,1,pointer)
                try:member=c.wstring_at(pointer)
                finally:kernel.LocalFree(pointer)
                value=Variant();info(child,11,value)
                widths={2:(16,True),3:(32,True),18:(16,False),19:(32,False),20:(64,True),21:(64,False),22:(32,True),23:(32,False)}
                require(value.vt in widths,'Noninteger enum value')
                bits,signed=widths[value.vt];number=value.value.unsigned&((1<<bits)-1)
                if signed and number&(1<<(bits-1)):number-=1<<bits
                values.append({'name':member,'value':number})
            require(len({x['name'] for x in values})==len(values),'Duplicate enum member name')
            enums[name]={'typeIndex':index,'members':values}
        layouts=[]
        for row in types:
            if row['tag']!=11 or not (row['name'] in layout_names or any(s in row['name'] for s in ('STATE_ENTRY','STATE_TRANSITION','SM_CONTEXT','STATE_MACHINE_CONTEXT'))):continue
            index=row['typeIndex'];length=c.c_ulonglong();count=w.ULONG();info(index,2,length);info(index,13,count)
            require(count.value<=4096,'Struct member count exceeds bound')
            class Fields(c.Structure):_fields_=[('Count',w.ULONG),('Start',w.ULONG),('ChildId',w.ULONG*count.value)]
            fields=Fields();fields.Count=count.value;info(index,7,fields);members=[]
            for child in fields.ChildId:
                pointer=c.c_void_p();info(child,1,pointer)
                try:member=c.wstring_at(pointer)
                finally:kernel.LocalFree(pointer)
                offset=w.ULONG();field_type=w.ULONG();info(child,10,offset);info(child,4,field_type)
                members.append({'name':member,'offset':offset.value,'typeIndex':field_type.value})
            layouts.append({**row,'length':length.value,'members':members})
        result={'scope':'Offline enum definitions from the pinned installed-image/public-PDB pair; not a live kernel state or historical-image identity proof',
                'imageSha256':sha(image),'pdbSha256':sha(pdb),'rsds':identity,'pdbIdentity':actual,'dbghelpSha256':sha(dbghelp_path),
                'enumeratedTypes':len(types),'enums':enums,'symbols':symbols,'layouts':layouts,
                'selected':{name:[x for x in data['members'] if x['value'] in (0x1080,0xfab)] for name,data in enums.items()}}
        result['imageSemantics']=semantics(image,result)
        return result
    finally:require(dbg.SymCleanup(process),'Release offline symbol handler')


def semantics(image,result):
    pe=pefile.PE(str(image));symbols=result['symbols'];engine=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
    def symbol(name):
        found=[x for x in symbols if x['name']==name];require(len(found)==1,'Missing unique symbol: '+name);return found[0]
    def layout(name,fields):
        found=[x for x in result['layouts'] if x['name']==name]
        require(found and all({m['name']:m['offset'] for m in x['members']}==fields for x in found),'Unexpected layout: '+name)
    layout('_STATE_ENTRY',{'EtwName':0,'EntryFunc':8,'StateFlags':16,'SubSmEntries':24,'Transitions':32})
    layout('_STATE_TRANSITION',{'Event':0,'TargetState':4})
    require(all(x['length']==8 for x in result['layouts'] if x['name']=='_STATE_TRANSITION'),'Transition stride differs')
    context=next(x for x in result['layouts'] if x['name']=='_SM_CONTEXT')
    offsets={x['name']:x['offset'] for x in context['members']}
    require(all(offsets[k]==v for k,v in {'CurrentState':0x354,'StateTable':0x3d0,'StartIndex':0x3d8}.items()),'State lookup offsets differ')
    logger=symbol('HUBSM_LogUnhandledEvent')['rva']
    boundaries=[x.struct for x in pe.DIRECTORY_ENTRY_EXCEPTION if x.struct.BeginAddress==logger]
    require(len(boundaries)==1,'Logger function boundary missing')
    end=boundaries[0].EndAddress;code=list(engine.disasm(pe.get_data(logger,end-logger),logger))
    texts={i.address:i.mnemonic+' '+i.op_str for i in code}
    expected={0xbe86:'mov edx, dword ptr [rdi + 0x3d8]',0xbe8c:'mov ecx, dword ptr [rdi + 0x354]',
              0xbe92:'mov rax, qword ptr [rdi + 0x3d0]',0xbe99:'sub ecx, edx',0xbea6:'mov rax, qword ptr [rax + rcx*8]',
              0xbeaa:'mov eax, dword ptr [rax]',0xbeac:'mov dword ptr [rsp + 0x30], eax',
              0xbea2:'mov dword ptr [rsp + 0x38], ebx',0xbeb7:'mov dword ptr [rsp + 0x28], edx',
              0xbebb:'lea rdx, [rip + 0x5679e]',0xbec7:'call 0xc5b4'}
    require(all(texts.get(address)==text for address,text in expected.items()),'Unhandled-event logger dataflow differs')
    descriptor_rva=0xbebb+7+0x5679e;descriptor=struct.unpack('<HBBBBHQ',pe.get_data(descriptor_rva,16))
    require(descriptor==(111,0,16,2,11,13,0x4000000000000001),'Unhandled event descriptor differs')
    internal={m['name']:m['value'] for m in result['enums']['_DSM_STATE']['members']}
    event_names={m['value']:m['name'] for m in result['enums']['_DSM_EVENT']['members']}
    state_names={m['value']:m['name'] for m in result['enums']['_DSM_STATE']['members']}
    etw_names={m['value']:m['name'] for m in result['enums']['_DSM_STATE_ETW']['members']}
    table=symbol('DSMStateTable')['rva'];entries=[]
    for name in ('DsmStateStoppedEnumerated','DsmStateStopped'):
        value=internal[name];pointer=struct.unpack('<Q',pe.get_data(table+(value-4000)*8,8))[0]
        rva=pointer-pe.OPTIONAL_HEADER.ImageBase;require(0<rva<pe.OPTIONAL_HEADER.SizeOfImage,'Invalid state-entry pointer')
        etw,_,function,flags,_,submachines=struct.unpack('<IIQIIQ',pe.get_data(rva,32))
        transitions=[]
        for n in range(128):
            event,target=struct.unpack('<II',pe.get_data(rva+32+8*n,8))
            require(event in event_names and target in state_names,'Unknown transition enum')
            transitions.append({'event':event,'eventName':event_names[event],'target':target,'targetName':state_names[target]})
            if event_names[event]=='DsmEventNull':
                require(state_names[target]=='DsmStateNull','Invalid transition terminator');break
        else:raise ValueError('State transition table missing bounded terminator')
        entries.append({'name':name,'internalValue':value,'entryRva':rva,'entryFunctionRva':function-pe.OPTIONAL_HEADER.ImageBase,
                        'etwValue':etw,'etwName':etw_names[etw],'stateFlags':flags,'submachineTableRva':submachines-pe.OPTIONAL_HEADER.ImageBase if submachines else None,
                        'transitions':transitions,'topLevelClientCyclePresent':any(t['eventName']=='DsmEventClientRequestCycle' for t in transitions)})
    require(entries[0]['etwValue']==0x1080 and not entries[0]['topLevelClientCyclePresent'],'Stopped-enumerated interpretation differs')
    return {'unhandledLoggerRva':logger,'unhandledLoggerEndRva':end,'unhandledLoggerBytesSha256':hashlib.sha256(pe.get_data(logger,end-logger)).hexdigest(),
            'unhandledLoggerInstructions':[{'rva':i.address,'text':i.mnemonic+' '+i.op_str} for i in code],
            'verifiedLoggerInstructions':[{'rva':address,'text':text} for address,text in expected.items()],
            'eventDescriptorRva':descriptor_rva,'eventId':111,'eventTask':13,'stateFieldIsEntryEtwName':True,
            'stateTableRva':table,'stateEntries':entries}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,default=REFERENCE/'USBHUB3.SYS')
    parser.add_argument('--pdb',type=Path,default=REFERENCE/'usbhub3.pdb')
    parser.add_argument('--output',type=Path,default=ROOT/'analysis/usbhub3-state-symbols.json');args=parser.parse_args()
    result=inspect(args.image.resolve(),args.pdb.resolve())
    result['exporterSha256']=sha(Path(__file__))
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'enumeratedTypes':result['enumeratedTypes'],'selected':result['selected']},indent=2))


if __name__=='__main__':main()
