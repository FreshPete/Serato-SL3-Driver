"""Publish and retire a bounded diagnostic broker session from the desktop token."""
import argparse
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import json
import msvcrt
from pathlib import Path
import subprocess
import time


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(controller, *args):
    result = subprocess.run(
        [str(controller), *map(str, args)], capture_output=True, text=True,
        encoding="utf-8", timeout=10, check=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return json.loads(result.stdout)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


@contextmanager
def handoff_lock(session):
    with session.with_suffix(".lock").open("a+b") as lock:
        deadline = time.monotonic() + 25
        while True:
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                require(time.monotonic() < deadline, "Diagnostic broker handoff is still in progress")
                time.sleep(.05)
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


@contextmanager
def process_handle(pid):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    handle = kernel.OpenProcess(0x101000, False, pid)  # SYNCHRONIZE | QUERY_LIMITED_INFORMATION
    if not handle:
        error = ctypes.get_last_error()
        if error != 87:  # ERROR_INVALID_PARAMETER: no such PID
            raise ctypes.WinError(error)
        yield None
        return
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(item) for item in times)):
            raise ctypes.WinError(ctypes.get_last_error())
        created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        yield created, lambda timeout: kernel.WaitForSingleObject(handle, timeout) == 0
    finally:
        kernel.CloseHandle(handle)


def start(controller, source, session, pointer, controller_sha, limit_ms=120000):
    require(type(limit_ms) is int and 1000 <= limit_ms <= 600000, "Diagnostic lifetime must be 1000..600000 ms")
    require(digest(controller) == controller_sha, "Diagnostic controller hash differs")
    config = session / "sl3-asio.conf"
    ownership = session.with_suffix(".pointer.json")
    require(not session.with_suffix(".closed").exists(), "Diagnostic broker handoff has closed")
    require(not session.exists() and not ownership.exists() and not pointer.exists()
            and not pointer.with_name(pointer.name + ".pending").exists(), "Fresh session and pointer required")
    inspection = run(controller, "--inspect-input", "--input", source)
    require(inspection["rateHz"] == 44100 and inspection["bufferFrames"] == 128
            and inspection["latencyAvailable"] is False, "Expected unmeasured 44.1 kHz input")
    pointer.parent.mkdir(exist_ok=True)
    with session.with_suffix(".stdout").open("xb") as out, session.with_suffix(".stderr").open("xb") as err:
        process = subprocess.Popen(
            [str(controller), "--run", "--input", str(source), "--output", str(session), "--limit-ms", str(limit_ms)],
            stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    expected_sha = None
    try:
        ready_path = session / "ready.json"
        deadline = time.monotonic() + 12
        while not ready_path.exists():
            require(process.poll() is None and time.monotonic() < deadline, "Diagnostic broker did not become ready")
            time.sleep(.025)
        ready = read(ready_path)
        config_sha = digest(config)
        require(process.poll() is None and ready["controllerPid"] == process.pid
                and ready["configSha256"] == config_sha and ready["brokerSha256"] == controller_sha
                and ready["kind"] == inspection["kind"]
                and ready["rateHz"] == 44100 and ready["workerSha256"] == inspection["workerSha256"]
                and ready["limitMs"] == limit_ms,
                "Diagnostic broker readiness does not match the launched process")
        expected = (
            f"SL3-ASIO-SESSION-POINTER-1\nconfiguration={config}\nconfiguration_sha256={config_sha}\n"
        ).encode("utf-8")
        expected_sha = hashlib.sha256(expected).hexdigest()
        with process_handle(process.pid) as identity:
            require(identity and process.poll() is None, "Cannot bind live diagnostic controller")
            with ownership.open("x", encoding="utf-8") as stream:
                json.dump({"controllerSha256": controller_sha, "configSha256": config_sha,
                           "controllerPid": process.pid, "controllerCreatedFileTime": str(identity[0]),
                           "pointerSha256": expected_sha, "pointer": str(pointer)}, stream)
        result = run(controller, "--publish-pointer", "--config", config, "--pointer", pointer)
        require(result["pointerPublished"] is True and digest(pointer) == expected_sha,
                "Published diagnostic pointer differs")
    except Exception:
        try:
            if expected_sha is not None and ownership.is_file() and pointer.exists():
                run(controller, "--withdraw-pointer", "--pointer", pointer, "--sha256", expected_sha)
        finally:
            if process.poll() is None and config.is_file():
                run(controller, "--stop", "--config", config)
        raise
    return {"pointerPublished": True, "controllerPid": process.pid, "configSha256": config_sha}


def stop(controller, session, pointer, controller_sha):
    require(digest(controller) == controller_sha, "Diagnostic controller hash differs")
    config = session / "sl3-asio.conf"
    result_path = session / "result.json"
    ownership = read(session.with_suffix(".pointer.json"))
    require(ownership["controllerSha256"] == controller_sha and ownership["pointer"] == str(pointer)
            and ownership["configSha256"] == digest(config), "Diagnostic ownership record differs")
    if pointer.exists():
        run(controller, "--withdraw-pointer", "--pointer", pointer, "--sha256", ownership["pointerSha256"])
    with process_handle(ownership["controllerPid"]) as identity:
        if identity and str(identity[0]) == ownership["controllerCreatedFileTime"]:
            if not result_path.exists() and not identity[1](0):
                try:
                    run(controller, "--stop", "--config", config)
                except subprocess.CalledProcessError:
                    if not result_path.exists():
                        raise
            require(identity[1](15000), "Exact diagnostic controller still running")
    require(result_path.is_file(), "Diagnostic broker did not report retirement")
    result = read(result_path)
    require(result["processExited"] and result["jobEmpty"] and result["ioRetiredVerified"]
            and result["deviceReleasedVerified"] and not pointer.exists(),
            "Diagnostic worker retirement is incomplete")
    return {**result, "controllerExited": True}


def close_handoff(controller, session, pointer, controller_sha):
    session.with_suffix(".closed").touch(exist_ok=True)
    if not session.with_suffix(".pointer.json").exists():
        require(not session.exists() and not session.with_suffix(".stdout").exists()
                and not session.with_suffix(".stderr").exists()
                and not pointer.exists() and not pointer.with_name(pointer.name + ".pending").exists(),
                "Broker startup lacks a complete ownership record; preserve files for review")
        return {"controllerExited": True, "brokerStarted": False}
    return stop(controller, session, pointer, controller_sha)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop"))
    parser.add_argument("--controller", type=Path, required=True)
    parser.add_argument("--controller-sha256", required=True)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--pointer", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--limit-ms", type=int, help="Start lifetime, default 120000, maximum 600000")
    args = parser.parse_args()
    require(all(path.is_absolute() for path in (args.controller, args.session, args.pointer)), "Absolute paths required")
    with handoff_lock(args.session):
        if args.action == "start":
            require(args.input is not None and args.input.is_absolute(), "Start requires an absolute input")
            result = start(args.controller, args.input, args.session, args.pointer, args.controller_sha256,
                           120000 if args.limit_ms is None else args.limit_ms)
        else:
            require(args.input is None and args.limit_ms is None, "Stop does not take an input or lifetime")
            result = close_handoff(args.controller, args.session, args.pointer, args.controller_sha256)
    print(json.dumps(result))
