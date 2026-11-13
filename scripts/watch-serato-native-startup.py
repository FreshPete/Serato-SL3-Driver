"""Rehearse the prepared native loader against independently started Serato processes."""

import argparse
from contextlib import closing, contextmanager, nullcontext
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import re
import runpy
import sys
import tempfile
import time
import winreg

HERE = Path(__file__).resolve().parent
TRIAL = runpy.run_path(str(HERE / "run-serato-native-descriptor-trial.py"))
PROBE, SESSION = TRIAL["PROBE"], TRIAL["SESSION"]
ROOT, require, digest = TRIAL["ROOT"], TRIAL["require"], TRIAL["digest"]
LIBRARY = TRIAL["LIBRARY"]
WINDOWS_EPOCH = 116444736000000000
WATCHER_MUTEX = r"Local\SL3CompatibilityWatcher-v1"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "SL3CompatibilityWatcher"
READY_SCHEMA = "sl3.native-watcher-ready.v1"


def startup_value(key):
    try:
        return winreg.QueryValueEx(key, RUN_NAME)
    except FileNotFoundError:
        return None


class SignInRegistration:
    def __init__(self, root):
        self.python = root / "runtime/python/pythonw.exe"
        self.bootstrap = root / "watch.pyw"
        self.receipt = root / "analysis/watcher-ready.json"
        self.command = f'"{self.python}" -I -B "{self.bootstrap}"'
        require(len(self.command.encode("utf-16-le")) // 2 <= 260, "Watcher sign-in command exceeds 260 characters")

    def owns(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                return startup_value(key) == (self.command, winreg.REG_SZ)
        except FileNotFoundError:
            return False

    def ready_bytes(self):
        require(not self.receipt.is_symlink() and not self.receipt.is_junction() and
                not self.receipt.parent.is_symlink() and not self.receipt.parent.is_junction(),
                "Watcher readiness cannot use redirected paths")
        try:
            with self.receipt.open("rb") as stream:
                raw = stream.read(4097)
        except FileNotFoundError:
            return None
        require(0 < len(raw) <= 4096, "Bounded watcher readiness receipt required")
        return raw

    def ready_process(self, expected):
        raw = self.ready_bytes()
        if raw is None:
            return None
        row = json.loads(raw)
        require(isinstance(row, dict) and set(row) == {"schema", "startupPlanSha256", "process"} and
                row["schema"] == READY_SCHEMA and row["startupPlanSha256"] == expected,
                "Watcher readiness differs from the reviewed startup plan")
        identity = row["process"]
        require(isinstance(identity, dict) and set(identity) == {"pid", "created", "session"} and
                type(identity["pid"]) is int and 0 < identity["pid"] <= 0xffffffff and
                type(identity["session"]) is int and 0 <= identity["session"] <= 0xffffffff and
                isinstance(identity["created"], str) and re.fullmatch(r"[1-9][0-9]{0,19}", identity["created"]) and
                int(identity["created"]) < 2**64,
                "Watcher readiness process identity is invalid")
        try:
            return WatchedProcess(self.python, identity)
        except (OSError, ValueError):
            return None  # A stale receipt cannot authorize a process wait or stop.

    @contextmanager
    def ready(self, expected):
        require(self.owns(), "Watcher sign-in command was withdrawn before readiness")
        with closing(WatchedProcess(self.python, {"pid": os.getpid()}, not_before=0)) as process:
            raw = (json.dumps({"schema": READY_SCHEMA, "startupPlanSha256": expected,
                               "process": process.identity}) + "\n").encode("utf-8")
        previous = self.ready_process(expected)
        if previous is not None:
            previous.close()
            raise ValueError("Another verified watcher already published readiness")
        with tempfile.TemporaryDirectory(prefix="watcher-ready-", dir=self.receipt.parent) as scratch:
            pending = Path(scratch) / self.receipt.name
            pending.write_bytes(raw)
            pending.replace(self.receipt)
        try:
            yield
        finally:
            if self.ready_bytes() == raw:
                self.receipt.unlink(missing_ok=True)


@contextmanager
def watcher_lease(name=WATCHER_MUTEX, timeout_ms=0):
    kernel = c.WinDLL("kernel32", use_last_error=True)
    for function_name, arguments, result in (
        ("CreateMutexW", [c.c_void_p, w.BOOL, w.LPCWSTR], w.HANDLE),
        ("WaitForSingleObject", [w.HANDLE, w.DWORD], w.DWORD),
        ("ReleaseMutex", [w.HANDLE], w.BOOL),
        ("CloseHandle", [w.HANDLE], w.BOOL),
    ):
        function = getattr(kernel, function_name)
        function.argtypes, function.restype = arguments, result
    handle = WatchedProcess.checked(kernel.CreateMutexW(None, False, name))
    try:
        result = kernel.WaitForSingleObject(handle, timeout_ms)
        if result == 0xffffffff:
            raise c.WinError(c.get_last_error())
        require(result in (0, 128), "An SL3 startup watcher is already running in this session")
        try:
            yield
        finally:
            WatchedProcess.checked(kernel.ReleaseMutex(handle))
    finally:
        kernel.CloseHandle(handle)


class ProcessEntry(c.Structure):
    _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("pid", w.DWORD), ("heap", c.c_size_t),
                ("module", w.DWORD), ("threads", w.DWORD), ("parent", w.DWORD), ("priority", w.LONG),
                ("flags", w.DWORD), ("name", w.WCHAR * 260)]


class DifferentImage(ValueError):
    pass


class WatchedProcess:
    """Owns only a query handle to the verified Serato process."""

    def __init__(self, application, candidate, not_before=None):
        self.application = application
        self.pid = candidate["pid"]
        self.k = c.WinDLL("kernel32", use_last_error=True)
        self.adv = c.WinDLL("advapi32", use_last_error=True)
        require(type(self.pid) is int and 0 < self.pid <= 0xffffffff, "Invalid watched process ID")
        for library, name, arguments, result in (
            (self.k, "OpenProcess", [w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            (self.k, "GetCurrentProcess", [], w.HANDLE),
            (self.k, "GetCurrentProcessId", [], w.DWORD),
            (self.k, "ProcessIdToSessionId", [w.DWORD, c.POINTER(w.DWORD)], w.BOOL),
            (self.k, "QueryFullProcessImageNameW", [w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)], w.BOOL),
            (self.k, "GetProcessTimes", [w.HANDLE] + [c.POINTER(w.FILETIME)] * 4, w.BOOL),
            (self.k, "WaitForSingleObject", [w.HANDLE, w.DWORD], w.DWORD),
            (self.k, "CloseHandle", [w.HANDLE], w.BOOL),
            (self.adv, "OpenProcessToken", [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)], w.BOOL),
            (self.adv, "GetTokenInformation", [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)], w.BOOL),
            (self.adv, "EqualSid", [c.c_void_p, c.c_void_p], w.BOOL),
        ):
            function = getattr(library, name)
            function.argtypes, function.restype = arguments, result
        self.handle = self.checked(self.k.OpenProcess(0x101000, False, self.pid))
        try:
            self.verify(candidate, not_before)
        except BaseException:
            self.close()
            raise

    @staticmethod
    def checked(result):
        if not result:
            raise c.WinError(c.get_last_error())
        return result

    def session(self, pid):
        result = w.DWORD()
        self.checked(self.k.ProcessIdToSessionId(pid, c.byref(result)))
        return result.value

    @contextmanager
    def token(self, process):
        token = w.HANDLE()
        self.checked(self.adv.OpenProcessToken(process, 8, c.byref(token)))
        try:
            yield token
        finally:
            self.k.CloseHandle(token)

    def sid_buffer(self, token, kind):
        size = w.DWORD()
        self.adv.GetTokenInformation(token, kind, None, 0, c.byref(size))
        require(c.get_last_error() == 122 and 0 < size.value <= 65536, "Invalid token information size")
        buffer = c.create_string_buffer(size.value)
        self.checked(self.adv.GetTokenInformation(token, kind, buffer, len(buffer), c.byref(size)))
        return buffer

    def verify(self, candidate, not_before):
        session = self.session(self.pid)
        require(session == self.session(self.k.GetCurrentProcessId()) == candidate.get("session", session),
                "Watched Serato belongs to another Windows session")
        image = c.create_unicode_buffer(32768)
        length = w.DWORD(len(image))
        self.checked(self.k.QueryFullProcessImageNameW(self.handle, 0, image, c.byref(length)))
        times = [w.FILETIME() for _ in range(4)]
        self.checked(self.k.GetProcessTimes(self.handle, *(c.byref(value) for value in times)))
        self.created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        creation_matches = (self.created >= not_before if not_before is not None else
                            str(self.created) == candidate["created"])
        if Path(image.value) != self.application:
            raise DifferentImage("Watched Serato path differs")
        require(creation_matches and not self.wait(0), "Watched Serato creation time differs or process has exited")
        with self.token(self.k.GetCurrentProcess()) as current, self.token(self.handle) as target:
            for kind in (1, 25):  # TokenUser and TokenIntegrityLevel both start with a SID pointer.
                left, right = self.sid_buffer(current, kind), self.sid_buffer(target, kind)
                left_sid = c.cast(left, c.POINTER(c.c_void_p))[0]
                right_sid = c.cast(right, c.POINTER(c.c_void_p))[0]
                require(self.adv.EqualSid(left_sid, right_sid), "Watched Serato user or integrity level differs")
        self.identity = {"pid": self.pid, "created": str(self.created), "session": session}

    def wait(self, seconds):
        result = self.k.WaitForSingleObject(self.handle, int(seconds * 1000))
        require(result in (0, 258), "Watched Serato wait failed")
        return result == 0

    def close(self):
        self.k.CloseHandle(self.handle)


class ProcessWatcher:
    def __init__(self, application):
        self.application = application
        self.not_before = time.time_ns() // 100 + WINDOWS_EPOCH
        self.active = None
        self.k = c.WinDLL("kernel32", use_last_error=True)
        for name, arguments, result in (
            ("CreateToolhelp32Snapshot", [w.DWORD, w.DWORD], w.HANDLE),
            ("Process32FirstW", [w.HANDLE, c.POINTER(ProcessEntry)], w.BOOL),
            ("Process32NextW", [w.HANDLE, c.POINTER(ProcessEntry)], w.BOOL),
            ("ProcessIdToSessionId", [w.DWORD, c.POINTER(w.DWORD)], w.BOOL),
            ("GetCurrentProcessId", [], w.DWORD),
            ("GetCurrentProcess", [], w.HANDLE),
            ("DuplicateHandle", [w.HANDLE, w.HANDLE, w.HANDLE, c.POINTER(w.HANDLE), w.DWORD, w.BOOL, w.DWORD], w.BOOL),
            ("WaitForSingleObject", [w.HANDLE, w.DWORD], w.DWORD),
            ("CloseHandle", [w.HANDLE], w.BOOL),
        ):
            function = getattr(self.k, name)
            function.argtypes, function.restype = arguments, result
        self.session = w.DWORD()
        WatchedProcess.checked(self.k.ProcessIdToSessionId(self.k.GetCurrentProcessId(), c.byref(self.session)))

    def candidates(self):
        snapshot = self.k.CreateToolhelp32Snapshot(2, 0)
        require(snapshot != c.c_void_p(-1).value, "Process inventory unavailable")
        try:
            row = ProcessEntry()
            row.size = c.sizeof(row)
            WatchedProcess.checked(self.k.Process32FirstW(snapshot, c.byref(row)))
            candidates = []
            while True:
                if row.name.casefold() == self.application.name.casefold():
                    session = w.DWORD()
                    if self.k.ProcessIdToSessionId(row.pid, c.byref(session)) and session.value == self.session.value:
                        candidates.append(row.pid)
                if not self.k.Process32NextW(snapshot, c.byref(row)):
                    require(c.get_last_error() == 18, "Process inventory was incomplete")
                    return candidates
        finally:
            self.k.CloseHandle(snapshot)

    def next_launch(self, timeout, keep_running=None):
        deadline = time.monotonic() + timeout if timeout is not None else None
        while (deadline is None or time.monotonic() < deadline) and (keep_running is None or keep_running()):
            if self.active is not None:
                status = self.k.WaitForSingleObject(self.active, 100)
                require(status in (0, 258), "Watcher process-exit wait failed")
                if status == 258:
                    continue
                self.close()
            process = self.sole_verified_process()
            if process is not None:
                try:
                    current = self.k.GetCurrentProcess()
                    wait_handle = w.HANDLE()
                    WatchedProcess.checked(self.k.DuplicateHandle(current, process.handle, current,
                                                                  c.byref(wait_handle), 0x100000, False, 0))
                    self.active = wait_handle.value
                    if process.created >= self.not_before:
                        self.not_before = process.created + 1
                        return process
                except BaseException:
                    process.close()
                    raise
                process.close()
                continue
            time.sleep(.1)
        return None

    def sole_verified_process(self):
        processes = []
        try:
            for pid in self.candidates():
                try:
                    processes.append(WatchedProcess(self.application, {"pid": pid}, not_before=0))
                except DifferentImage:
                    continue
                except (OSError, ValueError):
                    return None  # The candidate could be an exact image whose identity is unavailable.
                if len(processes) > 1:
                    return None
            return processes.pop() if processes else None
        finally:
            for process in processes:
                process.close()

    def close(self):
        if self.active is not None:
            self.k.CloseHandle(self.active)
            self.active = None


def run(plan_path, expected, output, reopen_output=None, device_required=False, observe_seconds=None,
        notice_selection=False, registration=None):
    require(c.sizeof(c.c_void_p) == 8 and not c.windll.shell32.IsUserAnAdmin(), "Use ordinary-user 64-bit Python")
    require(observe_seconds is None or (type(observe_seconds) is int and 1 <= observe_seconds <= 600 and
                                       device_required and reopen_output is None),
            "Resident rehearsal needs --device-required, 1–600 seconds and a single output")
    with watcher_lease():
        return watch_launches(plan_path, expected, output, reopen_output, device_required, observe_seconds,
                              notice_selection, registration)


def watch_launches(plan_path, expected, output, reopen_output, device_required, observe_seconds, notice_selection,
                   registration):
    if registration is not None:
        require(device_required and notice_selection and reopen_output is None and observe_seconds is None and
                registration.owns(), "The exact watcher sign-in command is required")
    outputs = (output, reopen_output) if reopen_output else (output,)
    require(len({path.resolve() for path in outputs}) == len(outputs) and all(
            path.parent.resolve() == (ROOT / "analysis").resolve() and not path.exists() for path in outputs),
            "Distinct fresh private analysis outputs are required")
    plan = TRIAL["read_plan"](plan_path, expected)
    notice_api = TRIAL["NOTICE"]
    notice_sha = plan["noticeLibrarySha256"]
    require(not notice_selection or notice_sha == notice_api["RETIRING_HELPER_SHA"],
            "The watcher requires a startup plan for the self-restoring notice helper")
    application = Path(os.environ["ProgramFiles"]) / "Serato/Serato DJ Pro/Serato DJ Pro.exe"
    archive = application.with_name("userio_resources.bin")
    logs = Path(os.environ["USERPROFILE"]) / "Music/_Serato_/Logs"

    def hashes():
        return {"application": digest(application), "archive": digest(archive), "library": digest(LIBRARY)}

    before = hashes()
    require(before == {"application": plan["applicationSha256"], "archive": plan["archiveSha256"],
                       "library": plan["librarySha256"]} and
            not any(path.is_symlink() or path.parent.is_junction() for path in (application, archive, LIBRARY)),
            "Original installation and reviewed native library are required")
    readiness = runpy.run_path(str(HERE / "inspect-sl3-session-readiness.py"))
    watchers = PROBE["watcher_state"]()
    if registration is None:
        PROBE["require_watcher_state"](watchers, False, require)
    else:
        require(watchers["registered"] and watchers["running"] == 0 and registration.owns(),
                "Expected the exact sign-in command and no other SL3 watcher")
    stage = Path(os.environ["ProgramFiles"]) / "SL3 Rebuild"
    native = PROBE["driver"]() if device_required else None
    require((native is not None and native.manifest.get("outputReadyTrial") is True) or
            not (stage / "output-ready-trial-v1").exists(), "Remove the output-ready trial before the watcher rehearsal")
    device_admission = None
    broker_readout = None
    if device_required:
        stage_before = native.observe()
        require(stage_before["state"] in ("absent", "installed"), "Expected the reviewed driver stage or clean setup")
        require(registration is None or stage_before["state"] == "installed", "Sign-in watcher requires the reviewed driver stage")
        transport = PROBE["transport_state"]() if stage_before["state"] == "installed" else None
        if transport is not None:
            local_appdata = native.s.known_folder("f1b32785-6fba-4fcf-9d55-7b8e7f157091")

            def broker_readout(process):
                return PROBE["broker_evidence_for_process"](native.destination, local_appdata, process.pid,
                                                           process.identity["created"],
                                                           expected_frames=native.manifest["diagnosticBufferFrames"])

        def device_admission():
            presence = readiness["sl3_presence"]()
            if presence["matchingPresentIdentities"] == 0:
                return False
            require(transport is not None and native.observe() == stage_before,
                    "The reviewed driver stage must be installed before watching a connected SL3")
            PROBE["require_connected_transport"]({**transport, "sl3": presence}, require)
            return True
    else:
        require(readiness["sl3_presence"]()["matchingPresentIdentities"] == 0, "Unplug the SL3 for this watcher rehearsal")
        require(not (stage / "on-demand-diagnostic-v1").exists(), "Remove the diagnostic driver before the watcher rehearsal")
    profile = PROBE["reviewed_profile"](before["application"], require)
    keep_running = registration.owns if registration is not None else None

    def observe(process, report_path):
        def prepare_notice():
            if not device_required:
                require(readiness["sl3_presence"]()["matchingPresentIdentities"] == 0,
                        "Keep the SL3 unplugged during the offline notice rehearsal")
            return notice_api["OwnedNoticePoll"](report_path, notice_sha)

        return observe_launch(process, profile, plan, logs, hashes, before, expected, watchers, device_admission,
                              prepare_notice if notice_selection else None, broker_readout, keep_running)

    with closing(ProcessWatcher(application)) as detector:
        if observe_seconds is not None or registration is not None:
            ready = registration.ready(expected) if registration is not None else nullcontext()
            with output.open("x", encoding="utf-8") as stream, ready:
                deadline = time.monotonic() + observe_seconds if observe_seconds is not None else None
                failed = False
                print("watcher_ready", flush=True)
                while True:
                    remaining = deadline - time.monotonic() if deadline is not None else None
                    process = detector.next_launch(remaining, keep_running)
                    if process is None:
                        break
                    report_path = output.with_name(f"{output.stem}-{process.pid}-{process.created}{output.suffix}")
                    report = observe(process, report_path)
                    stream.write(json.dumps(report) + "\n")
                    stream.flush()
                    if not report["inputsUnchanged"]:
                        return 1
                    failed |= bool(report["failure"]) or not report["processStillRunning"]
            return int(failed)

        for index, report_path in enumerate(outputs):
            print("watcher_ready" if index == 0 else "watcher_ready_for_reopen", flush=True)
            report = observe(detector.next_launch(60), report_path)
            with report_path.open("x", encoding="utf-8") as stream:
                json.dump(report, stream, indent=2)
                stream.write("\n")
            print(json.dumps({key: value for key, value in report.items() if key != "primaryRegistry"}, indent=2))
            if report["failure"] or not report["inputsUnchanged"] or not report["processStillRunning"]:
                return 1
    return 0


def observe_launch(process, profile, plan, logs, hashes, before, expected, watchers, device_admission, prepare_notice,
                   broker_readout, keep_running=None):
    report = {"before": before, "preparedStartupPlanSha256": expected, "watchersAtPreflight": watchers,
              "failure": None, "fridaAgentUsed": False, "processStillRunning": False}
    try:
        require(process is not None, "No fresh verified Serato launch appeared in the observation window")
        with closing(process):
            age = (time.time_ns() // 100 + WINDOWS_EPOCH - process.created) / 10_000_000
            require(0 <= age <= 4, "The watched process is outside the startup window")
            created_wall_time = (process.created - WINDOWS_EPOCH) / 10_000_000
            launch_clock = time.monotonic() - age
            report["process"] = process.identity
            report["userAndIntegrityVerified"] = True
            require(not process.wait(max(0, 2.5 - age)), "Watched Serato exited during startup")
            connected = device_admission is not None
            if connected and not device_admission():
                report["outcome"] = "skipped_sl3_absent"
            else:
                require(hashes() == before, "Reviewed inputs changed before native loading")
                require(keep_running is None or keep_running(), "Watcher sign-in command was withdrawn")
                notice = prepare_notice() if prepare_notice else None
                try:
                    require(time.monotonic() - launch_clock <= 4, "Admission exceeded the startup window")
                    require(keep_running is None or keep_running(), "Watcher sign-in command was withdrawn")
                    with closing(TRIAL["OwnedLoader"](process, process.identity["created"])) as loader:
                        TRIAL["exercise"](loader, profile, plan, logs, created_wall_time, launch_clock, report,
                                          connected, notice, keep_running)
                finally:
                    if notice is not None:
                        notice.close(process)
                        report["ownedNotice"] = notice.report()
                    if broker_readout is not None:
                        report["brokerAtObservation"] = broker_readout(process)
                report["outcome"] = "descriptor_registered"
            report["processStillRunning"] = not process.wait(0)
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        report["failure"] = str(error)
    for key in tuple(report):
        if key.endswith("AfterShortcutMs"):
            report[key.replace("AfterShortcutMs", "AfterProcessCreationMs")] = report.pop(key)
    report["after"] = hashes()
    report["inputsUnchanged"] = report["after"] == before
    return report


def run_registered(expected):
    registration = SignInRegistration(ROOT)
    require(Path(sys.executable) == registration.python, "Start the watcher through its bundled Python window launcher")
    if not registration.owns():
        return 0
    reports = ROOT / "analysis"
    reports.mkdir(exist_ok=True)
    require(not reports.is_symlink() and not reports.is_junction(), "Ordinary watcher report directory required")
    output = reports / f"watch-{time.time_ns()}-{os.getpid()}.jsonl"
    return run(TRIAL["PACKAGED_PLAN"], expected, output, device_required=True, notice_selection=True,
               registration=registration)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--startup-plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reopen-output", type=Path, help="Wait for a second fresh Serato launch in the same watcher")
    parser.add_argument("--device-required", action="store_true", help="Skip launches without the SL3")
    parser.add_argument("--observe-seconds", type=int, help="Bounded resident rehearsal with one JSON record per launch")
    parser.add_argument("--notice-selection", action="store_true", help="Arm the reviewed self-restoring notice helper")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{64}", args.expected_plan_sha256):
        parser.error("Expected a lowercase startup plan SHA-256")
    try:
        reopen = args.reopen_output.absolute() if args.reopen_output else None
        raise SystemExit(run(args.startup_plan.absolute(), args.expected_plan_sha256, args.output.absolute(), reopen,
                             device_required=args.device_required, observe_seconds=args.observe_seconds,
                             notice_selection=args.notice_selection))
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        parser.exit(1, f"{error}\n")
