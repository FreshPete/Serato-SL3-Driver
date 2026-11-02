"""Verify released UsbDk failure rollback; prepare offline TMF additions only."""
import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import uuid

ROOT = Path(__file__).resolve().parents[1]
GUID = 'b5e6b989-2f0e-e5db-a780-e327b8ea6fff'


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT/'scripts'/name)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


source = module('prepare-usbdk-lifecycle-trace.py')
images = module('export-serato-clock-handshake-evidence.py')
require = source.require


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rollback_formats(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 8*1024*1024, 'Bounded TMF bytes required')
    records = defaultdict(set); current = None; lines = raw.decode('utf-8').splitlines(); n = 0
    while n < len(lines):
        header = re.fullmatch(r'([0-9a-f-]{36}) UsbDk // SRC=(\w+\.cpp) MJ= MN=', lines[n])
        if header:
            current = (header[1], header[2])
        entry = re.match(r'#typev\s+\S+\s+(\d+) ', lines[n])
        if entry:
            first = n
            while n < len(lines) and lines[n] != '}':
                n += 1
            require(n < len(lines), 'Truncated TMF definition')
            if current == (GUID, 'ControlDevice.cpp') and int(entry[1]) in (34, 35):
                body = '\n'.join(lines[first:n+1])
                require('FUNC=CUsbDkControlDevice::AddRedirectRollBack' in body and
                        'LEVEL=TRACE_LEVEL_ERROR' in body and 'FLAGS=TRACE_CONTROLDEVICE' in body, 'Rollback metadata differs')
                records[int(entry[1])].add(body)
        n += 1
    require(set(records) == {34, 35} and all(len(v) == 1 for v in records.values()), 'Missing or architecture-dependent rollback formats')
    body = f'{GUID} UsbDk // SRC=ControlDevice.cpp MJ= MN=\n'+'\n'.join(next(iter(records[n])) for n in (34, 35))+'\n'
    return body.encode('utf-8'), [{'messageId': n, 'formatSha256': hashlib.sha256(next(iter(records[n])).encode()).hexdigest()}
                                 for n in (34, 35)]


def verify():
    baseline, selected = source.check()
    require(len(baseline['messages']) == 32 and baseline['flags'] == '0x650' and baseline['level'] == 4,
            'Historical baseline decoder/configuration differs')
    text = (ROOT/'artifacts/references/usbdk-1.0.22/ControlDevice.cpp').read_text(encoding='utf-8')
    addition, add_lines = source.source_function(text, 'CUsbDkControlDevice::AddRedirect')
    rollback, rollback_lines = source.source_function(text, 'CUsbDkControlDevice::AddRedirectRollBack')
    reset_failure = addition.index('Reset after start redirection failed.')
    attach_failure = addition.index('Wait for redirector attachment failed.')
    handle_failure = addition.index('CreateRedirectorHandle() failed.')
    require('AddRedirectRollBack(DeviceId, false)' in addition[reset_failure:attach_failure] and
            'AddRedirectRollBack(DeviceId, true)' in addition[attach_failure:handle_failure] and
            'AddRedirectRollBack(DeviceId, true)' in addition[handle_failure:], 'Source failure rollback arguments differ')
    require(rollback.index('m_Redirections.Delete(&DeviceId)') < rollback.index('if (!WithReset)') <
            rollback.index('ResetUsbDevice(DeviceId, false)'), 'Source rollback deletion/reset order differs')
    app = images.Image('artifacts/extracted/usbdk-msi/UsbDk.sys10', source.SYS_SHA)
    facts = []
    def fact(va, expected):
        row = app.at(va); require(row.mnemonic+' '+row.op_str == expected, 'Instruction differs at '+hex(va))
        facts.append({'va': hex(va), 'assembly': expected, 'bytes': bytes(row.bytes).hex()})
    checks = [
        (0x140002f3c, 'call 0x1400032d8'), (0x140002f41, 'test eax, eax'), (0x140002f43, 'js 0x14000311e'),
        (0x140002f76, 'lea r8, [rip + 0xf30b]'), (0x140002f7d, 'mov edx, 0x24'),
        (0x140002fd4, 'mov r8b, 1'), (0x140002fdd, 'call 0x140005280'),
        (0x140002fe9, 'test eax, eax'), (0x140002feb, 'jns 0x140003032'),
        (0x14000300b, 'lea r8, [rip + 0xf276]'), (0x140003012, 'mov edx, 0x25'),
        (0x14000301f, 'xor r8d, r8d'), (0x140003028, 'call 0x1400031fc'), (0x14000302d, 'jmp 0x1400030fe'),
        (0x140003032, 'lea rcx, [r15 + 0x30]'), (0x140003036, 'xor r9d, r9d'),
        (0x140003039, 'mov r8, 0xffffffffb8797400'), (0x140003040, 'mov dl, 1'),
        (0x140003042, 'call 0x14000c850'), (0x140003047, 'mov edi, eax'),
        (0x140003049, 'test eax, eax'), (0x14000304b, 'js 0x1400030b1'),
        (0x14000304d, 'cmp eax, 0x102'), (0x140003052, 'je 0x1400030b1'),
        (0x14000305d, 'call 0x140003cb8'), (0x140003062, 'test eax, eax'), (0x140003064, 'jns 0x1400030ad'),
        (0x140003084, 'lea r8, [rip + 0xf1fd]'), (0x14000308b, 'mov edx, 0x27'),
        (0x140003098, 'mov r8b, 1'), (0x1400030a1, 'call 0x1400031fc'),
        (0x1400030a6, 'mov ebx, 0xc000009d'), (0x1400030ad, 'xor ebx, ebx'),
        (0x1400030ce, 'lea r8, [rip + 0xf1b3]'), (0x1400030d5, 'mov edx, 0x26'),
        (0x1400030e2, 'mov r8b, 1'), (0x1400030eb, 'call 0x1400031fc'),
        (0x1400030f0, 'cmp edi, 0x102'), (0x1400030f6, 'mov ebx, 0xc000009d'), (0x1400030fb, 'cmove edi, ebx'),
        (0x140003213, 'mov bl, r8b'), (0x140003220, 'call 0x140001014'),
        (0x140003268, 'lea r8, [rip + 0xf019]'), (0x14000326f, 'mov edx, 0x22'),
        (0x140003279, 'test bl, bl'), (0x14000327b, 'je 0x1400032c1'),
        (0x14000327d, 'xor r8d, r8d'), (0x140003280, 'mov rdx, rdi'), (0x140003283, 'mov rcx, rsi'),
        (0x140003286, 'call 0x140005280'), (0x14000328b, 'test eax, eax'), (0x14000328d, 'jns 0x1400032c1'),
        (0x1400032ad, 'lea r8, [rip + 0xefd4]'), (0x1400032b4, 'mov edx, 0x23'),
        (0x14000528a, 'mov bl, r8b'), (0x1400052b4, 'mov dl, bl'), (0x1400052bb, 'call 0x1400064b0'),
        (0x1400064d5, 'mov bl, dl'), (0x1400064fa, 'test bl, bl'), (0x1400064fc, 'je 0x1400065a7'),
        (0x14000659d, 'xor r8d, r8d'), (0x1400065a0, 'xor edx, edx'), (0x1400065a2, 'call 0x14000c850'),
        (0x1400065bf, 'mov r8d, 0x22001f'), (0x1400065ce, 'call 0x14000a3a0'),
        (0x140006607, 'mov ebx, eax'), (0x140006609, 'test eax, eax'), (0x140006648, 'mov eax, ebx'),
        (0x14000c854, 'neg dl'), (0x14000c856, 'mov qword ptr [rsp + 0x40], r8'),
        (0x14000c85b, 'lea rdx, [rsp + 0x40]'), (0x14000c860, 'sbb rax, rax'), (0x14000c863, 'and rax, rdx'),
        (0x14000c869, 'mov qword ptr [rsp + 0x20], rax'), (0x14000c872, 'xor r8d, r8d'),
        (0x14000c875, 'xor edx, edx'), (0x14000c877, 'call qword ptr [rip + 0x587b]'),
    ]
    for va, expected in checks:
        fact(va, expected)
    require(app.at(0x140003039).operands[1].imm == -120*10_000_000, 'Attachment relative interval differs')
    app.pe.parse_data_directories(directories=[1])
    imports = {e.address: (d.dll.decode(), e.name.decode() if e.name else '') for d in app.pe.DIRECTORY_ENTRY_IMPORT for e in d.imports}
    require(imports[app.rip(app.at(0x14000c877))] == ('ntoskrnl.exe', 'KeWaitForSingleObject'), 'Actual wait import differs')
    for ref in [0x140002f76, 0x14000300b, 0x140003084, 0x1400030ce, 0x140003268, 0x1400032ad]:
        require(app.rip(app.at(ref)) == 0x140012288 and app.data(0x140012288, 16) == uuid.UUID(GUID).bytes_le, 'WPP GUID instruction reference differs')
    raw = (ROOT/'artifacts/extracted/usbdk-msi/UsbDk_TMF').read_bytes()
    require(hashlib.sha256(raw).hexdigest() == source.TMF_SHA, 'Bundled TMF differs')
    supplement, formats = rollback_formats(raw)
    focused_path = ROOT/'analysis/usbdk-rollback-20261102-decompile.json'
    focused = json.loads(focused_path.read_text(encoding='utf-8-sig'))
    spans = {(0x140002f10, 0x14000313b), (0x1400031fc, 0x1400032d6), (0x140005280, 0x1400052e8),
             (0x14000c850, 0x14000c882), (0x1400064b0, 0x140006670)}
    require(focused['binary_sha256'] == app.sha and len(focused['functions']) == 5 and
            {(int(r['start'], 16), int(r['end_exclusive'], 16)) for r in focused['functions']} == spans and
            spans <= set(app.spans) and all(r['complete'] is True and r.get('pseudocode') and not r.get('diagnostic')
                                          for r in focused['functions']), 'Focused binary report differs')
    result = {'schema': 'sl3.usbdk-rollback-contract.v1', 'sourceCommit': source.COMMIT, 'driverSha256': app.sha,
              'scope': 'Selected source/binary rollback flow and offline decoder additions; no device/driver execution',
              'checkedInstructions': facts, 'focusedFunctions': 5, 'focusedReportSha256': sha(focused_path),
              'sourceFunctions': {'AddRedirect': add_lines, 'AddRedirectRollBack': rollback_lines},
              'normalizedUpstreamSourceSha256': baseline['sourceLfSha256'],
              'wppMessageGuid': GUID, 'wppGuidVa': '0x140012288', 'supplementFormats': formats,
              'supplementSha256': hashlib.sha256(supplement).hexdigest(),
              'historicalBaselineDefinitions': 32, 'historicalBaselineSelectedTmfSha256': baseline['selectedTmfSha256'],
              'baselineDecoderChanged': False, 'captureFlagChangeRequiredForTheseErrorMessages': False,
              'failureBranches': [
                  {'reason': 'initial reset failure', 'rollbackCall': '0x140003028', 'withReset': False},
                  {'reason': 'attachment wait failure or timeout', 'rollbackCall': '0x1400030eb', 'withReset': True},
                  {'reason': 'redirect handle failure', 'rollbackCall': '0x1400030a1', 'withReset': True}],
              'rollback': {'function': '0x1400031fc', 'deleteBeforeConditionalReset': True,
                           'resetCall': '0x140003286', 'forceD0': False, 'cycleIoctlLiteral': '0x22001f'},
              'attachmentWait': {'call': '0x140003042', 'relative100ns': -120*10_000_000, 'seconds': 120,
                                 'alertable': False, 'timeoutStatus': '0x102', 'timeoutReturnStatus': '0xc000009d',
                                 'boundsEntireStartOrRollback': False},
              'sourceSha256': {name: sha(ROOT/name) for name in ['scripts/export-usbdk-rollback-contract.py',
                  'scripts/prepare-usbdk-lifecycle-trace.py', 'scripts/export-serato-clock-handshake-evidence.py',
                  'scripts/ghidra/FocusedDecompile.java']},
              'deviceAccess': False, 'driverExecutedOrModified': False, 'tracingEnabled': False,
              'historicalStallCauseProven': False, 'kernelQuiescenceFromWorkerExitProven': False,
              'reacquisitionRepairVerified': False,
              'limits': ['Selected release-binary branches are checked; full source/binary equivalence and request cancellation are not exhausted.',
                         'A failed start can select an extra reset internally; that is not proof of a cycle in a preserved historical run.',
                         'Attachment timeout is not a total deadline; reset/power/pending-IRP paths have separate unresolved waits.',
                         'Rollback messages report failures only; missing messages do not prove no rollback or successful quiescence.',
                         'No readiness gate, sleep/retry policy, binding change or driver patch is selected.']}
    return result, supplement


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', type=Path, help='Fresh direct analysis directory for offline supplement only')
    args = parser.parse_args()
    if args.prepare:
        require(args.prepare.resolve().parent == (ROOT/'analysis').resolve() and not args.prepare.exists(), 'Fresh direct analysis directory required')
    result, supplement = verify()
    encoded = (json.dumps(result, indent=2)+'\n').encode()
    if args.prepare:
        args.prepare.mkdir()
        (args.prepare/'rollback-supplement.tmf').write_bytes(supplement)
        (args.prepare/'plan.json').write_bytes(encoded)
    (ROOT/'docs/evidence/usbdk-rollback-contract-20261102.json').write_bytes(encoded)
    print(json.dumps({'verified': True, 'instructionFacts': len(result['checkedInstructions']), 'focusedFunctions': 5,
                      'extraDecoderFormats': 2, 'historicalBaselineChanged': False, 'deviceAccess': False}))


if __name__ == '__main__':
    main()
