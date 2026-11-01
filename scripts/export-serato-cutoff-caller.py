"""Compare one historical DriverAPI caller's local instructions, never execute it.

Relocated external calls and RIP references are inventoried, not equated.
Internal direct branch targets retain their exact instruction index.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

import capstone as cs
from capstone import x86

ROOT=Path(__file__).resolve().parents[1]


def require(ok,message):
    if not ok:raise ValueError(message)


def shape(rows,start,end,image_start,image_end):
    require(rows and rows[0].address==start and rows[-1].address+rows[-1].size==end,
            'Incomplete range decoding')
    require(all(a.address+a.size==b.address for a,b in zip(rows,rows[1:])), 'Instruction gap')
    positions={row.address:i for i,row in enumerate(rows)}
    result=[];references=[];edges=[]
    for index,row in enumerate(rows):
        operands=[]
        for operand in row.operands:
            if operand.type==cs.CS_OP_REG:
                value=['register',row.reg_name(operand.reg),operand.size]
            elif operand.type==cs.CS_OP_IMM:
                target=operand.imm
                if row.group(cs.CS_GRP_JUMP) or row.group(cs.CS_GRP_CALL):
                    if start<=target<end:
                        require(target in positions,'Direct branch targets an instruction interior')
                        value=['local-control',positions[target],operand.size]
                        edges.append([index,row.mnemonic,positions[target]])
                    else:
                        value=['external-control',image_start<=target<image_end,operand.size]
                        references.append({'index':index,'kind':'external-control','target':hex(target)})
                elif image_start<=target<image_end:
                    value=['image-address',operand.size]
                    references.append({'index':index,'kind':'image-address','target':hex(target)})
                else:value=['integer',target,operand.size]
            elif operand.type==cs.CS_OP_MEM:
                memory=operand.mem
                displacement=memory.disp
                if memory.base==x86.X86_REG_RIP:
                    references.append({'index':index,'kind':'rip','target':hex(row.address+row.size+displacement)})
                    displacement='relocated-rip'
                value=['memory',row.reg_name(operand.mem.segment),row.reg_name(memory.base),
                       row.reg_name(memory.index),memory.scale,displacement,operand.size]
            else:raise ValueError('Unknown instruction operand')
            operands.append(value)
        result.append([row.mnemonic,operands])
    return {'instructions':result,'localDirectEdges':edges,'uncomparedReferences':references}


def compare(left,right):
    require(len(left['instructions'])==len(right['instructions']),'Instruction counts differ; index pairing refused')
    changes=[{'index':i,'old':a,'new':b} for i,(a,b) in enumerate(zip(left['instructions'],right['instructions'])) if a!=b]
    return {'pairedInstructions':len(left['instructions']),'changes':changes,
            'localDirectEdgesEqual':left['localDirectEdges']==right['localDirectEdges'],
            'localDirectEdgeCount':len(left['localDirectEdges']),
            'uncomparedReferenceCounts':[len(value['uncomparedReferences']) for value in (left,right)]}


def main():
    spec=importlib.util.spec_from_file_location('cutoff_caller_images',ROOT/'scripts/export-serato-clock-handshake-evidence.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    targets=[('2.5.5',helper.OLD_SHA,0x1400f9500,0x1400fb0d7),
             ('2.5.6','3b04472cd5597fd56266e1c2c86dc298431b0026001aefe4b43aa3b909ee35c5',0x1400f9fb0,0x1400fbb87)]
    versions=[];shapes=[];instructions=[]
    for version,digest,start,end in targets:
        image=helper.Image(f'artifacts/extracted/Serato DJ Pro {version}/tree/Serato/Serato DJ Pro/Serato DJ Pro.exe',digest)
        require((start,end) in image.spans,'Unexpected unwind boundary')
        rows=image.function(start);projection=shape(rows,start,end,image.base,image.base+image.pe.OPTIONAL_HEADER.SizeOfImage)
        versions.append({'version':version,'binarySha256':digest,'range':[hex(start),hex(end)],
                         'rangeSha256':hashlib.sha256(image.data(start,end-start)).hexdigest(),
                         'localDirectEdges':projection['localDirectEdges'],'uncomparedReferences':projection['uncomparedReferences']})
        shapes.append(projection);instructions.append(rows)
    comparison=compare(*shapes)
    require(comparison['pairedInstructions']==1595 and len(comparison['changes'])==9 and comparison['localDirectEdgesEqual'],
            'Historical caller comparison changed')
    for change in comparison['changes']:
        for name,rows in zip(('old','new'),instructions):
            row=rows[change['index']]
            change[name+'Instruction']={'va':hex(row.address),'assembly':row.mnemonic+' '+row.op_str,'bytes':bytes(row.bytes).hex()}
    # A displacement hit is not field/type provenance. Check this candidate's
    # actual vtable and receiver before attributing it to the caller's object.
    writer=0x1402d0850;table=0x1449709b0;locator=struct.unpack('<Q',image.data(table-8,8))[0]
    signature,offset,constructor,descriptor,hierarchy,self_rva=struct.unpack('<6I',image.data(locator,24))
    require(signature==1 and self_rva+image.base==locator and offset==0x138 and constructor==0,
            'Writer receiver RTTI changed')
    name=image.text(image.base+descriptor+16)
    require(name=='.?AVCGUIAdvancedPopupMenu@@' and struct.unpack('<Q',image.data(table+0x18,8))[0]==writer,
            'Writer vtable/type changed')
    writer_facts=[]
    for address,mnemonic,operands in [(0x1402d0875,'mov','rsi, rcx'),(0x1402d0878,'cmp','edx, 0x24e'),
                                      (0x1402d087e,'je','0x1402d0bd6'),(0x1402d0bdc,'call','qword ptr [rax + 0x10]'),
                                      (0x1402d0bdf,'mov','byte ptr [rsi + 0x2e9], al')]:
        row=image.at(address,mnemonic,operands)
        writer_facts.append({'va':hex(row.address),'assembly':row.mnemonic+' '+row.op_str,'bytes':bytes(row.bytes).hex()})
    reports={}
    for filename,start,end,digest in [('serato255-device-registration-07.json',targets[0][2],targets[0][3],targets[0][1]),
                                    ('serato256-device-registration-20261101.json',targets[1][2],targets[1][3],targets[1][1]),
                                    ('serato256-field-writer-20261101.json',writer,0x1402d0c06,targets[1][1])]:
        path=ROOT/'analysis'/filename;focused=json.loads(path.read_text(encoding='utf-8-sig'))
        matched=[f for f in focused['functions'] if int(f['start'],16)==start and int(f['end_exclusive'],16)==end]
        require(focused['binary_sha256']==digest and len(matched)==1 and matched[0]['complete'] is True and
                not matched[0].get('diagnostic'),'Focused comparison report changed')
        reports[filename]=hashlib.sha256(path.read_bytes()).hexdigest()
    record={'scope':'Complete linear decoding and local direct-edge comparison of one historical DriverAPI caller',
            'versions':versions,'comparison':comparison,'vendorCodeExecuted':False,
            'focusedReportSha256':reports,
            'candidateDisplacementWriter':{'type':name,'vtable':hex(table),'slot':'0x18','locator':hex(locator),
                'receiverSubobjectOffset':hex(offset),'relativeStoreOffset':'0x2e9',
                'completeObjectOffsetIfDispatchedThroughThisSlot':hex(offset+0x2e9),'facts':writer_facts,
                'sameObjectTypeAsCallerReadProved':False},
            'runtimeEligibilityVerified':False,'currentSeratoIntegrationVerified':False,
            'limits':['External callees, RIP-referenced data and relocated image-address values are not treated as equivalent',
                      'Indirect control-flow targets, runtime predecessors, object types and mutable globals are unresolved',
                      'Equal local direct edges do not establish equivalent behavior or exclude a support cutoff elsewhere'],
            'exporterSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'imageReaderSha256':hashlib.sha256((ROOT/'scripts/export-serato-clock-handshake-evidence.py').read_bytes()).hexdigest()}
    path=ROOT/'docs/evidence/serato-cutoff-caller-20261101.json'
    path.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'instructions':1595,'differences':9,'localEdges':comparison['localDirectEdgeCount'],
                      'uncomparedReferences':comparison['uncomparedReferenceCounts']}))


if __name__=='__main__':main()
