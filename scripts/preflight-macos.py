"""Read-only Mac/SL3 preflight. Default is a plan; --collect requires macOS.

No USB user client, driver activation, signing change, firmware, audio or capture
option is used. Registry serial properties and unrelated USB devices are omitted.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import plistlib
import re
import subprocess

VENDOR, PRODUCT = 0x1CC5, 1
IOREG = ["/usr/sbin/ioreg", "-a", "-r", "-c", "IOUSBHostDevice", "-l"]
QUERIES = {
    "os_version": ["/usr/bin/sw_vers", "-productVersion"],
    "os_build": ["/usr/bin/sw_vers", "-buildVersion"],
    "process_architecture": ["/usr/bin/uname", "-m"],
    "model": ["/usr/sbin/sysctl", "-n", "hw.model"],
    "hardware_arm64": ["/usr/sbin/sysctl", "-n", "hw.optional.arm64"],
    "process_translated": ["/usr/sbin/sysctl", "-n", "sysctl.proc_translated"],
    "sip": ["/usr/bin/csrutil", "status"],
    "assessment": ["/usr/sbin/spctl", "--status"],
    "loaded_extensions": ["/usr/bin/kmutil", "showloaded"],
    "legacy_receipt": ["/usr/sbin/pkgutil", "--pkg-info", "com.rane.pkg.Sl3"],
    "developer_directory": ["/usr/bin/xcode-select", "-p"],
}


def integer(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip(), 16 if value.strip().lower().startswith("0x") else 10)
        except ValueError:
            pass
    return None


def usb_projection(data):
    if not data or len(data) > 8*1024*1024:
        raise ValueError("USB registry output is empty or exceeds 8 MiB")
    roots = plistlib.loads(data)
    if isinstance(roots, dict):
        roots = [roots]
    if not isinstance(roots, list):
        raise ValueError("USB registry is not a list of objects")
    found, visited, seen = [], 0, set()

    def label(node):
        return {key: str(node[key])[:256] for key in ("IORegistryEntryName", "IOObjectClass", "IOClass", "IOUserClass", "IOUserServerName")
                if isinstance(node.get(key), str)}

    def summaries(node, depth=0):
        if depth > 32:
            raise ValueError("SL3 service tree exceeds depth limit")
        rows = [label(node)]
        for key in ("bInterfaceNumber", "bAlternateSetting", "bInterfaceClass", "bInterfaceSubClass", "bInterfaceProtocol", "bNumEndpoints"):
            value = integer(node.get(key))
            if value is not None:
                rows[0][key] = value
        for child in node.get("IORegistryEntryChildren", []):
            if not isinstance(child, dict):
                raise ValueError("USB service child is not an object")
            rows.extend(summaries(child, depth+1))
        return [r for r in rows if r]

    def walk(node, root=False, depth=0):
        nonlocal visited
        visited += 1
        if visited > 20000 or depth > 32 or not isinstance(node, dict):
            raise ValueError("Invalid or oversized USB registry tree")
        device_class = node.get("IOObjectClass") == "IOUSBHostDevice"
        if (root or device_class) and "bInterfaceNumber" not in node and integer(node.get("idVendor")) == VENDOR and integer(node.get("idProduct")) == PRODUCT:
            registry_id, location = integer(node.get("IORegistryEntryID")), integer(node.get("locationID"))
            identity = ("registry", registry_id) if registry_id is not None else ("location", location) if location is not None else None
            if identity is not None and identity in seen:
                return
            if identity is not None:
                seen.add(identity)
            row = {"vendor_id": VENDOR, "product_id": PRODUCT, "identity": label(node), "services": summaries(node)}
            for key in ("bcdDevice", "bDeviceClass", "bDeviceSubClass", "bDeviceProtocol", "bNumConfigurations", "locationID", "USBSpeed"):
                value = integer(node.get(key))
                if value is not None:
                    row[key] = value
            row["driver_service_labels"] = [entry for entry in row["services"] if any(re.search(r"(?i)(sl3|com\.rane)", str(v)) for v in entry.values())]
            found.append(row)
        children = node.get("IORegistryEntryChildren", [])
        if not isinstance(children, list):
            raise ValueError("USB service children are not a list")
        for child in children:
            walk(child, depth=depth+1)

    for node in roots:
        walk(node, root=True)
    return {"status": "collected", "raw_sha256": hashlib.sha256(data).hexdigest(), "registry_nodes": visited,
            "sl3_devices": found, "serial_properties_extracted": False,
            "meaning": "Registry identity/service observations only; no interface claim or audio compatibility proof"}


def query(argv):
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False)
        return {"argv": argv, "status": "completed", "exit_code": result.returncode,
                "stdout": result.stdout, "stderr": result.stderr[:2048].decode("utf-8", errors="replace")}
    except subprocess.TimeoutExpired:
        return {"argv": argv, "status": "timeout", "exit_code": None, "stdout": b"", "stderr": "Read-only command exceeded 20 seconds"}
    except OSError as error:
        return {"argv": argv, "status": "unavailable", "exit_code": None, "stdout": b"", "stderr": str(error)[:2048]}


def text_result(result):
    return {**result, "stdout": result["stdout"][:4096].decode("utf-8", errors="replace"), "stdout_truncated": len(result["stdout"]) > 4096}


def successful_value(result):
    return result["stdout"].decode("utf-8", errors="replace").strip() if result["status"] == "completed" and result["exit_code"] == 0 else None


def legacy_signature(runner=query, bundle=Path("/Library/Extensions/Sl3Driver.10.9.kext")):
    if not bundle.is_dir():
        return {"status": "not_found_at_default_path", "path": str(bundle), "loaded_or_admitted": "not established"}
    command = runner(["/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", str(bundle)])
    result = {"path": str(bundle), "command": text_result(command),
              "status": "verification_succeeded" if command["status"] == "completed" and command["exit_code"] == 0 else "verification_failed_or_unavailable",
              "loaded_or_admitted": "not established; signature integrity does not prove loading or compatibility"}
    info = bundle/"Contents/Info.plist"
    try:
        if info.stat().st_size > 1024*1024:
            raise ValueError("Legacy driver Info.plist exceeds 1 MiB")
        data = info.read_bytes()
        parsed = plistlib.loads(data)
        result["bundle"] = {key: parsed.get(key) for key in ("CFBundleIdentifier", "CFBundleVersion", "CFBundleExecutable")}
        result["info_plist_sha256"] = hashlib.sha256(data).hexdigest()
    except (OSError, ValueError, TypeError, plistlib.InvalidFileException) as error:
        result["metadata_error"] = str(error)[:256]
    return result


def collect(runner=query):
    results = {name: runner(argv) for name, argv in QUERIES.items()}
    registry = runner(IOREG)
    if registry["status"] == "completed" and registry["exit_code"] == 0:
        try:
            usb = usb_projection(registry["stdout"])
        except (ValueError, plistlib.InvalidFileException, TypeError, RecursionError, OverflowError) as error:
            usb = {"status": "invalid", "reason": str(error)[:256], "sl3_devices": None}
    else:
        usb = {"status": registry["status"] if registry["status"] != "completed" else "failed", "sl3_devices": None, "reason": registry["stderr"]}
    loaded = successful_value(results["loaded_extensions"])
    extension = {"status": "unknown" if loaded is None else "queried", "matching_lines": []}
    if loaded is not None:
        extension["matching_lines"] = [s[:512] for s in loaded.splitlines() if re.search(r"(?i)(com\.rane\.driver\.sl3|Sl3Driver)", s)]
        extension["interpretation"] = "matching loaded-extension lines" if extension["matching_lines"] else "not listed; not proof of package absence or compatibility"
    host = {key: successful_value(results[key]) for key in ("os_version", "os_build", "process_architecture", "model")}
    host["hardware_arm64"] = {"1": True, "0": False}.get(successful_value(results["hardware_arm64"]))
    host["process_translated"] = {"1": True, "0": False}.get(successful_value(results["process_translated"]))
    host["oclp_status"] = "not determined; model/version alone are insufficient"
    # Do not retain kmutil's unrelated bundle inventory or ioreg's raw USB tree.
    commands = {name: text_result(value) for name, value in results.items() if name != "loaded_extensions"}
    commands["loaded_extensions"] = {k: v for k, v in text_result(results["loaded_extensions"]).items() if k != "stdout"}
    commands["usb_registry"] = {k: v for k, v in text_result(registry).items() if k != "stdout"}
    developer = successful_value(results["developer_directory"])
    sdk_paths = []
    if developer and Path(developer).is_absolute():
        for parent in (Path(developer)/"SDKs", Path(developer)/"Platforms/MacOSX.platform/Developer/SDKs"):
            if parent.is_dir():
                sdk_paths.extend(str(p) for p in parent.glob("MacOSX*.sdk"))
    return {"host": host, "usb_registry": usb, "legacy_loaded_extension": extension,
            "legacy_driver_signature": legacy_signature(runner),
            "developer_sdk_paths": sorted(set(sdk_paths)), "commands": commands,
            "security_interpretation": "Query results only. SIP/assessment output does not establish Apple Silicon boot policy or driver admission."}


def make_report(do_collect=False, runner=query):
    if do_collect and platform.system() != "Darwin":
        raise ValueError("--collect requires the actual macOS target; no Mac commands were executed")
    report = {"schema": 1, "utc": datetime.now(timezone.utc).isoformat(), "plan_only": not do_collect,
              "analysis_platform": platform.system(), "scope": "Read-only Mac/SL3 host and registry preflight",
              "usb_user_client_opened": False, "driver_activated": False, "driver_unloaded": False,
              "security_changed": False, "firmware_operations": 0, "audio_submissions": 0,
              "physical_audio_compatibility_verified": False, "commands_to_query": {**QUERIES, "usb_registry": IOREG},
              "conditional_commands": {"existing_legacy_kext_signature": ["/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", "/Library/Extensions/Sl3Driver.10.9.kext"]}}
    if do_collect:
        report.update(collect(runner))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        output = json.dumps(make_report(args.collect), indent=2)+"\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as destination:
                destination.write(output)
        print(output, end="")
    except (ValueError, OSError) as error:
        parser.exit(2, f"{error}\n")
