"""Check Serato's JUCE ASIO reset chain from the original PE; no execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reset_image', ROOT/'scripts/export-serato-clock-handshake-evidence.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
require = helper.require


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    app = helper.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe', helper.CURRENT_SHA)
    require(sha(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe')) == app.sha, 'Installed image differs')
    checked = []

    def check(va, op, operands, leaf=None):
        row = leaf[va] if leaf is not None else app.at(va)
        require(row.mnemonic == op and row.op_str == operands, f'Instruction differs: {va:x}')
        checked.append({'va': hex(va), 'bytes': row.bytes.hex(), 'opcode': op, 'operands': operands})
        return row

    def qword(va):
        return struct.unpack('<Q', app.data(va, 8))[0]

    # The secondary vtable receiver is a Timer base, not the complete device.
    vtable, timer_vtable = 0x1431dd708, 0x1431dd7d0
    bases = []
    for table, offset in ((vtable, 0), (timer_vtable, 24)):
        col = qword(table-8)
        fields = struct.unpack('<6I', app.data(col, 24))
        require(fields[0] == 1 and fields[1] == offset and fields[5]+app.base == col, 'RTTI locator differs')
        require(app.text(app.base+fields[3]+16) == '.?AVASIOAudioIODevice@juce@@', 'Wrong complete type')
        hierarchy = struct.unpack('<4I', app.data(app.base+fields[4], 16))
        require(hierarchy[2] == 3, 'Unexpected base count')
        current = []
        for rva in struct.unpack('<3I', app.data(app.base+hierarchy[3], 12)):
            descriptor = struct.unpack('<6I', app.data(app.base+rva, 24))
            current.append({'name': app.text(app.base+descriptor[0]+16), 'memberDisplacement': descriptor[2]})
        require(current == [
            {'name': '.?AVASIOAudioIODevice@juce@@', 'memberDisplacement': 0},
            {'name': '.?AVAudioIODevice@juce@@', 'memberDisplacement': 0},
            {'name': '.?AVTimer@juce@@', 'memberDisplacement': 24}], 'Wrong base hierarchy')
        bases = current
    require(qword(timer_vtable+8) == 0x142212da0, 'Wrong Timer callback')
    check(0x1422081ba, 'lea', 'rcx, [rdi + 0x18]')
    check(0x1422081be, 'call', '0x142213920')
    check(0x1422081c4, 'lea', 'rax, [rip + 0xfd553d]')
    check(0x1422081cb, 'mov', 'qword ptr [rdi], rax')
    check(0x1422081ce, 'lea', 'rax, [rip + 0xfd55fb]')
    check(0x1422081d5, 'mov', 'qword ptr [rdi + 0x18], rax')
    require(app.rip(app.at(0x1422081c4)) == vtable and
            app.rip(app.at(0x1422081ce)) == timer_vtable, 'Constructor vtable binding differs')
    for offset, target in ((0x30, 0x14220f230), (0x38, 0x14220b7d0), (0x48, 0x142212aa0)):
        require(qword(vtable+offset) == target, 'Wrong complete-object virtual method')

    # Special callback slot zero: the constructor registers complete objects in
    # this array, and both dummy-buffer and ordinary-open paths select this leaf.
    check(0x1422083be, 'lea', 'rcx, [rip + 0x1eaf16b]')
    require(app.rip(app.at(0x1422083be)) == 0x1440b7530, 'Wrong active array')
    check(0x1422083c5, 'mov', 'qword ptr [rcx + rax*8], rdi')
    for va, op, operands in [
        (0x14220d731, 'mov', 'rbx, rcx'),
        (0x14220d7c9, 'cmp', 'qword ptr [rip + 0x1ea9d60], rbx'),
        (0x14220d7d0, 'lea', 'rsi, [rcx + 0x40]'),
        (0x14220d7d4, 'jne', '0x14220d803'),
        (0x14220d7e0, 'lea', 'rax, [rip - 0x2fc7]'),
        (0x14220d7e7, 'mov', 'qword ptr [rsi + 0x10], rax'),
        (0x14220d824, 'mov', 'qword ptr [rsp + 0x20], rsi'),
        (0x14220d82c, 'call', 'qword ptr [rax + 0x98]'),
        (0x14220f7e7, 'lea', 'rbx, [rdi + 0x40]'),
        (0x14220f7eb, 'cmp', 'qword ptr [rip + 0x1ea7d3e], rdi'),
        (0x14220f7f2, 'jne', '0x14220f821'),
        (0x14220f7fe, 'lea', 'rax, [rip - 0x4fe5]'),
        (0x14220f805, 'mov', 'qword ptr [rbx + 0x10], rax'),
        (0x14220f840, 'mov', 'qword ptr [rsp + 0x20], rbx'),
        (0x14220f856, 'call', 'qword ptr [rax + 0x98]'),
    ]:
        check(va, op, operands)
    for va in (0x14220d7c9, 0x14220f7eb):
        require(app.rip(app.at(va)) == 0x1440b7530, 'Wrong selected active object')
    for va in (0x14220d7e0, 0x14220f7fe):
        require(app.rip(app.at(va)) == 0x14220a820, 'Wrong message leaf')
    start, end = 0x14220a820, 0x14220a83b
    rows = list(app.dis.disasm(app.data(start, end-start), start))
    require(rows[-1].address+rows[-1].size == end and rows[-1].mnemonic == 'ret', 'Incomplete explicit leaf')
    leaf = {row.address: row for row in rows}
    for va, op, operands in [
        (start, 'mov', 'eax, ecx'),
        (start+2, 'mov', 'rcx, qword ptr [rip + 0x1eacd07]'),
        (start+9, 'test', 'rcx, rcx'), (start+12, 'je', '0x14220a838'),
        (start+14, 'mov', 'r8d, edx'), (start+17, 'mov', 'edx, eax'),
        (start+19, 'jmp', '0x14220a8e0'),
        (start+24, 'xor', 'eax, eax'), (start+26, 'ret', ''),
    ]:
        check(va, op, operands, leaf)
    require(app.rip(leaf[start+2]) == 0x1440b7530, 'Wrong leaf object receiver')

    for va, op, operands in [
        (0x14220a8e4, 'dec', 'edx'), (0x14220a8e6, 'cmp', 'edx, 0xe'),
        (0x14220a8e9, 'ja', '0x14220a913'),
        (0x14220a8ee, 'lea', 'r9, [rip - 0x220a8f5]'),
        (0x14220a8f5, 'mov', 'edx, dword ptr [r9 + rax*4 + 0x220a94c]'),
        (0x14220a8fd, 'add', 'rdx, r9'), (0x14220a900, 'jmp', 'rdx'),
        (0x14220a902, 'cmp', 'r8d, 0xf'), (0x14220a906, 'ja', '0x14220a913'),
        (0x14220a908, 'mov', 'eax, 0x846c'), (0x14220a90d, 'bt', 'eax, r8d'),
        (0x14220a911, 'jb', '0x14220a928'), (0x14220a913, 'xor', 'eax, eax'),
        (0x14220a91a, 'add', 'rcx, 0x18'), (0x14220a91e, 'mov', 'edx, 0x1f4'),
        (0x14220a923, 'call', '0x1422150b0'), (0x14220a928, 'mov', 'eax, 1'),
        (0x14220a932, 'mov', 'eax, 2'), (0x14220a93c, 'inc', 'dword ptr [rcx + 0x7b8]'),
        (0x14220a942, 'mov', 'eax, 1'),
        (0x142212dd1, 'mov', 'rbp, rcx'), (0x142212dd4, 'cmp', 'byte ptr [rcx + 0x79e], 0'),
        (0x142212ddb, 'jne', '0x142212ed3'), (0x142212de1, 'call', '0x1422151c0'),
        (0x142212de6, 'mov', 'r15, qword ptr [rbp + 0x728]'),
        (0x142212ded, 'mov', 'rax, qword ptr [rbp - 0x18]'),
        (0x142212df1, 'lea', 'rcx, [rbp - 0x18]'),
        (0x142212df5, 'call', 'qword ptr [rax + 0x38]'),
        (0x142212df8, 'mov', 'byte ptr [rbp + 0x79d], 1'),
        (0x142212dff, 'mov', 'rax, qword ptr [rbp - 0x18]'),
        (0x142212e03, 'mov', 'rsi, qword ptr [rax + 0x30]'),
        (0x142212e07, 'mov', 'edi, dword ptr [rbp + 0x6c4]'),
        (0x142212e0d, 'movsd', 'xmm6, qword ptr [rbp + 0x6d0]'),
        (0x142212e3b, 'mov', 'dword ptr [rsp + 0x28], edi'),
        (0x142212e3f, 'movsd', 'qword ptr [rsp + 0x20], xmm6'),
        (0x142212e50, 'lea', 'rcx, [rbp - 0x18]'), (0x142212e54, 'call', 'rsi'),
        (0x142212e7f, 'test', 'r15, r15'), (0x142212e82, 'je', '0x142212e92'),
        (0x142212e88, 'mov', 'rdx, r15'), (0x142212e8f, 'call', 'qword ptr [rax + 0x48]'),
        (0x142212ed3, 'mov', 'edx, 0x64'), (0x142212ed8, 'call', '0x1422150b0'),
        (0x14220f663, 'cmp', 'byte ptr [rdi + 0x7b5], 0'),
        (0x14220f66a, 'je', '0x14220f734'), (0x14220f673, 'call', '0x142211340'),
        (0x14220f688, 'call', '0x142212f30'), (0x14220f695, 'call', '0x14220e8c0'),
    ]:
        check(va, op, operands)
    require(app.rip(app.at(0x14220a8ee)) == app.base, 'Wrong jump-table image base')
    destinations = [app.base+rva for rva in struct.unpack('<15I', app.data(0x14220a94c, 60))]
    require(destinations == [0x14220a902, 0x14220a932]+[0x14220a91a]*3+[0x14220a928]+[0x14220a913]*8+[0x14220a93c], 'Selector table differs')
    sdk = ROOT/'artifacts/references/asio-sdk-2.3.4/ASIOSDK/common/asio.h'
    source = re.sub(r'//[^\n]*', '', sdk.read_text(encoding='utf-8'))
    enum = source[source.index('kAsioSelectorSupported = 1'):].split('};', 1)[0]
    selectors = re.findall(r'\bkAsio\w+\b', enum)
    require(selectors == ['kAsioSelectorSupported', 'kAsioEngineVersion', 'kAsioResetRequest', 'kAsioBufferSizeChange',
                         'kAsioResyncRequest', 'kAsioLatenciesChanged', 'kAsioSupportsTimeInfo', 'kAsioSupportsTimeCode',
                         'kAsioMMCCommand', 'kAsioSupportsInputMonitor', 'kAsioSupportsInputGain', 'kAsioSupportsInputMeter',
                         'kAsioSupportsOutputGain', 'kAsioSupportsOutputMeter', 'kAsioOverload', 'kAsioNumMessageSelectors'], 'SDK selector order differs')
    callbacks = source[source.index('typedef struct ASIOCallbacks'):] if 'typedef struct ASIOCallbacks' in source else source[:source.index('} ASIOCallbacks;')].rsplit('typedef struct', 1)[-1]
    callback_names = re.findall(r'\(\*(\w+)\)', callbacks.split('} ASIOCallbacks;', 1)[0])
    require(callback_names == ['bufferSwitch', 'sampleRateDidChange', 'asioMessage', 'bufferSwitchTimeInfo'], 'SDK callback order differs')
    result = {
        'scope': 'Original installed PE static reset chain; no vendor execution or native operation',
        'binarySha256': app.sha, 'installedImageMatches': True, 'sdkSha256': sha(sdk),
        'baseClasses': bases, 'timerSubobjectOffset': 24, 'completeResetFlagOffset': '0x7b5',
        'timerReceiverFlagOffset': '0x79d', 'timerVtable': hex(timer_vtable),
        'explicitMessageLeafRange': [hex(start), hex(end)], 'selectedActiveSlot': 0,
        'sdkCallbackOrder': callback_names, 'boundaryCheckedInstructions': checked,
        'selectorDispatch': [{'selector': n, 'name': selectors[n-1], 'destination': hex(va),
                              'advertisedSupported': bool(0x846c & (1 << n))} for n, va in enumerate(destinations, 1)],
        'timerIntervalArguments': {'resetScheduling': 500, 'modalRetry': 100},
        'findings': [
            'Dummy-buffer setup and ordinary open install the slot-zero leaf as ASIOCallbacks.asioMessage',
            'Non-null active slot-zero object is passed to the common selector handler',
            'Selectors 3, 4 and 5 schedule Timer+24 then return one; support query advertises 3 and 5 but not 4',
            'Timer callback closes complete object, sets complete+0x7b5 and invokes its Open method',
            'Open tests that flag and enters the previously verified IASIO release/create/init path',
            'Saved audio callback is conditionally passed to the complete-object Start method after Open'],
        'limits': ['No runtime reset request, measured timer deadline, active SL3 backend selection or application success proved',
                   'Other active-slot wrapper bindings and external device-change window dispatch are not covered',
                   'No native lifetime, driver policy, registration, firmware or application resources changed']}
    (ROOT/'docs/evidence/serato500-asio-reset.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified original PE ASIO message binding, selector dispatch, Timer subobject and close/flag/open/recreate chain')


if __name__ == '__main__':
    main()
