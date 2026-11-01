"""Pin the original hardware-exchange path and tested original control codec."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
helper_path = ROOT / "scripts/export-serato-clock-handshake-evidence.py"
spec = importlib.util.spec_from_file_location("sl3_static_image_reader", helper_path)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
Image, require = helper.Image, helper.require


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    app = Image("artifacts/extracted/Serato DJ Pro 2.5.5/tree/Serato/Serato DJ Pro/Serato DJ Pro.exe", helper.OLD_SHA)
    driver = Image("artifacts/extracted/rane-windows/x64/RaneAsioSL3.dll", helper.DRIVER_SHA)
    kernel_sha = "e8e992a8ece1a57eab337d815a406b9f815954176c03db545fcf6d951ec615f5"
    kernel = Image("artifacts/extracted/rane-windows/x64/strmdrv.sys", kernel_sha)
    reports = {}

    def focused(image, file, start):
        path = ROOT / "analysis" / file
        report = load(path)
        require(report["binary_sha256"] == image.sha, "Focused report targets another image")
        row = next(r for r in report["functions"] if r["start"] == start)
        require(row["complete"] and (int(start, 16), int(row["end_exclusive"], 16)) in image.spans, "Incomplete focused report/range mismatch")
        reports[file] = digest(path)
        return row["pseudocode"].replace("\r", "")

    loader = focused(app, "serato255-sl3-api-loader-15.json", "14069afd0")
    caller = focused(app, "serato255-sl3-api-state-14.json", "140691980")
    through = focused(app, "serato255-sl3-api-state-14.json", "140691cb0")
    through_read = focused(app, "serato255-sl3-api-state-14.json", "140691c10")
    timer = focused(driver, "rane-driver-timer-03.json", "1800068a0")
    command = focused(driver, "rane-control-command-04.json", "180009ac0")
    ioctl = focused(kernel, "rane-control-ioctl-dispatch-05.json", "0001a168")
    require(app.text(0x1447bbf20) == "sl3_driver_timer" and "1447bbf20" in loader and "param_1 + 0x80" in loader, "Wrong export binding")
    require(struct.unpack("<Q", app.data(0x1447b9b08+0x70, 8))[0] == 0x140691980, "Wrong SL3 API vtable slot")
    app.at(0x140691a3a, "mov", "dword ptr [rsp + 0x20], 8")
    app.at(0x140691a42, "call", "qword ptr [rbx + 0x80]")
    app.at(0x140691a90, "call", "0x14054f520")
    app.at(0x140691aa2, "cmp", "rcx, qword ptr [rsp + 0x88]")
    app.at(0x140691ab6, "cmove", "eax, edx")
    require("param_1 + 0x80" in caller and "FUN_14054f520" in caller, "Wrong original response check")
    require("param_3 ^ 1" in through and "param_1 + 0x98" in through and "param_1 + 0x90" in through_read, "Control slice adapter changed")
    for index in ("0xe", "0x14", "8"):
        require(f"uVar1 = {index};" in through and f"uVar1 = {index};" in through_read, "Control table index changed")
    driver.pe.parse_data_directories(directories=[0])
    export = next(e for e in driver.pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name == b"sl3_driver_timer")
    require(driver.base+export.address == 0x180007140, "Wrong original timer export")
    thunk = next(driver.dis.disasm(driver.data(0x180007140, 5), 0x180007140))
    require(thunk.mnemonic == "jmp" and thunk.op_str == "0x1800068a0", "Timer thunk changed")
    require("param_3 < 8" in timer and "param_5 < 8" in timer and "param_1,0x44,0" in timer, "Timer contract changed")
    require("0x220010" in command and "param_5" in command, "IOCTL exchange changed")
    require("param_5 == 0x220010" in ioctl and "FUN_00011e80" in ioctl, "Kernel IOCTL route changed")
    kernel.at(0x1a45f, "call", "0x11e80")
    kernel.at(0x1205a, "sub", "eax, 0x41")
    kernel.at(0x12063, "mov", "edi, 1")
    for va in (0x12068, 0x12070, 0x12074):
        kernel.at(va, "sub", "eax, edi")
    kernel.at(0x12076, "je", "0x12099")
    kernel.at(0x120a3, "mov", "dl, 0x37")
    kernel.at(0x120a5, "call", "0x116a0")
    kernel.at(0x120aa, "mov", "r9d, 8")
    kernel.at(0x120b0, "mov", "dl, 0x37")
    kernel.at(0x120c1, "call", "0x118c4")

    builds = []
    folder = ROOT / "artifacts/build/native"
    for configuration in ("Release", "Debug"):
        record = folder / f"native-build-{configuration}.json"
        build = load(record)
        require(build["configuration"] == configuration, "Wrong build configuration")
        for path, expected in build["inputs"].items():
            require(digest(ROOT / path).upper() == expected.upper(), f"Stale build input: {path}")
        require(digest(ROOT / "scripts/build-native.ps1").upper() == build["buildScriptSha256"].upper(), "Stale build script")
        log = folder / f"ctest-{configuration}.log"
        require(digest(log).upper() == build["ctestLogSha256"].upper(), "Stale native log")
        require("100% tests passed, 0 tests failed out of 27" in log.read_text(encoding="utf-8"), "Incomplete native suite")
        require(len(build["ctestTests"]) == 27 and "sl3_control_frames_tests" in build["ctestTests"], "Control codec test missing")
        control = build["controlFrames"]
        require(control["testsPassed"] and control["maximumReceivedFrames"] == 4 and control["nativeRateQueryConnected"], "Control checkpoint missing")
        require(not control["additionalQueriesSubmitted"] and not control["deviceResponseVerified"] and not control["physicalQueriesTested"], "Unverified physical claim")
        test = folder / configuration / "sl3_control_frames_tests.exe"
        worker = folder / configuration / "sl3_usbdk.exe"
        require(digest(test).upper() == control["testExecutableSha256"].upper(), "Stale codec test binary")
        require(digest(worker).upper() == build["usbdk"]["executableSha256"].upper(), "Stale native worker")
        require(not build["usbdk"]["helperLoadedDuringPlan"] and not build["usbdk"]["physicalCaptureTested"], "Unexpected live build action")
        builds.append({"configuration": configuration, "manifestSha256": digest(record), "ctestLogSha256": digest(log),
                       "testCount": 27, "controlTestSha256": digest(test), "nativeWorkerSha256": digest(worker)})
    sdk_folder = ROOT / "artifacts/build/native-without-sdk"
    sdk_log = sdk_folder / "ctest-control-frames.log"
    require("100% tests passed, 0 tests failed out of 19" in sdk_log.read_text(encoding="utf-8"), "SDK-free suite incomplete")
    cache = (sdk_folder / "CMakeCache.txt").read_text(encoding="utf-8")
    require("SL3_BUILD_ASIO_COMPONENT:BOOL=OFF" in cache and "C:/definitely-absent-sl3-sdk" in cache, "SDK-free configuration changed")
    sources = ["CMakeLists.txt", "scripts/build-native.ps1", "src/core/control_frames.hpp", "src/core/control_frames.cpp",
               "tests/native/control_frames_tests.cpp", "src/windows/usbdk_main.cpp", "scripts/export-serato-clock-handshake-evidence.py"]
    result = {
        "generatedUtc": datetime.now(timezone.utc).isoformat(),
        "scope": "Static original hardware-challenge path plus compiled bounded control codec and existing native rate-query integration; no new USB query, original binary execution or application handshake success",
        "sourceSha256": {p: digest(ROOT / p) for p in sources}, "focusedReportSha256": reports,
        "originalImages": {"serato255": app.sha, "raneAsio": driver.sha, "raneKernel": kernel.sha},
        "originalExchange": {"apiFunction": "0x140691980", "dllExport": "sl3_driver_timer", "ioctl": "0x220010",
                             "getSelector": "0x44", "usbInterruptCommand": "0x37", "challengeBytes": 8, "replyBytes": 8,
                             "replyComparedWithTransformedChallenge": True, "liveVerified": False,
                             "kernelAssembly": kernel.window(0x1205a, 0, 35),
                             "comparisonAssembly": app.window(0x140691a95, 0, 7)},
        "codecQueries": [{"command": "0x30", "replyBytes": 2, "purpose": "reported rate"},
                         {"command": "0x32", "replyBytes": 22, "purpose": "opaque audio-control table"},
                         {"command": "0x35", "replyBytes": 6, "purpose": "overload bytes"},
                         {"command": "0x37", "replyBytes": 8, "purpose": "real device challenge response; no verifier or emulated reply"}],
        "maximumReceivedFrames": 4, "nativeRuntimeQueriesConnected": ["0x30"],
        "historicalControlSlices": {"apiChannelIndexToTableIndex": {"0": 14, "1": 20, "2": 8},
                                    "readFunction": "0x140691c10", "writeFunction": "0x140691cb0",
                                    "writeByteExpression": "incoming byte XOR 1", "sliceBytes": 1,
                                    "physicalJackOrEnableMeaningVerified": False, "nativeWritesImplemented": False},
        "additionalQueriesSubmitted": False, "hardwareResponseVerified": False,
        "builds": builds, "sdkFree": {"testCount": 19, "ctestLogSha256": digest(sdk_log),
                                      "cacheSha256": digest(sdk_folder / "CMakeCache.txt"),
                                      "controlTestSha256": digest(sdk_folder / "Release/sl3_control_frames_tests.exe")},
        "limits": ["Codec byte tests do not prove device acceptance, command effects or timing",
                   "No rate setter, route/status enable, reset or firmware operation is implemented by this codec",
                   "No driver-timer exchange is exposed through IPC or run on hardware",
                   "Current Serato integration, legitimate product/account requirements and physical DVS remain unresolved"],
    }
    output = ROOT / "docs/evidence/control-frames-build.json"
    output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(f"Verified original device exchange, 27/27 Release+Debug and 19/19 SDK-free; wrote {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
