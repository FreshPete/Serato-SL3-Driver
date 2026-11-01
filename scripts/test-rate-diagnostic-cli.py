"""Reject malformed diagnostic invocations; probe a valid one only if no UsbDk service exists."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def absent_service():
    # An affirmative ERROR_SERVICE_DOES_NOT_EXIST is required. Access-denied,
    # transient failures and stopped-but-installed services never permit a run.
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.OpenSCManagerW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    api.OpenSCManagerW.restype = wintypes.HANDLE
    api.OpenServiceW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD]
    api.OpenServiceW.restype = wintypes.HANDLE
    api.CloseServiceHandle.argtypes = [wintypes.HANDLE]
    api.CloseServiceHandle.restype = wintypes.BOOL
    manager = api.OpenSCManagerW(None, None, 1)
    if not manager:
        return False
    try:
        service = api.OpenServiceW(manager, "UsbDk", 4)
        error = ctypes.get_last_error()
        if service:
            api.CloseServiceHandle(service)
            return False
        return error == 1060
    finally:
        api.CloseServiceHandle(manager)


def main():
    if os.name != "nt":
        raise RuntimeError("Windows-only CLI check")
    rejected = [["--select-rate"], ["--select-rate", "96000"], ["--select-rate", "+48000"],
                ["--select-rate", "48000 "], ["--select-rate", "48000", "--select-rate", "44100"],
                ["--select-rate", "48000", "--output", "unused"],
                ["--select-rate", "48000", "--helper", "unused"]]
    for conflict in ("--plan", "--list", "--capture", "--duplex-silence", "--worker", "--stream-worker"):
        rejected.append(["--select-rate", "48000", conflict, "--helper", "unused", "--output", "unused"])
    records = []
    for configuration in ("Release", "Debug"):
        exe = ROOT / "artifacts/build/native" / configuration / "sl3_usbdk.exe"
        for arguments in rejected:
            result = subprocess.run([str(exe), *arguments], capture_output=True, text=True, timeout=5)
            if result.returncode != 2:
                raise RuntimeError(f"Malformed arguments not rejected: {arguments}: {result.returncode}")
        record = {"configuration": configuration, "executableSha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
                  "invalidCasesRejected": len(rejected), "absentServiceTested": False}
        if absent_service():
            with tempfile.TemporaryDirectory(prefix="sl3-rate-cli-") as temporary:
                output = Path(temporary) / "fresh"
                result = subprocess.run([str(exe), "--select-rate", "48000", "--helper", str(Path(temporary) / "absent.dll"),
                                         "--output", str(output)], capture_output=True, text=True, timeout=5)
                if result.returncode != 1 or "Win32=1060" not in result.stderr:
                    raise RuntimeError("Expected explicit absent-service rejection")
                progress = json.loads((output / "rate.json").read_text(encoding="utf-8"))
                if progress.get("phase") != "before service query or helper load":
                    raise RuntimeError("Advanced beyond absent-service boundary")
                record.update(absentServiceTested=True, serviceError=1060, helperLoaded=False,
                              deviceRedirected=False, rateWrites=0, progress=progress)
        records.append(record)
    output = ROOT / "analysis/rate-diagnostic-cli.json"
    output.write_text(json.dumps({"cases": rejected, "builds": records}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(records))


if __name__ == "__main__":
    main()
