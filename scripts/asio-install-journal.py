"""Installer lock and flushed recovery journal primitives; CLI is plan-only."""
from contextlib import contextmanager, ExitStack
import ctypes
from ctypes import wintypes as W
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import uuid

MAX_RECORD = 65536
MAX_TOTAL = 4*1024*1024
MAX_RECORDS = 4096
ZERO = '0'*64
LOCK_NAME = 'installer-lock.json'


def stage_module():
    name = 'sl3_install_journal_stage'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name('asio-file-stage.py'))
        module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    return sys.modules[name]


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_flush(handle, raw):
    s = stage_module(); count = W.DWORD()
    s.check(s.api('kernel32.dll', 'WriteFile', W.BOOL, [W.HANDLE, s.P, W.DWORD, ctypes.POINTER(W.DWORD), s.P])(
        handle, raw, len(raw), ctypes.byref(count), None))
    s.require(count.value == len(raw), 'Complete journal write required')
    s.check(s.api('kernel32.dll', 'FlushFileBuffers', W.BOOL, [W.HANDLE])(handle))


def parse(raw):
    """Verify complete records; preserve an incomplete tail without replaying it."""
    s = stage_module(); s.require(0 < len(raw) <= MAX_TOTAL, 'Journal size limit')
    records = []; previous = ZERO; position = 0
    while position < len(raw):
        end = raw.find(b'\n', position)
        if end < 0:
            break
        line = raw[position:end]; s.require(0 < len(line) <= MAX_RECORD, 'Journal record size limit')
        item = json.loads(line)
        s.require(encoded(item) == line and set(item) == {'schema', 'sequence', 'previous', 'payload', 'sha256'},
                  'Canonical exact journal envelope required')
        body = {k: v for k, v in item.items() if k != 'sha256'}
        s.require(item['schema'] == 'sl3.install-journal-record.v1' and type(item['sequence']) is int and
                  item['sequence'] == len(records) and item['previous'] == previous and isinstance(item['payload'], dict) and
                  item['sha256'] == digest(encoded(body)), 'Journal sequence/hash chain mismatch')
        records.append(item); s.require(len(records) <= MAX_RECORDS, 'Journal record count limit')
        previous = item['sha256']; position = end+1
    s.require(records and records[0]['payload'].get('event') == 'transaction_header', 'Complete transaction header required')
    tail = raw[position:]; s.require(len(tail) <= MAX_RECORD, 'Incomplete tail limit')
    return {'records': records, 'completeBytes': position, 'tornTailBytes': len(tail),
            'tornTailSha256': digest(tail) if tail else None, 'wholeFileSha256': digest(raw),
            'automaticallyReplayed': False, 'operationCompletionVerified': False}


class Journal:
    def __init__(self, handle, path, policy):
        self.handle = handle; self.path = path; self.policy = policy
        self.raw = b''; self.count = 0; self.previous = ZERO; self.poisoned = False; self.active = True

    def __call__(self, event):
        self.append({'event': 'step', 'data': event})

    def append(self, payload):
        s = stage_module()
        s.require(self.active and not self.poisoned, 'Journal closed/poisoned; no further mutation authorized')
        try:
            s.require(isinstance(payload, dict), 'Object payload required')
            body = {'schema': 'sl3.install-journal-record.v1', 'sequence': self.count,
                    'previous': self.previous, 'payload': payload}
            checksum = digest(encoded(body)); line = encoded(dict(body, sha256=checksum))+b'\n'
            s.require(len(line)-1 <= MAX_RECORD and len(self.raw)+len(line) <= MAX_TOTAL and
                      self.count < MAX_RECORDS, 'Journal append bound exceeded')
            info = s.inspect_policy(self.handle, self.policy, False)['file']
            s.require(info['size'] == len(self.raw), 'Journal size changed')
            if self.raw:
                s.require(s.read_handle(self.handle, MAX_TOTAL) == self.raw, 'Journal prefix changed')
            s.check(s.api('kernel32.dll', 'SetFilePointerEx', W.BOOL,
                         [W.HANDLE, ctypes.c_longlong, s.P, W.DWORD])(self.handle, 0, None, 2))
            write_flush(self.handle, line)
            s.inspect_policy(self.handle, self.policy, False)
            s.require(s.read_handle(self.handle, MAX_TOTAL) == self.raw+line, 'Flushed journal readback mismatch')
            self.raw += line; self.previous = checksum; self.count += 1
        except Exception:
            self.poisoned = True
            raise


@contextmanager
def transaction(base, policy, action, bindings):
    """Trusted caller serializes all package operations under this fixed base."""
    s = stage_module(); s.local(base)
    s.require(action in ('install', 'uninstall'), 'Known installer action required')
    s.require(isinstance(bindings, dict) and 'packageId' in bindings and
              set(bindings) <= {'packageId', 'bundleManifestSha256', 'stageRecordSha256'} and
              all(isinstance(v, str) and re.fullmatch('[0-9a-f]{64}', v) for v in bindings.values()), 'Reviewed lowercase hash bindings required')
    if policy == s.PRODUCTION:
        s.require(s.elevated() and ctypes.sizeof(s.P) == 8, 'Explicit native x64 elevation required; no automatic UAC')
        s.require(base == s.known_folder('905e63b6-c1bf-494e-b29c-65b732d3d21a')/'SL3 Rebuild', 'Fixed production installer base required')
    with ExitStack() as stack:
        parents = stack.enter_context(s.pinned_parents(base))
        if policy == s.PRODUCTION:
            trusted = {s.SYSTEM, s.ADMINS, s.account_sid('NT SERVICE\\TrustedInstaller')}
            for handle in parents:
                s.safe_parent(handle, trusted)
        root = stack.enter_context(s.open_file(base, True, access=0x20080, share=3))
        directory = s.inspect_policy(root, policy, True)['file']
        s.require(Path(directory['path']) == base, 'Installer base path changed')
        lock_bytes = encoded({'schema': 'sl3.installer-lock.v1', 'directory': str(base),
                              'identity': directory['identity'], 'policy': policy.record()})+b'\n'
        lock_path = base/LOCK_NAME
        try:
            lock = stack.enter_context(s.open_file(lock_path, access=0xc0000000, share=0))
            created = False
        except FileNotFoundError:
            with s.descriptor(policy.sddl(False)) as attributes:
                lock = stack.enter_context(s.open_file(lock_path, access=0xc0000000, share=0, create=1, security=attributes))
            created = True
        s.inspect_policy(lock, policy, False)
        if created:
            write_flush(lock, lock_bytes)
        s.require(s.read_handle(lock, MAX_RECORD) == lock_bytes, 'Foreign/damaged installer lock preserved; no automatic repair')
        path = base/('transaction-'+uuid.uuid4().hex+'.jsonl')
        with s.descriptor(policy.sddl(False)) as attributes:
            handle = stack.enter_context(s.open_file(path, access=0xc0000000, share=0, create=1, security=attributes))
        file = s.inspect_policy(handle, policy, False)['file']
        writer = Journal(handle, path, policy)
        try:
            writer.append({'event': 'transaction_header', 'action': action, 'bindings': bindings,
                           'directory': str(base), 'directoryIdentity': directory['identity'],
                           'journalIdentity': file['identity'], 'journalName': path.name,
                           'policy': policy.record(), 'productionPolicy': policy == s.PRODUCTION})
            yield writer
        finally:
            writer.active = False
        # Lock and journal files persist. OS handle release, including process
        # death, releases exclusivity; an old pathname alone is not a live lock.


def inspect_journal(base, path, policy):
    s = stage_module(); s.local(base); s.local(path)
    s.require(path.parent == base and re.fullmatch(r'transaction-[0-9a-f]{32}\.jsonl', path.name), 'Direct typed journal filename required')
    with ExitStack() as stack:
        stack.enter_context(s.pinned_parents(base))
        root = stack.enter_context(s.open_file(base, True, access=0x20080, share=3))
        directory = s.inspect_policy(root, policy, True)['file']
        handle = stack.enter_context(s.open_file(path))
        file = s.inspect_policy(handle, policy, False)['file']; result = parse(s.read_handle(handle, MAX_TOTAL))
        header = result['records'][0]['payload']
        s.require(header['directory'] == str(base) and header['directoryIdentity'] == directory['identity'] and
                  header['journalIdentity'] == file['identity'] and header['journalName'] == path.name and
                  header['policy'] == policy.record() and header['productionPolicy'] == (policy == s.PRODUCTION),
                  'Journal root/file/policy identity mismatch')
        return result


if __name__ == '__main__':
    if sys.argv[1:] not in ([], ['--plan']):
        print('Only --plan is exposed; installer operations require a trusted caller', file=sys.stderr); sys.exit(2)
    print(json.dumps({'schema': 'sl3.install-journal-plan.v1', 'planOnly': True, 'filesWritten': False,
                      'registryWritten': False, 'deviceAccess': False, 'machineMutationCliExposed': False}))
