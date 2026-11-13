"""Run one bounded Serato registration probe using the reviewed local-only runtime."""
import argparse
from contextlib import closing
import ctypes
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import runpy
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUNTIME = ROOT / "artifacts/build/embedded-python-local-frida-descriptor-20261109"
RUNTIME_SHA = "f11669fa63baa4c6d8fc167061f41cb369044e90624e70763d5ca7137b31c386"
FALLBACK = ROOT / "artifacts/build/SL3-Private-Serato5-64-Frame-20261108.zip"
FALLBACK_SHA = "02e9eecdf3cc91515b19b0d09509b5cc159408545e26571c696b3479c09011a0"
DESKTOP_SHORTCUT_SHA = "05817c714478cb5c7801b3a701ceca33211b34a9655312da6dc433fba73d8e1c"
PAIR_EXCHANGE = ROOT / "artifacts/build/native-descriptor-pair-20261110/Release/sl3_descriptor_pair.dll"
PAIR_EXCHANGE_SHA = "a6d92a5b799c34db662d35934d2ddd52ab24a7f4e6023f793a19cf4eaae22c94"
ENTRY_READER = PAIR_EXCHANGE.with_name("sl3_descriptor_reader.dll")
ENTRY_READER_SHA = "092f541de06f5e6cad55a8e6c737142aea1d4800d0d490ce73f6ec58f336bd7e"
NATIVE_FACTORY = PAIR_EXCHANGE.with_name("sl3_descriptor_factory.dll")
NATIVE_FACTORY_SHA = "d3c979e5c09cb49e235dc6fd9c663ecb95f468f1e66b1f1ec5d7af36485d97d8"
NATIVE_HOOK_LIBRARY = ROOT / "artifacts/build/native-descriptor-hooks-20261110/Release/sl3_descriptor_hook_library.dll"
NATIVE_HOOK_LIBRARY_SHA = "e813aa1d102ff02176057051414d6c100daba38c4a69ed79f5b862aa0c5636e0"
DRIVER_BUNDLE = ROOT / "artifacts/build/deployment-bundles/worker-loopback-64-20261108"
DRIVER_BUNDLE_SHA = "141eed009b4bd0db4eeb98e53e182f78dd652d8ac8919305b0a2256ba127d733"
APPLICATION_LIFETIME_BUNDLE = ROOT / "artifacts/build/deployment-bundles/beta64-application-lifetime-20261108"
APPLICATION_LIFETIME_BUNDLE_SHA = "3bc4de178fe88dec35a6ad34b57b5d34cc08c8024b6332cb472289ff8cde6aa9"
DIAGNOSTIC_32_BUNDLE = ROOT / "artifacts/build/deployment-bundles/worker-recovery-context-32-20261110"
DIAGNOSTIC_32_BUNDLE_SHA = "c8c64b68d9982db7ea17e14260d4474ccfa171afd254318b1543180fb75611e8"
OUTPUT_DEADLINE_BUNDLES = {
    32: (ROOT / "artifacts/build/deployment-bundles/worker-output-deadline-32-20261110",
         "fe9f5237de72863b844ac661307a8ca2d438a7718ed4bc660ffd78ab502d54de"),
    64: (ROOT / "artifacts/build/deployment-bundles/worker-output-deadline-64-20261110",
         "ce4d61283abc2d970c128934bc33df88a37d61ed6931e90f53d32b7ef089ba5d"),
}
OUTPUT_READY_BUNDLE = ROOT / "artifacts/build/deployment-bundles/output-ready-trial-64-20261110"
OUTPUT_READY_BUNDLE_SHA = "958b39c9da2136f8cfaa0a899a5aac2954de1510af079bd35105c7fe3f7cb306"
ASIO_CALLBACK_PROBE = ROOT / "artifacts/build/native-callback-signalled-20261110/Release/sl3_input_record_probe.exe"
ASIO_CALLBACK_PROBE_SHA = "5abd24777a8f1b227bf764604895c0ab3ac67b8120f5f614e3dfba245d6166a0"
WATCHER = ROOT / "artifacts/build/native-setup-window-latency-64-playback-20261108/build/Release/watcher"
WATCHER_PINS = {
    "watch-notice-startup.ps1": "a65a266eed1b05e5771a6d555a68fc32204e22cfd389f7e64200b8914512a5d0",
    "sl3-notice-startup-early.dll": "2550e2c4682a0599dc5903069db6094f796a76f959a9073334931fc2e9199ad1",
}
SL3_IDENTITY = [0x1cc5, 1, 0]
PROFILE_SHA = "a76d22478a173c13fdba339106461271e94fb1c7479d262b3f852799c951574e"
# Relative order of the project fields in the live-tested 5.0.0.1278 descriptor.
DEVICE_ORDER = (
    "vendor_id", "product_id", "requires_usb", "handshake_type", "secret_key",
    "output_calibration_gain", "braking_type", "use_legacy_portaudio", "win_audio_api",
    "mac_audio_api", "win_audio_device_name", "mac_audio_device_name", "sample_rate",
    "buffer_alignments", "driver", "num_decks", "dvs_device", "hardware_mixer",
    "output_endpoints", "input_endpoint", "record_sources", "software_mic_gain",
    "software_cue_gain", "software_cf_curve", "software_uf_curve", "software_cue_mix",
    "cue_crossfader_type", "software_master_cue", "software_split_cue",
    "software_crossfader_reverse", "provides_talk_over", "midi_direction", "has_hid",
)


def reviewed_xml():
    recipe = runpy.run_path(str(HERE / "prepare-serato-installed-phase-archive.py"))
    candidate = runpy.run_path(str(HERE / "prepare-serato-sl3-archive.py"))["c"]
    history = candidate.read(ROOT / recipe["HISTORY"])
    candidate.require(candidate.digest(history) == candidate.HISTORY_SHA, "Reviewed historical specification evidence required")
    targets = candidate.parsed(history)["targets"]
    xml = recipe["serialize_phase_descriptor"](candidate, targets[0], DEVICE_ORDER)
    return xml.decode("utf-8")


def reviewed_profile(executable_sha, require):
    raw = (HERE / "serato-memory-descriptor-profile.json").read_text(encoding="utf-8")
    require(hashlib.sha256(raw.encode("utf-8")).hexdigest() == PROFILE_SHA, "Reviewed probe profile required")
    profile = json.loads(raw)
    require(profile["executableSha256"] == executable_sha, "Probe profile does not match the Serato executable")
    return profile


def windows_state(require):
    shell = system_powershell()
    check = (
        "$env:PSModulePath = $PSHOME + '\\Modules'; "
        "$ErrorActionPreference='Stop'; "
        "if(Get-Process -Name 'Serato DJ Pro','sl3_usbdk','sl3_broker_controller' -ErrorAction SilentlyContinue){exit 32}; "
        "if(Get-PnpDevice -PresentOnly | Where-Object InstanceId -Like 'USB\\VID_1CC5&PID_0001*'){exit 31}"
    )
    outcome = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-Command", check],
                             capture_output=True, timeout=25, creationflags=subprocess.CREATE_NO_WINDOW)
    require(outcome.returncode in (0, 31), f"Idle Windows preflight failed ({outcome.returncode})")
    return outcome.returncode == 31


def system_powershell():
    path = ctypes.create_unicode_buffer(32768)
    count = ctypes.windll.kernel32.GetSystemDirectoryW(path, len(path))
    if not 0 < count < len(path):
        raise OSError("Could not locate Windows PowerShell")
    return Path(path.value) / "WindowsPowerShell/v1.0/powershell.exe"


def watcher_state():
    shell = system_powershell()
    query = r"""
$env:PSModulePath = $PSHOME + '\Modules'
$ErrorActionPreference = 'Stop'
$run = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$registered = (Test-Path -LiteralPath $run) -and
    ((Get-Item -LiteralPath $run).GetValueNames() -contains 'SL3CompatibilityWatcher')
$session = (Get-Process -Id $PID).SessionId
$fileOption = '^\s*(?:"[^"]+"|\S+)(?:\s+-(?:NoLogo|NoProfile|NonInteractive|NoExit|Sta|Mta|WindowStyle\s+\w+|ExecutionPolicy\s+\w+))*\s+-File\s+'
$watcherName = '(?:"(?:[^"]*[\\/])?watch-notice-startup\.ps1"|(?:[^\s"]*[\\/])?watch-notice-startup\.ps1)(?:\s|$)'
$watchers = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" |
    Where-Object { $_.SessionId -eq $session -and $_.CommandLine -match ($fileOption + $watcherName) })
$expected = [regex]::Escape($env:SL3_PROBE_TEMP_WATCHER)
$temporary = @($watchers | Where-Object {
    $_.CommandLine -match ($fileOption + ('(?:"{0}"|{0})\s*$' -f $expected))
})
@{registered = $registered; running = $watchers.Count; reviewedTemporary = $temporary.Count} |
    ConvertTo-Json -Compress
"""
    environment = {**os.environ, "SL3_PROBE_TEMP_WATCHER": str(WATCHER / "watch-notice-startup.ps1")}
    outcome = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-Command", query], env=environment,
                             capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    if outcome.returncode != 0:
        raise ValueError(f"Could not verify the Windows watcher state ({outcome.returncode})")
    return json.loads(outcome.stdout)


def require_watcher_state(state, paired, require):
    require(state["registered"] is False, "Restore the installed SL3 sign-in watcher before this test")
    if paired:
        require(state["running"] == state["reviewedTemporary"] == 1,
                "Expected exactly one reviewed temporary watcher and no other watcher")
    else:
        require(state["running"] == 0, "Stop the temporary SL3 watcher before this test")


def transport_state():
    import winreg

    readiness = runpy.run_path(str(HERE / "inspect-sl3-session-readiness.py"))
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\SecureBoot\State") as key:
            secure_boot, kind = winreg.QueryValueEx(key, "UEFISecureBootEnabled")
        secure_boot_enabled = kind == winreg.REG_DWORD and secure_boot == 1
    except FileNotFoundError:
        secure_boot_enabled = False
    shell = system_powershell()
    policy = subprocess.run(
        [str(shell), "-NoProfile", "-NonInteractive", "-Command",
         "$env:PSModulePath = $PSHOME + '\\Modules'; $ErrorActionPreference='Stop'; "
         "(Get-CimInstance -Namespace root/Microsoft/Windows/DeviceGuard -ClassName Win32_DeviceGuard)"
         ".CodeIntegrityPolicyEnforcementStatus"],
        capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    value = policy.stdout.strip()
    code_integrity = int(value) if policy.returncode == 0 and value in (b"0", b"1", b"2") else None
    return {
        "secureBootEnabled": secure_boot_enabled,
        "codeIntegrityPolicy": code_integrity,
        "usbDk": readiness["driver_state"](),
        "sl3": readiness["sl3_presence"](),
    }


def require_connected_transport(state, require):
    require(state["secureBootEnabled"] and state["codeIntegrityPolicy"] == 2,
            "Secure Boot and enforced Windows code integrity could not be verified")
    require(state["usbDk"]["running"] and state["usbDk"]["reviewedImageOnDisk"],
            "Expected the running UsbDk service with its reviewed driver image")
    require(state["sl3"]["matchingPresentIdentities"] == 1, "Expected exactly one present SL3 USB device")


def driver(output_ready_trial=None, application_lifetime=None, buffer_frames=None, output_deadline_trial=None):
    api = runpy.run_path(str(HERE / "serato-on-demand-test.py"))
    payload_path = ROOT / "watcher-payload.json"
    payload = json.loads(payload_path.read_bytes()) if payload_path.is_file() else {}
    if output_ready_trial is None:
        output_ready_trial = payload.get("outputReadyTrial", False)
    if application_lifetime is None:
        application_lifetime = payload.get("applicationLifetime", False)
    if buffer_frames is None:
        buffer_frames = payload.get("diagnosticBufferFrames", 64)
    if output_deadline_trial is None:
        output_deadline_trial = payload.get("outputDeadlineTrial", False)
    if (type(application_lifetime) is not bool or type(output_ready_trial) is not bool or
            type(output_deadline_trial) is not bool or
            type(buffer_frames) is not int or buffer_frames not in (32, 64) or
            sum((application_lifetime, output_ready_trial, output_deadline_trial)) > 1 or
            (buffer_frames == 32 and (application_lifetime or output_ready_trial))):
        raise ValueError("Select one reviewed driver profile")
    if output_ready_trial:
        bundle, expected = OUTPUT_READY_BUNDLE, OUTPUT_READY_BUNDLE_SHA
    elif application_lifetime:
        bundle, expected = APPLICATION_LIFETIME_BUNDLE, APPLICATION_LIFETIME_BUNDLE_SHA
    elif output_deadline_trial:
        bundle, expected = OUTPUT_DEADLINE_BUNDLES[buffer_frames]
    elif buffer_frames == 32:
        bundle, expected = DIAGNOSTIC_32_BUNDLE, DIAGNOSTIC_32_BUNDLE_SHA
    else:
        bundle, expected = DRIVER_BUNDLE, DRIVER_BUNDLE_SHA
    return api["Native"](bundle, expected)


def serato_file_state(application, session):
    def matches(path, expected):
        try:
            return not path.is_symlink() and path.is_file() and session["digest"](path) == expected
        except OSError:
            return False

    return {"applicationReviewed": matches(application, session["APP_SHA"]),
            "archiveOriginal": matches(application.with_name("userio_resources.bin"), session["ORIGINAL_RESOURCES"])}


def driver_stage(action, output_ready_trial=None):
    session = runpy.run_path(str(HERE / "run-serato-startup-session.py"))
    require = session["require"]
    connected = windows_state(require)
    native = driver(output_ready_trial)
    program_files = native.s.known_folder("905e63b6-c1bf-494e-b29c-65b732d3d21a")
    application = program_files / "Serato/Serato DJ Pro/Serato DJ Pro.exe"
    files = serato_file_state(application, session)
    if action == "install":
        require(all(files.values()), "Original Serato files required to install")
    native.check_action_dependencies()
    before = native.observe()
    watchers = watcher_state()
    report = {"schema": "sl3.native-watcher-driver-stage.v1", "action": action, "sl3Present": connected, "before": before,
              "actionDependenciesVerified": True,
              "bundleSha256": native.expected, "applicationLifetime": native.manifest.get("applicationLifetime", False),
              "diagnosticBufferFrames": native.manifest["diagnosticBufferFrames"],
              "outputReadyTrial": native.manifest.get("outputReadyTrial", False),
              "watchers": watchers, **files}
    if action in ("plan", "install"):
        report["transport"] = transport_state()
    if action != "plan":
        require(ctypes.windll.shell32.IsUserAnAdmin(), "Use an administrator terminal for this driver stage action")
        require_watcher_state(watchers, False, require)
        native.require_idle()
        try:
            if action == "install":
                require(connected and before["state"] == "absent", "Connect the SL3 and restore any existing driver stage")
                require_connected_transport(report["transport"], require)
                report["transaction"] = native.install()
            elif before["state"] in ("installed", "unregistered"):
                report["transaction"] = native.remove(before["stageRecordSha256"])
            else:
                require(before["state"] == "absent", "Driver ownership could not be verified for removal")
        finally:
            report["after"] = native.observe()
            report.update(serato_file_state(application, session))
            print(json.dumps(report, indent=2))
        require(report["after"]["state"] == ("installed" if action == "install" else "absent") and
                (action != "install" or (report["applicationReviewed"] and report["archiveOriginal"])),
                "Driver stage or original Serato verification failed")
    else:
        print(json.dumps({**report, "after": before}, indent=2))


def offline_log(folder, pid, since):
    logs = [path for path in folder.glob(f"*.{pid}.log") if path.stat().st_birthtime >= since - 1]
    if len(logs) != 1:
        return None
    limit = 512 * 1024
    complete = True
    with logs[0].open("rb") as stream:
        contents = stream.read(limit)
        if len(contents) == limit:
            end = stream.seek(0, os.SEEK_END)
            tail = max(limit, end - limit)
            if tail > limit:
                complete = False
                contents = contents.rpartition(b"\n")[0] + b"\n"
                stream.seek(tail - 1)
                starts_at_line = stream.read(1) == b"\n"
            else:
                stream.seek(tail)
                starts_at_line = True
            suffix = stream.read(limit)
            contents += suffix if starts_at_line else suffix.partition(b"\n")[2]
    rows = contents.splitlines()
    markers = {
        b"On shutdown stage kExitYes": "exit_confirmed",
        b"On shutdown stage kRunAsyncOperationsForExit": "async_exit_started",
        b"On shutdown stage kRunAsyncOperationsForExitCompleted": "async_exit_completed",
    }
    stages = dict.fromkeys(stage for row in rows for marker, stage in markers.items() if row.rstrip().endswith(marker))
    sl3_start = re.compile(rb"^I\d{8} \d\d:\d\d:\d\d\.\d{6} \d+ :\d+\] \[Device\] "
                           rb"Audio connection, start succeeded\. Device: Rane SL3, "
                           rb"latency: (\d{1,6}(?:\.\d{1,9})?), buffer size: ([1-9]\d{0,5}), sample rate: (\d{4,6})$")
    sl3_starts = [match for row in rows if (match := sl3_start.fullmatch(row))]
    last = sl3_starts[-1] if sl3_starts else None
    return {
        "file": logs[0].name,
        "offlineAudioStarted": b"Audio connection, start succeeded. Device: Offline Device" in contents,
        "sl3AudioStartCount": len(sl3_starts),
        "lastSl3AudioStart": {"latencyMs": float(last[1]), "applicationBufferFrames": int(last[2]),
                              "sampleRateHz": int(last[3])} if last else None,
        "mainThreadHangReported": any(b"Hang Detected" in row and b"Main Thread" in row for row in rows),
        "shutdownPhaseReported": b"Application phase set to Shutdown" in contents,
        "shutdownStages": list(stages),
        "logReadComplete": complete,
    }


def notice_log(cleanup):
    created = cleanup.get("processFileTimes", {}).get("first")
    pid = cleanup.get("pid")
    if not pid or not created:
        return None
    path = WATCHER / f"notice-hook-{pid}-{created}.log"
    if not path.is_file():
        return None
    with path.open("rb") as stream:
        raw = stream.read(4097)
    if len(raw) > 4096:
        return {"error": "Notice helper log exceeds the expected size"}
    return {"file": path.name, "events": raw.decode("ascii", errors="replace").splitlines()}


def output_ready_summaries(trace, first, last):
    if not (trace["sessionMetadataComplete"] and trace["observedPairsComplete"] and
            trace["actualEtwCaptureDecoded"] and trace["build"] == "production"):
        raise ValueError("Complete production trace required for an output-ready result")
    if trace.get("moduleCallBudgetReached") is not False:
        raise ValueError("Output-ready trace may have ended at the call budget")
    span = trace["eventFileTimeRange"]
    if not first <= int(span["first"]) <= int(span["last"]) <= last:
        raise ValueError("Trace timestamps fall outside the owned Serato process lifetime")
    starts, stops, summaries = {}, {}, []
    for call in sorted(trace["pairs"], key=lambda pair: pair["terminalRecord"]):
        device, operation = call["object"], call["operation"]
        if operation == "start" and call["rawResult"] == 0:
            if device in starts or device in stops:
                raise ValueError("Successful start lacks the previous output-ready retirement")
            starts[device] = call["call"]
        elif operation == "stop":
            if device in stops:
                raise ValueError("Repeated Stop precedes the output-ready summary")
            if device in starts:
                stops[device] = (starts.pop(device), call)
        elif operation == "output_ready_summary":
            if device not in stops:
                raise ValueError("Output-ready summary lacks an observed start and stop")
            start, stop = stops.pop(device)
            if (call["thread"] != stop["thread"] or call["rawResult"] != stop["rawResult"] or
                    call["beginRecord"] <= stop["terminalRecord"]):
                raise ValueError("Output-ready summary does not match its Stop call")
            blocks, missed = call["argument0"], call["argument1"]
            if type(blocks) is not int or type(missed) is not int or not 0 <= missed <= blocks < 2**63:
                raise ValueError("Invalid output-ready block counts")
            summaries.append({"object": device, "startCall": start, "stopCall": stop["call"],
                              "stopResult": stop["rawResult"], "blocks": blocks, "missedSignals": missed,
                              "audioSecondsAt64Frames44100Hz": blocks * 64 / 44100})
    if starts or stops:
        raise ValueError("Trace ended before a successful start had its output-ready summary")
    return summaries


def owned_asio_trace_folders(local_appdata, pid, first, last):
    root = local_appdata / "SL3Rebuild/AsioTraces"
    for path in (local_appdata, root.parent, root):
        if path.is_symlink() or path.is_junction():
            raise ValueError("Unexpected reparse point in the ASIO trace path")
    pattern = re.compile(rf"run-{pid}-\{{[0-9a-f]{{8}}(?:-[0-9a-f]{{4}}){{3}}-[0-9a-f]{{12}}\}}", re.IGNORECASE)
    records = []
    for path in sorted(root.glob(f"run-{pid}-*")):
        if not pattern.fullmatch(path.name):
            continue
        if path.is_symlink() or path.is_junction():
            raise ValueError("Unexpected reparse point in an ASIO trace session")
        created = path.stat().st_birthtime_ns // 100 + 116444736000000000
        if path.is_dir() and first <= created <= last:
            records.append(path)
            if len(records) > 4:
                raise ValueError("Owned process trace session limit exceeded")
    return records


def output_ready_evidence(local_appdata, cleanup, output):
    times = cleanup.get("processFileTimes")
    if (not times or not cleanup.get("processExited") or cleanup.get("observerForcedTermination") or
            cleanup.get("exitCode") != 0):
        return {"outcome": "normal_host_exit_unverified"}
    pid = cleanup["pid"]
    first, last = int(times["first"]), int(times["last"])
    records, summaries = [], []
    try:
        records = owned_asio_trace_folders(local_appdata, pid, first, last)
        if not records:
            return {"outcome": "private_trace_absent"}
        decode = runpy.run_path(str(HERE / "analyse-asio-call-log.py"))["decode"]
        for number, folder in enumerate(records, 1):
            destination = output.with_name(f"{output.stem}-asio-{number}")
            trace = decode(folder / "private.etl", folder / "session.json", destination, expected_pid=pid)
            summaries.extend({"trace": destination.name, **item} for item in output_ready_summaries(trace, first, last))
    except (OSError, KeyError, ValueError) as error:
        return {"outcome": "output_ready_trace_unverified", "error": str(error), "sessionsFound": len(records)}
    outcome = "output_ready_summary_absent"
    if summaries:
        if any(item["stopResult"] for item in summaries):
            outcome = "stop_failure_observed"
        elif any(item["missedSignals"] for item in summaries):
            outcome = "retired_streams_with_missed_signals"
        elif all(item["blocks"] > 0 for item in summaries):
            outcome = "retired_streams_observed"
        else:
            outcome = "no_blocks_observed"
    return {"outcome": outcome, "summaries": summaries, "sessionsDecoded": len(records)}


def asio_control_summary(trace, pid, first, last):
    if not trace["actualEtwCaptureDecoded"] or trace["pid"] != pid:
        raise ValueError("An actual decoded trace from the owned PID is required")
    span = trace["eventFileTimeRange"]
    if trace["recordCount"] and (trace["build"] != "production" or
            not first <= int(span["first"]) <= int(span["last"]) <= last):
        raise ValueError("ASIO trace does not match the owned production process lifetime")
    operations = {"start", "stop", "dispose_buffers"}
    fields = ("call", "operation", "object", "thread", "phase", "rawResult")
    return {"records": trace["recordCount"], "loggerCompleted": trace["sessionMetadataComplete"],
            "observedPairsComplete": trace["observedPairsComplete"], "traceBudgetReached": trace["moduleCallBudgetReached"],
            "streamCalls": [{key: pair[key] for key in fields} for pair in trace["pairs"]
                            if pair["operation"] in operations],
            "unterminatedCalls": trace["unterminatedBegins"],
            "unterminatedCallDetails": trace.get("unterminatedBeginDetails", []),
            "orphanTerminals": trace["orphanTerminals"]}


def asio_control_evidence(local_appdata, cleanup, output):
    times = cleanup.get("processFileTimes")
    if not cleanup.get("processExited") or not times:
        return {"outcome": "host_exit_identity_unavailable"}
    pid = cleanup["pid"]
    first, last = int(times["first"]), int(times["last"])
    sessions = []
    try:
        folders = owned_asio_trace_folders(local_appdata, pid, first, last)
        if not folders:
            return {"outcome": "private_trace_absent"}
        decode = runpy.run_path(str(HERE / "analyse-asio-call-log.py"))["decode"]
        incomplete = runpy.run_path(str(HERE / "inspect-incomplete-asio-call-log.py"))["inspect"]
        for number, folder in enumerate(folders, 1):
            destination = output.with_name(f"{output.stem}-asio-control-{number}")
            etl, marker = folder / "private.etl", folder / "session.json"
            session = {"trace": destination.name}
            try:
                if marker.is_symlink() or marker.is_junction():
                    raise ValueError("Unexpected reparse point in ASIO completion marker")
                trace = decode(etl, marker, destination, expected_pid=pid) if marker.exists() else incomplete(etl, pid, destination)
                session.update(asio_control_summary(trace, pid, first, last))
            except (OSError, KeyError, TypeError, ValueError) as error:
                session["error"] = str(error)[:512]
            sessions.append(session)
    except (OSError, ValueError) as error:
        return {"outcome": "private_trace_unverified", "error": str(error)[:512]}
    return {"outcome": "control_records_observed" if any(session.get("records") for session in sessions) else
            "control_records_unverified", "sessions": sessions}


def loopback_evidence(folder):
    evidence = {"directory": folder.name, "scope": "Worker-side output and input PCM"}
    try:
        files = [folder] + [folder / name for name in ("ready.json", "arm.txt", "capture.json", "capture-error.json",
                                                      "capture.pcm", "input.pcm")]
        if any(path.is_symlink() or path.is_junction() for path in files):
            raise ValueError("Unexpected reparse point in the worker capture")
        if not (folder / "ready.json").is_file():
            return {**evidence, "outcome": "worker_capture_not_prepared"}
        if not (folder / "arm.txt").is_file():
            return {**evidence, "outcome": "worker_capture_not_armed"}
        if (folder / "capture-error.json").exists() or not (folder / "capture.json").is_file():
            return {**evidence, "outcome": "worker_capture_incomplete"}
        reader = runpy.run_path(str(HERE / "export-output-capture.py"))["read_capture"]
        metadata, _, returned = reader(folder)
        if returned is None or metadata["rateHz"] != 44100:
            raise ValueError("Expected paired 44.1 kHz capture from the tested worker")
        return {**evidence, "outcome": "paired_worker_capture_verified", "framesPerDirection": metadata["frames"],
                "outputFirstFrame": metadata["firstFrame"], "inputFirstFrame": metadata["input"]["firstFrame"],
                "outputPcmSha256": metadata["pcmSha256"], "inputPcmSha256": metadata["input"]["pcmSha256"]}
    except (OSError, KeyError, ValueError) as error:
        return {**evidence, "outcome": "worker_capture_unverified", "error": str(error)}


def broker_evidence(destination, local_appdata, cleanup, wait_seconds=8):
    if not cleanup["processExited"] or not cleanup.get("processFileTimes"):
        return {"outcome": "host_exit_identity_unavailable"}
    return broker_evidence_for_process(destination, local_appdata, cleanup["pid"],
                                       cleanup["processFileTimes"]["first"], wait_seconds)


def broker_evidence_for_process(destination, local_appdata, pid, created, wait_seconds=0, *, expected_frames=64):
    reader = runpy.run_path(str(HERE / "read-installed-asio-start.py"))
    try:
        pid, created = reader["identity"]({"pid": pid, "creationFileTimeUtc": created})
        root = local_appdata / "SL3RebuildActivated"
        folder = root / f"application-{pid}-{created}"
        identity = {"hostPid": pid, "hostCreationFileTimeUtc": created, "sessionDirectory": folder.name}
        for path in (root, folder):
            reader["require"](not path.is_symlink() and not path.is_junction(),
                              "Unexpected reparse point in the activation path")
        claim = folder.with_name(folder.name + ".claim")
        if not claim.exists():
            return {**identity, "outcome": "activation_receipt_absent"}
        deadline = time.monotonic() + wait_seconds
        while not (folder / "result.json").exists() and time.monotonic() < deadline:
            time.sleep(.2)
        activation_path = destination / "sl3-asio.conf"
        activation, digest = reader["configuration"](activation_path)
        profile = reader["diagnostic_profile"](activation_path, activation, digest)
        reader["require"](expected_frames in (32, 64) and profile["configuredBufferFrames"] == expected_frames,
                          "The activation receipt does not match the selected buffer profile")
        return {**identity, **reader["summarize"](folder, activation, profile), "profile": profile}
    except (OSError, ValueError, KeyError) as error:
        return {"outcome": "activation_evidence_unavailable", "error": str(error)[:512]}


def asio_callback_loopback(output, output_ready_trial):
    from ctypes import wintypes
    import numpy  # Check the analyzer dependency before opening the device.

    api = runpy.run_path(str(HERE / "run-serato-startup-session.py"))
    require, digest = api["require"], api["digest"]
    require(output.parent.resolve() == (ROOT / "analysis").resolve() and not output.exists(),
            "Fresh private analysis output required")
    folder = output.with_name(f"{output.stem}-pcm")
    require(not (folder.exists() or folder.is_symlink() or folder.is_junction()), "Fresh callback PCM directory required")
    require(not ctypes.windll.shell32.IsUserAnAdmin(), "Use an ordinary user terminal for the callback loopback")
    require(windows_state(require), "Connect the SL3 before the callback loopback")
    require_watcher_state(watcher_state(), False, require)
    require_connected_transport(transport_state(), require)
    app = Path(os.environ["ProgramFiles"]) / "Serato/Serato DJ Pro/Serato DJ Pro.exe"
    archive = app.with_name("userio_resources.bin")
    require(digest(app) == api["APP_SHA"] and digest(archive) == api["ORIGINAL_RESOURCES"], "Original Serato files required")
    require(digest(ASIO_CALLBACK_PROBE) == ASIO_CALLBACK_PROBE_SHA, "Reviewed callback probe executable required")
    native = driver(output_ready_trial)
    stage = native.observe()
    require(stage["state"] == "installed", "Install the selected reviewed 64-frame driver stage")
    dll = native.destination / "sl3_asio.dll"
    dll_sha = native.manifest["files"]["sl3_asio.dll"]["sha256"]
    require(digest(dll) == dll_sha, "Staged ASIO DLL differs from the selected bundle")
    environment = {**os.environ, "SL3_ASIO_PRIVATE_TRACE": "1" if output_ready_trial else "0"}
    for key in ("SL3_OUTPUT_CAPTURE_DIRECTORY", "SL3_LOOPBACK_CAPTURE"):
        environment.pop(key, None)
    child = subprocess.Popen([str(ASIO_CALLBACK_PROBE), "--run-asio-loopback", str(dll), str(folder),
                              "--confirm-line-loopback"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                             env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
    timed_out = False
    try:
        try:
            _, errors = child.communicate(timeout=25)
        except subprocess.TimeoutExpired:
            timed_out = True
            child.kill()
            _, errors = child.communicate(timeout=5)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
    get_times = ctypes.WinDLL("kernel32", use_last_error=True).GetProcessTimes
    get_times.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    get_times.restype = wintypes.BOOL
    values = [wintypes.FILETIME() for _ in range(4)]
    times = None
    if get_times(int(child._handle), *(ctypes.byref(value) for value in values)):
        times = {name: str(value.dwHighDateTime << 32 | value.dwLowDateTime)
                 for name, value in zip(("first", "last"), values)}
    cleanup = {"pid": child.pid, "processFileTimes": times, "processExited": child.poll() is not None,
               "exitCode": child.returncode, "observerForcedTermination": timed_out or child.returncode == 70}
    local_appdata = native.s.known_folder("f1b32785-6fba-4fcf-9d55-7b8e7f157091")
    broker = broker_evidence(native.destination, local_appdata, cleanup)
    report = {"schema": "sl3.asio-callback-loopback-session.v1", "stage": stage, "dllSha256": dll_sha,
              "outputReadyTrial": output_ready_trial, "host": cleanup, "pcmDirectory": folder.name,
              "broker": broker, "stderr": errors.decode("utf-8", "replace")[:1024],
              "inputsUnchanged": digest(app) == api["APP_SHA"] and digest(archive) == api["ORIGINAL_RESOURCES"] and
                                 digest(dll) == dll_sha and digest(ASIO_CALLBACK_PROBE) == ASIO_CALLBACK_PROBE_SHA}
    if output_ready_trial:
        report["outputReadyEvidence"] = output_ready_evidence(local_appdata, cleanup, output)
    if child.returncode == 0:
        try:
            analyzer = runpy.run_path(str(HERE / "analyse-timer-loopback.py"))["analyse_exact_asio"]
            report["measurement"] = analyzer(folder, dll_sha)
        except (OSError, KeyError, ValueError) as error:
            report["measurementError"] = str(error)
    measured = report.get("measurement", {})
    report["successful"] = (report["inputsUnchanged"] and child.returncode == 0 and measured.get("bothMarkersAccepted") is True and
                            measured.get("outputReadyAccepted") is output_ready_trial and
                            broker.get("nativeAcquisitionReported") is True and broker.get("streamStartReplies") == 1 and
                            broker.get("applicationExitRetirementReported") is True and
                            (not output_ready_trial or report["outputReadyEvidence"]["outcome"] == "retired_streams_observed"))
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(report, indent=2))
    return 0 if report["successful"] else 1


def check_delayed_probe(mode, attach_after_ms, late_factory_probe, manual_close_seconds,
                        native_notice_helper, owned_notice_helper, output_ready_trial, loopback_capture,
                        watcher_rehearsal=False):
    if owned_notice_helper and (attach_after_ms is not None or watcher_rehearsal) and (
            late_factory_probe != "replace" or attach_after_ms is None or attach_after_ms < 2500):
        raise ValueError("The delayed owned notice helper requires the atomic swap and an attach delay of at least 2500 ms")
    if watcher_rehearsal:
        if (mode != "inject" or late_factory_probe != "replace" or
                (attach_after_ms is not None and not 0 <= attach_after_ms <= 5000) or
                any((manual_close_seconds, native_notice_helper, output_ready_trial, loopback_capture))):
            raise ValueError("Watcher rehearsal requires an unplugged replacement and a bounded delay")
        return
    if attach_after_ms is None:
        if late_factory_probe:
            raise ValueError("The temporary factory test requires --attach-after-ms")
        return
    if not 0 <= attach_after_ms <= 5000:
        raise ValueError("Delayed attach must be between 0 and 5000 milliseconds")
    if mode == "inject":
        return
    if (mode == "connected" and late_factory_probe == "replace" and 15 <= manual_close_seconds <= 180 and
            not any((native_notice_helper, output_ready_trial, loopback_capture))):
        return
    raise ValueError("Delayed attach requires an unplugged injection or an attended 64-frame connected swap")


def factory_verified(events, sl3_entries, probe):
    expected = {"prepare": "late_factory_prepared", "passthrough": "late_factory_passthrough",
                "full": "late_factory_candidate", "replace": "late_factory_replaced"}[probe]
    built = [event for event in events if event["event"] == expected]
    replaced = probe == "replace"
    transfer = [event for event in events if event["event"] == "sl3_aggregation_transfer"]
    return (sl3_entries == [SL3_IDENTITY + [replaced]] and len(built) == 1 and
            built[0]["scratchReleased"] and built[0]["optionsRestored"] and
            (not replaced or (built[0].get("atomicPairExchange") is True and
                              len(transfer) == 1 and transfer[0]["sameOwner"] and
                              transfer[0]["sameDescriptor"] and transfer[0]["ownerRefs"] == 2)))


class LaunchTimingObserver:
    """One read-only detector for up to two owned shortcut launches."""

    def __init__(self):
        self.child = None
        self.application = None
        self.responses = queue.Queue()

    def arm(self, application):
        if self.child is not None:
            if self.child.poll() is not None or application != self.application:
                raise ValueError("The launch timing observer cannot be reused")
            return
        powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        arguments = [str(powershell), "-NoProfile", "-NonInteractive", "-File", str(HERE / "observe-serato-launch-timing.ps1"),
                     "-Application", str(application)]
        child = subprocess.Popen(
            arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.child, self.application = child, application

        def collect():
            for line in child.stdout:
                self.responses.put(line.strip())
            self.responses.put(None)

        threading.Thread(target=collect, daemon=True).start()
        if self.response() != "ready":
            raise ValueError("Launch timing observer did not arm")

    def response(self):
        try:
            line = self.responses.get(timeout=6)
        except queue.Empty as error:
            raise ValueError("Launch timing observer did not answer within six seconds") from error
        if line is None:
            self.child.wait(timeout=2)
            raise ValueError(f"Launch timing observer stopped: {self.child.stderr.read().strip()[:240]}")
        return line

    def begin_poll(self):
        self.child.stdin.write("start\n")
        self.child.stdin.flush()

    def close(self):
        if self.child is None:
            return
        child = self.child
        try:
            child.stdin.close()
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=2)
                raise ValueError("Launch timing observer did not stop on request")
            if child.returncode:
                raise ValueError(f"Launch timing observer failed: {child.stderr.read().strip()[:240]}")
        finally:
            child.stdout.close()
            child.stderr.close()
            self.child = None


def timing_observer_candidate(detector, observer, primary_thread, require):
    candidate = json.loads(detector.response())
    times = [observer.w.FILETIME() for _ in range(4)]
    observer.checked(observer.k.GetProcessTimes(observer.handle, *(ctypes.byref(value) for value in times)))
    creation = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    require(candidate["pid"] == observer.pid and candidate["created"] == str(creation) and not observer.wait(0),
            "Launch timing candidate does not match the live owned process")
    if primary_thread is not None:
        require(candidate["thread"] == primary_thread, "Launch timing candidate does not match the primary thread")
    else:
        k, w = observer.k, observer.w
        k.OpenThread.argtypes, k.OpenThread.restype = [w.DWORD, w.BOOL, w.DWORD], w.HANDLE
        k.GetProcessIdOfThread.argtypes, k.GetProcessIdOfThread.restype = [w.HANDLE], w.DWORD
        thread = observer.checked(k.OpenThread(0x800, False, candidate["thread"]))
        try:
            require(k.GetProcessIdOfThread(thread) == observer.pid, "Shortcut candidate thread belongs to another process")
        finally:
            k.CloseHandle(thread)
    return candidate


def run(mode, output, manual_close_seconds=0, native_notice_helper=False, owned_notice_helper=False,
        output_ready_trial=False, loopback_capture=False, attach_after_ms=None, late_factory_probe=None,
        watcher_rehearsal=False, desktop_shortcut_rehearsal=False, usb_startup_observer=False,
        asio_control_trace=False, native_reader_trial=False, native_factory_trial=False, timing_detector=None,
        native_hook_library=False):
    check_delayed_probe(mode, attach_after_ms, late_factory_probe, manual_close_seconds,
                        native_notice_helper, owned_notice_helper, output_ready_trial, loopback_capture, watcher_rehearsal)
    deferred_attach = attach_after_ms is not None or watcher_rehearsal
    session = runpy.run_path(str(HERE / "run-serato-startup-session.py"))
    require, digest = session["require"], session["digest"]
    require(not desktop_shortcut_rehearsal or watcher_rehearsal, "Desktop shortcut requires the unplugged watcher rehearsal")
    require(not native_reader_trial or (mode == "inject" and attach_after_ms is not None and
            late_factory_probe in ("full", "replace")), "Native reader trial requires an unplugged delayed factory test")
    require(not native_factory_trial or native_reader_trial,
            "Native factory trial requires the unplugged native reader trial")
    require(not native_hook_library or (native_factory_trial and late_factory_probe == "replace"),
            "Native hook library requires the unplugged native replacement trial")
    plain = mode == "plain"
    require(not usb_startup_observer or not plain, "USB startup observation requires an instrumented launch")
    require(manual_close_seconds == 0 or (mode == "connected" and 15 <= manual_close_seconds <= 180),
            "Manual close requires a connected test and a window between 15 and 180 seconds")
    require(not native_notice_helper or mode == "connected", "Native notice observation requires a connected test")
    require(not output_ready_trial or (mode == "connected" and manual_close_seconds > 0),
            "The output-ready trial requires a connected test with an attended close")
    require(not asio_control_trace or (mode == "connected" and manual_close_seconds > 0 and not output_ready_trial),
            "ASIO control trace requires the attended standard 64-frame stage")
    require(not loopback_capture or (mode == "connected" and manual_close_seconds >= 30),
            "Paired loopback requires a connected test with at least 30 seconds for the attended close")
    require(not any(os.environ.get(name) for name in ("SL3_OUTPUT_CAPTURE_DIRECTORY", "SL3_LOOPBACK_CAPTURE")),
            "Remove inherited capture variables and use the explicit loopback option")
    require(not owned_notice_helper or (mode in ("connected", "inject") and not native_notice_helper),
            "Owned notice helper requires its own connected or unplugged injection run")
    frida = None
    if not plain:
        require(Path(sys.executable).resolve() == (RUNTIME / "python.exe").resolve(), "Use the reviewed local-only Python runtime")
        runpy.run_path(str(HERE / "run-local-frida-owned-probe.py"))["verify_sdk"](RUNTIME, RUNTIME_SHA)
    require(output.parent.resolve() == (ROOT / "analysis").resolve() and not output.exists(),
            "Fresh private analysis output required")
    capture = output.with_name(f"{output.stem}-loopback") if loopback_capture else None
    require(capture is None or not (capture.exists() or capture.is_symlink() or capture.is_junction()),
            "Fresh worker loopback directory required")
    application = Path(os.environ["ProgramFiles"]) / "Serato/Serato DJ Pro/Serato DJ Pro.exe"
    resource = application.with_name("userio_resources.bin")
    shortcut = Path(os.environ["PUBLIC"]) / "Desktop/Serato DJ Pro.lnk" if desktop_shortcut_rehearsal else None
    if shortcut is not None:
        require(not shortcut.is_symlink() and not shortcut.parent.is_junction() and digest(shortcut) == DESKTOP_SHORTCUT_SHA,
                "The reviewed Serato desktop shortcut changed")

    def hashes():
        return {"executable": digest(application), "archive": digest(resource), "fallback": digest(FALLBACK)}

    before = hashes()
    require(before == {"executable": session["APP_SHA"], "archive": session["ORIGINAL_RESOURCES"],
                       "fallback": FALLBACK_SHA}, "Original executable/archive and verified fallback required")
    connected = mode == "connected"
    require(windows_state(require) == connected, "Physical SL3 state does not match the requested test")
    require(not ctypes.windll.shell32.IsUserAnAdmin(), "Run the probe as an ordinary user")
    watchers = watcher_state()
    require_watcher_state(watchers, native_notice_helper, require)
    native = driver(output_ready_trial) if connected else None
    driver_before = native.observe() if native else None
    local_appdata = None
    if native:
        require(driver_before["state"] == "installed", "Verified 64-frame ASIO stage required")
        transport = transport_state()
        require_connected_transport(transport, require)
        local_appdata = native.s.known_folder("f1b32785-6fba-4fcf-9d55-7b8e7f157091")
        if asio_control_trace:
            trace_home = os.environ.get("LOCALAPPDATA")
            require(trace_home and Path(trace_home).resolve() == local_appdata.resolve(),
                    "The ASIO trace environment differs from the user's Local AppData directory")
        if native_notice_helper:
            require(all(digest(WATCHER / name) == expected for name, expected in WATCHER_PINS.items()),
                    "Reviewed temporary notice helper files required")
    else:
        parent = Path(os.environ["ProgramFiles"]) / "SL3 Rebuild"
        require(not any((parent / name).exists() for name in ("on-demand-diagnostic-v1", "output-ready-trial-v1")),
                "Remove any diagnostic driver stage for unplugged tests")
    source = None
    owned_notice = None
    factory_journal = None
    if not plain:
        import frida
        require(Path(frida.__file__).resolve().is_relative_to(RUNTIME), "Unexpected Frida import")
        profile = reviewed_profile(before["executable"], require)
        xml = reviewed_xml() if mode != "baseline" else None
        asio_path = str(native.destination / "sl3_asio.dll") if native else None
        use_native_notice = native_notice_helper or owned_notice_helper
        transfer = None
        factory = None
        if deferred_attach:
            inspector = runpy.run_path(str(HERE / "inspect-serato-memory-descriptor.py"))
            discovery = inspector["discover"](application)
            aggregation = discovery["aggregationRegistry"]
            require(discovery["executableSha256"] == before["executable"] and
                    all(aggregation[key] == value for key, value in profile["aggregationRegistry"].items()) and
                    aggregation["primaryManagerGlobalRva"] == discovery["selectionHelper"].get("primaryManagerGlobalRva"),
                    "Reviewed aggregation layout and primary manager global required")
            transfer = {key: aggregation[key] for key in (
                "primaryVectorGetterRva", "primaryVectorGetterCallRva", "primaryManagerGlobalRva")}
            if late_factory_probe:
                factory = discovery["lateFactory"].copy()
                require(factory.pop("outcome") == "static candidate" and
                        factory == profile["lateFactory"],
                        "Discovered factory recipe differs from the reviewed layout")
                if late_factory_probe == "replace" and not native_hook_library:
                    require(not PAIR_EXCHANGE.is_symlink() and not PAIR_EXCHANGE.parent.is_junction() and
                            digest(PAIR_EXCHANGE) == PAIR_EXCHANGE_SHA, "Reviewed atomic descriptor exchange DLL required")
                    factory["pairExchangeDll"] = str(PAIR_EXCHANGE)
                if native_reader_trial:
                    require(discovery["entryReader"] == profile["entryReader"],
                            "Discovered entry reader differs from the reviewed layout")
                    factory.update(discovery["entryReader"])
                    if not native_hook_library:
                        require(not ENTRY_READER.is_symlink() and not ENTRY_READER.parent.is_junction() and
                                digest(ENTRY_READER) == ENTRY_READER_SHA, "Reviewed native descriptor reader DLL required")
                        factory["entryReaderDll"] = str(ENTRY_READER)
                if native_factory_trial and not native_hook_library:
                    require(not NATIVE_FACTORY.is_symlink() and not NATIVE_FACTORY.parent.is_junction() and
                            digest(NATIVE_FACTORY) == NATIVE_FACTORY_SHA, "Reviewed native factory DLL required")
                    factory["nativeFactoryDll"] = str(NATIVE_FACTORY)
                if native_hook_library:
                    require(not NATIVE_HOOK_LIBRARY.is_symlink() and not NATIVE_HOOK_LIBRARY.parent.is_junction() and
                            digest(NATIVE_HOOK_LIBRARY) == NATIVE_HOOK_LIBRARY_SHA, "Reviewed native hook library required")
                    factory["hookLibraryDll"] = str(NATIVE_HOOK_LIBRARY)
                factory_journal = output.with_name(f"{output.stem}-phases.jsonl")
                with factory_journal.open("x", encoding="utf-8"):
                    pass
                factory.update(journal=str(factory_journal), mode=late_factory_probe)
        source = (f"const PROBE_XML = {json.dumps(xml)};\nconst PROBE_ASIO_PATH = {json.dumps(asio_path)};\n"
                  f"const PROBE_NATIVE_NOTICE = {json.dumps(use_native_notice)};\n"
                  f"const PROBE_LATE_TRANSFER = {json.dumps(transfer)};\n"
                  f"const PROBE_LATE_FACTORY = {json.dumps(factory)};\n"
                  f"const PROBE_PROFILE = {json.dumps(profile)};\n"
                  + (HERE / "serato-asio-start-probe.js").read_text(encoding="utf-8") + "\n"
                  + (HERE / "serato-memory-descriptor-probe.js").read_text(encoding="utf-8"))
        if usb_startup_observer:
            usb_inspector = runpy.run_path(str(HERE / "inspect-serato-usb-subscription.py"))
            layout = usb_inspector["startup_observer_layout"](application, before["executable"])
            source += "\n" + (HERE / "serato-usb-startup-observer.js").read_text(encoding="utf-8")
            source += f"\nobserveUsbStartup({json.dumps(layout)}, base, report, guard);\n"
        if owned_notice_helper:
            owned_notice = runpy.run_path(str(HERE / "serato-owned-notice-poll.py"))["OwnedNoticePoll"](output)
            source += owned_notice.startup_script()
    messages = queue.Queue()
    events = []
    cleanup = {}
    failure = None
    detached_before_close = False
    asio_started = False
    registry_seen = False
    logs = Path(os.environ["USERPROFILE"]) / "Music/_Serato_/Logs"
    since = time.time()
    offline_ready = False
    manual_exit = False
    notice_retired = False
    observer = session["WindowsProcess"](application, frida, asio_private_trace=output_ready_trial or asio_control_trace,
                                         loopback_capture_directory=capture)
    watchdog = None
    if late_factory_probe:
        # Connected runs also allow time for the attended close and fallback cleanup.
        watchdog = session["HardDeadline"](100 + manual_close_seconds if connected else
                                           95 if owned_notice else 70 if usb_startup_observer else 55)
    timing = {"requestedAttachDelayMs": attach_after_ms, "desktopShortcutSha256": DESKTOP_SHORTCUT_SHA,
              "timeOrigin": "desktop_shortcut_request"} if shortcut is not None else None
    resumed = None
    detector = None
    primary_thread = None
    usb_tail_until = None
    usb_observation_end = None
    usb_tail_completed = False

    def attach_phase(stage):
        if factory_journal is not None:
            with factory_journal.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"stage": stage}) + "\n")

    try:
        callback = None if plain else lambda message, _data: messages.put((time.perf_counter(), message))
        if watcher_rehearsal:
            detector = timing_detector or LaunchTimingObserver()
            detector.arm(application)
        if shortcut is not None:
            resumed = time.perf_counter()
            detector.begin_poll()
            observer.start_shortcut(shortcut, DESKTOP_SHORTCUT_SHA)
            timing["shellReturnedAfterMs"] = round((time.perf_counter() - resumed) * 1000, 1)
        elif not deferred_attach:
            observer.start(source, callback)
        else:
            observer.start(None, None, deferred_attach=True)
            timing = {"requestedAttachDelayMs": attach_after_ms}
        if detector is not None and shortcut is None:
            thread_id = observer.k.GetThreadId
            thread_id.argtypes, thread_id.restype = [observer.w.HANDLE], observer.w.DWORD
            primary_thread = observer.checked(thread_id(observer.primary_thread))
        if owned_notice and not deferred_attach:
            owned_notice.bind(observer)
        if shortcut is None:
            resumed = time.perf_counter()
            observer.resume()
            if detector is not None:
                detector.begin_poll()
        if timing is not None:
            if detector is not None:
                candidate = timing_observer_candidate(detector, observer, primary_thread, require)
                receipt = "reportedAfterShortcutMs" if shortcut is not None else "reportedAfterResumeMs"
                timing["watcher"] = {**candidate, "detectorPid": detector.child.pid,
                                     receipt: round((time.perf_counter() - resumed) * 1000, 1)}
                if attach_after_ms:
                    remaining = attach_after_ms / 1000 - (time.perf_counter() - resumed)
                    if remaining > 0:
                        # The Win32 wait truncates to whole milliseconds.
                        require(not observer.wait(remaining + .001), "Owned process exited before the watcher attach window")
            elif attach_after_ms:
                require(not observer.wait(attach_after_ms / 1000), "Owned process exited before delayed attach")
            timing["attachStartedMs"] = round((time.perf_counter() - resumed) * 1000, 1)
            attach_phase("supervisor_attach_started")
            observer.attach(source, callback)
            attach_phase("supervisor_attach_finished")
            timing["hooksLoadedMs"] = round((time.perf_counter() - resumed) * 1000, 1)
            if owned_notice:
                owned_notice.bind(observer, after_resume=True)
        deadline = time.monotonic() + (55 if connected or owned_notice else 25 if usb_startup_observer else
                                       12 if timing is not None else 35)
        while time.monotonic() < deadline and not observer.wait(0):
            if plain:
                status = offline_log(logs, observer.pid, since)
                offline_ready = bool(status and status["offlineAudioStarted"])
                if offline_ready:
                    break
                time.sleep(.25)
                continue
            if owned_notice:
                notice_retired = owned_notice.poll(observer)
            if (registry_seen and (not connected or asio_started) and (not owned_notice or notice_retired) and
                    (usb_tail_until is None or time.monotonic() >= usb_tail_until)):
                break
            try:
                observed, message = messages.get(timeout=.1 if owned_notice else .25)
            except queue.Empty:
                continue
            event = message["payload"] if message.get("type") == "send" else {"event": "instrumentation_error", "detail": message}
            if timing is not None or usb_startup_observer:
                event = {**event, "receivedAfterResumeMs": round((observed - resumed) * 1000, 1)}
            events.append(event)
            if event["event"] in ("probe_error", "instrumentation_error"):
                failure = event["event"]
                break
            if connected and event["event"] == "asio_start_result" and event["result"] == 0:
                asio_started = True
            if event["event"] == "aggregation_registry":
                registry_seen = True
                if usb_startup_observer and not connected:
                    usb_tail_until = time.monotonic() + 8
        if usb_startup_observer:
            usb_observation_end = round((time.perf_counter() - resumed) * 1000, 1)
            usb_tail_completed = usb_tail_until is not None and time.monotonic() >= usb_tail_until
        if owned_notice and not notice_retired and failure is None:
            failure = "Owned notice observer retirement was not verified"
        if not plain and not observer.wait(0):
            observer.detach()
            detached_before_close = True
    except Exception as error:
        failure = str(error)
    finally:
        if detector is not None and timing_detector is None:
            try:
                detector.close()
            except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                failure = failure or str(error)
        if owned_notice:
            try:
                owned_notice.close(observer)
            except OSError as error:
                failure = failure or str(error)
        if observer.handle and not observer.wait(0):
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline and not observer.wait(0):
                if observer.window_snapshot()["visibleWindows"]:
                    break
                time.sleep(.25)
            if manual_close_seconds and detached_before_close and (not owned_notice or notice_retired) and not observer.wait(0):
                if capture:
                    print(f"Paired capture is opt-in. With verified LINE loopback and the test track looping in INT, "
                          f"create {capture / 'arm.txt'} once the worker has written ready.json. "
                          "Wait for capture.json before closing Serato.", flush=True)
                print(f"Probe detached. Close Serato normally within {manual_close_seconds} seconds, "
                      "including any exit confirmation.", flush=True)
                manual_exit = observer.wait(manual_close_seconds)
            elif detached_before_close or offline_ready:
                observer.wait(8)
        try:
            cleanup = observer.cleanup()
        finally:
            if watchdog:
                watchdog.close()
        after = hashes()
        if shortcut is not None:
            try:
                timing["desktopShortcutUnchanged"] = digest(shortcut) == DESKTOP_SHORTCUT_SHA
            except OSError:
                timing["desktopShortcutUnchanged"] = False
            if not timing["desktopShortcutUnchanged"]:
                failure = failure or "Desktop shortcut changed during the rehearsal"
        report = {"mode": mode, "sl3AbsentAtPreflight": not connected, "before": before, "after": after,
                  "inputsUnchanged": before == after, "events": events, "failure": failure,
                  "detachedBeforeClose": detached_before_close, "cleanup": cleanup, "watchersAtPreflight": watchers}
        if not plain:
            report["reviewedProfileSha256"] = PROFILE_SHA
        if native:
            report["outputReadyTrial"] = output_ready_trial
            report["driverStage"] = driver_before
            report["transportAtPreflight"] = transport
            report["asioStarted"] = asio_started
            broker = broker_evidence(native.destination, local_appdata, cleanup)
            report["broker"] = broker
            report["nativeStreamStartCorroborated"] = (
                broker.get("nativeAcquisitionReported") is True and broker.get("streamStartReplies", 0) > 0
            )
            report["manualCloseSeconds"] = manual_close_seconds
            report["normalExitDuringManualClose"] = manual_exit and cleanup["exitCode"] == 0
            if native_notice_helper:
                report["nativeNoticeLog"] = notice_log(cleanup)
            if output_ready_trial:
                report["outputReadyEvidence"] = output_ready_evidence(local_appdata, cleanup, output)
            if asio_control_trace:
                report["asioControlEvidence"] = asio_control_evidence(local_appdata, cleanup, output)
            if capture:
                report["loopbackCapture"] = loopback_evidence(capture)
        if plain:
            report["offlineReadyBeforeClose"] = offline_ready
        if timing is not None:
            report["delayedAttach"] = timing
        if usb_startup_observer:
            report["usbStartupObservation"] = {"endedAfterLaunchMs": usb_observation_end,
                                               "unpluggedTailCompleted": usb_tail_completed}
        if plain or connected or timing is not None or usb_startup_observer:
            report["applicationLog"] = offline_log(logs, observer.pid, since)
        if factory_journal:
            report["factoryPhases"] = factory_journal.name
            report["factoryMode"] = late_factory_probe
            if native_hook_library:
                report["nativeHookLibrarySha256"] = NATIVE_HOOK_LIBRARY_SHA
            else:
                if late_factory_probe == "replace":
                    report["pairExchangeSha256"] = PAIR_EXCHANGE_SHA
                if native_reader_trial:
                    report["nativeReaderSha256"] = ENTRY_READER_SHA
                if native_factory_trial:
                    report["nativeFactorySha256"] = NATIVE_FACTORY_SHA
        if owned_notice:
            try:
                report["ownedNotice"] = owned_notice.report()
            except (OSError, ValueError) as error:
                report["ownedNotice"] = {"error": str(error)}
        with output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
    print(json.dumps({**report, "events": [{**event, "entries": len(event["entries"])} if "entries" in event else event
                                         for event in events]}, indent=2))
    if failure or before != after or not cleanup.get("processExited") or not cleanup.get("jobEmpty"):
        return 1
    if plain:
        return 0 if offline_ready and cleanup["exitCode"] == 0 and not cleanup["observerForcedTermination"] else 2
    if usb_startup_observer and not any(event["event"] == "usb_startup_observer_armed" for event in events):
        return 1
    registries = [event["entries"] for event in events if event["event"] == "aggregation_registry"]
    if len(registries) != 1:
        return 1
    sl3_entries = [entry for entry in registries[0] if entry is not None and entry[:3] == SL3_IDENTITY]
    if late_factory_probe:
        if not factory_verified(events, sl3_entries, late_factory_probe):
            return 1
        if native_reader_trial and [event.get("stage") for event in events if event["event"] == "native_descriptor_text"] != [
                "classification", "fullParse"]:
            return 1
        if native_reader_trial and not any(event["event"] == "native_reader_entry_restored" and
                                           event.get("nativeDispatch") is True for event in events):
            return 1
        if native_factory_trial and not any(
                event.get("nativeScratchFactory") is True and
                event.get("nativePublication") is (late_factory_probe == "replace") and
                event.get("nativePrimaryLookup") is (late_factory_probe == "replace") and
                (late_factory_probe != "replace" or event.get("nativeGetterDispatch") is True)
                for event in events if event["event"] in ("late_factory_candidate", "late_factory_replaced")):
            return 1
        if native_factory_trial and late_factory_probe == "replace" and not any(
                event["event"] == "native_getter_restored" for event in events):
            return 1
        if native_hook_library and not any(event["event"] == "late_factory_replaced" and
                                           event.get("nativeHookLibrary") is True for event in events):
            return 1
    elif sl3_entries != [SL3_IDENTITY + [mode != "baseline"]]:
        return 1
    if connected and not asio_started:
        return 2
    if connected and not report["nativeStreamStartCorroborated"]:
        return 3
    if output_ready_trial and report["outputReadyEvidence"]["outcome"] != "retired_streams_observed":
        return 4
    if capture and report["loopbackCapture"]["outcome"] != "paired_worker_capture_verified":
        return 5
    if connected and late_factory_probe and not (report["normalExitDuringManualClose"] and
            report["broker"].get("applicationExitRetirementReported") is True):
        return 6
    if asio_control_trace and report["asioControlEvidence"]["outcome"] != "control_records_observed":
        return 7
    return 0


def compare(baseline_path, injection_path):
    baseline, injection = [
        json.loads(path.read_text(encoding="utf-8")) for path in (baseline_path, injection_path)
    ]

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def events(report, name):
        return [event for event in report["events"] if event["event"] == name]

    for report, mode in ((baseline, "baseline"), (injection, "inject")):
        require(report["mode"] == mode and report["sl3AbsentAtPreflight"] and not report["failure"],
                f"Expected a successful unplugged {mode} observation")
        cleanup = report["cleanup"]
        require(cleanup["processExited"] and cleanup["jobEmpty"], f"{mode} process cleanup incomplete")
        require(report["before"] == report["after"] == baseline["before"], f"{mode} input hashes differ")

    listing = events(injection, "audio_listing")
    appended = events(injection, "resource_appended")
    require(listing == events(baseline, "audio_listing") and len(listing) == len(appended) == 1
            and appended[0]["count"] == listing[0]["count"] + 1, "Expected one added resource")
    require([event["stage"] for event in events(injection, "descriptor_text")] == ["classification", "fullParse"],
            "Expected both parser reads in order")

    sl3 = SL3_IDENTITY

    def split(entries):
        matching = [entry for entry in entries if entry is not None and entry[:3] == sl3]
        other = [entry for entry in entries if entry is None or entry[:3] != sl3]
        return matching, other

    counts = {}
    for name, expected in (("primary_registry", [True, False]), ("aggregation_registry", [True])):
        original, rebuilt = events(baseline, name), events(injection, name)
        require(len(original) == len(rebuilt) == 1, f"Expected one {name} snapshot per run")
        original_entries, rebuilt_entries = original[0]["entries"], rebuilt[0]["entries"]
        original_sl3, original_other = split(original_entries)
        rebuilt_sl3, rebuilt_other = split(rebuilt_entries)
        require(original_sl3 == [sl3 + [False]], f"Unexpected baseline SL3 entry in {name}")
        require(rebuilt_sl3 == [sl3 + [value] for value in expected], f"Unexpected SL3 entries in {name}")
        require(original_other == rebuilt_other, f"Non-SL3 identities or order changed in {name}")
        counts[name] = {"baseline": len(original_entries), "inject": len(rebuilt_entries)}

    print(json.dumps({"registeredInMemory": True, "entries": counts,
                      "normalExit": {report["mode"]: report["cleanup"]["exitCode"] == 0
                                     and not report["cleanup"]["observerForcedTermination"]
                                     for report in (baseline, injection)}}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--mode", choices=("plain", "baseline", "inject", "connected"))
    action.add_argument("--driver-stage", choices=("plan", "install", "restore"))
    action.add_argument("--compare", type=Path, nargs=2, metavar=("BASELINE", "INJECTION"))
    action.add_argument("--asio-callback-loopback", action="store_true",
                        help="Measure the staged driver through IASIO with Serato closed")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manual-close-seconds", type=int, default=0, help="Attended connected close window")
    parser.add_argument("--native-notice-helper", action="store_true",
                        help="Leave the notice entry intact for the separately armed helper")
    parser.add_argument("--owned-notice-helper", action="store_true",
                        help="Use the native message helper only inside the owned Serato process")
    parser.add_argument("--output-ready-trial", action="store_true",
                        help="Select the separate pinned 64-frame output-ready driver stage")
    parser.add_argument("--asio-control-trace", action="store_true",
                        help="Record private ASIO control calls in an attended standard 64-frame run")
    parser.add_argument("--loopback-capture", action="store_true",
                        help="Prepare a manually armed five-second paired PCM capture for the owned connected session")
    parser.add_argument("--confirm-line-loopback", action="store_true",
                        help="Confirm physical OUT 1/2 to IN 3/4 set to LINE for the callback loopback")
    parser.add_argument("--attach-after-ms", type=int,
                        help="Set a minimum delay before attaching in a private launch rehearsal")
    parser.add_argument("--late-factory-probe", choices=("prepare", "passthrough", "full", "replace"),
                        help="Test scratch construction or replace one SL3 slot before aggregation")
    parser.add_argument("--watcher-rehearsal", action="store_true",
                        help="Time a private launch detector before attaching to an owned unplugged process")
    parser.add_argument("--desktop-shortcut-rehearsal", action="store_true",
                        help="Use the reviewed Windows desktop shortcut in the unplugged watcher rehearsal")
    parser.add_argument("--reopen-output", type=Path,
                        help="Repeat the unplugged shortcut launch with the same detector and save a second report")
    parser.add_argument("--usb-startup-observer", action="store_true",
                        help="Observe the Engine startup branch and USB manager registration")
    parser.add_argument("--native-reader-trial", action="store_true",
                        help="Test the native reader at function entry during an unplugged factory trial")
    parser.add_argument("--native-factory-trial", action="store_true",
                        help="Test native factory ownership and cleanup in an unplugged trial")
    parser.add_argument("--native-hook-library", action="store_true",
                        help="Let a single native DLL install and retire both hooks in the unplugged replacement trial")
    args = parser.parse_args()
    if args.manual_close_seconds and args.mode != "connected":
        parser.error("--manual-close-seconds is only used with --mode connected")
    if args.native_notice_helper and args.mode != "connected":
        parser.error("--native-notice-helper is only used with --mode connected")
    if args.owned_notice_helper and (args.mode not in ("connected", "inject") or args.native_notice_helper):
        parser.error("--owned-notice-helper requires a separate connected or inject run")
    if args.output_ready_trial and not (args.driver_stage or args.mode == "connected" or args.asio_callback_loopback):
        parser.error("--output-ready-trial requires driver stage, connected mode or callback loopback")
    if args.output_ready_trial and args.mode == "connected" and not args.manual_close_seconds:
        parser.error("--output-ready-trial requires --manual-close-seconds for a connected test")
    if args.asio_control_trace and (args.mode != "connected" or not args.manual_close_seconds or args.output_ready_trial):
        parser.error("--asio-control-trace requires the attended standard 64-frame stage")
    if args.loopback_capture and (args.mode != "connected" or args.manual_close_seconds < 30):
        parser.error("--loopback-capture requires connected mode and at least 30 seconds for manual close")
    if args.confirm_line_loopback != args.asio_callback_loopback:
        parser.error("--asio-callback-loopback requires explicit --confirm-line-loopback")
    if args.desktop_shortcut_rehearsal and not args.watcher_rehearsal:
        parser.error("--desktop-shortcut-rehearsal requires --watcher-rehearsal")
    if args.reopen_output and (not args.desktop_shortcut_rehearsal or not args.output or
                               args.reopen_output.stem == args.output.stem or
                               args.reopen_output.parent.resolve() != (ROOT / "analysis").resolve() or
                               args.reopen_output.exists() or
                               args.reopen_output.with_name(f"{args.reopen_output.stem}-phases.jsonl").exists()):
        parser.error("--reopen-output requires the desktop shortcut rehearsal and a distinct fresh analysis path")
    if args.usb_startup_observer and args.mode not in ("baseline", "inject", "connected"):
        parser.error("--usb-startup-observer requires an instrumented launch")
    if args.native_reader_trial and (args.mode != "inject" or args.attach_after_ms is None or
                                   args.late_factory_probe not in ("full", "replace")):
        parser.error("--native-reader-trial requires an unplugged delayed factory test")
    if args.native_factory_trial and not args.native_reader_trial:
        parser.error("--native-factory-trial requires the unplugged native reader trial")
    if args.native_hook_library and (not args.native_factory_trial or args.late_factory_probe != "replace"):
        parser.error("--native-hook-library requires the unplugged native replacement trial")
    try:
        check_delayed_probe(args.mode, args.attach_after_ms, args.late_factory_probe, args.manual_close_seconds,
                            args.native_notice_helper, args.owned_notice_helper, args.output_ready_trial,
                            args.loopback_capture, args.watcher_rehearsal)
    except ValueError as error:
        parser.error(str(error))
    if args.compare:
        if args.output:
            parser.error("--output is only used with --mode")
        try:
            compare(*args.compare)
        except (ValueError, KeyError, OSError) as error:
            parser.exit(1, f"{error}\n")
    elif args.driver_stage:
        if args.output:
            parser.error("--output is only used with --mode")
        try:
            driver_stage(args.driver_stage, args.output_ready_trial or None)
        except (ValueError, OSError, RuntimeError) as error:
            parser.exit(1, f"{error}\n")
    elif args.asio_callback_loopback:
        if not args.output:
            parser.error("--asio-callback-loopback requires --output")
        try:
            raise SystemExit(asio_callback_loopback(args.output.absolute(), args.output_ready_trial))
        except (ValueError, OSError, RuntimeError, ImportError) as error:
            parser.exit(1, f"{error}\n")
    else:
        if not args.output:
            parser.error("--mode requires --output")

        def run_once(output, detector=None):
            return run(args.mode, output.absolute(), args.manual_close_seconds,
                       args.native_notice_helper, args.owned_notice_helper, args.output_ready_trial,
                       args.loopback_capture, args.attach_after_ms, args.late_factory_probe,
                       args.watcher_rehearsal, args.desktop_shortcut_rehearsal, args.usb_startup_observer,
                       args.asio_control_trace, args.native_reader_trial, args.native_factory_trial,
                       timing_detector=detector, native_hook_library=args.native_hook_library)

        try:
            if args.reopen_output:
                with closing(LaunchTimingObserver()) as detector:
                    result = run_once(args.output, detector)
                    if result == 0:
                        result = run_once(args.reopen_output, detector)
            else:
                result = run_once(args.output)
            raise SystemExit(result)
        except (ValueError, OSError, RuntimeError) as error:
            parser.exit(1, f"{error}\n")
