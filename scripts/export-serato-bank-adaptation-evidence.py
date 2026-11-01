"""Verify the static user/host bank split and our simulated IASIO retry test.

Reads original PE bytes and existing build records; executes no vendor/device code.
"""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "sl3_image", ROOT / "scripts/export-serato-clock-handshake-evidence.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
require = helper.require


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    app = helper.Image("artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe", helper.CURRENT_SHA)
    reports = {}
    for filename in (
        "serato500-portaudio-bank-open-01.json", "serato500-pa-open-dispatch-02.json",
        "serato500-pa-asio-initialize-03.json", "serato500-pa-asio-open-04.json",
        "serato500-pa-buffer-wrapper-05.json", "serato500-pa-asio-callback-06.json",
        "serato500-pa-buffer-end-07.json",
    ):
        path = ROOT / "analysis" / filename
        report = load(path)
        require(report["binary_sha256"] == app.sha, "Focused image mismatch")
        for row in report["functions"]:
            require(row["complete"] and (int(row["start"], 16), int(row["end_exclusive"], 16)) in app.spans,
                    "Incomplete or mismatched unwind range")
        reports[filename] = digest(path)

    require(struct.unpack("<Q", app.data(0x1431d7248 + 8, 8))[0] == 0x1421e60a0, "Connection slot changed")
    checks = [
        (0x1421e60ce, "cvttsd2si", "r9d, qword ptr [r8]"),
        (0x1421e60d3, "mov", "r8d, dword ptr [r8 + 8]"),
        (0x1421e60f3, "call", "0x1421e69b0"),
        (0x142218ed2, "mov", "qword ptr [rax + 0x38], rcx"),
        (0x1422170ef, "lea", "r8, [rbx + 0xbc]"),
        (0x142217104, "call", "0x142221eb0"),
        (0x142221eea, "call", "qword ptr [rax + 0x58]"),
        (0x142217745, "call", "0x142221e00"),
        (0x142217756, "je", "0x1422177d4"),
        (0x142217758, "cmp", "ebx, dword ptr [r13 + 0x1d8]"),
        (0x14221775f, "je", "0x1422177ad"),
        (0x142217777, "mov", "ebx, dword ptr [r13 + 0x1d8]"),
        (0x142217787, "mov", "dword ptr [rsp + 0x78], ebx"),
        (0x14221779e, "mov", "r8d, ebx"),
        (0x1422177a4, "call", "0x142221e00"),
        (0x1422177ab, "je", "0x1422177d4"),
        (0x142217aa1, "mov", "eax, dword ptr [rsp + 0x78]"),
        (0x142217aaa, "mov", "dword ptr [rsp + 0x50], eax"),
        (0x142217ab9, "mov", "eax, dword ptr [rsp + 0x770]"),
        (0x142217ac0, "mov", "dword ptr [rsp + 0x40], eax"),
        (0x142217adf, "call", "0x142221680"),
        (0x14222169b, "mov", "edi, dword ptr [rsp + 0x98]"),
        (0x1422216e2, "mov", "dword ptr [rcx], edi"),
        (0x14222170b, "mov", "r15d, dword ptr [rsp + 0xa0]"),
        (0x142221713, "mov", "dword ptr [rcx + 4], r15d"),
        (0x142221717, "mov", "ecx, dword ptr [rsp + 0xa8]"),
        (0x14222171e, "mov", "dword ptr [rbx + 8], ecx"),
        (0x1422219bd, "mov", "dword ptr [rbx + 0xc], r8d"),
        (0x14222145b, "cmp", "dword ptr [rbx + 0xc], r12d"),
        (0x14222145f, "je", "0x1422215cf"),
    ]
    for address, opcode, operands in checks:
        app.at(address, opcode, operands)
    require(app.rip(app.at(0x142218eb6, "lea")) == 0x142217160, "Wrong ASIO opener installed")
    callback_table = struct.unpack("<4Q", app.data(0x143a86a00, 32))
    require(callback_table == (0x1422160a0, 0x1422166e0, 0x142216700, 0x142216150), "Callback table changed")

    builds = []
    folder = ROOT / "artifacts/build/native"
    for configuration in ("Release", "Debug"):
        path = folder / f"native-build-{configuration}.json"
        build = load(path)
        require(build["configuration"] == configuration, "Configuration mismatch")
        for source, expected in build["inputs"].items():
            require(digest(ROOT / source).upper() == expected.upper(), f"Stale build input: {source}")
        require(digest(ROOT / "scripts/build-native.ps1").upper() == build["buildScriptSha256"].upper(), "Stale build script")
        log = folder / f"ctest-{configuration}.log"
        require(digest(log).upper() == build["ctestLogSha256"].upper(), "Stale log")
        require("100% tests passed, 0 tests failed out of 27" in log.read_text(encoding="utf-8"), "Incomplete suite")
        facade = build["asioComponent"]["driverFacade"]
        require(facade["preferredBankRetryTested"] and facade["actualAsioVtableSessionsTested"]
                and facade["rejectedApplicationFrames"] == 240 and facade["acceptedPreferredFrames"] == 128
                and facade["timingProfileSynthetic"] and not facade["physicalAudioTested"], "Retry checkpoint missing")
        for binary, field in (("sl3_asio_session_tests.exe", "sessionAbiTestExecutableSha256"),
                              ("sl3_asio_session_fixture.dll", "sessionFixtureDllSha256"),
                              ("sl3_driver_facade_tests.exe", "testExecutableSha256")):
            require(digest(folder / configuration / binary).upper() == facade[field].upper(), "Stale tested binary")
        builds.append({"configuration": configuration, "manifestSha256": digest(path),
                       "ctestLogSha256": digest(log), "nativeTestsPassed": 27, "retry": facade})
    record = {
        "generatedUtc": datetime.now(timezone.utc).isoformat(),
        "currentSeratoSha256": app.sha, "focusedReportsSha256": reports,
        "checkedInstructions": [f"{a:x}: {o} {v}" for a, o, v in checks],
        "asioOpenVA": "142217160", "processorInitializeVA": "142221680",
        "processorEndVA": "142221440", "callbackTable": [hex(v) for v in callback_table],
        "staticFinding": "Requested user frames and selected ASIO host frames remain separate; failed requested-bank creation retries driver preferred frames.",
        "builds": builds, "seratoExecuted": False, "portAudioExecuted": False,
        "physicalAudioTested": False, "productionBankRulesChanged": False,
        "limits": "Our real IASIO vtable retry uses a simulated worker and synthetic timing. Static adaptation does not prove physical latency, stable USB audio, current descriptor/handshake integration or DVS.",
    }
    output = ROOT / "docs/evidence/serato500-bank-adaptation.json"
    output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"Verified static bank adaptation and 27/27 Release/Debug retry evidence: {output}")


if __name__ == "__main__":
    main()
