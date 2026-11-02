"""Check selected resource-path accessor callers without executing vendor code."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT/'artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe'
INSTALLED = Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe')


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/file)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    helper = load('sl3_path_image', 'export-serato-clock-handshake-evidence.py')
    app = helper.Image(ORIGINAL, helper.CURRENT_SHA); require = helper.require
    require(sha(INSTALLED) == app.sha, 'Installed executable differs')
    navigator = load('sl3_path_navigation', 'pe-navigate.py')
    targets = [0x14083dfe0, 0x143fe8860, 0x143fe8880, 0x143fe88a0, 0x143fe88c0]
    navigation = navigator.navigate(ORIGINAL, list(map(hex, targets)))
    require(navigation['binary_sha256'] == app.sha, 'Navigation input differs')
    expected_calls = [0x1404a84fa, 0x1404a9ca0, 0x14153f868, 0x14153f9f6, 0x14153fc91, 0x141cb2362, 0x141cb4c72]
    require([int(x['call_va'],16) for x in navigation['targets'][0]['direct_callers']] == expected_calls, 'Identified direct accessor calls differ')
    facts = []
    def fact(address, assembly):
        instruction = app.at(address)
        require(instruction.mnemonic+' '+instruction.op_str == assembly, 'Instruction differs at '+hex(address))
        facts.append({'va': hex(address), 'bytes': bytes(instruction.bytes).hex(), 'assembly': assembly})
        return instruction
    for address in expected_calls:
        fact(address, 'call 0x14083dfe0')
    for address, assembly in [
        (0x1404a84ff, 'mov rsi, rax'), (0x1404a8502, 'cmp qword ptr [rax + 0x10], 0'),
        (0x1404a9ca5, 'mov rdx, rax'), (0x1404a9ca8, 'lea rcx, [rsp + 0x40]'),
        (0x1404a9cad, 'call 0x141cb3290'),
        (0x14153f86d, 'cmp qword ptr [rax + 0x10], r13'),
        (0x14153f94a, 'mov dword ptr [rsp + 0x28], 0x2001f'),
        (0x14153f957, 'xor r9d, r9d'), (0x14153f95a, 'xor r8d, r8d'),
        (0x14153f964, 'mov rcx, 0xffffffff80000001'),
        (0x14153f9fb, 'cmp qword ptr [rax + 0x18], 0xf'),
        (0x14153fa02, 'mov rax, qword ptr [rax]'), (0x14153fa05, 'mov rdx, rax'),
        (0x14153fa08, 'lea rcx, [rbp - 0x48]'), (0x14153fa0c, 'call 0x1420fa120'),
        (0x14153fa12, 'lea r8, [rbp - 0x48]'), (0x14153fa16, 'mov rdx, rbx'),
        (0x14153fa19, 'lea rcx, [rsp + 0x70]'), (0x14153fa1e, 'call 0x141540320'),
        (0x14153fc96, 'mov rdx, rax'), (0x14153fc99, 'mov rcx, rdi'), (0x14153fc9c, 'call 0x1404a19c0'),
        (0x141cb2367, 'mov rbx, rax'), (0x141cb236a, 'mov rdx, rax'),
        (0x141cb2371, 'call 0x141cb4400'), (0x141cb2377, 'lea rdx, [rbx + 0x40]'),
        (0x141cb237f, 'call 0x1404a3300'),
        (0x141540379, 'xor edx, edx'), (0x14154037b, 'mov r9d, 2'),
        (0x141540381, 'mov rcx, rbp'), (0x1415403fe, 'mov r9d, 2'),
        (0x141540404, 'mov r8, r14'), (0x141540407, 'xor edx, edx'), (0x141540409, 'mov rcx, rbp'),
        (0x14083e098, 'call 0x142117e20'), (0x142117e24, 'call 0x142117de0'),
        (0x142117df3, 'call 0x1421205de'), (0x142117dfa, 'mov rdx, rbx'),
        (0x142117e04, 'call 0x1421205d8'),
        (0x1425e234b, 'call 0x1404a3d40'), (0x1425e2357, 'call 0x1404a3d40'),
        (0x1425e2363, 'call 0x1404a3d40'), (0x1425e2373, 'jmp 0x1404a3d40'),
    ]:
        fact(address, assembly)
    key = 'Software\\Microsoft\\DirectX\\UserGpuPreferences'
    require(app.rip(app.at(0x14153f95d, 'lea')) == 0x142f51cd0 and
            app.data(0x142f51cd0, (len(key)+1)*2) == key.encode('utf-16le')+b'\0\0', 'GPU preference key literal differs')
    require(app.rip(app.at(0x14083e091, 'lea')) == 0x1425e2340, 'Exit callback argument differs')
    cleanup_addresses = [0x143fe88c0, 0x143fe88a0, 0x143fe8880, 0x143fe8860]
    for address, expected in zip([0x1425e2344,0x1425e2350,0x1425e235c,0x1425e2368], cleanup_addresses):
        require(app.rip(app.at(address, 'lea')) == expected, 'Cleanup state address differs')
    app.pe.parse_data_directories(directories=[1])
    imports = {entry.address: entry.name.decode('ascii') for dll in app.pe.DIRECTORY_ENTRY_IMPORT for entry in dll.imports if entry.name}
    imported = []
    for address, expected in [(0x14153f96b,'RegCreateKeyExW'),(0x14153fb3b,'RegCloseKey'),
                              (0x141540384,'RegGetValueW'),(0x14154040c,'RegGetValueW'),(0x1404a9c92,'GetModuleFileNameW')]:
        instruction = app.at(address, 'call'); require(imports[app.rip(instruction)] == expected, 'OS import differs')
        imported.append({'va': hex(address), 'import': expected, 'bytes': bytes(instruction.bytes).hex()})
    thunks = []
    for address, expected in [(0x1421205d8,'_register_onexit_function'),(0x1421205de,'_crt_atexit')]:
        instruction = next(app.dis.disasm(app.data(address,6),address))
        require(instruction.size == 6 and instruction.mnemonic == 'jmp' and imports[app.rip(instruction)] == expected, 'CRT exit thunk differs')
        thunks.append({'va': hex(address), 'import': expected, 'bytes': bytes(instruction.bytes).hex()})
    ranges = {(0x1404a84c0,0x1404a8ab8),(0x1404a9c30,0x1404a9d94),(0x14153f830,0x14153fed6),
              (0x141cb2330,0x141cb25f4),(0x1425e2340,0x1425e2378),(0x141540320,0x141540594),(0x142117de0,0x142117e1a)}
    reports = []; found = set()
    for stem in ['serato500-path-callers-20261102','serato500-path-helpers-20261102']:
        path = ROOT/'analysis'/(stem+'-decompile.json'); log = ROOT/'analysis'/(stem+'-decompile.log')
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        require(value['binary_sha256'] == app.sha, 'Focused report image differs')
        for row in value['functions']:
            span = int(row['start'],16),int(row['end_exclusive'],16)
            require(span in ranges and span in app.spans and span not in found and row['complete'] is True and
                    row.get('pseudocode') and not row.get('diagnostic'), 'Incomplete/unexpected/duplicate focused function')
            found.add(span)
        text = log.read_text(encoding='utf-8',errors='replace')
        require('Loaded 0 additional files' in text and 'Discarded file import due to readOnly option' in text and 'Import succeeded' in text,
                'Read-only import/cleanup evidence missing')
        reports.append({'reportSha256': sha(path), 'logSha256': sha(log), 'functions': len(value['functions'])})
    require(found == ranges, 'Focused range coverage differs')
    result = {'schema':'sl3.serato-path-callers.v1','applicationSha256':app.sha,'installedMatches':True,
        'accessorVA':'0x14083dfe0','identifiedDirectCallers':navigation['targets'][0]['direct_callers'],
        'navigationSha256': hashlib.sha256(json.dumps(navigation,sort_keys=True).encode()).hexdigest(),
        'checkedInstructions':facts,'checkedImports':imported,'checkedExitThunks':thunks,
        'gpuQuery':{'functionVA':'0x14153f830','hive':'HKEY_CURRENT_USER','key':key,'requestedKeyAccess':'0x2001f',
                    'queryHelperVA':'0x141540320','queryFlags':2,'valueNameSource':'module path string through 0x1420fa120',
                    'regGetValueCalls':2,'queriedNamespaceIsGpuPreferences':True},
        'secondPathBuilder':{'functionVA':'0x141cb2330','componentOffset':'0x40','directoryPartHelper':'0x141cb4400'},
        'cleanupCallback':{'functionVA':'0x1425e2340','registrationArgumentVA':'0x14083e091',
                           'registrationWrapper':'0x142117e20','stateAddresses':list(map(hex,cleanup_addresses))},
        'focusedReports':reports,'focusedFunctionCount':len(found),
        'sourceSha256':{p:sha(ROOT/p) for p in ['scripts/export-serato-path-callers.py','scripts/pe-navigate.py','scripts/export-serato-clock-handshake-evidence.py','scripts/ghidra/FocusedDecompile.java']},
        'applicationExecuted':False,'applicationModified':False,'vendorRegistryCallsExecuted':False,'accountInspected':False,
        'deviceAccess':False,'externalDescriptorRegistrationEstablished':False,'currentSeratoAdmissionVerified':False,
        'limits':['Direct-call candidates cover E8 rel32 calls validated within recovered unwind ranges; leaf/indirect callers are not exhausted.',
                  'RIP/data reference navigation is pattern-scoped, not a complete state-writer inventory.',
                  'Checked argument use is not a proof that every indirect callee is read-only.',
                  'Focused Ghidra completion describes requested functions, not full ABI/control-flow or runtime validation.',
                  'RegCreateKeyExW could create its branch if the vendor application executes this path; this analysis invokes none of it.',
                  'No resource override, archive/app modification, support-value change or handshake fallback was selected.']}
    output = ROOT/'docs/evidence/serato500-path-callers.json'
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'verified':True,'identifiedDirectCallSites':len(expected_calls),'focusedFunctions':len(found),'instructionFacts':len(facts),'osImportSites':len(imported),'exitThunks':len(thunks)}))


if __name__ == '__main__':
    main()
