"""Check the 2.5.6 descriptor-support consumer and local factory-call gate.

Local flow assumes calls return normally; it does not model callees, callbacks,
exceptions, runtime dispatch or executed device/application eligibility.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

import capstone as cs

ROOT=Path(__file__).resolve().parents[1]


def require(ok,message):
    if not ok:raise ValueError(message)


def local_reach(rows,start,targets):
    """Reach instruction addresses only, preserving every unresolved exit."""
    by_address={r.address:r for r in rows};pending=[start];seen=set();unresolved=[]
    first,last=rows[0].address,rows[-1].address+rows[-1].size
    while pending:
        address=pending.pop()
        if address in seen:continue
        require(address in by_address,'Local edge is not an instruction boundary')
        seen.add(address);row=by_address[address];fallthrough=address+row.size
        if row.group(cs.CS_GRP_RET) or row.mnemonic in ('ud2','int3'):continue
        successors=[]
        if row.group(cs.CS_GRP_JUMP):
            if len(row.operands)==1 and row.operands[0].type==cs.CS_OP_IMM:
                destination=row.operands[0].imm
                if destination in by_address:successors.append(destination)
                else:unresolved.append({'site':hex(address),'kind':
                    'non-boundary-branch' if first<=destination<last else 'external-branch','target':hex(destination)})
            else:unresolved.append({'site':hex(address),'kind':'indirect-branch'})
            if row.id not in (cs.x86.X86_INS_JMP,cs.x86.X86_INS_LJMP):successors.append(fallthrough)
        else:successors.append(fallthrough) # Calls are not entered; normal return is assumed.
        for destination in successors:
            if destination in by_address:pending.append(destination)
            else:unresolved.append({'site':hex(address),'kind':'external-fallthrough','target':hex(destination)})
    return {'visitedInstructions':len(seen),'reachedTargets':[hex(t) for t in sorted(set(targets)&seen)],
            'unresolvedExits':unresolved,'normalCallReturnAssumed':True,'exceptionsAndCallbacksModeled':False}


def load(name):
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),ROOT/'scripts'/name)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    prior=load('export-serato-historical-app-support.py');prior.main()
    api=load('export-serato256-sl3-api-path.py');api.main()
    helper=load('export-serato-clock-handshake-evidence.py')
    image=helper.Image('artifacts/extracted/Serato DJ Pro 2.5.6/tree/Serato/Serato DJ Pro/Serato DJ Pro.exe',
                       '3b04472cd5597fd56266e1c2c86dc298431b0026001aefe4b43aa3b909ee35c5')
    facts=[]
    def fact(address,mnemonic,operands=None):
        row=image.at(address,mnemonic,operands)
        facts.append({'va':hex(address),'assembly':row.mnemonic+' '+row.op_str,'bytes':bytes(row.bytes).hex()})
        return row
    def rtti(site,name):
        table=image.rip(fact(site,'lea'));locator=struct.unpack('<Q',image.data(table-8,8))[0]
        signature,offset,constructor,type_rva,hierarchy,self_rva=struct.unpack('<6I',image.data(locator,24))
        require(signature==1 and offset==constructor==0 and locator==image.base+self_rva and
                image.text(image.base+type_rva+16)==name,'Aggregation type differs')
        return {'type':name,'table':hex(table),'locator':hex(locator)}
    manager=rtti(0x1406a45e6,'.?AVDeviceManager@composite@device@serato@@')
    thread=rtti(0x1406a90a2,'.?AVDeviceAggregationThread@composite@device@serato@@')
    delegate=fact(0x1406a91dc,'lea');require(image.rip(delegate)==0x1406a96d0,'Worker delegate differs')
    spans=[(0x14015fef0,0x14016018a),(0x1406a6820,0x1406a6b33),(0x1406a0240,0x1406a0a85),
           (0x14069fd50,0x14069fe33),(0x1406a9030,0x1406a93c6),(0x1406a96d0,0x1406abd8e)]
    for span in spans:require(span in image.spans,'Selected boundary differs')
    source_begin=image.rip(fact(0x140160072,'mov'));source_end=image.rip(fact(0x140160079,'mov'))
    require(source_begin==0x144f4b450 and source_end==image.rip(image.at(0x14035dbf4)),'Parser registry differs')
    selected=[
        # Registered descriptors are copied and passed through their typed +0x10 interface.
        (0x1401600ad,'call','0x1400f0c40'),(0x1401600d5,'call','0x1400f0c40'),
        (0x14016011f,'lea','rax, [rbx + 0x10]'),(0x14016012a,'mov','qword ptr [rsp + 0x60], rax'),
        (0x140160134,'lea','rdx, [rsp + 0x60]'),(0x140160139,'mov','rcx, qword ptr [r14 + 0x28]'),
        (0x14016013d,'call','0x1406a5f40'),
        # Matcher scans the manager's descriptor vector and returns an exact three-word match.
        (0x1406a68ac,'mov','r14, qword ptr [rdi + 0x48]'),(0x1406a68e1,'mov','rdi, qword ptr [r14]'),
        (0x1406a68fe,'call','qword ptr [rax + 0x18]'),(0x1406a691e,'call','qword ptr [rax + 0x20]'),
        (0x1406a693d,'call','qword ptr [rax + 0x28]'),(0x1406a6940,'cmp','ax, r13w'),
        (0x1406a6944,'je','0x1406a6ad0'),(0x1406a6ad0,'mov','qword ptr [r12], rdi'),
        # The selected shared interface feeds the aggregation record constructor.
        (0x1406a03ef,'call','0x1406a6820'),(0x1406a043e,'movaps','xmm0, xmmword ptr [rbp - 0x80]'),
        (0x1406a0442,'movdqa','xmmword ptr [rbp + 0x30], xmm0'),(0x1406a044b,'lea','rdx, [rbp + 0x30]'),
        (0x1406a0452,'call','0x14069fd50'),(0x14069fdb9,'mov','rax, qword ptr [rdx]'),
        (0x14069fdbc,'mov','qword ptr [rcx + 0x40], rax'),
        # Notification processing preserves a known record's descriptor in a new record.
        (0x1406a23f8,'mov','rax, qword ptr [r13 + 0x40]'),(0x1406a23fc,'mov','qword ptr [rbp + 0x30], rax'),
        (0x1406a240c,'lea','rdx, [rbp + 0x30]'),(0x1406a2413,'call','0x14069fd50'),
        (0x1406a2418,'mov','rsi, rax'),(0x1406a2420,'mov','qword ptr [rbp - 0x58], rsi'),
        (0x1406a248b,'mov','r12, qword ptr [rbp - 0x58]'),(0x1406a249e,'mov','qword ptr [rbp + 0x20], r12'),
        (0x1406a2667,'lea','rdx, [rbp + 0x20]'),(0x1406a2672,'call','0x1400deb10'),
        (0x1406a2677,'mov','rsi, rax'),(0x1406a26e3,'mov','qword ptr [rsp + 0x30], rsi'),
        (0x1406a26fb,'call','0x1406a9030'),
        (0x1406a9090,'mov','r10, qword ptr [rsp + 0x190]'),(0x1406a9164,'mov','rax, qword ptr [r10]'),
        (0x1406a9167,'mov','qword ptr [rdi + 0x58], rax'),
        # The supported flag is saved across shared-reference cleanup, then used twice.
        (0x1406a9720,'lea','rsi, [rcx + 0x58]'),(0x1406a9d10,'mov','rcx, qword ptr [rsi]'),
        (0x1406a9d24,'mov','rcx, qword ptr [rcx + 0x40]'),(0x1406a9d38,'mov','rax, qword ptr [rcx]'),
        (0x1406a9d3b,'call','qword ptr [rax + 0x20]'),(0x1406a9d3e,'movzx','edi, al'),
        (0x1406a9d71,'test','dil, dil'),(0x1406a9d74,'jne','0x1406a9e94'),
        (0x1406a9d92,'mov','dword ptr [rsp + 0x94], 9'),(0x1406a9e01,'call','0x1406aea00'),
        (0x1406a9e50,'call','0x1406af100'),(0x1406a9ee3,'test','dil, dil'),
        (0x1406a9ee6,'je','0x1406abd3c'),(0x1406a9f31,'call','0x140681ae0'),
        (0x1406aa18e,'call','0x140681ae0'),(0x1406aa81e,'call','0x140681ae0')]
    for address,mnemonic,operands in selected:fact(address,mnemonic,operands)
    # These small copy/debug helpers have no unwind entry. Retain their exact
    # checked boundaries rather than assigning them an adjacent unwind range.
    leaf_helpers={}
    for start,end,expected in [
        (0x1400deb10,0x1400deb32,['mov rax, qword ptr [rdx]','mov qword ptr [rcx], rax',
            'mov r8, qword ptr [rdx + 8]','mov qword ptr [rcx + 8], r8','test r8, r8',
            'je 0x1400deb2e','mov eax, 1','lock xadd dword ptr [r8 + 8], eax','mov rax, rcx','ret ']),
        (0x1400ac2c0,0x1400ac2d5,['mov qword ptr [rsp + 8], rcx','mov qword ptr [rsp + 0x10], rdx',
            'mov qword ptr [rsp + 0x18], r8','mov qword ptr [rsp + 0x20], r9','ret '])]:
        raw=image.data(start,end-start);decoded=list(image.dis.disasm(raw,start))
        require([r.mnemonic+' '+r.op_str for r in decoded]==expected and decoded[-1].address+decoded[-1].size==end,
                'Shared pointer helper changed')
        leaf_helpers[hex(start)]={'endExclusive':hex(end),'sha256':hashlib.sha256(raw).hexdigest()}
    rows=image.function(0x1406a96d0);targets={0x1406a9f31,0x1406aa18e,0x1406aa81e}
    require(rows[0].address==0x1406a96d0 and rows[-1].address+rows[-1].size==0x1406abd8e and
            all(a.address+a.size==b.address for a,b in zip(rows,rows[1:])),'Worker decoding is incomplete')
    false_path=local_reach(rows,0x1406abd3c,targets);true_path=local_reach(rows,0x1406a9eec,targets)
    require(not false_path['reachedTargets'] and not false_path['unresolvedExits'],'False local branch is not isolated')
    require(set(true_path['reachedTargets'])=={hex(t) for t in targets},'True local path factory calls differ')
    report_files=['support256-aggregation-work-20261101.json','support256-manager-notifications-20261101.json']
    for filename in report_files:
        report=json.loads((ROOT/'analysis'/filename).read_text(encoding='utf-8-sig'))
        require(report['binary_sha256']==image.sha and all(f.get('complete') is True and not f.get('diagnostic')
                for f in report['functions']),'Focused report incomplete')
    record={'scope':'2.5.6 typed descriptor registration, selected record provenance and local support gate',
            'binarySha256':image.sha,'manager':manager,'thread':thread,'workRange':['0x1406a96d0','0x1406abd8e'],
            'registry':[hex(source_begin),hex(source_end)],'facts':facts,'leafHelpers':leaf_helpers,'falseFlagLocalContinuation':false_path,
            'trueFlagLocalContinuation':true_path,'actionOnFalse':9,'actionMeaningResolved':False,
            'runtimeEligibilityVerified':False,'physicalOrCurrentSeratoIntegrationVerified':False,'vendorCodeExecuted':False,
            'focusedReportSha256':{n:sha(ROOT/'analysis'/n) for n in report_files},
            'priorEvidenceSha256':{n:sha(ROOT/'docs/evidence'/n) for n in
                ('serato-historical-app-support-20261101.json','serato256-sl3-api-path.json')},
            'exporterSha256':sha(Path(__file__)),'limits':['Selected static registration/record paths only; no observed runtime descriptor or singleton',
                'Local reachability assumes normal call return and excludes callee effects, exceptions and callbacks',
                'Matching and reaching retained factory code does not prove DLL admission, connection, audio or DVS',
                'Action 9 is not equated with current discontinued handling or account/licensing decisions']}
    (ROOT/'docs/evidence/serato-historical-support-consumer-20261101.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print('Checked historical flag gate: false skips three factory call sites in local normal-return model')


if __name__=='__main__':main()
