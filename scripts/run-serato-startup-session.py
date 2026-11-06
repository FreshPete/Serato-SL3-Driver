"""Bounded ordinary-user process supervisor; protected staging stays external."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import queue
import runpy
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
APP_SHA = '66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265'
ORIGINAL_RESOURCES = '872fc4fdad2eab2ddd34387d2d3c04dd9731c84798d9fdc7bd05ca54e1567db8'
PHASE_RESOURCES = 'd135e6f1c03601cc44b3e5f623eed36af81bbff585332a3fdc8d5d533b2cb66a'
BUNDLE_NAME = '8c7758f23375cee18a9cf3be4a3acc15.bin'


class UserStopRequested(Exception):
    pass


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def launcher_environment(capsule, expected, application, bundle, bundle_sha):
    if capsule is None and expected is None:
        return {}
    require(capsule is not None and expected is not None, 'Complete launcher capsule binding required')
    path = Path(capsule).absolute()
    api = runpy.run_path(str(ROOT/'scripts/serato-session-capsule.py'))
    record, _, _ = api['verify'](path, expected)
    require(Path(record['application']['path']).absolute() == Path(application).absolute() and
            Path(record['bundle']['path']).absolute() == Path(bundle).absolute() and
            record['bundle']['sha256'] == bundle_sha, 'Launcher capsule differs from supervised application/package')
    return {'SL3_SESSION_CAPSULE':str(path),'SL3_SESSION_CAPSULE_SHA256':expected}


def preflight(prepared, preparation_sha, application, bundle, bundle_sha, installer_sha, running=False):
    # Keep native Windows spelling; resolve() can rewrite packaged-app profile
    # paths. The deployment verifier performs its own containment checks.
    prepared, application, bundle = (Path(value).absolute() for value in (prepared,application,bundle))
    require(application.name == 'Serato DJ Pro.exe', 'Expected the reviewed application filename')
    record_path = prepared/'preparation.json'
    require(record_path.stat().st_size <= 16384 and digest(record_path) == preparation_sha, 'Preparation manifest differs')
    record = json.loads(record_path.read_bytes())
    require(record['schema'] == 'sl3.startup-shim-preparation.v1' and record['applicationSha256'] == APP_SHA,
            'Unsupported startup preparation')
    require(digest(application) == APP_SHA, 'Reviewed application differs')
    builder = runpy.run_path(str(ROOT/'scripts/prepare-serato-startup-shim.py'))
    planned = builder['asio_path'](record['plannedAsioPath'])
    template = (ROOT/'scripts/serato-sl3-startup-shim.js').read_bytes()
    configuration = ('globalThis.SL3_SESSION_CONFIG = Object.freeze(' + json.dumps({'asioPath': planned}) + ');\n').encode()
    script = (prepared/'startup-shim.js').read_bytes()
    require(len(script) <= 65536 and script == configuration + template and
            hashlib.sha256(template).hexdigest() == record['templateSha256'] and
            hashlib.sha256(script).hexdigest() == record['preparedScriptSha256'], 'Prepared startup script differs')
    runpy.run_path(str(ROOT/'scripts/prepare-asio-deployment.py'))['verify'](bundle, bundle_sha)
    deployment = json.loads((bundle/'deployment-plan.json').read_bytes())
    package = json.loads((bundle/'bundle-manifest.json').read_bytes())
    asio = Path(deployment['installationDirectory'])/'sl3_asio.dll'
    require(str(asio).replace('/', '\\').lower() == planned.lower(), 'Prepared DLL path differs from deployment')
    require(len(installer_sha) == 64 and all(c in '0123456789abcdef' for c in installer_sha), 'Expected installer bundle SHA-256 required')
    resources = application.with_name('userio_resources.bin')
    resource_sha = digest(resources)
    require(resource_sha in (ORIGINAL_RESOURCES, PHASE_RESOURCES), 'Unreviewed installed resources')
    installer = application.parent/'bundles'/BUNDLE_NAME
    if running:
        require(os.name == 'nt' and resource_sha == PHASE_RESOURCES and installer.is_file() and digest(installer) == installer_sha,
                'Reviewed protected resource and installer staging required before Run')
        require(not asio.exists(), 'Fresh temporary ASIO install state required')
        import winreg
        for entry in deployment['registryEntries']:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, entry['key'], 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
            except FileNotFoundError:
                continue
            key.Close()
            raise ValueError('Temporary ASIO registry state must be absent at startup')
    return {'script': script.decode('utf-8'), 'application': application, 'asio': asio,
            'asioSha256': package['files']['sl3_asio.dll']['sha256'],
            'resourceState': 'original' if resource_sha == ORIGINAL_RESOURCES else 'staged',
            'scriptSha256': record['preparedScriptSha256'], 'preparationSha256': preparation_sha,
            'deploymentManifestSha256': bundle_sha}


def supervise(backend, script, verify_driver, stop_requested, clock=time.monotonic,
              click_seconds=180, start_seconds=60, viewing_seconds=540, event_sink=None):
    """One owned process. Backend cleanup runs even on partial startup failure."""
    incoming = queue.Queue(maxsize=128)
    overflow = threading.Event()
    report = {'schema': 'sl3.startup-supervisor-result.v1', 'events': [], 'error': None,
              'asioStartObserved': False, 'stagedAsioVerified': False, 'tracerDetached': False,
              'hostDirectDeviceAccess': False, 'hardwareStreamingVerified': False,
              'registryWrittenByHost': False, 'resourcesRestoredByHost': False}

    def message(value, data=None):
        try:
            incoming.put_nowait(value)
        except queue.Full:
            overflow.set()

    def event(name, **fields):
        require(len(report['events']) < 256, 'Startup event bound exceeded')
        item = {'event': name, 'hostMonotonicSeconds':clock(), **fields}
        report['events'].append(item)
        if event_sink:
            event_sink(item)

    def wait_for(name, seconds):
        deadline = clock() + seconds
        while clock() < deadline:
            if stop_requested():
                raise UserStopRequested()
            require(not overflow.is_set(), 'Startup message bound exceeded')
            try:
                item = incoming.get_nowait()
            except queue.Empty:
                require(not backend.wait(.025), 'Owned application exited during startup')
                continue
            require(isinstance(item, dict), 'Malformed instrumentation message')
            if item.get('type') == 'error':
                raise ValueError('Startup shim: ' + str(item.get('description', 'unknown error'))[:512])
            if item.get('type') != 'send':
                continue
            payload = item.get('payload')
            require(isinstance(payload, dict) and isinstance(payload.get('event'), str), 'Malformed startup event')
            event(payload['event'], timeMs=payload.get('timeMs'))
            if payload['event'] == name and (name != 'asio_live_start_end' or payload.get('result') == 0):
                return
        raise TimeoutError('Startup deadline: ' + name)

    try:
        backend.start(script, message)
        wait_for('trace_ready', 5)
        backend.resume()
        wait_for('installer_action', click_seconds)
        wait_for('asio_live_start_end', start_seconds)
        report['asioStartObserved'] = True
        verify_driver()
        report['stagedAsioVerified'] = True
        backend.detach()
        report['tracerDetached'] = True
        event('diagnostic_tracer_detached')
        deadline = clock() + viewing_seconds
        while clock() < deadline:
            if backend.wait(.1):
                report['endReason'] = 'application_exited'
                break
            if stop_requested():
                report['endReason'] = 'manual_stop'
                report['userStopRequested'] = True
                event('manual_stop_observed',phase='interaction')
                break
        else:
            report['endReason'] = 'viewing_limit'
        event('viewing_window_ended',reason=report['endReason'])
    except UserStopRequested:
        report['endReason'] = 'manual_stop_during_startup'
        report['userStopRequested'] = True
    except Exception as error:
        report['error'] = str(error)[:1024]
        report['endReason'] = 'failure'
    finally:
        try:
            report['process'] = backend.cleanup()
        except Exception as error:
            report['cleanupError'] = str(error)[:1024]
    process = report.get('process', {})
    report['supervisionCompleted'] = bool(not report['error'] and not report.get('cleanupError') and
        report['tracerDetached'] and process.get('processExited') and process.get('jobEmpty') and
        not process.get('observerForcedTermination') and process.get('exitCode') == 0)
    return report


class HardDeadline:
    # Library calls can block before their protocol deadline can be serviced.
    # Exiting closes the owned process job. No logging or file I/O is attempted
    # on this containment path, and no successful cleanup result is fabricated.
    def __init__(self, seconds=840, abort=os._exit):
        self.finished = threading.Event()
        def watch():
            if not self.finished.wait(seconds):
                abort(70)
        self.thread = threading.Thread(target=watch,daemon=True)
        self.thread.start()
    def close(self):
        self.finished.set()
        self.thread.join()


class WindowsProcess:
    """Frida-spawned process and retained Win32 handles; never kills by PID lookup."""
    def __init__(self, application, frida, expected_application_sha=APP_SHA, launcher_context=None, asio_private_trace=False):
        import ctypes as c
        from ctypes import wintypes as w
        self.c, self.w, self.application = c, w, application
        self.expected_application_sha = expected_application_sha
        require(type(asio_private_trace) is bool, 'ASIO private tracing requires an explicit Boolean')
        self.asio_private_trace = asio_private_trace
        self.launcher_context = dict(launcher_context or {})
        require(set(self.launcher_context) in (set(), {'SL3_SESSION_CAPSULE','SL3_SESSION_CAPSULE_SHA256'}),
                'Unexpected launcher environment fields')
        self.device = frida.get_local_device()
        self.handle = self.job = self.session = self.script = self.pid = None
        self.k = k = c.WinDLL('kernel32', use_last_error=True)
        for name, args, result in (
            ('OpenProcess', [w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            ('CreateJobObjectW', [c.c_void_p, w.LPCWSTR], w.HANDLE),
            ('SetInformationJobObject', [w.HANDLE,w.DWORD,c.c_void_p,w.DWORD],w.BOOL),
            ('AssignProcessToJobObject',[w.HANDLE,w.HANDLE],w.BOOL),
            ('QueryInformationJobObject',[w.HANDLE,w.DWORD,c.c_void_p,w.DWORD,c.c_void_p],w.BOOL),
            ('WaitForSingleObject',[w.HANDLE,w.DWORD],w.DWORD),
            ('TerminateProcess',[w.HANDLE,w.UINT],w.BOOL),
            ('GetExitCodeProcess',[w.HANDLE,c.POINTER(w.DWORD)],w.BOOL),
            ('GetProcessTimes',[w.HANDLE]+[c.POINTER(w.FILETIME)]*4,w.BOOL),
            ('CloseHandle',[w.HANDLE],w.BOOL)):
            function = getattr(k, name); function.argtypes = args; function.restype = result

    def checked(self, result):
        if not result:
            raise self.c.WinError(self.c.get_last_error())
        return result

    def start(self, script, callback):
        c, w, k = self.c, self.w, self.k
        require(digest(self.application) == self.expected_application_sha, 'Application changed before process creation')
        class Basic(c.Structure):
            _fields_ = [('times', c.c_int64*2), ('flags', w.DWORD), ('minimum', c.c_size_t),
                        ('maximum', c.c_size_t), ('active', w.DWORD), ('affinity', c.c_size_t),
                        ('priority', w.DWORD), ('scheduling', w.DWORD)]
        class Extended(c.Structure):
            _fields_ = [('basic', Basic), ('io', c.c_uint64*6), ('limits', c.c_size_t*4)]
        limits = Extended(); limits.basic.flags = 0x2000 | 0x1000
        self.job = self.checked(k.CreateJobObjectW(None, None))
        self.checked(k.SetInformationJobObject(self.job, 9, c.byref(limits), c.sizeof(limits)))
        environment = {'SL3_ASIO_PRIVATE_TRACE':'1' if self.asio_private_trace else '0',
                       'SL3_SESSION_CAPSULE':'','SL3_SESSION_CAPSULE_SHA256':''}
        environment.update(self.launcher_context)
        self.pid = self.device.spawn([str(self.application)], cwd=str(self.application.parent), stdio='pipe', env=environment)
        self.handle = self.checked(k.OpenProcess(0x101101, False, self.pid))
        self.checked(k.AssignProcessToJobObject(self.job, self.handle))
        self.session = self.device.attach(self.pid)
        require(not self.wait(0), 'Owned process exited before script load')
        self.script = self.session.create_script(script)
        self.script.on('message', callback)
        self.script.load()

    def resume(self):
        require(not self.wait(0), 'Owned process exited before resume')
        self.device.resume(self.pid)

    def wait(self, seconds):
        value = self.k.WaitForSingleObject(self.handle, int(seconds*1000))
        require(value in (0, 258), 'Owned process wait failed')
        return value == 0

    def detach(self):
        if self.script:
            self.script.unload(); self.script = None
        if self.session:
            self.session.detach(); self.session = None

    def window_snapshot(self, post_close=False, user32=None):
        """Owned top-level metadata only; no titles, screenshots or synchronous messages."""
        c, w = self.c, self.w
        u = user32 if user32 is not None else c.WinDLL('user32', use_last_error=True)
        callback_type = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        u.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
        u.GetWindowThreadProcessId.restype = w.DWORD
        u.IsWindowVisible.argtypes = [w.HWND]; u.IsWindowVisible.restype = w.BOOL
        u.IsWindowEnabled.argtypes = [w.HWND]; u.IsWindowEnabled.restype = w.BOOL
        u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]; u.PostMessageW.restype = w.BOOL
        u.EnumWindows.argtypes = [callback_type, w.LPARAM]; u.EnumWindows.restype = w.BOOL
        result = {'ownedTopLevelWindows': 0, 'visibleWindows': 0, 'enabledVisibleWindows': 0,
                  'closeMessagesPosted': 0, 'closePostFailures': 0, 'closePostErrors': [],
                  'postCloseRequested': post_close, 'enumerationSucceeded': False,
                  'enumerationError': None, 'callbackError': None}
        @callback_type
        def visit(hwnd, unused):
            try:
                # Keep using the retained process object: never target another
                # process by a stale PID after our owned child has exited.
                if self.wait(0):
                    return True
                pid = w.DWORD()
                if not u.GetWindowThreadProcessId(hwnd, c.byref(pid)) or pid.value != self.pid:
                    return True
                result['ownedTopLevelWindows'] += 1
                if u.IsWindowVisible(hwnd):
                    result['visibleWindows'] += 1
                    result['enabledVisibleWindows'] += bool(u.IsWindowEnabled(hwnd))
                    if post_close:
                        c.set_last_error(0)
                        if u.PostMessageW(hwnd, 0x10, 0, 0):
                            result['closeMessagesPosted'] += 1
                        else:
                            result['closePostFailures'] += 1
                            if len(result['closePostErrors']) < 8:
                                result['closePostErrors'].append(c.get_last_error())
                return True
            except Exception as error:
                result['callbackError'] = str(error)[:256]
                return False
        c.set_last_error(0)
        result['enumerationSucceeded'] = bool(u.EnumWindows(visit, 0))
        if not result['enumerationSucceeded']:
            result['enumerationError'] = c.get_last_error()
        return result

    def cleanup(self):
        c, w, k = self.c, self.w, self.k
        result = {'processStarted': self.pid is not None, 'pid':self.pid, 'processExited': False,
                  'observerForcedTermination': False, 'closeRequested': False, 'exitCode': None, 'jobEmpty': False}
        try:
            if self.handle:
                if not self.wait(0):
                    result['closeRequested'] = True
                    result['closeWindowObservation'] = self.window_snapshot(post_close=True)
                    # A rejected/enumeration-failed close is evidence, not a
                    # reason to skip the bounded wait and lose the final report.
                    if not self.wait(8):
                        result['closeTimeoutWindowObservation'] = self.window_snapshot()
                        self.checked(k.TerminateProcess(self.handle, 1))
                        result['observerForcedTermination'] = True
                        self.wait(5)
                result['processExited'] = self.wait(0)
                code = w.DWORD(); self.checked(k.GetExitCodeProcess(self.handle,c.byref(code)))
                result['exitCode'] = code.value if result['processExited'] else None
                times = [w.FILETIME() for _ in range(4)]
                if k.GetProcessTimes(self.handle, *(c.byref(value) for value in times)):
                    result['processFileTimes'] = {name: str((value.dwHighDateTime<<32)|value.dwLowDateTime)
                        for name,value in zip(('first','last'),times)}
            elif self.pid is not None:
                # No retained process object means no safe termination by PID.
                result['ownershipUnproven'] = True
            else:
                result['processExited'] = True
            try:
                self.detach()
            except Exception as error:
                result['detachError'] = str(error)[:512]
            if self.job:
                class Accounting(c.Structure):
                    _fields_ = [('times',c.c_int64*4),('faults',w.DWORD),('total',w.DWORD),
                                ('active',w.DWORD),('terminated',w.DWORD)]
                accounting = Accounting()
                deadline = time.monotonic()+1
                while True:
                    self.checked(k.QueryInformationJobObject(self.job,1,c.byref(accounting),c.sizeof(accounting),None))
                    if not accounting.active or time.monotonic() >= deadline:
                        break
                    time.sleep(.01)
                result['jobEmpty'] = accounting.active == 0 and not result.get('ownershipUnproven',False)
        finally:
            if self.handle:
                k.CloseHandle(self.handle); self.handle = None
            if self.job:
                k.CloseHandle(self.job); self.job = None
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--plan', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--expected-preparation-sha256', required=True)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--expected-bundle-sha256', required=True)
    parser.add_argument('--expected-installer-bundle-sha256', required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--frida-directory', type=Path)
    parser.add_argument('--launcher-capsule', type=Path)
    parser.add_argument('--expected-launcher-capsule-sha256')
    parser.add_argument('--asio-private-trace', action='store_true', help='Opt in to bounded DLL-owned ASIO metadata logs')
    args = parser.parse_args()
    require(not args.run or args.output is not None, 'Fresh output directory required for Run')
    prepared = preflight(args.prepared,args.expected_preparation_sha256,args.app,args.bundle,
                         args.expected_bundle_sha256,args.expected_installer_bundle_sha256,args.run)
    context = launcher_environment(args.launcher_capsule,args.expected_launcher_capsule_sha256,
                                   args.app,args.bundle,args.expected_bundle_sha256)
    if not args.run:
        print(json.dumps({'planOnly':True,'inputsVerified':True,'resourceState':prepared['resourceState'],
                          'asioPrivateTraceRequested':args.asio_private_trace,
                          'processStarted':False,'filesWritten':False,'registryWritten':False,'deviceAccess':False}))
        return
    import ctypes
    from ctypes import wintypes
    shell = ctypes.WinDLL('shell32',use_last_error=True)
    shell.IsUserAnAdmin.restype = wintypes.BOOL
    require(not shell.IsUserAnAdmin(), 'Start the application with an ordinary user token')
    output = args.output
    require(output.parent.resolve() == (ROOT/'analysis').resolve() and output.name.startswith('sl3-startup-session-')
            and not output.exists() and not output.is_symlink(), 'Fresh analysis/sl3-startup-session-* directory required')
    if args.frida_directory:
        sys.path.insert(0,str(args.frida_directory.resolve()))
    output.mkdir()
    stop_api = runpy.run_path(str(ROOT/'scripts/serato-session-stop.py'))
    supervisor_owner = stop_api['current_owner'](Path(sys.executable))
    with (output/'intent.json').open('x',encoding='utf-8') as stream:
        json.dump({'schema':'sl3.startup-supervisor-intent.v1','applicationSha256':APP_SHA,
                   'scriptSha256':prepared['scriptSha256'],'preparationSha256':prepared['preparationSha256'],
                   'deploymentManifestSha256':prepared['deploymentManifestSha256'],
                   'requiresExternalRollback':True,'hardDeadlineSeconds':840,'launcherCapsuleBound':bool(context),
                   'launcherCapsuleSha256':args.expected_launcher_capsule_sha256,'supervisorOwner':supervisor_owner,
                   'asioPrivateTraceRequested':args.asio_private_trace},stream,indent=2)
    intent_sha = digest(output/'intent.json')
    def verify_driver():
        require(digest(prepared['asio']) == prepared['asioSha256'], 'Installed ASIO differs from reviewed package')
    watchdog = HardDeadline()
    report = None
    try:
        frida = importlib.import_module('frida')
        with (output/'events.jsonl').open('x',encoding='utf-8') as events:
            def publish(item):
                events.write(json.dumps(item)+'\n'); events.flush()
            report = supervise(WindowsProcess(prepared['application'],frida,launcher_context=context,
                                             asio_private_trace=args.asio_private_trace),prepared['script'],verify_driver,
                               lambda:stop_api['read_request'](output/'stop.txt',args.expected_launcher_capsule_sha256,
                                                              intent_sha,supervisor_owner),event_sink=publish)
        report['fridaVersion'] = frida.__version__
    except Exception as error:
        if report is None:
            report = {'schema':'sl3.startup-supervisor-result.v1','error':str(error)[:1024],
                      'process':{'processStarted':None,'processExited':False,'jobEmpty':False}}
        else:
            report['publicationError'] = str(error)[:1024]
        report['supervisionCompleted'] = False
    finally:
        watchdog.close()
    report['asioPrivateTraceRequested'] = args.asio_private_trace
    with (output/'result.json').open('x',encoding='utf-8') as stream:
        json.dump(report,stream,indent=2)
        stream.write('\n')
    print(json.dumps(report))
    raise SystemExit(0 if report['supervisionCompleted'] else 1)


if __name__ == '__main__':
    main()
