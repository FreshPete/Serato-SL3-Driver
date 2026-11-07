"""Compare pinned historical USB startup paths without executing vendor code."""

import hashlib
import json
from pathlib import Path
import runpy
import struct


SCRIPTS = Path(__file__).resolve().parent
HISTORICAL = 'artifacts/extracted/Serato DJ Pro {}/tree/Serato/Serato DJ Pro/Serato DJ Pro.exe'
CURRENT = 'artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe'


def module(name):
    return runpy.run_path(str(SCRIPTS/name))


def manager_startup(old, current, require):
    facts = (
        (0x140488eb8,'call','0x1402afb50'),
        (0x1402b1004,'call','0x1401474c0'),
        (0x1401147b8,'lea','eax, [rdx - 0x21]'),
        (0x1401147bb,'cmp','eax, 0xf8'),
        (0x1401147cf,'movzx','eax, byte ptr [rdx + rax + 0x118630]'),
        (0x1401147d7,'mov','ecx, dword ptr [rdx + rax*4 + 0x118570]'),
        (0x1401147e1,'jmp','rcx'),
        (0x140117e3f,'call','0x1401474c0'),
        (0x140117e5e,'mov','edx, 0x13e5'),
        (0x140117e63,'mov','r8d, edx'),
        (0x140117e69,'call','0x140147e10'),
        (0x1401474dc,'cmp','qword ptr [rip + 0x4bf18dc], 0'),
        (0x1401474e4,'jne','0x1401475e0'),
        (0x1401474fd,'je','0x14014750c'),
        (0x140147502,'call','0x140146c00'),
        (0x140147594,'mov','qword ptr [rip + 0x4bf1825], rcx'),
        (0x140146c49,'mov','qword ptr [rcx], rax'),
        (0x140146c53,'mov','qword ptr [rcx + 0x10], rax'),
        (0x140146c81,'lea','rdx, [rdi + 0x10]'),
        (0x140146c8c,'call','0x140480480'),
        (0x140146cb9,'lea','rdx, [rdi + 0x10]'),
        (0x140146cc4,'call','0x140480480'),
        (0x1401478d7,'sub','edx, 0x105'),
        (0x1401478dd,'je','0x140147a9b'),
        (0x140147ab6,'call','0x140147ad0'),
    )
    for address, opcode, operands in facts:
        old.at(address,opcode,operands)
    require(old.rip(old.at(0x1401147c8,'lea'))==old.base,'Historical dispatcher image base differs')
    selector = old.data(old.base+0x118630+0x119-0x21,1)[0]
    destination, = struct.unpack('<I',old.data(old.base+0x118570+selector*4,4))
    require(old.base+destination==0x140117e2c,'Historical USB state message target differs')
    require(old.rip(old.at(0x1401474dc))==old.rip(old.at(0x140147594)), 'Historical singleton store differs')
    for address, table, receiver in ((0x140146c42,0x144745190,0),(0x140146c4c,0x1447451c0,0x10)):
        require(old.rip(old.at(address,'lea'))==table, 'Historical USB manager table differs')
        locator, = struct.unpack('<Q',old.data(table-8,8))
        signature, offset, displacement, name, _, self_rva = struct.unpack('<6I',old.data(locator,24))
        require((signature,offset,displacement)==(1,receiver,0) and old.base+self_rva==locator and
                old.text(old.base+name+16)=='.?AVCUSBAudioManager@@','Historical USB manager RTTI differs')
    require(struct.unpack('<Q',old.data(0x1447451c8,8))[0]==0x1401478d0, 'Historical listener target differs')
    nav = module('inspect-serato-primary-publishers.py')['direct_calls']
    old_calls = nav(old,(0x1402afb50,0x1401474c0,0x140146c00))
    require(list(old_calls.values())==[[0x140488eb8],[0x140117e3f,0x1402b1004],[0x140147502]], 'Historical direct callers differ')
    new_calls = nav(current,(0x140710720,0x14070fd70))
    require(list(new_calls.values())==[[0x141373a93],[0x140710762]], 'Current direct callers differ')
    for address, opcode, operands in (
        (0x141373a5a,'mov','r8d, dword ptr [rdx + 0xc]'),
        (0x141373a5e,'sub','r8d, 0x2ca'),
        (0x141373a6b,'sub','r8d, 1'),
        (0x141373a75,'cmp','r8d, 0x309'),
        (0x141373a7c,'jne','0x141373bf8'),
        (0x141373a93,'call','0x140710720'),
    ):
        current.at(address,opcode,operands)
    return {'historical':{'caller':'0x140488da0','bootstrap':'0x1402afb50','initializer':'0x1401474c0',
                          'constructor':'0x140146c00','listenerOffset':'0x10','arrivalId':0x105,
                          'bootstrapCall':'0x1402b1004','messageHandler':'0x140114740','stateMessage':0x119,
                          'stateMessageCall':'0x140117e3f'},
            'current':{'engineHandler':'0x141373a40','message':0x2ca+1+0x309,'initializer':'0x140710720',
                       'constructor':'0x14070fd70','calls':[hex(rows[0]) for rows in new_calls.values()]}}


def worker_projection(image, start, end, cleanup, after, false_path, true_path, factory, require):
    require((start,end) in image.spans, 'Historical worker extent differs')
    rows = image.function(start)
    shape = module('export-serato-cutoff-caller.py')['shape']
    result = shape(rows,start,end,image.base,image.base+image.pe.OPTIONAL_HEADER.SizeOfImage)
    positions = {row.address:index for index,row in enumerate(rows)}
    first, last = positions[cleanup], positions[after]
    def index(position):
        require(not first<position<last, 'Worker branch enters the replaced cleanup block')
        return position if position<last else position-(last-first-1)
    edges = [[index(source),op,index(target)] for source,op,target in result['localDirectEdges']
             if not first<=source<last]
    instructions = result['instructions'][:first] + [['reviewed cleanup block']] + result['instructions'][last:]
    for op, operands in (entry for entry in instructions if len(entry)==2):
        for operand in operands:
            if operand[0]=='local-control':
                operand[1] = index(operand[1])
    targets = [row.address for row in rows if row.mnemonic=='call' and row.op_str==hex(factory)]
    local_reach = module('export-serato-historical-support-consumer.py')['local_reach']
    rejected = local_reach(rows,false_path,targets)
    admitted = local_reach(rows,true_path,targets)
    require(len(targets)==3 and not rejected['reachedTargets'] and admitted['reachedTargets']==list(map(hex,targets))
            and not rejected['unresolvedExits'] and not admitted['unresolvedExits'], 'Historical worker gate differs')
    return {'imageSha256':image.sha,'range':[hex(start),hex(end)],'instructions':len(rows),
            'replacedCleanupInstructions':last-first,'relocatedReferences':len(result['uncomparedReferences']),
            'falseBranch':rejected,'trueBranch':admitted}, (instructions,edges)


def main():
    api = module('export-serato-clock-handshake-evidence.py')
    require = api['require']
    old = api['Image'](HISTORICAL.format('2.5.5'),api['OLD_SHA'])
    later = api['Image'](HISTORICAL.format('2.5.6'),'3b04472cd5597fd56266e1c2c86dc298431b0026001aefe4b43aa3b909ee35c5')
    current = api['Image'](CURRENT,api['CURRENT_SHA'])
    manager = manager_startup(old,current,require)
    old.at(0x1406a75b6,'je','0x1406a941a')
    later.at(0x1406a9ee6,'je','0x1406abd3c')
    old.at(0x1406a93e6,'lock xadd','dword ptr [rbx + 0xc], eax')
    old.at(0x1406a93f6,'call','qword ptr [rax + 0x10]')
    later.at(0x1406abd16,'call','0x14009fe50')
    helper = [(row.mnemonic,row.op_str) for row in later.dis.disasm(later.data(0x14009fe50,23),0x14009fe50)]
    require(helper==[('mov','eax, 0xffffffff'),('lock xadd','dword ptr [rcx + 0xc], eax'),
                     ('cmp','eax, 1'),('jne','0x14009fe66'),('mov','rax, qword ptr [rcx]'),
                     ('jmp','qword ptr [rax + 0x10]'),('ret','')], 'Out-of-line cleanup leaf differs')
    one, old_projection = worker_projection(old,0x1406a6da0,0x1406a946c,0x1406a93e3,0x1406a93f9,
        0x1406a941a,0x1406a75bc,0x140680270,require)
    two, later_projection = worker_projection(later,0x1406a96d0,0x1406abd8e,0x1406abd13,0x1406abd1b,
        0x1406abd3c,0x1406a9eec,0x140681ae0,require)
    require(old_projection==later_projection, 'Historical worker local projection differs outside cleanup')
    print(json.dumps({'schema':'sl3.serato-historical-usb-startup.v1',
                      'currentImageSha256':current.sha,
                      'exporterSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      'usbManager':manager,'aggregationWorkers':{'2.5.5':one,'2.5.6':two,
                          'matchedInstructionsOutsideCleanup':len(old_projection[0])-1,
                          'matchedLocalEdgesOutsideCleanup':len(old_projection[1])},
                      'runtimeSelectionObserved':False,'vendorCodeExecuted':False,'deviceAccess':False},indent=2))


if __name__=='__main__':
    main()
