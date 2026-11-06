"""Explicit candidate-only test in an owned Windows job; no Serato or USB access."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def require(value, message):
    if not value: raise ValueError(message)


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def source_identity():
    return hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def process_created(process):
    k = C.WinDLL('kernel32', use_last_error=True)
    k.GetProcessTimes.argtypes = [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4
    k.GetProcessTimes.restype = W.BOOL
    values = [W.FILETIME() for _ in range(4)]
    require(k.GetProcessTimes(W.HANDLE(int(process._handle)), *(C.byref(x) for x in values)),
            'Owned process time query failed')
    return str((values[0].dwHighDateTime << 32) | values[0].dwLowDateTime)


def verify_sdk(directory, expected):
    directory = Path(directory).resolve()
    require(directory.parent == (ROOT / 'artifacts/build').resolve() and
            directory.name.startswith('embedded-python-local-frida-'), 'Explicit isolated candidate SDK required')
    api = runpy.run_path(str(ROOT / 'scripts/prepare-embedded-python.py'))
    manifest = api['verify'](directory, expected)
    require(manifest.get('scope') == 'owned-process-local-frida-candidate-only' and
            manifest.get('listedNativeAssetsMatchFinalImage') is True, 'Candidate-only preparation required')
    return manifest


class Job:
    class Basic(C.Structure):
        _fields_ = [('times', C.c_int64 * 2), ('flags', W.DWORD), ('minimum', C.c_size_t),
                    ('maximum', C.c_size_t), ('active', W.DWORD), ('affinity', C.c_size_t),
                    ('priority', W.DWORD), ('scheduling', W.DWORD)]
    class Accounting(C.Structure):
        _fields_ = [('times', C.c_int64 * 4), ('faults', W.DWORD), ('total', W.DWORD),
                    ('active', W.DWORD), ('terminated', W.DWORD)]

    def __init__(self):
        class Extended(C.Structure):
            _fields_ = [('basic', Job.Basic), ('io', C.c_uint64 * 6), ('limits', C.c_size_t * 4)]
        self.k = C.WinDLL('kernel32', use_last_error=True)
        for name, arguments, result in (
            ('CreateJobObjectW', [C.c_void_p, W.LPCWSTR], W.HANDLE),
            ('SetInformationJobObject', [W.HANDLE, C.c_int, C.c_void_p, W.DWORD], W.BOOL),
            ('QueryInformationJobObject', [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p], W.BOOL),
            ('AssignProcessToJobObject', [W.HANDLE, W.HANDLE], W.BOOL),
            ('TerminateJobObject', [W.HANDLE, W.UINT], W.BOOL),
            ('GetProcessTimes', [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4, W.BOOL),
            ('OpenProcess', [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            ('QueryFullProcessImageNameW', [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)], W.BOOL),
            ('CloseHandle', [W.HANDLE], W.BOOL)):
            function = getattr(self.k, name); function.argtypes = arguments; function.restype = result
        self.handle = self.checked(self.k.CreateJobObjectW(None, None))
        limits = Extended(); limits.basic.flags = 0x2000 | 0x8; limits.basic.active = 4
        try:
            self.checked(self.k.SetInformationJobObject(self.handle, 9, C.byref(limits), C.sizeof(limits)))
            observed = Extended()
            self.checked(self.k.QueryInformationJobObject(self.handle, 9, C.byref(observed), C.sizeof(observed), None))
            require(observed.basic.flags == limits.basic.flags and observed.basic.active == 4, 'Job limits differ')
        except BaseException:
            self.close(); raise

    def checked(self, value):
        if not value: raise C.WinError(C.get_last_error())
        return value

    def assign(self, process):
        self.checked(self.k.AssignProcessToJobObject(self.handle, W.HANDLE(int(process._handle))))

    def creation(self, process):
        return process_created(process)

    def accounting(self):
        result = self.Accounting()
        self.checked(self.k.QueryInformationJobObject(self.handle, 1, C.byref(result), C.sizeof(result), None))
        return {'total': result.total, 'active': result.active, 'terminated': result.terminated}

    def members(self):
        class Members(C.Structure):
            _fields_ = [('assigned', W.DWORD), ('count', W.DWORD), ('pids', C.c_size_t * 64)]
        result = Members()
        self.checked(self.k.QueryInformationJobObject(self.handle, 3, C.byref(result), C.sizeof(result), None))
        require(result.assigned == result.count and result.count <= 64, 'Incomplete job process list')
        return list(result.pids[:result.count])

    def member_images(self):
        result = {}
        for pid in self.members():
            handle = self.checked(self.k.OpenProcess(0x1000, False, pid))
            try:
                buffer = C.create_unicode_buffer(32768); length = W.DWORD(len(buffer))
                self.checked(self.k.QueryFullProcessImageNameW(handle, 0, buffer, C.byref(length)))
                result[str(pid)] = buffer.value
            finally: self.k.CloseHandle(handle)
        return result

    def retire(self):
        self.checked(self.k.TerminateJobObject(self.handle, 70))

    def close(self):
        if self.handle:
            self.k.CloseHandle(self.handle); self.handle = None


def probe(sdk, expected, output):
    # The outer supervisor assigns this cooperative child to its job before opening the gate.
    deadline = time.monotonic() + 10
    while not (output / 'go').is_file():
        require(time.monotonic() < deadline, 'Owned-job gate timed out')
        time.sleep(.02)
    class Extended(C.Structure):
        _fields_ = [('basic', Job.Basic), ('io', C.c_uint64 * 6), ('limits', C.c_size_t * 4)]
    k = C.WinDLL('kernel32', use_last_error=True)
    k.QueryInformationJobObject.argtypes = [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p]
    k.QueryInformationJobObject.restype = W.BOOL
    limits = Extended()
    require(k.QueryInformationJobObject(None, 9, C.byref(limits), C.sizeof(limits), None) and
            limits.basic.flags == 0x2008 and limits.basic.active == 4, 'Candidate probe is not in its expected job')
    manifest = verify_sdk(sdk, expected)
    require(Path(sys.executable).resolve() == sdk / 'python.exe', 'Wrong private interpreter')
    report = {'schema': 'sl3.local-frida-owned-probe.v1', 'candidateSha256': manifest['candidateSha256'],
              'runnerNormalizedSha256': source_identity(),
              'stages': [], 'passed': False, 'fixtureStarted': False, 'deviceOpened': False,
              'seratoStarted': False, 'securityHoldCleared': False}
    fixture = session = script = frida = None
    def stage(name):
        report['stages'].append(name); save(output / 'progress.json', report)
    try:
        import frida
        require(Path(frida.__file__).resolve() == sdk / 'packages/frida/__init__.py' and
                Path(frida._frida.__file__).resolve() == sdk / 'packages/frida/_frida.pyd', 'Wrong SDK import path')
        report['version'] = frida.__version__; stage('candidate_imported')
        device = frida.get_local_device()
        require(device.type == 'local', 'Local process backend required'); stage('local_backend_ready')
        fixture = subprocess.Popen([str(sdk / 'python.exe'), '-I', '-B', str(Path(__file__).resolve()),
                                    '--fixture-mode', '--output', str(output)], creationflags=subprocess.DETACHED_PROCESS)
        report['fixtureStarted'] = True; report['fixturePid'] = fixture.pid
        report['fixtureCreated'] = process_created(fixture)
        require(fixture.poll() is None, 'Owned fixture exited before attachment')
        stage('fixture_owned')
        session = device.attach(fixture.pid); stage('fixture_attached')
        require(process_created(fixture) == report['fixtureCreated'] and fixture.poll() is None, 'Fixture ownership changed')
        script = session.create_script('rpc.exports.health = () => ({pid: Process.id, arch: Process.arch, runtime: Script.runtime});')
        script.load(); stage('script_loaded')
        result = script.exports_sync.health()
        require(result == {'pid': fixture.pid, 'arch': 'x64', 'runtime': 'QJS'}, 'Unexpected owned-process health reply')
        report['health'] = result; stage('health_rpc_passed')
        script.unload(); script = None; stage('script_unloaded')
        session.detach(); session = None; stage('fixture_detached')
        frida.shutdown(); frida = None; stage('manager_closed')
        (output / 'stop-fixture').write_text('stop', encoding='ascii')
        require(fixture.wait(timeout=5) == 0, 'Fixture did not exit normally')
        report['fixtureExitCode'] = fixture.returncode; stage('fixture_exited')
        report['passed'] = True
    except BaseException as error:
        report['error'] = str(error)[:1024]
    finally:
        # A native-library cleanup stall is bounded by the outer retained job handle.
        try:
            if script: script.unload()
            if session: session.detach()
            if frida: frida.shutdown()
            if fixture and fixture.poll() is None:
                (output / 'stop-fixture').write_text('stop', encoding='ascii'); fixture.wait(timeout=5)
        except BaseException as error:
            report['cleanupError'] = str(error)[:1024]; report['passed'] = False
        save(output / 'probe-result.json', report)
    return 0 if report['passed'] else 1


def run(sdk, expected, output):
    manifest = verify_sdk(sdk, expected)
    shell = C.WinDLL('shell32'); shell.IsUserAnAdmin.restype = W.BOOL
    require(not shell.IsUserAnAdmin(), 'Probe requires an ordinary user token; no elevation')
    require(output.parent.resolve() == (ROOT / 'analysis').resolve() and
            output.name.startswith('local-frida-owned-probe-') and not output.exists(), 'Fresh project-local output required')
    output.mkdir()
    report = {'schema': 'sl3.local-frida-owned-supervision.v1', 'candidateSha256': manifest['candidateSha256'],
              'runnerNormalizedSha256': source_identity(),
              'sdkManifestSha256': expected, 'processStarted': False, 'timedOut': False,
              'forcedJobCleanup': False, 'activeProcessLimit': 4, 'silentBreakawayAllowed': False,
              'killOnJobClose': True, 'ordinaryToken': True, 'securityHoldCleared': False,
              'deviceOpened': False, 'seratoStarted': False, 'passed': False}
    job = Job(); child = None; assigned = False
    try:
        with (output / 'stdout.txt').open('xb') as stdout, (output / 'stderr.txt').open('xb') as stderr:
            child = subprocess.Popen([str(sdk / 'python.exe'), '-I', '-B', str(Path(__file__).resolve()),
                                      '--probe-mode', '--sdk', str(sdk), '--expected-sdk-manifest-sha256', expected,
                                      '--output', str(output)], stdout=stdout, stderr=stderr,
                                     creationflags=subprocess.DETACHED_PROCESS)
            report['processStarted'] = True; report['probePid'] = child.pid
            job.assign(child); assigned = True; report['probeCreated'] = job.creation(child)
            require(child.poll() is None, 'Probe exited before job gate')
            (output / 'go').write_text('owned', encoding='ascii')
            try: report['probeExitCode'] = child.wait(timeout=35)
            except subprocess.TimeoutExpired:
                report['timedOut'] = True; job.retire(); report['forcedJobCleanup'] = True; child.wait(timeout=5)
            deadline = time.monotonic() + 3
            while job.accounting()['active'] and time.monotonic() < deadline: time.sleep(.05)
            report['beforeCleanup'] = job.accounting()
            if report['beforeCleanup']['active']:
                job.retire(); report['forcedJobCleanup'] = True
            deadline = time.monotonic() + 3
            while job.accounting()['active'] and time.monotonic() < deadline: time.sleep(.05)
            report['afterCleanup'] = job.accounting()
            path = output / 'probe-result.json'
            if path.is_file(): report['probe'] = json.loads(path.read_text())
            report['passed'] = (report.get('probeExitCode') == 0 and not report['timedOut'] and
                                not report['forcedJobCleanup'] and report['afterCleanup']['active'] == 0 and
                                report.get('probe', {}).get('runnerNormalizedSha256') == report['runnerNormalizedSha256'] and
                                report.get('probe', {}).get('passed') is True)
    except BaseException as error:
        report['error'] = str(error)[:1024]
    finally:
        try:
            if child and child.poll() is None:
                if assigned: job.retire(); report['forcedJobCleanup'] = True
                else: child.kill()
                child.wait(timeout=5)
            if assigned:
                report['finalAccounting'] = job.accounting()
                if report['finalAccounting']['active']:
                    report['passed'] = False; report['forcedJobCleanup'] = True; job.retire()
                    deadline = time.monotonic() + 3
                    while job.accounting()['active'] and time.monotonic() < deadline: time.sleep(.05)
                    report['finalAccounting'] = job.accounting()
        finally:
            job.close(); save(output / 'result.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--probe-mode', action='store_true', help=argparse.SUPPRESS)
    mode.add_argument('--fixture-mode', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--sdk', type=Path)
    parser.add_argument('--expected-sdk-manifest-sha256')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.fixture_mode:
        deadline = time.monotonic() + 50
        while not (args.output / 'stop-fixture').exists() and time.monotonic() < deadline: time.sleep(.02)
    else:
        require(args.sdk is not None and args.expected_sdk_manifest_sha256, 'Explicit candidate SDK identity required')
        sdk = args.sdk.resolve()
        if args.probe_mode:
            sys.exit(probe(sdk, args.expected_sdk_manifest_sha256, args.output.resolve()))
        elif args.run:
            require(args.output is not None, 'Fresh output required for run')
            result = run(sdk, args.expected_sdk_manifest_sha256, args.output.absolute())
            print(json.dumps(result, indent=2)); sys.exit(0 if result['passed'] else 1)
        else:
            manifest = verify_sdk(sdk, args.expected_sdk_manifest_sha256)
            print(json.dumps({'planOnly': True, 'scope': manifest['scope'], 'candidateSha256': manifest['candidateSha256'],
                              'fridaImported': False, 'processStarted': False, 'deviceOpened': False}, indent=2))
