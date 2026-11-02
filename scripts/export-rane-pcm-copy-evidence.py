"""Verify the selected original PCM copy and saved raw-byte origins without vendor execution."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
h=module('copy_image','export-serato-clock-handshake-evidence.py')
o=module('copy_origin','audit-capture-origin.py')
KERNEL_SHA='e8e992a8ece1a57eab337d815a406b9f815954176c03db545fcf6d951ec615f5'
CHECKS=[
 (0x13449,'cmp','byte ptr [rdi + 0x2c481], 0'),(0x13450,'jne','0x134f1'),
 (0x13456,'test','r11d, r11d'),(0x13459,'mov','r9d, 6'),(0x1345f,'je','0x13493'),
 (0x13461,'lea','rdx, [rsp + 0x78]'),(0x13466,'mov','r8, r9'),
 (0x13469,'mov','rcx, qword ptr [rdx]'),(0x1346c,'mov','eax, dword ptr [r15]'),
 (0x1346f,'add','r15, 3'),(0x13473,'xor','eax, dword ptr [rcx]'),
 (0x13475,'and','eax, 0xffffff'),(0x1347a,'xor','dword ptr [rcx], eax'),
 (0x1347c,'lea','rax, [rcx + 3]'),(0x13480,'mov','qword ptr [rdx], rax'),
 (0x13483,'add','rdx, 8'),(0x13487,'sub','r8, 1'),(0x1348b,'jne','0x13469'),
 (0x1348d,'add','r11d, -1'),(0x13491,'jne','0x13461'),
 (0x134ca,'mov','eax, dword ptr [r15]'),(0x134cd,'add','r15, 3'),
 (0x134d1,'xor','eax, dword ptr [rcx]'),(0x134d3,'and','eax, 0xffffff'),
 (0x134d8,'xor','dword ptr [rcx], eax'),(0x134da,'lea','rax, [rcx + 3]'),
]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);args=parser.parse_args()
    if args.output:h.require(not args.output.exists() and not args.output.is_symlink(),'Fresh output required')
    kernel=h.Image('artifacts/extracted/rane-windows/x64/strmdrv.sys',KERNEL_SHA)
    asio=h.Image('artifacts/extracted/rane-windows/x64/RaneAsioSL3.dll',h.DRIVER_SHA)
    facts=[]
    for va,op,operands in CHECKS:
        r=kernel.at(va,op,operands);facts.append({'va':hex(va),'bytes':r.bytes.hex(),'assembly':r.mnemonic+' '+r.op_str})
    r=asio.at(0x180010ddc,'mov','dword ptr [rdi + 0x10], 0x11')
    channel_type={'va':hex(r.address),'bytes':r.bytes.hex(),'assembly':r.mnemonic+' '+r.op_str,'asioType':17}
    focus=ROOT/'analysis/rane-kernel-startup.json';value=json.loads(focus.read_text(encoding='utf-8-sig'))
    h.require(value['binary_sha256']==kernel.sha,'Original focused image differs')
    rows=[f for f in value['functions'] if f['start']=='0001301c']
    h.require(len(rows)==1 and rows[0]['complete'] is True and rows[0]['end_exclusive']=='0001395f' and
              (0x1301c,0x1395f) in kernel.spans and rows[0].get('pseudocode') and not rows[0].get('diagnostic'),'Selected original function incomplete')
    historical=ROOT/'docs/evidence/usbdk-physical-checkpoint-20261030.json';history=json.loads(historical.read_text())
    earlier=ROOT/'artifacts/build/checkpoints/com-activation-20261102/manifest.json'
    h.require(sha(earlier)=='199a3b9eb6a9da511211b7a86e33140771c85f18ab2f79a8ca9a2b184022340b','Earlier raw checkpoint differs')
    inventory=json.loads(earlier.read_text())['files'];captures=[];raw_witnesses=0
    for rate,name,key in [(44100,'usbdk-capture-postrestart-20261030-01','capture'),(48000,'usbdk-capture48-postrestart-20261030-01','capture48k')]:
        base=ROOT/'tests/results/local'/name;folder=base/'capture';result=o.audit_directory(folder);old=history[key]
        h.require(sha(base/'run.json')==old['runRecordSha256'] and sha(folder/'capture.json')==old['nativeRecordSha256'] and
                  sha(folder/'capture.pcm')==old['pcmSha256'] and result['reportedRateHz']==rate,'Historical capture provenance changed')
        for n in range(4):
            name_relative=(folder/f'registered-{n}.bin').relative_to(ROOT).as_posix()
            matches=[r for r in inventory if r['path']==name_relative]
            h.require(len(matches)==1 and matches[0]['bytes']==8064 and
                      sha(folder/f'registered-{n}.bin')==matches[0]['sha256']==sha(earlier.parent/name_relative),'Saved raw buffer differs from earlier checkpoint')
            raw_witnesses+=1
        result['earlierCheckpointRawHashesMatched']=4;captures.append(result)
    sources=['scripts/export-rane-pcm-copy-evidence.py','scripts/audit-capture-origin.py','scripts/analyse-capture-pcm.py',
             'scripts/validate-asio-private-trace.py','scripts/export-serato-clock-handshake-evidence.py','tests/test_capture_origin.py']
    result={'schema':'sl3.original-pcm-copy-and-origin.v1','kernelSha256':kernel.sha,'originalAsioSha256':asio.sha,
            'checkedKernelInstructions':facts,'originalAsioTypeStore':channel_type,
            'selectedFunction':{'start':'0x1301c','endExclusive':'0x1395f','imageBytesSha256':hashlib.sha256(kernel.data(0x1301c,0x1395f-0x1301c)).hexdigest(),'completeFocusedReportSha256':sha(focus)},
            'selectedCopyContract':{'channelsPerFrame':6,'bytesPerChannel':3,'bytesPerFrame':18,'mask':'0x00ffffff',
              'store':'destination XOR ((source XOR destination) AND mask)','copiesSampleBitsUnchanged':True,'preservesFourthDestinationByte':True,
              'selectedModeCondition':'Complete-object byte +0x2c481 equals zero; no runtime mode asserted','entireStartupAndRoutingContractVerified':False},
            'historicalPhysicalReportSha256':sha(historical),'savedCaptures':captures,'modelTestsPassed':6,
            'earlierRawCheckpoint':{'name':'com-activation-20261102','manifestSha256':sha(earlier),'registeredFilesMatched':raw_witnesses,'isContemporaneousCaptureTimeWitness':False},
            'localSourceSha256':{n:sha(ROOT/n) for n in sources},
            'publishedSourceSha256':{n:hashlib.sha256((ROOT/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in sources},
            'vendorCodeExecuted':False,'newPhysicalCapture':False,'deviceAccess':False,'audioPlayed':False,'packingChanged':False,'prefixDiscardPolicyAdded':False,
            'startupCauseDiagnosed':False,'physicalAudioVerified':False,'currentSeratoAdmissionVerified':False,'twoDeckDvsVerified':False,
            'limits':['This verifies a selected original byte-copy path and models its low-24-bit stores; it does not execute the vendor driver.',
                      'Historical run/metadata/PCM hashes and all eight raw buffers in an earlier 2 November checkpoint match; that later checkpoint is not a capture-time raw-buffer witness.',
                      'Raw registered-buffer equality binds saved file bytes, not physical ADC provenance, input wiring or correct native DMA/continuity.',
                      'This scope does not newly attest pipe direction/source-pointer bindings or the runtime mode that selects the original copy.',
                      'Source peak values are preserved; neither a startup cause nor a trim/mute/gain policy follows.',
                      'Ring wrap, callback timing, mode selection, full routing and current-worker audio still require separate validation.']}
    raw=json.dumps(result,indent=2)+'\n'
    if args.output:
        with args.output.open('x',encoding='utf-8',newline='\n') as f:f.write(raw)
    else:print(raw,end='')
if __name__=='__main__':main()
