"""Correlate a saved SL3 redirect with Serato's installed USB descriptor path."""
import argparse
import json
from pathlib import Path
import runpy
import struct
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
USB_DLL_SHA = '68883bc3254dbb4129cf68b49f9efe149cd50fd15e990c58a94a53d3ed4f7151'
TRACE_SHA = '54d930b440299ada740dc14ce687978558cacc49395b1604e1fdbb61ef518f4b'
CI_SHA = '58ab0ddb8b7fee94391a4fca7b95a1d29db3d5dd471a728c4ef4a3e3fe095cde'
PNP_SHA = '16ecf063ef947fa49e478661e802082f4b80b79867ea6f479c259dca2b29a5cc'
NS = {'e': 'http://schemas.microsoft.com/win/2004/08/events/event'}

# Leaf routines without unwind entries are decoded at their reviewed entry.
LEAVES = {0x18000141f: 5, 0x18000d1a0: 25, 0x180017b90: 24}
FACTS = """
18000141f jmp 0x180005da0
180005dca movups xmm0, xmmword ptr [rbx + 0x64]
180005dce movups xmmword ptr [rdi], xmm0
180005dd1 movzx eax, word ptr [rbx + 0x74]
180005dda mov word ptr [rdi + 0x10], ax
180007a36 mov rax, qword ptr [rip + 0x1db53]
180007a3d lea rdx, [rcx + 0x64]
180007a51 call rax
18000cd33 lea rax, [rip + 0x19d46]
18000cd3c mov qword ptr [rbx + 0x220], rax
18000d1a0 mov rax, qword ptr [rcx + 0x30]
18000d1ab mov rax, qword ptr [rax + 0x220]
18000d1b2 mov r8, qword ptr [rax + 0x28]
18000d1b6 jmp r8
1800172ff call 0x18001ae40
180017309 jne 0x180017359
180017315 call 0x180001438
180017b90 movups xmm0, xmmword ptr [rcx + 0x5b8]
180017b97 movups xmmword ptr [rdx], xmm0
180017b9a movzx eax, word ptr [rcx + 0x5c8]
180017ba1 mov word ptr [rdx + 0x10], ax
18001afe7 mov rcx, qword ptr [rbx + 0xa0]
18001b004 call qword ptr [rip + 0x1a15e]
18001b081 mov dword ptr [rbp - 0x31], r12d
18001b0ae lea r8, [rbp - 0x31]
18001b0c9 mov edx, 0x220448
18001b0ce mov rcx, rdi
18001b0d1 call qword ptr [rip + 0x1a0a9]
18001b0ed movups xmm0, xmmword ptr [rbp - 0x2d]
18001b0e9 movzx eax, word ptr [rbp - 0x1d]
18001b0f1 movups xmmword ptr [rsi + 0x5b8], xmm0
18001b0f8 mov word ptr [rsi + 0x5c8], ax
18001b2eb movzx eax, byte ptr [rbp - 0x18]
18001b2f1 mov byte ptr [rsi + 0x48], al
"""


def descriptor_path(dll, require):
    pe = runpy.run_path(str(ROOT/'scripts/export-serato-clock-handshake-evidence.py'))
    image = pe['Image'](dll, USB_DLL_SHA)
    image.pe.parse_data_directories(directories=[0, 1])
    exports = {item.name: image.base+item.address for item in image.pe.DIRECTORY_ENTRY_EXPORT.symbols}
    imports = {item.address: (entry.dll.lower(), item.name)
               for entry in image.pe.DIRECTORY_ENTRY_IMPORT for item in entry.imports}
    require(exports[b'libusb_get_device_descriptor']==0x18000141f, 'Descriptor export differs')
    for address, name in ((0x18001b004,b'CreateFileA'), (0x18001b0d1,b'DeviceIoControl')):
        require(imports.get(image.rip(image.at(address)))==(b'kernel32.dll',name), 'Hub import differs')
    require(image.rip(image.at(0x18000cd33))==0x180026a80 and
            struct.unpack('<Q',image.data(0x180026aa8,8))[0]==0x180017b90 and
            struct.unpack('<Q',image.data(image.rip(image.at(0x180007a36)),8))[0]==0x18000d1a0,
            'Backend descriptor dispatch differs')
    leaves = {row.address: row for start,size in LEAVES.items()
              for row in image.dis.disasm(image.data(start,size),start)}
    facts = []
    for line in FACTS.strip().splitlines():
        address, mnemonic, operands = line.split(maxsplit=2)
        va = int(address,16)
        row = leaves.get(va) or image.at(va)
        require((row.mnemonic,row.op_str)==(mnemonic,operands), 'Descriptor instruction differs: '+address)
        facts.append({'va':hex(va), 'bytes':row.bytes.hex(), 'assembly':mnemonic+' '+operands})
    return {'sha256':USB_DLL_SHA,'hubIoctl':'0x220448','descriptorBytesFromHubResponse':18,
            'backendDescriptorOffset':'0x5b8','exportedDescriptorOffset':'0x64',
            'observedLibusbWhileRedirected':False,'instructionFacts':facts}


def saved_events(trace, ci, pnp, timeline, require):
    digest, number = timeline['digest'], timeline['number']
    clock = runpy.run_path(str(ROOT/'scripts/validate-usb-state-capture.py'))['filetime']
    for path, expected in ((trace,TRACE_SHA),(ci,CI_SHA),(pnp,PNP_SHA)):
        require(digest(path)==expected, 'Unreviewed saved input: '+path.name)
    rows, total = timeline['parse'](trace)
    require(total==147471, 'Decoded event count differs')
    initial, = (r for r in rows if r['eventId']==6 and r['data'].get('fid_DeviceDescription')=='Rane SL3')
    hub = number(initial['data']['fid_HubDevice'])
    port = number(initial['data']['fid_PortNumber'])
    port_rows = [r for r in rows if number(r['data'].get('fid_HubDevice','0'))==hub
                 and number(r['data'].get('fid_PortNumber','0'))==port]
    redirected, restored = sorted((r for r in port_rows if r['eventId']==61), key=lambda r:clock(r['time']))
    require(all(number(r['data']['fid_NtStatus'])==0 for r in (redirected,restored)), 'Enumeration failed')
    child = number(redirected['data']['fid_UsbDevice'])
    require(port==4 and len({hub,child,number(restored['data']['fid_UsbDevice']),
                            number(initial['data']['fid_UsbDevice'])})==4, 'Port/child mapping differs')
    identity, = (r for r in port_rows if r['eventId']==43 and number(r['data']['fid_UsbDevice'])==child)
    require(clock(redirected['time'])<=clock(identity['time'])<clock(restored['time']) and
            identity['data']['fid_DeviceDescription']=='UsbDk device' and
            'USB#VID_2B23&PID_CAFE&REV_0001#' in identity['data']['fid_DeviceInterfacePath'].upper(),
            'Redirected Windows interface identity differs')

    def event(path, provider, event_id, record_id):
        xml = ET.parse(path)
        system = xml.find('e:System',NS)
        require(system.find('e:Provider',NS).get('Name')==provider and
                system.findtext('e:EventID',namespaces=NS)==event_id and
                system.findtext('e:EventRecordID',namespaces=NS)==record_id, 'Windows event identity differs')
        return system.find('e:TimeCreated',NS).get('SystemTime'), {
            row.get('Name'):row.text for row in xml.findall('e:EventData/e:Data',NS)}

    ci_time, ci_fields = event(ci,'Microsoft-Windows-CodeIntegrity','3077','89256')
    pnp_time, pnp_fields = event(pnp,'Microsoft-Windows-Kernel-PnP','219','84256')
    require(ci_fields['OriginalFileName']=='strmdrv.sys' and
            ci_fields['SHA256 Flat Hash'].lower()=='e8e992a8ece1a57eab337d815a406b9f815954176c03db545fcf6d951ec615f5' and
            ci_fields['Status']=='0xc0e90002' and pnp_fields['DriverName'].startswith('USB\\VID_1CC5&PID_0001\\'),
            'Unexpected original driver/PnP failure')
    delay = clock(ci_time)-clock(restored['time'])
    require(0<delay<1000000 and clock(ci_time)<clock(pnp_time), 'Enforced failure is outside release window')
    return {'port':port,'redirectedWindowsInterfaceVidPid':'2b23:cafe',
            'redirectedInterfaceObservedUtc':identity['time'],'postReleaseEnumerationUtc':restored['time'],
            'codeIntegrityUtc':ci_time,'kernelPnpUtc':pnp_time,'enumerationToPolicyBlockTicks':str(delay),
            'codeIntegrityStatus':ci_fields['Status'],'policy':ci_fields['PolicyName'],
            'policyGuid':ci_fields['PolicyGUID'],'policyVersion':ci_fields['PolicyID'],
            'originalDriverFlatSha256':ci_fields['SHA256 Flat Hash'].lower(),
            'savedInputSha256':{'usbTraceXml':TRACE_SHA,'ci3077Xml':CI_SHA,'pnp219Xml':PNP_SHA}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dll','trace','ci','pnp','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Fresh output required')
    timeline = runpy.run_path(str(ROOT/'scripts/export-reopen-usb-timeline.py'))
    require = timeline['require']
    result = {'schema':'sl3.redirect-discovery-evidence.v1',
              'inspectorSha256':timeline['digest'](Path(__file__)),
              'installedLibrary':descriptor_path(args.dll,require),
              'savedRelease':saved_events(args.trace,args.ci,args.pnp,timeline,require),
              'liveTestPerformed':False,'seratoSelectionVerified':False,'readinessAdmission':False}
    with args.output.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(result,stream,indent=2)
        stream.write('\n')


if __name__=='__main__':
    main()
