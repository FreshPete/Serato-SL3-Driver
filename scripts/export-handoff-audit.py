"""Bind the read-only host snapshot and existing tests to a full-scope handoff."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    snapshot = ROOT / "analysis/handoff-host-state.json"
    state = load(snapshot)
    require(len(state["devices"]) == 1 and state["devices"][0]["problemCode"] == 39
            and state["devices"][0]["service"] == "strmdrv", "Host state changed; reassess")
    require(state["usbDkDrivers"] == [] and state["developmentTrustEntries"] == [], "Dependency/trust state changed")
    require(not any(state["rebuiltComRegistration"].values()) and not any(state["adjacentProductionConfiguration"].values()), "Deployment state changed")
    builds = []
    for configuration in ("Release", "Debug"):
        manifest = ROOT / f"artifacts/build/native/native-build-{configuration}.json"
        build = load(manifest)
        for path, expected in build["inputs"].items():
            require(digest(ROOT / path).upper() == expected.upper(), f"Stale native source: {path}")
        require(digest(ROOT / "scripts/build-native.ps1").upper() == build["buildScriptSha256"].upper(), "Stale build script")
        log = ROOT / f"artifacts/build/native/ctest-{configuration}.log"
        require(digest(log).upper() == build["ctestLogSha256"].upper()
                and "100% tests passed, 0 tests failed out of 28" in log.read_text(encoding="utf-8"), "Native test evidence stale")
        for name, expected in (("sl3_usbdk.exe", build["usbdk"]["executableSha256"]),
                               ("sl3_asio.dll", build["asioComponent"]["comDllSha256"])):
            require(digest(ROOT / f"artifacts/build/native/{configuration}/{name}").upper() == expected.upper(), "Native binary changed")
        builds.append({"configuration": configuration, "testsPassed": 28,
                       "manifestSha256": digest(manifest), "ctestLogSha256": digest(log)})
    python_log = ROOT / "analysis/rate-traced-python-tests.log"
    text = python_log.read_text(encoding="utf-8")
    require("Ran 36 tests" in text and text.rstrip().endswith("OK"), "Python evidence incomplete")
    sdk_log = ROOT / "artifacts/build/native-without-sdk/ctest-rate-diagnostic.log"
    require("100% tests passed, 0 tests failed out of 20" in sdk_log.read_text(encoding="utf-8"), "SDK-free evidence incomplete")
    gates = {
        "normalSecurityPhysicalTransport": "incomplete: original code 39; candidate UsbDk absent",
        "physicalCapturePlayback": "unverified: original native code and simulated tests only",
        "rateAndControls": "partial: earlier 44100 getter observed; setter/routing/real response unverified",
        "hardwareAsio": "unverified: real COM/IASIO simulated sessions; no deployment or measured timing profile",
        "currentSeratoIntegration": "incomplete: retained discontinued path; external descriptor/handshake route unestablished",
        "twoDeckDvs": "unverified: no physical calibration/control-vinyl session",
        "latencyAndStability": "unverified: no measured loopback, four-hour run or required recovery cycles",
        "productionInstallationRemoval": "incomplete: no release configuration/registration/admitted hardware transport",
        "macosTahoe": "prepared only: no target Mac, native build/runtime or Core Audio/DVS verification",
        "reviewableProgressReport": "provided in STATUS.md; does not establish the full rebuild",
    }
    result = {"generatedUtc": datetime.now(timezone.utc).isoformat(), "scope": "Full objective remains unmet",
              "hostSnapshotSha256": digest(snapshot), "hostSnapshot": state, "nativeBuilds": builds,
              "python": {"testsPassed": 36, "logSha256": digest(python_log), "rerunForAudit": False},
              "sdkFree": {"testsPassed": 20, "logSha256": digest(sdk_log), "rerunForAudit": False},
              "acceptanceGates": gates, "complete": False,
              "officialSourcesChecked": ["https://serato.com/dj/hardware/rane-sl3",
                  "https://support.rane.com/en/support/solutions/articles/69000829417-rane-dj-hardware-won-t-connect-to-serato-",
                  "https://support.serato.com/hc/en-us/articles/203401184-Does-my-mixer-controller-interface-support-DVS-in-Serato-DJ-Pro"],
              "limits": ["Fresh non-elevated Secure Boot query is unknown, not false; earlier elevated enabled evidence is historical",
                         "No new device access, trust/install/binding/security change, vendor execution or firmware operation",
                         "Software tests do not prove physical transport/audio, timing, application integration or DVS"]}
    output = ROOT / "docs/evidence/handoff-audit.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Audited incomplete full objective and current host/build evidence: {output}")


if __name__ == "__main__":
    main()
