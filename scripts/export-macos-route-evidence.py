"""Pin Mac package/API research and tested read-only preflight, without Mac I/O."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import plistlib
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, text):
    if not condition:
        raise ValueError(text)


def main():
    archive = ROOT/"artifacts/downloads/Sl3-2.0.1f2.zip"
    require(digest(archive) == "e6558b7d8c95148a9629a0c2a70dfb8e4dd0351fb03c43b158304a08f1617264", "Mac package archive changed")
    package_info = ROOT/"artifacts/extracted/rane-mac/pkg/SL3.pkg/PackageInfo"
    package = ET.fromstring(package_info.read_bytes())
    require(package.attrib["identifier"] == "com.rane.pkg.Sl3" and package.attrib["version"] == "2.0.1f2", "Wrong Mac package")
    tree = ROOT/"artifacts/extracted/rane-mac/tree"
    info_path = tree/"Library/Extensions/Sl3Driver.10.9.kext/Contents/Info.plist"
    info = plistlib.loads(info_path.read_bytes())
    personality = info["IOKitPersonalities"]["Sl3Driver"]
    require(personality["IOProviderClass"] == "IOUSBHostDevice" and personality["idVendor"] == 7365 and personality["idProduct"] == 1, "Kext identity changed")
    prior_path = ROOT/"docs/evidence/rane-mac-macho.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8-sig"))
    binaries = []
    for row in prior:
        path = ROOT/row["path"]
        require(digest(path) == row["sha256"], "Legacy Mach-O bytes changed")
        binaries.append({"path": row["path"], "sha256": row["sha256"], "architectures": [s["architecture"] for s in row["slices"]],
                         "signature_verified_on_mac": False})
    kext = next(row for row in binaries if "Sl3Driver.10.9.kext" in row["path"])
    require(kext["architectures"] == ["x86_64"], "Kext architecture differs from recorded structural analysis")
    source_root = ROOT/"artifacts/references/apple-iousbhost"
    sources = json.loads((source_root/"index.json").read_text(encoding="utf-8"))
    for source in sources:
        require(source["url"].startswith("https://developer.apple.com/documentation/iousbhost/"), "Not an official IOUSBHost source")
        require(digest(ROOT/source["file"]) == source["sha256"], "Downloaded Apple API source changed")
    transactions = (source_root/"enqueue-transaction.md").read_text(encoding="utf-8")
    require("macOS: 12.0.0 -" in transactions and "transactionListCount" in transactions, "Transaction API availability/signature changed")
    plan_path = ROOT/"tests/results/local/macos-preflight-plan-03.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    require(plan["plan_only"] and plan["analysis_platform"] == "Windows" and not plan["usb_user_client_opened"] and not plan["security_changed"] and plan["audio_submissions"] == 0,
            "Evidence is not an execution-free Windows plan")
    log_path = ROOT/"tests/results/local/macos-python-suite-02.log"
    log = log_path.read_text(encoding="utf-8-sig")
    require(re.search(r"Ran 27 tests in .*\s+OK\s*$", log), "Python suite was not fully successful")
    result = {"utc": datetime.now(timezone.utc).isoformat(), "scope": "Windows structural package inspection, official Apple/Serato research and simulated read-only Mac preflight tests",
              "package": {"archive_sha256": digest(archive), "source": "https://cdn.inmusicbrands.com/rane/legacy-product-downloads/Sl3-2.0.1f2.zip",
                          "package_info_sha256": digest(package_info), "attributes": package.attrib},
              "kext": {"info_plist_sha256": digest(info_path), "personality": personality, "dependencies": info["OSBundleLibraries_x86_64"]},
              "legacy_binaries": binaries, "prior_macho_report_sha256": digest(prior_path), "apple_api_sources": sources,
              "research_links": ["https://developer.apple.com/documentation/iousbhost/iousbhostobjectinitoptions/devicecapture",
                                 "https://developer.apple.com/documentation/audiodriverkit",
                                 "https://developer.apple.com/documentation/usbdriverkit/iousbhostpipe",
                                 "https://developer.apple.com/documentation/driverkit/requesting-entitlements-for-driverkit-development",
                                 "https://developer.apple.com/documentation/coreaudio/creating-an-audio-server-driver-plug-in",
                                 "https://support.serato.com/hc/en-us/articles/12934808677007-macOS-26-Tahoe-supported-Serato-software-status"],
              "preflight_plan": plan, "plan_sha256": digest(plan_path), "python_tests_passed": 27, "python_log_sha256": digest(log_path),
              "inputs": {str(path.relative_to(ROOT)).replace("\\", "/"): digest(path) for path in
                         [ROOT/"scripts/preflight-macos.py", ROOT/"tests/test_macos_preflight.py", Path(__file__).resolve()]},
              "mac_compilation_performed": False, "mac_runtime_collection_performed": False, "mac_signatures_verified": False,
              "usb_transport_validated_on_mac": False, "core_audio_device_implemented": False, "mac_serato_dvs_validated": False}
    output = ROOT/"docs/evidence/macos-route-preflight.json"
    output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(f"Verified package/source/plan/test identities and wrote {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
