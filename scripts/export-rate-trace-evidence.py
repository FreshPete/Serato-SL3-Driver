"""Record tested rate-trace preparation without executing any live scenario."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    log = ROOT / "analysis/rate-traced-python-tests.log"
    text = log.read_text(encoding="utf-8")
    require("Ran 36 tests" in text and text.rstrip().endswith("OK") and "skipped" not in text, "Python suite incomplete")
    builds = []
    for configuration in ("Release", "Debug"):
        manifest = ROOT / f"artifacts/build/native/native-build-{configuration}.json"
        build = json.loads(manifest.read_text(encoding="utf-8-sig"))
        for name, expected in build["inputs"].items():
            require(digest(ROOT / name).upper() == expected.upper(), f"Stale native source {name}")
        require(digest(ROOT / "scripts/build-native.ps1").upper() == build["buildScriptSha256"].upper(), "Stale build script")
        exe = ROOT / f"artifacts/build/native/{configuration}/sl3_usbdk.exe"
        require(digest(exe).upper() == build["usbdk"]["executableSha256"].upper(), "Native executable changed")
        require(build["rateSelection"]["nativeDiagnosticImplemented"] and not build["rateSelection"]["physicalRateChangeTested"], "Unexpected rate checkpoint")
        builds.append({"configuration": configuration, "manifestSha256": digest(manifest), "nativeSha256": digest(exe)})
    sources = ["scripts/test-usbdk-traced.ps1", "scripts/validate-usbdk-rate.py", "scripts/validate-usbdk-capture.py",
               "tests/test_usbdk_rate_evidence.py", "scripts/capture-usb-startup.ps1",
               "scripts/preflight-usbdk.ps1", "scripts/collect-windows-state.ps1"]
    result = {"generatedUtc": datetime.now(timezone.utc).isoformat(),
              "scope": "Traced rate workflow preparation, read-only evidence validation and synthetic/plan tests",
              "sourceSha256": {name: digest(ROOT / name) for name in sources},
              "pythonTestsPassed": 36, "newRateEvidenceAndPlanTests": 9, "pythonLogSha256": digest(log),
              "nativeBuildsReusedWithoutSourceChange": builds,
              "nativeRateEvidenceSha256": digest(ROOT / "docs/evidence/rate-selection-build.json"),
              "planModesTested": ["List", "Capture", "DuplexSilence", "Rate 44100", "Rate 48000"],
              "rateRequiresPriorSameBuildCapture": True, "explicitTargetRequired": True,
              "automaticRateRestoration": False, "failurePreservesUnknownEffects": True,
              "liveRunnerInvoked": False, "physicalRateChangeTested": False,
              "limits": ["Live orchestration and native pending I/O have not been exercised",
                         "Validator checks record consistency, not hardware attestation or USB command correlation",
                         "Snapshot recovery is separate from restoring the prior sample rate",
                         "Physical audio/clock/latency, current Serato/DVS and Mac validation remain pending"]}
    path = ROOT / "docs/evidence/rate-trace-preparation.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Verified 36 Python tests and unchanged diagnostic builds: {path}")


if __name__ == "__main__":
    main()
