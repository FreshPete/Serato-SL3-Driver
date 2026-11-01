"""Read pinned Qt resource indexes; never load vendor code or export payloads."""
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/file)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


codec = module('qrc_codec', 'inspect-serato-resource-archive.py')
image_helper = module('qrc_image', 'export-serato-clock-handshake-evidence.py')
require = codec.require
PINNED = {
    'sdj_variant_resources.bin': 'bd43ee3a6d9cb5de28b6c3a60183b1fda346cedc6c12482013f01117269b963e',
    'dj_resources_common.bin': 'e0bb18ccbf03202eb2ffde89457aa8a5fe8b4b8984c950c1282ec96e6ae47a81',
    'dj_resources_fonts.bin': '05f34a95cd3e7e6f44be9dd40f41c46d3b489ddd84c90acf05f798f73816b489',
    'dj_resources_html.bin': 'b4e2a787572ee2db9bd38e62db0642169d71dcd92464115645e8a8ec66196043',
    'dj_resources_dark.bin': '00b525e16f0d30c87453f4f8964630ca11b04e5ac6795d50f3602eff9757b4f3',
    'dj_resources_light.bin': '20e21ac4666b6123f180e847a4c7f372fd72e756ed8ffcaae33d28211f04dc6e',
    'dj_resources_scratch_live.bin': '8224eacf44a384fa50fad483173bca184e3e2995dd02413963739e35e20b124a',
    'dj_resources_shaders.bin': 'a9e7fad8a8386b469cb4f18fc493d7ca98b23c00b85f09fb4b13b0bee13233ba',
    'dj_resources_localization.bin': 'fb7649b458b15ea7de0dc65579c92bfa69e683795aff1368e11717f28eafcd4c',
}
STATIC_CALLS = [0x1407641ae, 0x1408d70fe, 0x1408d716e, 0x14093aa2e, 0x14093aa9e,
                0x1409c89ae, 0x1409c8a1e, 0x140abefbe, 0x140abf01e, 0x140addd6e, 0x140adddce]
DYNAMIC_CALLS = [0x140b0ac25, 0x140b0acd8, 0x140b0ad81, 0x140b0ae29, 0x140b0aed1,
                 0x140b0af7a, 0x140b0b02f, 0x140b0b0ce, 0x140b0b14d]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tree_index(tree, names, payload, complete=True):
    """Index format-v3 records only. Compressed file contents remain opaque."""
    require(len(tree) >= 22 and (not complete or len(tree) % 22 == 0), 'Invalid tree extent')
    maximum = min(len(tree)//22, 100000)
    seen, identities, files = set(), set(), []

    def visit(node, parent, depth):
        require(depth <= 64 and 0 <= node < maximum and node not in seen, 'Cyclic/shared/out-of-bounds resource node')
        seen.add(node)
        at = node*22
        name_offset, flags = struct.unpack_from('>IH', tree, at)
        require(flags in (0, 1, 2, 4), 'Unknown/mixed resource flags')
        if node:
            require(name_offset+6 <= len(names), 'Name header outside table')
            length = struct.unpack_from('>H', names, name_offset)[0]
            end = name_offset+6+length*2
            require(0 < length <= 4096 and end <= len(names), 'Name outside table')
            name = names[name_offset+6:end].decode('utf-16-be')
            require(name not in ('.', '..') and not any(c in name for c in '/\\\0:'), 'Unsafe resource component')
            path = parent+'/'+name
        else:
            require(flags == 2, 'Resource root is not a directory')
            path = ''
        if flags == 2:
            count, first = struct.unpack_from('>II', tree, at+6)
            require(count <= maximum and first <= maximum and first+count <= maximum, 'Children outside tree')
            for child in range(first, first+count):
                visit(child, path, depth+1)
        else:
            territory, language, offset = struct.unpack_from('>HHI', tree, at+6)
            identity = (path, territory, language)
            require(identity not in identities, 'Duplicate locale resource')
            identities.add(identity)
            require(offset+4 <= len(payload), 'Payload length outside table')
            size = struct.unpack_from('>I', payload, offset)[0]
            require(offset+4+size <= len(payload), 'Payload outside table')
            files.append({'path': path, 'territory': territory, 'language': language,
                          'flags': flags, 'storedBytes': size})
    visit(0, '', 0)
    require(seen == set(range(max(seen)+1)), 'Unreachable resource node gap')
    require(not complete or len(seen) == len(tree)//22, 'Unreachable resource suffix')
    return files, len(seen)


def bundle_index(data):
    require(len(data) >= 24 and data[:4] == b'qres', 'Invalid Qt bundle header')
    version, tree, payload, names, features = struct.unpack_from('>5I', data, 4)
    require(version == 3 and features & ~5 == 0, 'Unsupported Qt resource version/features')
    require(24 <= payload <= names < tree < len(data), 'Invalid Qt section ordering')
    files, count = tree_index(data[tree:], data[names:tree], data[payload:names])
    require(all(not row['flags'] or row['flags'] & features for row in files), 'Compression feature not declared')
    return files, count


def summary(files, nodes):
    names = [row['path'] for row in files]
    return {'nodes': nodes, 'files': len(files),
            'rootCounts': dict(sorted(Counter(p.split('/')[1] for p in names).items())),
            'compressionFlagCounts': dict(sorted(Counter(str(row['flags']) for row in files).items())),
            'indexSha256': sha(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()),
            'deviceFolderPaths': [p for p in names if any(s.lower() in ('userio', 'userio_partner', 'userio_hidden_from_partners') for s in p.split('/')[1:-1])],
            'userioNamedPaths': [p for p in names if any(s.lower().startswith('userio') for s in p.split('/'))],
            'sl3NamedPaths': [p for p in names if 'sl3' in p.lower().replace('_', '').replace('-', '')]}


def inspect():
    app = image_helper.Image(codec.APP_RELATIVE, codec.APP_SHA)
    installed = Path('C:/Program Files/Serato/Serato DJ Pro')
    require(sha((installed/'Serato DJ Pro.exe').read_bytes()) == app.sha, 'Installed image differs')
    app.pe.parse_data_directories(directories=[1])
    imports = {e.address: e.name.decode() for d in app.pe.DIRECTORY_ENTRY_IMPORT for e in d.imports if e.name}
    require('qRegisterResourceData' in imports[0x142734138] and 'registerResource@QResource' in imports[0x142732fa0], 'Wrong Qt registration imports')
    # Verify the application routes dynamic bundles through its recovered codec.
    for va in DYNAMIC_CALLS:
        app.at(va, 'call', '0x140b0c3f0')
    app.at(0x140b0c424, 'call', '0x140b0c250')
    app.at(0x140b0c276, 'call', '0x140b0ddf0')
    app.at(0x140b0dec6, 'call', '0x141cc6030')
    require(app.rip(app.at(0x140b0c290, 'call')) == 0x142732fa0, 'Wrong dynamic registration call')
    thunk = list(app.dis.disasm(app.data(0x141b87910, 6), 0x141b87910))
    require(len(thunk) == 1 and thunk[0].mnemonic == 'jmp' and app.rip(thunk[0]) == 0x142734138, 'Wrong embedded registration thunk')
    seed = app.data(0x142f2de98, 16)
    key = struct.unpack('<4I', bytes((((x ^ 0xcf) >> (n & 7)) | ((x ^ 0xcf) << ((8-(n & 7)) & 7))) & 255 for n, x in enumerate(seed)))
    bundles = {}
    for name, expected in PINNED.items():
        raw = (ROOT/codec.APP_RELATIVE).with_name(name).read_bytes()
        require(sha(raw) == expected and (installed/name).read_bytes() == raw, 'Pinned/installed bundle differs: '+name)
        decoded = codec.decode_block(raw, key)
        files, nodes = bundle_index(decoded)
        bundles[name] = {'encryptedSha256': expected, 'decodedSha256': sha(decoded), **summary(files, nodes)}
    embedded = []
    for va in STATIC_CALLS:
        app.at(va, 'call', '0x141b87910')
        registers = {}
        for row in app.function(va):
            if row.address >= va:
                break
            if row.mnemonic == 'lea' and row.op_str.startswith(('rdx, [rip', 'r8, [rip', 'r9, [rip')):
                registers[row.op_str.split(',')[0]] = app.rip(row)
            if row.mnemonic == 'mov' and row.op_str.startswith('ecx,'):
                require(row.op_str == 'ecx, 3', 'Wrong embedded resource version')
                registers['version'] = 3
        require(set(registers) == {'rdx', 'r8', 'r9', 'version'}, 'Incomplete embedded call arguments')
        tree, names, payload = registers['rdx'], registers['r8'], registers['r9']
        require(payload < names < tree, 'Unexpected embedded array order')
        section = next(s for s in app.pe.sections if app.base+s.VirtualAddress <= tree < app.base+s.VirtualAddress+s.SizeOfRawData)
        tree_bytes = min(app.base+section.VirtualAddress+section.SizeOfRawData-tree, 100000*22)
        files, nodes = tree_index(app.data(tree, tree_bytes), app.data(names, tree-names), app.data(payload, names-payload), False)
        embedded.append({'callVa': hex(va), 'treeVa': hex(tree), 'namesVa': hex(names), 'payloadVa': hex(payload), **summary(files, nodes)})
    return {'scope': 'Nine registered external Qt bundles and eleven explicit embedded registration call sites; indexes only',
            'binarySha256': app.sha, 'installedMatches': True,
            'dynamicRegistrationCallVas': [hex(a) for a in DYNAMIC_CALLS], 'bundles': bundles, 'embedded': embedded,
            'vendorCodeExecuted': False, 'payloadsExported': False,
            'limits': ['No file payload interpretation, XML scalar-identity search, locale selection emulation or runtime provider trace',
                       'Embedded inspection covers the listed direct calls and their reachable nodes, not every possible indirect registration',
                       'No loose descriptor route, modified resource, accepted device, audio or DVS result is established']}


if __name__ == '__main__':
    print(json.dumps(inspect(), indent=2))
