"""Verify module-derived resource-root defaults; execute no vendor code."""
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
    app = helper.Image("artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe", helper.CURRENT_SHA)
    installed = Path("C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe")
    require(digest(installed) == app.sha, "Installed executable differs")
    reports = {}
    for name in ("serato500-qrc-root-07.json", "serato500-qrc-path-06.json", "serato500-resource-path-state-03.json"):
        path = ROOT / "analysis" / name
        report = json.loads(path.read_text(encoding="utf-8-sig"))
        require(report["binary_sha256"] == app.sha, "Wrong focused image")
        for row in report["functions"]:
            require(row["complete"] and (int(row["start"], 16), int(row["end_exclusive"], 16)) in app.spans,
                    "Incomplete focused report/range")
        reports[name] = digest(path)
    checks = [
        (0x14083e032, "mov", "rdx, rbx"), (0x14083e035, "mov", "rcx, rbx"),
        (0x14083e038, "call", "0x1420fc4b0"),
        (0x1420fc4e7, "call", "0x1420fc5b0"),
        (0x1420fc4ec, "mov", "r8d, 0x104"),
        (0x1420fc5cb, "mov", "ecx, 4"),
        (0x141cb4c72, "call", "0x14083dfe0"),
        (0x141cb4c7a, "mov", "rdx, rax"),
        (0x141cb4c81, "call", "0x141cb4400"),
        (0x141cb4c87, "lea", "rdx, [rbx + 0x20]"),
        (0x141cb4c8f, "call", "0x1404a3300"),
        (0x141cb4d0c, "call", "0x141cb6c00"),
        (0x141cb4dae, "call", "0x141cb1230"),
        (0x141cb445a, "call", "0x14210a070"),
        (0x14210a0d6, "cmp", "dx, 0x2f"),
        (0x14210a0dc, "cmp", "dx, 0x5c"),
    ]
    for va, op, operands in checks:
        app.at(va, op, operands)
    require(app.rip(app.at(0x14083e02b)) == 0x143fe8860, "Wrong path-state object")
    defaults = []
    for va, target in ((0x14083e058, 0x143fe8880), (0x14083e070, 0x143fe88a0), (0x14083e088, 0x143fe88c0)):
        row = app.at(va, "mov")
        require(app.rip(row) == target and row.op_str.endswith(", 0x2e") and row.op_str.startswith("word ptr"), "Wrong default path bytes")
        defaults.append({"storeVA": hex(va), "targetVA": hex(target), "bytes": "2e00"})
    app.pe.parse_data_directories(directories=[1])
    imports = {entry.address: entry.name.decode("ascii") for library in app.pe.DIRECTORY_ENTRY_IMPORT
               for entry in library.imports if entry.name}
    require(imports[app.rip(app.at(0x1420fc4fa, "call"))] == "GetModuleFileNameW", "Wrong module filename API")
    require(imports[app.rip(app.at(0x1420fc5d0, "call"))] == "GetModuleHandleExW", "Wrong module handle API")
    require(app.rip(app.at(0x1420fc5c4, "lea")) == 0x1404a67c0, "Module handle does not use the expected own-image address")
    result = {"generatedUtc": datetime.now(timezone.utc).isoformat(), "binarySha256": app.sha,
              "installedMatches": True, "focusedReportsSha256": reports,
              "checkedInstructions": [f"{a:x}: {o} {v}" for a, o, v in checks],
              "pathStateVA": "0x143fe8860", "componentDefaults": defaults,
              "moduleFilename": {"helper": "0x1420fc4b0", "api": "GetModuleFileNameW", "capacityWchars": 260,
                                 "handleHelper": "0x1420fc5b0", "handleApi": "GetModuleHandleExW", "flags": 4,
                                 "fromAddressVA": "0x1404a67c0"},
              "root": {"builder": "0x141cb4c40", "directoryPartHelper": "0x141cb4400",
                       "storedComponentOffset": "0x20", "defaultComponent": ".",
                       "joinHelper": "0x141cb6c00", "filesystemValidationHelper": "0x141cb1230"},
              "interpretation": "Under the verified default initialization and successful module/path queries, root derives from the containing executable directory plus dot; no Data default is established.",
              "vendorCodeExecuted": False, "overrideInstalled": False,
              "limits": ["No runtime path/provider instrumentation or exhaustive later-write analysis",
                         "Filesystem-validation helper is not promoted to a proved directory-only predicate",
                         "Archive precedence and QRC resource-only listing still constrain loose descriptor discovery",
                         "No user-editable supported override, current integration, audio or DVS result"]}
    output = ROOT / "docs/evidence/serato500-resource-root.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Verified module-derived resource defaults against original/installed PE: {output}")


if __name__ == "__main__":
    main()
