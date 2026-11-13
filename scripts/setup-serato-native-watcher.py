"""Check, register or withdraw a pre-staged native watcher for the current user."""

import argparse
from contextlib import closing
import json
import os
from pathlib import Path, PurePosixPath
import re
import runpy
import shutil
import subprocess
import tempfile
import time
import uuid
import winreg


HERE = Path(__file__).resolve().parent
WATCH = runpy.run_path(str(HERE / "watch-serato-native-startup.py"))
require, digest = WATCH["require"], WATCH["digest"]
RUN_KEY, RUN_NAME = WATCH["RUN_KEY"], WATCH["RUN_NAME"]
SETUP_MUTEX = r"Local\SL3CompatibilityWatcherSetup-v1"


class StartupSlot:
    def read(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                return WATCH["startup_value"](key)
        except FileNotFoundError:
            return None

    def change(self, command, register):
        try:
            access = winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE
            open_key = winreg.CreateKeyEx if register else winreg.OpenKey
            with open_key(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, access) as key:
                current = WATCH["startup_value"](key)
                require(current in (None, (command, winreg.REG_SZ)), "The sign-in slot is owned by another setup")
                if register and current is None:
                    winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, command)
                    return True
                if not register and current is not None:
                    winreg.DeleteValue(key, RUN_NAME)
        except FileNotFoundError:
            if register:
                raise
        return False


def read_payload(root, expected):
    manifest = root / "watcher-payload.json"
    require(root.is_dir() and not root.is_symlink() and not root.is_junction() and manifest.is_file() and
            not manifest.is_symlink() and manifest.stat().st_size <= 131072 and digest(manifest) == expected,
            "A verified watcher payload is required")
    record = json.loads(manifest.read_bytes())
    require(isinstance(record, dict) and record.get("schema") == "sl3.private-native-watcher-payload.v1" and
            isinstance(record.get("files"), dict) and 0 < len(record["files"]) <= 256 and
            type(record.get("applicationLifetime", False)) is bool and
            type(record.get("diagnosticBufferFrames", 64)) is int and record.get("diagnosticBufferFrames", 64) in (32, 64) and
            type(record.get("outputDeadlineTrial", False)) is bool and type(record.get("outputReadyTrial", False)) is bool and
            sum(record.get(key, False) for key in ("applicationLifetime", "outputDeadlineTrial", "outputReadyTrial")) <= 1 and
            (not (record.get("applicationLifetime") or record.get("outputReadyTrial")) or
             record.get("diagnosticBufferFrames", 64) == 64) and
            re.fullmatch(r"[0-9a-f]{64}", record.get("startupPlanSha256", "")), "Unknown watcher payload format")
    files = record["files"]
    require(len({name.casefold() for name in files}) == len(files), "Watcher payload contains path aliases")
    for name, row in files.items():
        member = PurePosixPath(name)
        require(member.parts and not member.is_absolute() and name == member.as_posix() and
                not ({"..", "."} & set(member.parts)) and member.parts[0].casefold() != "analysis" and
                "\\" not in name and ":" not in name and isinstance(row, dict) and type(row.get("bytes")) is int and
                0 <= row["bytes"] <= 64 * 1024 * 1024, "Invalid watcher payload member")
    actual = set()
    actual_directories = set()
    for directory, folders, names in os.walk(root):
        folder = Path(directory)
        for name in folders + names:
            path = folder / name
            require(not path.is_symlink() and not path.is_junction(), "Redirected watcher payload path")
        if folder == root and "analysis" in folders:
            folders.remove("analysis")
        actual_directories.update((folder / name).relative_to(root).as_posix() for name in folders)
        for name in names:
            actual.add((folder / name).relative_to(root).as_posix())
    require(actual == set(files) | {manifest.name}, "Watcher payload inventory differs")
    expected_directories = {directory.as_posix() for name in files for directory in PurePosixPath(name).parents
                            if directory.parts}
    require(actual_directories == expected_directories, "Watcher payload directory inventory differs")
    for name, row in files.items():
        path = root / name
        require(path.is_file() and path.stat().st_size == row["bytes"] and digest(path) == row["sha256"],
                "Watcher payload file differs: " + name)
    require(files["watcher-startup-plan.json"]["sha256"] == record["startupPlanSha256"] and
            {"watch.pyw", "runtime/python/pythonw.exe"} <= set(files), "Watcher payload lacks its pinned startup inputs")
    return record


def stage_payload(source, destination, expected):
    require(destination.parent.is_dir() and not destination.parent.is_symlink() and
            not destination.parent.is_junction() and destination == destination.parent.resolve() / destination.name and
            not destination.exists() and not destination.is_symlink() and not destination.is_junction(),
            "A fresh local watcher destination is required")
    read_payload(source, expected)

    def ignore_reports(folder, names):
        return {"analysis"} if Path(folder) == source and "analysis" in names else set()

    with tempfile.TemporaryDirectory(prefix="watcher-stage-", dir=destination.parent) as scratch:
        pending = Path(scratch) / destination.name
        shutil.copytree(source, pending, ignore=ignore_reports, symlinks=True)
        plan = read_payload(pending, expected)["startupPlanSha256"]
        require(pending.resolve().is_relative_to(destination.parent) and
                destination.resolve().parent == destination.parent, "Watcher stage move escaped its local parent")
        pending.rename(destination)
    return plan


def retire_payload(root, expected):
    inventory = read_payload(root, expected)["files"]
    parent = root.parent.resolve()
    retired = parent / f"{root.name}-retired-{uuid.uuid4().hex}"
    require(root == parent / root.name and retired.resolve().parent == parent and not retired.exists(),
            "Watcher retirement must stay in its local parent")
    root.rename(retired)

    # Diagnostic files stay in the retired directory. Remove only the verified payload.
    directories = set()
    pins = {name: row["sha256"] for name, row in inventory.items()}
    pins["watcher-payload.json"] = expected
    for name, identity in pins.items():
        path = retired / name
        require(path.resolve().is_relative_to(retired) and not path.is_symlink() and digest(path) == identity,
                "Watcher payload changed during retirement")
        path.unlink()
        directories.update(folder for folder in path.parents if folder != retired and folder.is_relative_to(retired))
    for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
        directory.rmdir()
    if not any(retired.iterdir()):
        retired.rmdir()


def coordinate(action, registration, plan, slot, launch, wait_idle, timeout=20):
    current = slot.read()
    command = registration.command
    require(current in (None, (command, winreg.REG_SZ)), "The sign-in slot is owned by another setup")
    try:
        process = registration.ready_process(plan)
    except (OSError, ValueError):
        if action == "Check":
            return "recovery-required"
        if action != "Restore":
            raise
        # An unreadable receipt cannot authorize a process wait. Withdraw only
        # our exact startup command and use the session lease to confirm exit.
        process = None
    if action == "Check":
        if process is not None:
            process.close()
        return "ready" if current is not None and process is not None else (
            "absent" if current is None and process is None else "stopped")
    if action == "Restore":
        try:
            slot.change(command, register=False)
            if process is not None:
                require(process.wait(timeout), "Watcher is still shutting down. Retry Restore original setup.")
        finally:
            if process is not None:
                process.close()
        wait_idle()
        require(slot.read() is None, "Watcher registration changed during restore")
        return "absent"
    require(action == "Install", "Unknown watcher setup action")
    if process is not None:
        process.close()
        require(current is not None, "Wait for the previous watcher to shut down")
        return "ready"
    wait_idle()
    added = slot.change(command, register=True)
    child = None
    try:
        child = launch()
        deadline = time.monotonic() + timeout
        while child.poll() is None and time.monotonic() < deadline:
            ready = registration.ready_process(plan)
            if ready is not None:
                with closing(ready):
                    require(ready.pid == child.pid and registration.owns(), "Unexpected watcher readiness process")
                    return "ready"
            time.sleep(.1)
        raise ValueError("Watcher did not become ready")
    except BaseException as error:
        if added:
            try:
                slot.change(command, register=False)
                if child is not None:
                    child.wait(timeout=12)
            except (OSError, ValueError, subprocess.TimeoutExpired) as cleanup:
                raise ValueError(f"{error}. Watcher rollback did not finish: {cleanup}") from cleanup
        raise


def setup(action, expected):
    require(not WATCH["c"].windll.shell32.IsUserAnAdmin(), "Use an ordinary-user setup session")
    native = WATCH["PROBE"]["driver"]()
    local = native.s.known_folder("f1b32785-6fba-4fcf-9d55-7b8e7f157091")
    root = local / "SL3RebuildNativeWatcher"
    registration = WATCH["SignInRegistration"](root)
    slot = StartupSlot()

    def wait_idle():
        with WATCH["watcher_lease"](timeout_ms=12000):
            pass

    def launch():
        return subprocess.Popen(registration.command, executable=str(registration.python), cwd=root,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NO_WINDOW)

    with WATCH["watcher_lease"](SETUP_MUTEX):
        missing = not (root.exists() or root.is_symlink() or root.is_junction())
        if action in ("Check", "Restore") and missing:
            current = slot.read()
            if current is None:
                return "absent"
            require(current == (registration.command, winreg.REG_SZ), "The sign-in slot is owned by another setup")
            if action == "Check":
                return "recovery-required"
        if action != "Check":
            readiness = runpy.run_path(str(HERE / "inspect-sl3-session-readiness.py"))
            require(not readiness["running_serato"]()["running"], "Close Serato before changing watcher setup")
        if action == "Restore" and missing:
            plan = read_payload(HERE.parent, expected)["startupPlanSha256"]
            return coordinate(action, registration, plan, slot, launch, wait_idle)
        if action == "Install":
            require(native.observe()["state"] == "installed", "Install the reviewed driver stage first")
            require(slot.read() in (None, (registration.command, winreg.REG_SZ)),
                    "The sign-in slot is owned by another setup")
            if not root.exists():
                stage_payload(HERE.parent, root, expected)
        plan = read_payload(root, expected)["startupPlanSha256"]
        status = coordinate(action, registration, plan, slot, launch, wait_idle)
        if action == "Check" and status == "absent":
            return "stopped"  # A verified payload still needs restoration or registration.
        if action == "Restore":
            require(HERE.parent.resolve() != root, "Restore must run from the original installer folder")
            with WATCH["watcher_lease"]():
                require(slot.read() is None, "Watcher registration changed during retirement")
                retire_payload(root, expected)
        return status


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("Check", "Install", "Restore"))
    parser.add_argument("--expected-payload-sha256", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{64}", args.expected_payload_sha256):
        parser.error("Expected a lowercase watcher payload SHA-256")
    try:
        print(setup(args.action, args.expected_payload_sha256))
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")
