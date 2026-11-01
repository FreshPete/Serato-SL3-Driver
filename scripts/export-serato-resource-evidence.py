"""Verify current Serato's descriptor resource dispatch without executing it.

Requires the original PE and locally generated focused Ghidra reports. This
records a static boundary, not an external override or a runtime integration.
"""
import bisect
import hashlib
import json
from pathlib import Path
import struct

import capstone
import pefile

ROOT = Path(__file__).resolve().parents[1]
SHA = "66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265"
BINARY = ROOT / "artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def main():
    raw = BINARY.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == SHA, "Original PE changed")
    pe = pefile.PE(data=raw, fast_load=True)
    pe.parse_data_directories(directories=[1, 3])
    base = pe.OPTIONAL_HEADER.ImageBase
    spans = sorted((base + e.struct.BeginAddress, base + e.struct.EndAddress)
                   for e in pe.DIRECTORY_ENTRY_EXCEPTION)
    starts = [s[0] for s in spans]
    dis = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    dis.detail = True
    cache = {}

    def function(address):
        i = bisect.bisect_right(starts, address) - 1
        require(i >= 0 and address < spans[i][1], "Missing unwind range")
        span = spans[i]
        if span not in cache:
            cache[span] = list(dis.disasm(pe.get_data(span[0]-base, span[1]-span[0]), span[0]))
        return cache[span]

    def at(address, mnemonic=None, operands=None):
        row = next(r for r in function(address) if r.address == address)
        require(mnemonic is None or row.mnemonic == mnemonic, f"Wrong opcode at {address:x}")
        require(operands is None or row.op_str == operands, f"Wrong operands at {address:x}")
        return row

    def window(address, before=0, after=12):
        rows = function(address)
        i = next(i for i, r in enumerate(rows) if r.address == address)
        return [f"{r.address:x}: {r.mnemonic} {r.op_str}" for r in rows[max(0, i-before):i+after]]

    def rip(row):
        refs = [row.address + row.size + o.mem.disp for o in row.operands
                if o.type == capstone.CS_OP_MEM and o.mem.base == capstone.x86.X86_REG_RIP]
        require(len(refs) == 1, "Ambiguous RIP reference")
        return refs[0]

    def text(address):
        return pe.get_data(address-base, 128).split(b"\0", 1)[0].decode("ascii")

    reports = {}

    def focused(file, start):
        path = ROOT / "analysis" / file
        report = json.loads(path.read_text(encoding="utf-8-sig"))
        require(report["binary_sha256"] == SHA, "Wrong focused-report binary")
        row = next(r for r in report["functions"] if r["start"] == start)
        require(row["complete"], "Incomplete focused report")
        require((int(start, 16), int(row["end_exclusive"], 16)) in spans, "Wrong focused range")
        reports[file] = hashlib.sha256(path.read_bytes()).hexdigest()
        return row["pseudocode"].replace("\r", "")

    def rtti(table, name, slots):
        locator = struct.unpack("<Q", pe.get_data(table-base-8, 8))[0]
        sig, offset, _, td, _, self_rva = struct.unpack("<6I", pe.get_data(locator-base, 24))
        require(sig == 1 and locator == base+self_rva and offset == 0, "Invalid primary RTTI")
        require(text(base+td+16) == name, "Wrong resource reader RTTI")
        for slot, target in slots.items():
            require(struct.unpack("<Q", pe.get_data(table-base+slot, 8))[0] == target, "Wrong reader slot")
        return {"vtable": hex(table), "locator": hex(locator), "type": name,
                "slots": {hex(k): hex(v) for k, v in slots.items()}}

    folder = focused("serato500-resource-providers-03.json", "1405037d0")
    factory = focused("serato500-descriptor-loader-01.json", "1405ce9d0")
    preparse = focused("serato500-descriptor-loader-01.json", "1405c7330")
    setup = focused("serato500-qrc-configuration-05.json", "140b0aa40")
    manager = focused("serato500-qrc-root-07.json", "14139b980")
    append = focused("serato500-resource-order-08.json", "141771c70")
    enumerate_manager = focused("serato500-qrc-path-06.json", "141771e50")
    read_manager = focused("serato500-descriptor-resource-02.json", "141772090")
    can_handle = focused("serato500-resource-providers-03.json", "141776aa0")
    prefix = focused("serato500-resource-order-08.json", "141773720")
    mapping = focused("serato500-archive-map-10.json", "1417765e0")
    archive_read = focused("serato500-archive-read-09.json", "141775520")
    qrc_read = focused("serato500-qrc-provider-04.json", "140b0d760")
    qrc_list = focused("serato500-qrc-configuration-05.json", "140b0d280")
    file_read = focused("serato500-qrc-path-06.json", "140b0bf50")
    resource_read = focused("serato500-qrc-path-06.json", "140b0bd40")
    require("FUN_141771e50" in folder and text(0x142808588) == "resource:", "Wrong descriptor resource prefix")
    folders = ["userio/midi", "userio/audio", "userio/hid",
               "userio_partner/midi", "userio_partner/audio", "userio_partner/hid",
               "userio_hidden_from_partners/midi", "userio_hidden_from_partners/audio",
               "userio_hidden_from_partners/hid"]
    addresses = [0x1428085a0, 0x1428085b0, 0x1428085c0, 0x1428085d0, 0x1428085e8,
                 0x142808600, 0x142808618, 0x142808640, 0x142808668]
    require([text(a) for a in addresses] == folders, "Wrong registration folders")
    require("FUN_1405c7330" in factory and "FUN_141772090" in preparse, "Wrong descriptor parse chain")
    require("FUN_14139b980" in setup and "FUN_141771c70" in setup, "Wrong provider setup chain")
    require("param_1 + 0x10" in append and "+ 0x10;" in append, "Provider append interpretation changed")
    require("+ 0x20" in read_manager and "+ 0x28" in enumerate_manager, "Wrong dispatch slots")
    require("param_1 + 0x58" in can_handle and "FUN_141773720" in can_handle, "Wrong archive match predicate")
    require("0x2f" in prefix and "param_1 + 0x28" in mapping, "Wrong prefix mapping")
    require("FUN_141776810" in archive_read and "FUN_141773520" in archive_read, "Wrong archive read source")
    require("FUN_140b0bf50" in qrc_read and "FUN_140b0bd40" in qrc_read, "Wrong QRC fallback")
    require("basic_streambuf" in file_read and "QResource" in resource_read, "Wrong fallback reader kinds")
    require("QDirIterator" in qrc_list and "param_1 +" not in qrc_list, "QRC listing now uses instance root")

    at(0x1405cea6c, "call", "0x1405c7330")
    at(0x1405c73a4, "call", "0x141772090")
    at(0x1417720f9, "call", "qword ptr [rax + 8]")
    at(0x1417720fe, "jne", "0x14177210b")
    at(0x141772117, "call", "qword ptr [rax + 0x20]")
    at(0x141771e89, "call", "qword ptr [rax + 8]")
    at(0x141771e8e, "jne", "0x141771ec2")
    at(0x141771ece, "call", "qword ptr [rax + 0x28]")
    at(0x141771ed1, "jmp", "0x141771ea4")
    at(0x140b0aa7a, "call", "0x14139b980")
    at(0x14139c0c9, "call", "0x141771c70")
    at(0x140b0b18a, "call", "0x141771c70")
    require(text(rip(at(0x14139bb18))) == "userio_resources.bin", "Wrong archive filename")
    require(text(rip(at(0x14139bb43))) == "userio", "Wrong archive prefix")
    at(0x14139bb6b, "call", "0x1417763c0")
    require("FUN_1417763c0" in manager, "Missing prefix registration")
    scheme = struct.unpack("<Q", pe.get_data(0x142fabb70-base, 8))[0]
    require(text(scheme) == "resource", "Wrong archive URI scheme")
    require(text(0x142814c28) == ":", "Wrong QRC listing prefix")
    at(0x140b0db3a, "call", "0x140b0bf50")
    at(0x140b0dc53, "cmp", "qword ptr [rsi + 0x10], 0")
    at(0x140b0dc58, "jne", "0x140b0d9e1")
    at(0x140b0dc6a, "call", "0x140b0bd40")

    readers = [rtti(0x142fabb98, ".?AVArchiveResourceReader@resources@serato@@",
                    {8: 0x141776aa0, 0x20: 0x141775360, 0x28: 0x1417738d0}),
               rtti(0x142e74538, ".?AVQRCResources@qt@ui@serato@@",
                    {8: 0x140b0e5a0, 0x20: 0x140b0d760, 0x28: 0x140b0d280})]
    installed = Path("C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe")
    installed_sha = hashlib.sha256(installed.read_bytes()).hexdigest() if installed.exists() else None
    require(installed_sha in (None, SHA), "Installed binary differs")
    archive = BINARY.parent / "userio_resources.bin"
    result = {
        "binarySha256": SHA, "installedBinarySha256": installed_sha,
        "scope": "Static resource dispatch only; no application/config/archive mutation or execution, device action or runtime override validation",
        "focusedReportSha256": reports, "readers": readers,
        "registrationFolders": folders,
        "descriptorFlow": ["0x140503a40 registration", "0x1405037d0 resource folder listing",
                           "0x141771e50 first-reader enumeration", "0x1405ce9d0 descriptor factory",
                           "0x1405c7330 type/product-ID pre-parser", "0x141772090 first-reader text read"],
        "userioArchive": {"prefix": "userio", "file": archive.name,
                          "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                          "bytes": archive.stat().st_size,
                          "registrationAssembly": window(0x14139bb18, 0, 20)},
        "providerOrder": {"archiveAppend": "0x14139c0c9", "qrcAppend": "0x140b0b18a",
                          "interpretation": "QRC factory constructs the base manager first, then appends QRC. The base manager appends the userio archive reader before return."},
        "firstMatchTextAssembly": window(0x1417720e2, 0, 22),
        "firstMatchEnumerationAssembly": window(0x141771e6a, 0, 38),
        "qrcFallback": {"fileReader": "0x140b0bf50", "qtResourceReader": "0x140b0bd40",
                        "listReader": "0x140b0d280", "listingPrefix": ":",
                        "assembly": window(0x140b0dc53, 0, 8),
                        "interpretation": "Optional instance root affects text reads; an empty file result falls back to QResource. Directory listing uses colon-prefixed URI path, not instance root."},
        "conclusion": "A loose Data/userio XML file is not established as a device-registration route. The mapped userio archive is selected before QRC, and manager dispatch does not merge readers or retry after an empty result.",
        "unresolved": ["Runtime provider construction and any later registration changes",
                       "Full configured resource-root initialization",
                       "Verified original SL3 descriptor content and duplicate identity precedence",
                       "A supported external integration boundary preserving product/account checks"],
        "physicalAudioVerified": False, "currentSeratoIntegrationVerified": False,
    }
    output = ROOT / "docs/evidence/serato500-resource-dispatch.json"
    output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(f"Verified resource dispatch against original/installed PE; wrote {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
