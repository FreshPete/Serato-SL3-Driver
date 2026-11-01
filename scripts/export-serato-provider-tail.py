"""Verify remaining default resource readers and literal registration arguments, without running Serato."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import capstone
import pefile

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = '66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265'
BINARY = ROOT / 'artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe'
BLOCKS = (
    (0x14139baeb, 0x14139bb6b, 0x1417763c0, 'userio', 'userio_resources.bin'),
    (0x14139bc1d, 0x14139bcb5, 0x1417763c0, 'components', 'dj_resources_components.bin'),
    (0x14139bd67, 0x14139bddb, 0x1417763c0, 'manifest', 'dj_resources_effect_manifest.bin'),
    (0x14139be8d, 0x14139bf14, 0x1417763c0, 'effects', 'dj_resources_effects.bin'),
    (0x14139bfc6, 0x14139c05a, 0x1417763c0, 'fade_effects', 'dj_resources_fade_effects.bin'),
    (0x14139c319, 0x14139c38b, 0x1417765e0, 'stems', 'bundle2.bin'),
    (0x14139c4d8, 0x14139c563, 0x1417765e0, 'analysis_beatgrid', 'bundle1.bin'),
    (0x1415feb51, 0x1415febe7, 0x1417763c0, 'userio_images', 'userio_image_resources.bin'),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    require(sha(BINARY) == EXPECTED and sha(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe')) == EXPECTED,
            'Original or installed application changed')
    pe = pefile.PE(str(BINARY), fast_load=True)
    pe.parse_data_directories(directories=[3])
    base = pe.OPTIONAL_HEADER.ImageBase
    spans = {(base + e.struct.BeginAddress, base + e.struct.EndAddress) for e in pe.DIRECTORY_ENTRY_EXCEPTION}
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    decoder.detail = True

    def image(address, count):
        value = pe.get_data(address - base, count)
        require(len(value) == count, 'Incomplete PE read')
        return value

    def body(start, end):
        instructions = list(decoder.disasm(image(start, end - start), start))
        require(sum(i.size for i in instructions) == end - start, 'Incomplete instruction decoding')
        return instructions

    def call(address, target):
        instruction = body(address, address + 5)[0]
        require(instruction.mnemonic == 'call' and instruction.operands[0].type == capstone.x86.X86_OP_IMM
                and instruction.operands[0].imm == target, 'Call target changed')

    spec = importlib.util.spec_from_file_location('static_copies', ROOT / 'scripts/static-string-copies.py')
    copies = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(copies)
    mappings = []
    for start, end, target, prefix, archive in BLOCKS:
        require(any(lo <= start < end < hi for lo, hi in spans), 'Construction outside one unwind range')
        call(end, target)
        model = copies.LiteralCopies(image, 0x142117f10)
        instructions = body(start, end)
        model.run(instructions)
        require(model.string_argument('rdx') == prefix and model.string_argument('r8') == archive,
                'Actual constructed registration arguments differ')
        mappings.append({'callVa': hex(end), 'prefix': prefix, 'archiveArgument': archive,
                         'constructionStart': hex(start), 'constructionBytesSha256': hashlib.sha256(image(start, end-start)).hexdigest(),
                         'instructionCount': len(instructions), 'registrationTarget': hex(target),
                         'inDefaultConstructor': start < 0x14139c643})
    for address in (0x14139ba27, 0x14139c2f3, 0x14139c4b2):
        call(address, 0x14139b810)
    for address in (0x14139c0c9, 0x14139c237, 0x14139c3f9, 0x14139c5c5):
        call(address, 0x141771c70)
    call(0x14139c1f7, 0x1413e37e0)
    call(0x140b0aa7a, 0x14139b980)
    call(0x140b0b18a, 0x141771c70)
    call(0x14139b899, 0x141772cd0)
    vtable = 0x142f345d0
    locator = struct.unpack('<Q', image(vtable - 8, 8))[0]
    fields = struct.unpack('<6I', image(locator, 24))
    require(fields[0] == 1 and fields[1] == fields[2] == 0 and base + fields[5] == locator,
            'Invalid EffectResources complete-object locator')
    decorated = image(base + fields[3] + 16, 128).split(b'\0', 1)[0].decode('ascii')
    require(decorated == '.?AVEffectResources@audio@serato@@', 'Wrong extra reader class')
    hierarchy = struct.unpack('<4I', image(base + fields[4], 16))
    require(0 < hierarchy[2] <= 16, 'Invalid reader hierarchy')
    bases = []
    for descriptor_rva in struct.unpack('<' + 'I' * hierarchy[2], image(base + hierarchy[3], 4 * hierarchy[2])):
        descriptor = struct.unpack('<IIiiiII', image(base + descriptor_rva, 28))
        name = image(base + descriptor[0] + 16, 128).split(b'\0', 1)[0].decode('ascii')
        bases.append({'type': name, 'memberDisplacement': descriptor[2], 'vbtableDisplacement': descriptor[3]})
    require(any(x['type'] == '.?AVResourceReader@resources@serato@@' and x['memberDisplacement'] == 0
                and x['vbtableDisplacement'] == -1 for x in bases), 'ResourceReader base layout differs')
    require(struct.unpack('<Q', image(vtable + 0x28, 8))[0] == 0x1404a4b40, 'Effect listing slot differs')
    constructor = body(0x1413e37e0, 0x1413e380c)
    lea = next(i for i in constructor if i.address == 0x1413e37ea)
    require(lea.mnemonic == 'lea' and lea.operands[1].mem.base == capstone.x86.X86_REG_RIP
            and lea.address + lea.size + lea.operands[1].mem.disp == vtable, 'Effect constructor table differs')
    store = next(i for i in constructor if i.address == 0x1413e37f1)
    require((store.mnemonic, store.op_str) == ('mov', 'qword ptr [rcx], rax'), 'Effect constructor table store differs')
    listing = body(0x1404a4b40, 0x1404a4b59)
    require([(i.mnemonic, i.op_str) for i in listing] == [
        ('sub', 'rsp, 0x18'), ('xor', 'eax, eax'), ('mov', 'qword ptr [rdx], rax'),
        ('mov', 'qword ptr [rdx + 8], rax'), ('mov', 'qword ptr [rdx + 0x10], rax'),
        ('mov', 'rax, rdx'), ('add', 'rsp, 0x18'), ('ret', '')], 'Effect listing is not the checked empty-vector leaf')
    report_path = ROOT / 'analysis/serato500-provider-tail-20261101-decompile.json'
    report = read(report_path)
    require(report['binary_sha256'] == EXPECTED and len(report['functions']) == 4, 'Focused report input differs')
    require({(int(f['start'], 16), int(f['end_exclusive'], 16)) for f in report['functions']} == {
        (0x14139b980, 0x14139c643), (0x1413e53e0, 0x1413e545c),
        (0x14139b810, 0x14139b8c4), (0x1404a4b40, 0x1404a4b59)}, 'Focused report targets differ')
    for function in report['functions']:
        extent = int(function['start'], 16), int(function['end_exclusive'], 16)
        require(extent in spans and function['complete'] is True and function.get('pseudocode')
                and not function.get('diagnostic'), 'Focused report incomplete or outside exact unwind bounds')
    tests_path = ROOT / 'analysis/static-string-copies-20261101-tests.log'
    tests = tests_path.read_text()
    require('Ran 8 tests' in tests and tests.rstrip().endswith('OK'), 'Static copier tests did not pass')
    result = {'scope': __doc__, 'applicationSha256': EXPECTED, 'registrations': mappings,
              'defaultConstructor': '0x14139b980', 'defaultAppendCalls': ['0x14139c0c9', '0x14139c237', '0x14139c3f9', '0x14139c5c5'],
              'extraReader': {'decoratedType': decorated, 'vtable': hex(vtable), 'listingSlot': '0x28',
                              'listingLeaf': '0x1404a4b40', 'listingAlwaysEmpty': True, 'baseTypes': bases},
              'qrcAppendedLaterAt': '0x140b0b18a', 'focusedReportSha256': sha(report_path),
              'copierSha256': sha(ROOT / 'scripts/static-string-copies.py'), 'copierTestsPassed': 8,
              'copierTestsSha256': sha(ROOT / 'tests/test_static_string_copies.py'), 'copierTestLogSha256': sha(tests_path),
              'exporterSha256': sha(Path(__file__)), 'applicationExecuted': False, 'applicationModified': False,
              'externalDeviceRegistrationVerified': False, 'currentSeratoAdmissionVerified': False,
              'limits': ['Literal-copy interpretation covers only the selected straight-line construction blocks.',
                         'The reader ordering is static construction evidence, not live dispatch.',
                         'These checked direct sites do not exhaust indirect registrations or later runtime mutations.',
                         'No archive writer, descriptor injection, handshake fallback or account change was used.']}
    (ROOT / 'docs/evidence/serato500-provider-tail.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Verified eight constructed archive mappings, four default reader appends and the empty EffectResources listing')


if __name__ == '__main__':
    main()
