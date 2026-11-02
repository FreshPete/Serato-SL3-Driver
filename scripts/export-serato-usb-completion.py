"""Bind discovered USB records to the composite completion branch; no vendor execution."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('completion_image',ROOT/'scripts/export-serato-clock-handshake-evidence.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
CHECKS=[
 (0x1421db981,'cmp','ebx, 1'),(0x1421db984,'jne','0x1421dd6ed'),
 (0x1421db993,'xor','r14d, r14d'),
 (0x1421db9c4,'call','0x140c00aa0'),(0x1421db9ce,'je','0x1421dbb8a'),
 (0x1421db9e8,'call','qword ptr [rax + 0x10]'),(0x1421db9ee,'test','eax, eax'),(0x1421db9f0,'setne','dil'),
 (0x1421dba43,'call','qword ptr [rax + 0x18]'),(0x1421dba46,'movzx','esi, al'),
 (0x1421dba98,'call','qword ptr [rax + 0x28]'),(0x1421dba9b,'movzx','ecx, al'),
 (0x1421dba9e,'add','ecx, edi'),(0x1421dbaa0,'add','ecx, esi'),(0x1421dbaa2,'mov','dword ptr [rsp + 0x98], ecx'),
 (0x1421dbb8a,'call','0x140c00ad0'),(0x1421dbb8f,'movzx','eax, al'),(0x1421dbb92,'mov','dword ptr [rsp + 0x98], eax'),(0x1421dbb99,'jmp','0x1421dbae6'),
 (0x140c0057d,'mov','rax, qword ptr [rcx + 0x38]'),(0x140c0058a,'mov','rax, qword ptr [rcx + 0x30]'),(0x140c0058e,'mov','qword ptr [rdx], rax'),(0x140c00591,'mov','rax, qword ptr [rcx + 0x38]'),(0x140c00595,'mov','qword ptr [rdx + 8], rax'),
 (0x1421dbae6,'mov','esi, r14d'),(0x1421dbae9,'mov','dword ptr [rsp + 0x58], r14d'),
 (0x1421dc5f0,'call','qword ptr [rax + 0x28]'),(0x1421dc5f3,'test','al, al'),(0x1421dc5f5,'je','0x1421dc608'),
 (0x1421dc5fa,'call','0x140be1d00'),(0x1421dc5ff,'test','al, al'),(0x1421dc601,'jne','0x1421dc608'),
 (0x1421dc603,'mov','dil, 1'),(0x1421dc608,'xor','dil, dil'),(0x1421dc652,'test','dil, dil'),
 (0x1421dc655,'je','0x1421dc8e9'),(0x1421dc6cc,'call','0x1421e2150'),
 (0x1421dc743,'cmp','qword ptr [rsp + 0xc0], 0'),(0x1421dc74c,'je','0x1421dc8a0'),
 (0x1421dc85b,'mov','rbx, qword ptr [r15]'),(0x1421dc85e,'movaps','xmm0, xmmword ptr [rsp + 0xc0]'),
 (0x1421dc866,'movdqa','xmmword ptr [rsp + 0x2a0], xmm0'),
 (0x1421dc88a,'lea','rdx, [rsp + 0x2a0]'),(0x1421dc892,'mov','rcx, rbx'),
 (0x1421dc895,'call','0x140c01ae0'),(0x1421dc89a,'inc','esi'),(0x1421dc89c,'mov','dword ptr [rsp + 0x58], esi'),
 (0x1421dc8ee,'cmp','esi, dword ptr [rsp + 0x98]'),(0x1421dc8f5,'jne','0x1421dcede'),
 (0x1421dc8fe,'call','0x140c00aa0'),(0x1421dc903,'test','al, al'),(0x1421dc905,'je','0x1421dcbe3'),
 (0x1421dcbe3,'mov','dl, 1'),(0x1421dcbe5,'mov','rcx, qword ptr [r15]'),(0x1421dcbe8,'call','0x140bc8140'),
 (0x1421dcbf0,'call','0x140c00af0'),(0x1421dcbfa,'test','al, al'),(0x1421dcbfc,'je','0x1421dcda4'),
 (0x140c01af4,'mov','rbp, qword ptr [rdx + 8]'),(0x140c01afb,'mov','rbx, qword ptr [rdx]'),
 (0x140c01afe,'mov','rdi, rcx'),(0x140c01b12,'mov','qword ptr [rdi + 0x20], rbx'),
 (0x140c01b16,'mov','rbx, qword ptr [rdi + 0x28]'),(0x140c01b1a,'mov','qword ptr [rdi + 0x28], rbp'),
]
DEPENDENCIES={
 'serato500-usb-discovery.json':('45e91ca74e7716a99018948e0a4fd502b4453d45557bb453bf0aeecdd8390029','instructions'),
 'serato500-usb-arrival.json':('7d018af5beaa3cb0f1111d3f2c79cff3369bdacec7e9e80f828f98794a3d9f50','checkedInstructions'),
 'serato500-component-profiles.json':('7be2adee7c84b01a6bb3f4ce7d0d68b3d39807d0c4f3368147f73c078b1ff91c','checkedInstructions'),
}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);args=p.parse_args()
 if args.output:h.require(not args.output.exists() and not args.output.is_symlink(),'Fresh output required')
 app=h.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe',h.CURRENT_SHA)
 h.require(sha(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe'))==app.sha,'Installed executable differs')
 facts=[]
 for va,op,operands in CHECKS:
  row=app.at(va,op,operands);facts.append({'va':hex(va),'bytes':row.bytes.hex(),'assembly':row.mnemonic+' '+row.op_str})
 prior=[]
 for name,(expected,key) in DEPENDENCIES.items():
  path=ROOT/'docs/evidence'/name;h.require(sha(path)==expected,'Prior evidence changed')
  value=json.loads(path.read_text(encoding='utf-8'))
  for row in value[key]:
   raw=bytes.fromhex(row['bytes']);h.require(app.data(int(row['va'],16),len(raw))==raw,'Prior instruction drift')
  prior.append({'name':name,'sha256':expected,'instructionBytesRechecked':len(value[key])})
 leaves=[]
 for va,code in [(0x140c00aa0,'48837930000f95c0c3'),(0x140be1d00,'48837920000f95c0c3'),(0x140bc8140,'885160c3')]:
  raw=bytes.fromhex(code);h.require(app.data(va,len(raw))==raw,'Complete helper leaf changed')
  leaves.append({'va':hex(va),'bytes':code,'assembly':[r.mnemonic+' '+r.op_str for r in app.dis.disasm(raw,va)]})
 rows=app.function(0x1421db390);aliases={h.capstone.x86.X86_REG_R14,h.capstone.x86.X86_REG_R14D,h.capstone.x86.X86_REG_R14W,h.capstone.x86.X86_REG_R14B}
 h.require(not any(set(r.regs_access()[1])&aliases for r in rows if 0x1421db993<r.address<0x1421dbae6),'Acquired-count zero source overwritten')
 reports=[]
 for name,start,end in [('serato500-usb-completion-20261102-decompile.json',0x140c01ae0,0x140c01bb8),('serato500-app-support-routing.json',0x1421db390,0x1421dd9d3)]:
  path=ROOT/'analysis'/name;value=json.loads(path.read_text(encoding='utf-8-sig'))
  h.require(value['binary_sha256']==app.sha and (start,end) in app.spans,'Focused image/range differs')
  matches=[f for f in value['functions'] if int(f['start'],16)==start]
  h.require(len(matches)==1 and matches[0]['complete'] is True and int(matches[0]['end_exclusive'],16)==end and matches[0].get('pseudocode') and not matches[0].get('diagnostic'),'Focused function incomplete')
  reports.append({'file':name,'sha256':sha(path),'start':hex(start),'endExclusive':hex(end),'imageBytesSha256':hashlib.sha256(app.data(start,end-start)).hexdigest()})
 log=ROOT/'analysis/serato500-usb-completion-20261102-decompile.log';text=log.read_text(encoding='utf-8')
 h.require(all(t in text for t in ['Loaded 0 additional files','Discarded file import due to readOnly option','Import succeeded']),'Read-only import not verified')
 h.require(not list((ROOT/'analysis/ghidra-usb-completion-20261102').iterdir()),'Temporary project remains')
 sources=['scripts/export-serato-usb-completion.py','scripts/export-serato-clock-handshake-evidence.py','scripts/ghidra/FocusedDecompile.java']
 result={'schema':'sl3.serato-usb-completion.v1','binarySha256':app.sha,'installedMatches':True,'checkedInstructions':facts,'completeHelperLeaves':leaves,'priorEvidence':prior,'focusedFunctions':reports,'freshFocusedFunctions':1,'focusedLogSha256':sha(log),'temporaryProjectAbsent':True,
  'ordinaryComponentBranch':{'condition':'Composite descriptor member +0x30 present','expected':'nonzero MIDI direction + has HID + requires USB','expectedCountStackOffset':'0x98','acquiredCountRegister':'ESI','initialAcquiredCount':0,'absentDescriptorExpectedCount':'HID component presence only','descriptorAccessor':'0x140c00570','descriptorMember':'0x30','descriptorSharedOwnerMember':'0x38'},
  'usbAttachment':{'requires':'requires USB and composite member +0x20 absent','recordTake':'0x1421e2150','recordMissSkipsAttachment':True,'attachMethod':'0x140c01ae0','recordMember':'0x20','sharedOwnerMember':'0x28','incrementsAcquiredCount':1,'usbOpenOrClaimIdentifiedInSetter':False},
  'completionBranch':{'requires':'Acquired count equals expected count','absentMember30Target':'0x1421dcbe3','setsCompositeByte':'0x60 = 1','nextPredicate':'0x140c00af0','nextPredicateIsPhysicalReadiness':False,'supportRequirementStillIndependent':True},
  'sl3ConditionalProjection':{'requiresPresentDescriptor':True,'midiDirection':0,'hasHid':False,'requiresUsb':True,'expectedComponents':1,'meaning':'A matching identity record can contribute the USB component under this branch; other gates remain','actualCompositeOrCompletionObserved':False},
  'localSourceSha256':{n:sha(ROOT/n) for n in sources},'publishedSourceSha256':{n:hashlib.sha256((ROOT/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in sources},
  'applicationExecuted':False,'applicationModified':False,'deviceAccess':False,'authorizationModified':False,'messageInjected':False,'currentSeratoAdmissionVerified':False,'audioOpened':False,'twoDeckDvsVerified':False,
  'limits':['Selected ordinary composite branch and USB-record handoff, not exhaustive control-flow or eligibility proof.','Internal completion byte is not a physical-audio, driver-policy or licensing result.','NONE/control/service semantics, actual descriptor parsing and runtime identity continuity remain unverified.','No descriptor, archive, account, security setting, firmware or hardware identity is changed.']}
 raw=json.dumps(result,indent=2)+'\n'
 if args.output:
  with args.output.open('x',encoding='utf-8',newline='\n') as f:f.write(raw)
 else:print(raw,end='')
if __name__=='__main__':main()
