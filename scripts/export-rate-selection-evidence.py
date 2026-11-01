"""Pin original rate instructions, injected runner tests and diagnostic build."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sl3_image", ROOT / "scripts/export-serato-clock-handshake-evidence.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
require = helper.require


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    kernel = helper.Image("artifacts/extracted/rane-windows/x64/strmdrv.sys",
                          "e8e992a8ece1a57eab337d815a406b9f815954176c03db545fcf6d951ec615f5")
    checks = [
        (0x11aa2, "movzx", "edi, word ptr [rcx + 0x2d180]"),
        (0x11ab2, "cmp", "di, 0xac44"), (0x11ab9, "cmp", "di, 0xbb80"),
        (0x11acb, "mov", "dl, 0x31"), (0x11acd, "rol", "r8w, 8"),
        (0x11ad2, "call", "0x1184c"),
        (0x11adf, "lea", "r9d, [r13 + 2]"), (0x11ae3, "mov", "dl, 0x31"),
        (0x11af7, "call", "0x118c4"),
        (0x11afc, "xor", "r8d, r8d"), (0x11aff, "mov", "dl, 0x30"),
        (0x11b0d, "call", "0x1184c"),
        (0x11b12, "lea", "r9d, [r13 + 2]"), (0x11b1b, "mov", "dl, 0x30"),
        (0x11b29, "call", "0x118c4"),
        (0x11b38, "movzx", "ecx, word ptr [rsp + 0x50]"),
        (0x11b54, "cmp", "ecx, edx"), (0x11b56, "cmovne", "eax, r13d"),
        (0x11b5f, "mov", "dword ptr [rbx + 0x2c4b0], r8d"),
    ]
    for va, op, operands in checks:
        kernel.at(va, op, operands)
    kernel.at(0x11ad7, "xor", "r13d, r13d")
    sources = ["CMakeLists.txt", "scripts/build-native.ps1", "src/core/control_frames.hpp",
               "src/core/control_frames.cpp", "src/core/rate_selection.hpp", "src/core/rate_selection.cpp",
               "tests/native/rate_selection_tests.cpp", "src/core/rate_diagnostic.hpp",
               "src/core/rate_diagnostic.cpp", "src/windows/usbdk_main.cpp"]
    callers = []
    for directory in (ROOT / "src", ROOT / "tests/native"):
        for path in directory.rglob("*.cpp"):
            if "RateSelection" in path.read_text(encoding="utf-8-sig"):
                callers.append(path.relative_to(ROOT).as_posix())
    require(sorted(callers) == ["src/core/rate_diagnostic.cpp", "src/core/rate_selection.cpp", "tests/native/rate_selection_tests.cpp"],
            "Unexpected runtime rate-selection caller")
    builds = []
    cli_path = ROOT / "analysis/rate-diagnostic-cli.json"
    cli = json.loads(cli_path.read_text(encoding="utf-8"))
    for configuration in ("Release", "Debug"):
        folder = ROOT / "artifacts/build/native"
        manifest = folder / f"native-build-{configuration}.json"
        build = json.loads(manifest.read_text(encoding="utf-8-sig"))
        require(build["configuration"] == configuration, "Wrong configuration")
        for path, expected in build["inputs"].items():
            require(digest(ROOT / path).upper() == expected.upper(), f"Stale input {path}")
        require(digest(ROOT / "scripts/build-native.ps1").upper() == build["buildScriptSha256"].upper(), "Stale build script")
        log = folder / f"ctest-{configuration}.log"
        require(digest(log).upper() == build["ctestLogSha256"].upper(), "Stale log")
        require("100% tests passed, 0 tests failed out of 28" in log.read_text(encoding="utf-8")
                and len(build["ctestTests"]) == 28 and "sl3_rate_selection_tests" in build["ctestTests"], "Incomplete suite")
        record = build["rateSelection"]
        require(record["testsPassed"] and not record["offlineOnly"] and record["maximumRequests"] == 3
                and record["maximumReceivedFrames"] == 12 and record["nativeSetterConnected"]
                and record["nativeDiagnosticImplemented"] and not record["automaticStartupRateChanges"]
                and not record["physicalRateChangeTested"], "Rate checkpoint inconsistent")
        executable = folder / configuration / "sl3_rate_selection_tests.exe"
        require(digest(executable).upper() == record["testExecutableSha256"].upper(), "Stale tested executable")
        cli_record = next(row for row in cli["builds"] if row["configuration"] == configuration)
        require(cli_record["executableSha256"].upper() == build["usbdk"]["executableSha256"].upper()
                and cli_record["invalidCasesRejected"] == 13 and len(cli["cases"]) == 13, "Stale CLI rejection evidence")
        require(digest(folder / configuration / "sl3_usbdk.exe").upper() == build["usbdk"]["executableSha256"].upper(), "Stale native diagnostic")
        if cli_record["absentServiceTested"]:
            require(cli_record["serviceError"] == 1060 and not cli_record["helperLoaded"]
                    and not cli_record["deviceRedirected"] and cli_record["rateWrites"] == 0, "Unexpected live CLI action")
        builds.append({"configuration": configuration, "testsPassed": 28,
                       "manifestSha256": digest(manifest), "ctestLogSha256": digest(log),
                       "rateTestSha256": digest(executable)})
    sdk = ROOT / "artifacts/build/native-without-sdk"
    log = sdk / "ctest-rate-diagnostic.log"
    cache = (sdk / "CMakeCache.txt").read_text(encoding="utf-8")
    require("SL3_BUILD_ASIO_COMPONENT:BOOL=OFF" in cache and "C:/definitely-absent-sl3-sdk" in cache, "SDK-free gate changed")
    require("100% tests passed, 0 tests failed out of 20" in log.read_text(encoding="utf-8"), "SDK-free suite incomplete")
    result = {
        "generatedUtc": datetime.now(timezone.utc).isoformat(),
        "scope": "Original kernel rate-change contract, injected diagnostic runner and explicit native rate-test mode; no physical rate change",
        "kernelSha256": kernel.sha,
        "checkedInstructions": [f"{va:x}: {op} {operands}" for va, op, operands in checks],
        "sourceSha256": {p: digest(ROOT / p) for p in sources},
        "cli": {"reportSha256": digest(cli_path), "runnerSha256": digest(ROOT / "scripts/test-rate-diagnostic-cli.py"),
                "builds": cli["builds"]},
        "sourceCallers": callers, "builds": builds,
        "sdkFree": {"testsPassed": 20, "ctestLogSha256": digest(log),
                    "cacheSha256": digest(sdk / "CMakeCache.txt"),
                    "rateTestSha256": digest(sdk / "Release/sl3_rate_selection_tests.exe")},
        "transaction": {"targetsHz": [44100, 48000], "maximumRequests": 3,
                        "maximumReceivedFrames": 12, "setterReplyBytesOpaque": 2,
                        "freshReadbackRequired": True, "automaticRetry": False,
                        "automaticRollbackWrite": False, "noncopyable": True},
        "nativeSetterConnected": True, "automaticStartupRateChanges": False,
        "physicalRateChangeTested": False,
        "limits": ["Native diagnostic requires an exclusive fresh redirect, keeps audio alts inactive, uses a 3000 ms control budget and bounded cancellation/drain",
                   "Post-set failure preserves possible device change; it cannot prove restoration",
                   "Matched readback is device reporting, not oscillator measurement or stream validity",
                   "Injected runner tests do not execute actual native pending transfers or prove driver admission",
                   "Current ASIO facade remains observed-rate-only; no physical/application/DVS result"]}
    output = ROOT / "docs/evidence/rate-selection-build.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Verified original rate sequence and injected diagnostic, 28/28 Release+Debug, 20/20 SDK-free: {output}")


if __name__ == "__main__":
    main()
