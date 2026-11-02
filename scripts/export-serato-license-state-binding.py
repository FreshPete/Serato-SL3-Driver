"""Identify LicenseController readiness properties and updates; never query or change licensing."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('license_image', ROOT/'scripts/export-serato-clock-handshake-evidence.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
CHECKS = [
    (0x141538ca6, 'mov', 'r13, rcx'), (0x141538cb4, 'xor', 'ebx, ebx'),
    (0x141538cbc, 'lea', 'r14, [r13 + 0x40]'), (0x141538cc0, 'mov', 'qword ptr [rsp + 0x58], r14'),
    (0x141538cd4, 'lea', 'rax, [rip + 0x1a18bcd]'), (0x141538cdb, 'mov', 'qword ptr [r13], rax'),
    (0x141538cdf, 'lea', 'rax, [rip + 0x1a18bf2]'), (0x141538ce6, 'mov', 'qword ptr [r14], rax'),
    (0x141538d1d, 'lea', 'rsi, [r13 + 0xc8]'), (0x141538d4a, 'lea', 'r14, [r13 + 0x100]'),
    (0x141538ea7, 'mov', 'word ptr [rcx + 0x288], bx'),
    (0x141538f01, 'xor', 'r9d, r9d'), (0x141538f04, 'mov', 'r8d, 0x692'),
    (0x141538f0e, 'mov', 'rdi, qword ptr [rsp + 0x58]'), (0x141538f13, 'mov', 'rcx, rdi'),
    (0x141538f16, 'call', '0x14154abf0'), (0x141538f1b, 'mov', 'rdx, rax'),
    (0x141538f1e, 'mov', 'rcx, rsi'), (0x141538f21, 'call', '0x141549ff0'),
    (0x141538f43, 'xor', 'r9d, r9d'), (0x141538f46, 'mov', 'r8d, 0x693'),
    (0x141538f5b, 'mov', 'rcx, r14'), (0x141538f5e, 'call', '0x141549ff0'),
    (0x14154ac09, 'movzx', 'edi, r9b'), (0x14154ac0d, 'mov', 'esi, r8d'),
    (0x14154ac4c, 'mov', 'r8d, edi'), (0x14154ac60, 'mov', 'edx, esi'),
    (0x14154ac65, 'call', '0x14185ec00'), (0x14154ac71, 'mov', 'rcx, qword ptr [r13 + 8]'),
    (0x14154ac94, 'mov', 'rdx, r13'), (0x14154ac97, 'call', 'qword ptr [rax + 0x40]'),
    (0x14154acb2, 'mov', 'dword ptr [rsp + 0x20], esi'), (0x14154acc3, 'call', '0x141549c00'),
    (0x14153b292, 'xor', 'esi, esi'),
    (0x14153b294, 'cmp', 'byte ptr [rcx + 0x288], sil'),
    (0x14153b29b, 'jne', '0x14153b2ab'), (0x14153b29d, 'cmp', 'byte ptr [rcx + 0x289], sil'),
    (0x14153b2a4, 'jne', '0x14153b2ab'), (0x14153b2a6, 'xor', 'dil, dil'),
    (0x14153b2ab, 'mov', 'dil, 1'), (0x14153b2ae, 'add', 'rcx, 0xc8'),
    (0x14153b2b5, 'xor', 'r8d, r8d'), (0x14153b2b8, 'movzx', 'edx, dil'),
    (0x14153b2bc, 'call', '0x14154bf30'),
    (0x14153b504, 'cmp', 'dl, byte ptr [rcx + 0x288]'), (0x14153b50c, 'mov', 'byte ptr [rcx + 0x288], dl'),
    (0x14153b512, 'call', '0x14153b280'),
    (0x14153b47d, 'sub', 'r8d, 0x693'), (0x14153b484, 'je', '0x14153b4a5'),
    (0x14153b486, 'cmp', 'r8d, 1'), (0x14153b4a0, 'jmp', '0x14153b5a0'),
    (0x14153b48a, 'jne', '0x14153b4da'), (0x14153b492, 'call', 'qword ptr [rax + 0x10]'),
    (0x14153b495, 'movzx', 'edx, al'), (0x14153b498, 'mov', 'rcx, rbx'),
    (0x14153b4ab, 'call', 'qword ptr [rax + 0x10]'), (0x14153b4ae, 'lea', 'rcx, [rbx + 0x100]'),
    (0x14153b4bb, 'call', '0x14154bf30'),
    (0x14154bf54, 'lea', 'r8, [rcx + 0x2c]'), (0x14154bf58, 'cmp', 'dl, byte ptr [r8]'),
    (0x14154bf3c, 'cmp', 'qword ptr [rcx], 0'), (0x14154bf40, 'je', '0x14154bfca'),
    (0x14154bf46, 'cmp', 'qword ptr [rcx + 8], 0'), (0x14154bf4b, 'je', '0x14154bfca'),
    (0x14154bf4d, 'cmp', 'qword ptr [rcx + 0x10], 0'), (0x14154bf52, 'je', '0x14154bfca'),
    (0x14154bf5d, 'cmp', 'eax, dword ptr [rcx + 0x30]'), (0x14154bf60, 'je', '0x14154bfca'),
    (0x14154bf78, 'lea', 'rdx, [rbx + 0x18]'),
    (0x14154bf62, 'mov', 'byte ptr [r8], dl'), (0x14154bf65, 'mov', 'dword ptr [rcx + 0x30], eax'),
    (0x14154bfa1, 'mov', 'rcx, qword ptr [rbx]'), (0x14154bfa7, 'mov', 'r10, qword ptr [rdx + 0x60]'),
    (0x14154bfbe, 'mov', 'r8, qword ptr [rbx + 8]'), (0x14154bfc2, 'mov', 'rdx, qword ptr [rbx + 0x10]'),
    (0x14154bfc6, 'call', 'r10'),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    if args.output:
        h.require(not args.output.exists(), 'Fresh output required')
    a = h.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe', h.CURRENT_SHA)
    h.require(sha(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe')) == a.sha, 'Installed image differs')
    facts = []
    for va, op, operands in CHECKS:
        i = a.at(va, op, operands)
        facts.append({'va': hex(va), 'bytes': i.bytes.hex(), 'instruction': op+' '+operands})
    rtti = []
    for table, offset in [(0x142f518a8, 0), (0x142f518d8, 64)]:
        col = struct.unpack('<Q', a.data(table-8, 8))[0]
        sig, off, _, td, _, own = struct.unpack('<6I', a.data(col, 24))
        h.require(sig == 1 and off == offset and a.base+own == col and a.text(a.base+td+16) == '.?AVLicenseController@dj@serato@@', 'LicenseController RTTI differs')
        rtti.append({'table': hex(table), 'offset': offset, 'locator': hex(col), 'type': '.?AVLicenseController@dj@serato@@'})
    h.require(a.rip(a.at(0x141538cd4)) == 0x142f518a8 and a.rip(a.at(0x141538cdf)) == 0x142f518d8, 'Constructor tables differ')
    # Neither nonvolatile register changes on these straight-line local intervals.
    preserved = []
    for start, end, aliases in [(0x141538cb6, 0x141538ea7, {'rbx','ebx','bx','bl','bh'}),
                                (0x141538d24, 0x141538f21, {'rsi','esi','si','sil'})]:
        rows = [i for i in a.function(start) if start <= i.address < end]
        h.require(rows and all(not i.mnemonic.startswith('j') and i.mnemonic != 'ret' for i in rows), 'Straight-line interval differs')
        h.require(all(not ({i.reg_name(n) for n in i.regs_access()[1]} & aliases) for i in rows), 'Preserved constructor register changed')
        preserved.append({'start': hex(start), 'endExclusive': hex(end), 'register': sorted(aliases)[0]})
    leaf = list(a.dis.disasm(a.data(0x14153b5a0, 20), 0x14153b5a0))
    h.require([(i.mnemonic, i.op_str) for i in leaf] == [('cmp','dl, byte ptr [rcx + 0x289]'),('je','0x14153b5b3'),
              ('mov','byte ptr [rcx + 0x289], dl'),('jmp','0x14153b280'),('ret','')], 'Second-flag setter leaf differs')
    move = list(a.dis.disasm(a.data(0x141549ff0, 87), 0x141549ff0))
    h.require(move[-1].address == 0x14154a046 and move[-1].mnemonic == 'ret' and
              any(i.mnemonic == 'mov' and i.op_str == 'byte ptr [rcx + 0x2c], al' for i in move), 'Property move leaf differs')
    metadata = list(a.dis.disasm(a.data(0x141549c00, 7), 0x141549c00))
    h.require([(i.mnemonic,i.op_str) for i in metadata] == [('mov','eax, dword ptr [rsp + 0x28]'),
              ('mov','dword ptr [rcx + 0x18], eax')], 'Property message-ID metadata store differs')
    focused = {}
    for name, expected in [('serato500-license-state-20261102-decompile.json', [(0x141538c70,0x14153b16a),(0x14154abf0,0x14154ace4),(0x141549ff0,0x14154a047)]),
                           ('serato500-license-state-updates-20261102-decompile.json', [(0x14153b280,0x14153b437),(0x14153b470,0x14153b4e0),(0x14153b500,0x14153b51e),(0x14154bf30,0x14154bfd0)])]:
        path = ROOT/'analysis'/name
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        h.require(value['binary_sha256'] == a.sha and len(value['functions']) == len(expected), 'Focused target/count differs')
        for row, extent in zip(value['functions'], expected):
            h.require(row['complete'] and (int(row['start'],16),int(row['end_exclusive'],16)) == extent, 'Focused range differs')
            h.require(extent in a.spans or extent == (0x141549ff0,0x14154a047), 'Exact unwind or independently decoded full leaf required')
        focused[name] = sha(path)
    prior = ROOT/'docs/evidence/serato500-usb-arrival.json'
    h.require(sha(prior) == '7d018af5beaa3cb0f1111d3f2c79cff3369bdacec7e9e80f828f98794a3d9f50', 'Prior state consumer proof differs')
    old_spec = importlib.util.spec_from_file_location('license_arrival', ROOT/'scripts/export-serato-usb-arrival.py')
    old = importlib.util.module_from_spec(old_spec)
    old_spec.loader.exec_module(old)
    for va, text in old.CHECKS:
        op, _, operands = text.partition(' ')
        a.at(va, op, operands)
    sources = ['scripts/export-serato-license-state-binding.py','scripts/export-serato-usb-arrival.py','scripts/export-serato-clock-handshake-evidence.py']
    report = {'schema':'sl3.license-readiness-property-binding.v1','status':'conditional_static_contract','applicationSha256':a.sha,
              'instructionFacts':facts,'types':rtti,'preservedConstructorRegisters':preserved,'privateFocusedReportSha256':focused,
              'priorStateConsumerProofSha256':sha(prior),'priorArrivalInstructionChecks':len(old.CHECKS),
              'sources':{p:{'localSha256':sha(ROOT/p),'gitLfSha256':hashlib.sha256((ROOT/p).read_bytes().replace(b'\r\n',b'\n')).hexdigest()} for p in sources},
              'properties':{'0x692':{'controllerOffset':'0xc8','constructorValue':False,'updatedValue':'Boolean OR of LicenseController +0x288 and +0x289'},
                            '0x693':{'controllerOffset':'0x100','constructorValue':False,'selectedUpdate':'Message 0x693 low byte through virtual +0x10'}},
              'selectedRoutes':{'firstFlag':'Setter 0x14153b500 changes +0x288 and calls updater when different',
                                'secondFlag':'Handler message 0x694 forwards low byte to leaf 0x14153b5a0, changing +0x289 and calling updater when different',
                                'propertyNotification':'0x14154bf30 requires three non-null bindings; changed byte/secondary value reaches bound virtual +0x60'},
              'usbHelperConclusion':'Stored manager bytes originate in application message state; a true OR is not evidence of USB clock/ASIO readiness',
              'allFlagProducersExhausted':False,'initialPropertyConstructionProvesMessageDelivery':False,'liveLicenseStateQueried':False,
              'authorizationChangedOrEmulated':False,'applicationExecuted':False,'deviceAccess':False,'currentSeratoAdmissionVerified':False,
              'twoDeckDvsVerified':False,'deploymentApproved':False,
              'remaining':['Meaning/provenance of every input flag, actual allowed state and complete bus delivery/timing',
                           'Resource load/selection, NONE control semantics, measured ASIO/protected deployment and physical current audio/DVS'],
              'limits':['LicenseController RTTI identifies the owner, not a particular product entitlement or purchase remedy',
                        'No flag, message, account, key, token, hardware identity or policy was substituted']}
    raw = json.dumps(report, indent=2)+'\n'
    if args.output:
        with args.output.open('x', encoding='utf-8', newline='\n') as f:f.write(raw)
    else:print(raw,end='')


if __name__ == '__main__':
    main()
