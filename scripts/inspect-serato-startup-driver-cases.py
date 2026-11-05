"""Interpret a bounded original startup branch; never execute vendor code."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

APP_SHA = '66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265'
START, END = 0x1421daef0, 0x1421daf41


def evaluate(instructions, values):
    registers = dict(zip(('bl','r15b','r12b','r13b'), values))
    pc = START
    zero = None
    selected = None
    pending = False
    for _ in range(64):
        if pc == END:
            if selected is None or not pending:
                raise ValueError('Branch did not produce a pending case')
            return selected
        item = instructions.get(pc)
        if item is None:
            raise ValueError('Branch left the reviewed instruction boundaries')
        operation, operands, size = item
        next_pc = pc + size
        if operation == 'test' and operands in tuple(f'{key}, {key}' for key in registers):
            zero = not registers[operands.split(',')[0]]
        elif operation in ('je','jne') and zero is not None:
            if zero == (operation == 'je'):
                next_pc = int(operands, 16)
        elif operation == 'jmp':
            next_pc = int(operands, 16)
        elif operation == 'mov' and operands.startswith('dword ptr [rbp + 0x67], '):
            selected = int(operands.rsplit(', ',1)[1],0)
        elif operation == 'mov' and operands == 'byte ptr [rbp + 0x6b], 1':
            pending = True
        else:
            raise ValueError('Unsupported startup instruction: '+operation+' '+operands)
        pc = next_pc
    raise ValueError('Startup branch instruction bound exceeded')


def inspect(path):
    import capstone
    import pefile
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != APP_SHA:
        raise ValueError('Expected original Serato 5.0.0.1278 image')
    pe = pefile.PE(data=data, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXCEPTION']])
    base = pe.OPTIONAL_HEADER.ImageBase
    if not any(base+x.struct.BeginAddress <= START < END <= base+x.struct.EndAddress
               for x in pe.DIRECTORY_ENTRY_EXCEPTION):
        raise ValueError('Branch is not within one PE function range')
    raw = pe.get_data(START-base, END-START)
    decoded = list(capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64).disasm(raw,START))
    if not decoded or sum(x.size for x in decoded) != len(raw):
        raise ValueError('Incomplete startup branch decoding')
    instructions = {x.address:(x.mnemonic,x.op_str,x.size) for x in decoded}
    cases = []
    for inputs in itertools.product((False,True),repeat=4):
        cases.append({'slot50':inputs[0],'slot48':inputs[1],'slot58':inputs[2],'slot90':inputs[3],
                      'pendingCase':evaluate(instructions,inputs)})
    generic_absent = evaluate(instructions,(False,False,False,False))
    generic_installed = evaluate(instructions,(True,True,True,False))
    installed_flag_only = evaluate(instructions,(True,True,True,True))
    return {'schema':'sl3.serato-startup-driver-cases.v1','applicationSha256':APP_SHA,
            'range':[hex(START),hex(END)],'rangeSha256':hashlib.sha256(raw).hexdigest(),
            'decodedInstructions':len(decoded),'cases':cases,
            'genericAbsentCase':generic_absent,'genericInstalledCase':generic_installed,
            'genericInstalledWithOnlySlot90ChangedCase':installed_flag_only,
            'allFourTrueStillSameCase':generic_installed==installed_flag_only,
            'scope':'Local branch after four virtual results; no inferred method semantics or upstream reachability',
            'vendorCodeExecuted':False,'applicationModified':False,'physicalDeviceAccess':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(inspect(args.application),indent=2))
