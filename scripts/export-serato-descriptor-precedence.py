"""Verify current Serato's numeric descriptor precedence without executing it."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

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
    for filename in ("serato500-descriptor-resource-02.json", "serato500-primary-selection-02.json",
                     "serato500-descriptor-precedence-04.json", "serato500-identity-lookup-callers-05.json"):
        path = ROOT / "analysis" / filename
        report = json.loads(path.read_text(encoding="utf-8-sig"))
        require(report["binary_sha256"] == app.sha, "Report identity changed")
        for row in report["functions"]:
            require(row["complete"] and (int(row["start"], 16), int(row["end_exclusive"], 16)) in app.spans,
                    "Focused report/range mismatch")
        reports[filename] = digest(path)
    table = app.rip(app.at(0x14050340d, "lea"))
    require(table == 0x142808488, "Wrong manager vtable")
    locator = struct.unpack("<Q", app.data(table-8, 8))[0]
    sig, offset, _, td, _, self_rva = struct.unpack("<6I", app.data(locator, 24))
    require(sig == 1 and offset == 0 and app.base+self_rva == locator
            and app.text(app.base+td+16) == ".?AVPrimaryDeviceManager@@", "Manager RTTI mismatch")
    checks = [
        (0x140503462, "mov", "qword ptr [rdi + 0xd8], rsi"),
        (0x140503469, "mov", "qword ptr [rdi + 0xe0], rsi"),
        (0x140503568, "call", "0x140503a40"),
        (0x140503d34, "call", "0x1405ce9d0"),
        (0x140503d72, "call", "0x140502ae0"),
        (0x140503d7b, "lea", "rcx, [r13 + 0xd8]"),
        (0x140503da5, "add", "qword ptr [rcx + 8], 0x10"),
        (0x140504a63, "call", "0x1405d02e0"),
        (0x140504a78, "lea", "rcx, [r13 + 0xd8]"),
        (0x140504aaf, "add", "qword ptr [rcx + 8], 0x10"),
        (0x14050537c, "mov", "r10, qword ptr [rcx + 0xd8]"),
        (0x140505383, "xor", "edi, edi"),
        (0x1405053b0, "mov", "rax, qword ptr [rsi + r10]"),
        (0x1405053b4, "movzx", "ecx, word ptr [rax + 0xa8]"),
        (0x1405053c0, "movzx", "ecx, word ptr [rax + 0xaa]"),
        (0x1405053cc, "movzx", "ecx, word ptr [rax + 0xac]"),
        (0x1405053d3, "cmp", "ecx, r15d"),
        (0x1405053d6, "je", "0x140505449"),
        (0x1405053d8, "jge", "0x140505421"),
        (0x1405053df, "mov", "rdi, rax"),
        (0x1405053f6, "call", "qword ptr [rax + 0x28]"),
        (0x14050540e, "call", "qword ptr [rdx + 0x28]"),
        (0x140505411, "cmp", "ax, bx"),
        (0x140505414, "ja", "0x140505421"),
        (0x14050541d, "mov", "rdi, qword ptr [rsi + rax]"),
        (0x140505432, "add", "rsi, 0x10"),
        (0x140505440, "jb", "0x1405053b0"),
        (0x140505446, "mov", "rax, rdi"),
        (0x1405c83b1, "mov", "word ptr [rsi + 0xac], di"),
        (0x1405c83ec, "mov", "word ptr [rsi + 0xac], ax"),
        (0x14050512b, "call", "qword ptr [rax + 0x30]"),
        (0x14050514d, "call", "0x140b21c80"),
        (0x140505200, "call", "0x140b1a150"),
        (0x14050520a, "call", "0x140b1a200"),
        (0x140505214, "call", "0x140b1a250"),
        (0x140505219, "mov", "r9d, edi"),
        (0x14050521c, "mov", "r8d, ebx"),
        (0x14050521f, "mov", "edx, eax"),
        (0x140505224, "call", "0x140505360"),
        (0x140505229, "mov", "rsi, rax"),
        (0x140505261, "mov", "rax, rsi"),
        (0x14218cc06, "xor", "r9d, r9d"),
        (0x14218cc17, "call", "0x140505360"),
    ]
    for va, op, operands in checks:
        app.at(va, op, operands)
    require(app.text(app.rip(app.at(0x1405c83b8))) == "bcd_device", "Wrong revision parser key")
    require(struct.unpack("<2i", app.data(app.rip(app.at(0x1405beae9)), 8)) == (-8, 0x730), "Wrong virtual-base adjustment")
    identity_table = app.rip(app.at(0x1405beb6f))
    require(identity_table == 0x14281cbe8 and struct.unpack("<Q", app.data(identity_table+0x28, 8))[0] == 0x1405c6530,
            "Wrong revision getter slot")
    leaf = list(app.dis.disasm(app.data(0x1405c6530, 8), 0x1405c6530))
    require([(r.mnemonic, r.op_str) for r in leaf] == [("movzx", "eax, word ptr [rcx - 0x68c]"), ("ret", "")], "Wrong revision leaf")
    require(8+0x730-0x68c == 0xac, "Revision field arithmetic mismatch")
    null_leaf = list(app.dis.disasm(app.data(0x140502ae0, 8), 0x140502ae0))
    require([(r.mnemonic, r.op_str) for r in null_leaf] == [("cmp", "qword ptr [rcx], 0"), ("sete", "al"), ("ret", "")], "Append predicate is not just null testing")
    result = {"generatedUtc": datetime.now(timezone.utc).isoformat(), "binarySha256": app.sha,
              "installedMatches": True, "focusedReportSha256": reports,
              "checkedInstructions": [f"{a:x}: {o} {v}" for a, o, v in checks],
              "manager": {"name": "PrimaryDeviceManager", "vtable": hex(table), "descriptorVectorOffset": "0xd8"},
              "numericLookup": {"function": "0x140505360", "fields": {"vendorId": "0xa8", "productId": "0xaa", "bcdDevice": "0xac"},
                                "exact": "first matching entry returns immediately",
                                "fallback": "highest strictly older bcd_device; later entry wins ties",
                                "newerOnly": "no descriptor returned", "inputScope": "ordinary 16-bit USB identity values"},
              "registration": "resource descriptors appended before identity-only discontinued stubs; immediate append predicate only tests null",
              "earlierMatch": "wrapper 0x1405050b0 checks nonempty interface-name matching before numeric fallback; matcher semantics not fully recovered",
              "callerCaveat": "call 0x14218cc17 explicitly passes revision zero; not every numeric lookup forwards a physical bcdDevice",
              "applicationExecuted": False, "descriptorInjected": False,
              "limits": ["Static selection rules do not establish a discoverable external descriptor provider",
                         "No successful current descriptor/control/handshake/DVS integration or physical audio result",
                         "Runtime input values, complete device-info construction and actual chosen descriptor not observed",
                         "No application/archive/account/driver/USB identity modifications"]}
    output = ROOT / "docs/evidence/serato500-descriptor-precedence.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Verified descriptor precedence against original and installed PE: {output}")


if __name__ == "__main__":
    main()
