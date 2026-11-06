"""Request shutdown of one verified live session; never terminate or uninstall."""
import argparse
from contextlib import contextmanager, ExitStack
import ctypes
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import runpy
import uuid

ROOT = Path(__file__).resolve().parents[1]


def require(value, message):
    if not value:
        raise ValueError(message)


def module(name):
    return runpy.run_path(str(ROOT / 'scripts' / name))


@contextmanager
def process_lease(pid, image, created=None):
    """Query/synchronize only; a retained object prevents PID-reuse confusion."""
    s = module('asio-install-journal.py')['stage_module']()
    require(type(pid) is int and 0 < pid <= 0xffffffff, 'Expected bounded process identity')
    with ExitStack() as stack:
        handle = stack.enter_context(s.Handle(s.api('kernel32.dll', 'OpenProcess', W.HANDLE,
            [W.DWORD, W.BOOL, W.DWORD])(0x101000, False, pid)))
        require(s.api('kernel32.dll', 'WaitForSingleObject', W.DWORD, [W.HANDLE, W.DWORD])(handle, 0) == 258,
                'Selected session owner has exited')
        times = [W.FILETIME() for _ in range(4)]
        s.check(s.api('kernel32.dll', 'GetProcessTimes', W.BOOL,
            [W.HANDLE] + [ctypes.POINTER(W.FILETIME)] * 4)(handle, *(ctypes.byref(value) for value in times)))
        actual_created = str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
        require(created is None or actual_created == created, 'Selected session owner creation differs')
        buffer = ctypes.create_unicode_buffer(32768); length = W.DWORD(len(buffer))
        s.check(s.api('kernel32.dll', 'QueryFullProcessImageNameW', W.BOOL,
            [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)])(handle, 0, buffer, ctypes.byref(length)))
        actual_image = Path(buffer.value)
        expected_file = stack.enter_context(s.open_file(Path(image).absolute()))
        actual_file = stack.enter_context(s.open_file(actual_image))
        require(s.information(expected_file, False)['identity'] == s.information(actual_file, False)['identity'],
                'Selected session owner image differs')
        yield {'pid': pid, 'created': actual_created}


def current_owner(image):
    with process_lease(os.getpid(), image) as owner:
        return owner


def read_request(path, expected_capsule, expected_intent, supervisor):
    if not path.exists():
        return False
    require(not path.is_symlink() and not getattr(path.lstat(), 'st_file_attributes', 0) & 0x400 and
            0 < path.stat().st_size <= 4096, 'Bounded regular stop request required')
    record = json.loads(path.read_bytes())
    require(record['schema'] == 'sl3.session-stop-request.v1' and record['capsuleSha256'] == expected_capsule and
            record['intentSha256'] == expected_intent and record['supervisor'] == supervisor,
            'Stop request belongs to another session')
    return True


def request(plan_path, expected, powershell, write=False):
    api = module('prepare-serato-session-plan.py')
    plan = api['verify'](Path(plan_path).absolute(), expected)
    directory = Path(plan['capsule']['path']).parent; output = Path(plan['hostOutput'])
    require(output.parent.resolve() == (ROOT / 'analysis').resolve() and output.name.startswith('sl3-startup-session-') and
            output.is_dir() and not output.is_symlink() and not output.is_junction(), 'Selected supervisor output is unavailable')
    require(not (output / 'result.json').exists() and not (directory / 'session-final.json').exists(),
            'Selected session has already finished; preserve its result')
    s = module('asio-install-journal.py')['stage_module']()
    with ExitStack() as stack:
        stack.enter_context(s.pinned_parents(output / 'stop.txt'))
        stack.enter_context(s.pinned_parents(directory / 'session-run.lock'))
        owner_file = stack.enter_context(s.open_file(directory / 'session-run.lock', share=3))
        owner = json.loads(s.read_handle(owner_file, 4096))['runner']
        intent_file = stack.enter_context(s.open_file(output / 'intent.json'))
        raw = s.read_handle(intent_file, 16384); intent = json.loads(raw)
        intent_sha = hashlib.sha256(raw).hexdigest()
        prepared = json.loads((Path(plan['preparedShim']['path']) / 'preparation.json').read_bytes())
        require(intent['schema'] == 'sl3.startup-supervisor-intent.v1' and
                intent['applicationSha256'] == plan['application']['sha256'] and
                intent['scriptSha256'] == prepared['preparedScriptSha256'] and
                intent['deploymentManifestSha256'] == plan['nativeBundle']['sha256'] and
                intent['preparationSha256'] == plan['preparedShim']['sha256'] and
                intent['requiresExternalRollback'] is True and intent['hardDeadlineSeconds'] == 840 and
                intent['launcherCapsuleBound'] is True and
                intent['launcherCapsuleSha256'] == plan['capsule']['sha256'], 'Supervisor intent differs from selected session')
        supervisor = intent['supervisorOwner']
        stack.enter_context(process_lease(owner['pid'], Path(powershell) / 'pwsh.exe', owner['created']))
        stack.enter_context(process_lease(supervisor['pid'], plan['python']['path'], supervisor['created']))
        destination = output / 'stop.txt'
        existing = read_request(destination, plan['capsule']['sha256'], intent_sha, supervisor)
        report = {'schema': 'sl3.session-stop-dispatch.v1', 'planOnly': not write, 'liveOwnersVerified': True,
                  'stopAlreadyRequested': existing, 'stopRequested': False, 'processTerminated': False,
                  'registryWritten': False, 'deviceAccess': False, 'shutdownConfirmed': False}
        if not write or existing:
            return {**report, 'stopRequested': existing}
        value = {'schema': 'sl3.session-stop-request.v1', 'capsuleSha256': plan['capsule']['sha256'],
                 'intentSha256': intent_sha, 'supervisor': supervisor, 'runner': owner}
        pending = output / ('stop-' + uuid.uuid4().hex + '.pending')
        with pending.open('xb') as stream:
            stream.write((json.dumps(value, sort_keys=True) + '\n').encode())
            stream.flush(); os.fsync(stream.fileno())
        # Windows same-directory rename is atomic and refuses an existing target.
        # Preserve a pending request after any failed publication for diagnosis.
        pending.rename(destination)
        return {**report, 'stopRequested': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-plan', type=Path, required=True)
    parser.add_argument('--expected-session-plan-sha256', required=True)
    parser.add_argument('--powershell-directory', type=Path, required=True)
    parser.add_argument('--request', action='store_true')
    args = parser.parse_args()
    print(json.dumps(request(args.session_plan, args.expected_session_plan_sha256,
                             args.powershell_directory, args.request), indent=2))
