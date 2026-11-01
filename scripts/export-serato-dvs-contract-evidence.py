"""Bounded, execution-free evidence for current Serato descriptor/DVS consumers.

Reads the original PE and focused reports. Does not patch or execute Serato,
load a driver, change account/product state or claim physical DVS operation.
"""
import bisect
import hashlib
import json
import math
from pathlib import Path
import struct
import capstone
import pefile

ROOT = Path(__file__).resolve().parents[1]
SHA = "66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265"
BINARY = ROOT / "artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def main():
    raw = BINARY.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == SHA, "Original PE changed")
    pe = pefile.PE(data=raw, fast_load=True)
    pe.parse_data_directories(directories=[1, 3])
    base = pe.OPTIONAL_HEADER.ImageBase
    spans = sorted((base + e.struct.BeginAddress, base + e.struct.EndAddress) for e in pe.DIRECTORY_ENTRY_EXCEPTION)
    starts = [s[0] for s in spans]
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    decoder.detail = True
    cache = {}

    def function(address):
        index = bisect.bisect_right(starts, address) - 1
        require(index >= 0 and address < spans[index][1], "No containing unwind range")
        span = spans[index]
        if span not in cache:
            cache[span] = list(decoder.disasm(pe.get_data(span[0] - base, span[1] - span[0]), span[0]))
        return cache[span]

    def at(address, mnemonic=None, operands=None):
        row = next(x for x in function(address) if x.address == address)
        require(mnemonic is None or row.mnemonic == mnemonic, f"Wrong instruction at {address:x}")
        require(operands is None or row.op_str == operands, f"Wrong operands at {address:x}")
        return row

    def rip(row):
        values = [row.address + row.size + o.mem.disp for o in row.operands
                  if o.type == capstone.CS_OP_MEM and o.mem.base == capstone.x86.X86_REG_RIP]
        require(len(values) == 1, "Not an unambiguous RIP-relative reference")
        return values[0]

    def window(address, before=0, after=12):
        rows = function(address)
        index = next(i for i, x in enumerate(rows) if x.address == address)
        return [f"{x.address:x}: {x.mnemonic} {x.op_str}" for x in rows[max(0, index-before):index+after]]

    def cstring(address):
        return pe.get_data(address-base, 128).split(b"\0", 1)[0].decode("ascii")

    def rtti(table, expected):
        locator = struct.unpack("<Q", pe.get_data(table-base-8, 8))[0]
        signature, offset, _, td, _, self_rva = struct.unpack("<6I", pe.get_data(locator-base, 24))
        require(signature == 1 and locator == base+self_rva, "Invalid complete-object locator")
        name = cstring(base+td+16)
        require(name == expected, "Wrong RTTI type")
        return {"vtable": hex(table), "locator": hex(locator), "objectOffset": hex(offset), "type": name}

    reports = {}

    def focused(file, start):
        path = ROOT / "analysis" / file
        report = json.loads(path.read_text(encoding="utf-8-sig"))
        require(report["binary_sha256"].lower() == SHA, "Focused report targets another PE")
        row = next(f for f in report["functions"] if f["start"] == start)
        require(row["complete"], "Incomplete decompilation")
        require((int(row["start"], 16), int(row["end_exclusive"], 16)) in spans, "Focused range disagrees with unwind table")
        reports[file] = hashlib.sha256(path.read_bytes()).hexdigest()
        return row["pseudocode"].replace("\r", "")

    initializer = focused("serato500-dvs-fields-03.json", "1405c27d0")
    predicate = focused("serato500-dvs-consumers-01.json", "1421426f0")
    constructor = focused("serato500-dvs-links-05.json", "142142330")
    creation = focused("serato500-dvs-links-05.json", "142186ad0")
    parser = focused("serato500-dvs-parser-02.json", "1405c7f90")
    require("0x464" in predicate and "0xcc" in predicate and "0x98" in predicate, "Predicate interpretation changed")
    require("UNK_1431c4488" in constructor and "param_1 + 0x90" in constructor, "Manager constructor identity changed")
    require("FUN_1421999f0" in creation and "lVar5 + 0x318" in creation and "FUN_14219abb0" in creation, "Decoder calibration caller changed")

    # These are copies of inline enum strings, not string-pointer references.
    enum_rows = []
    for label, value, reference, store in (
        ("DVS_DEVICE_NO", 0, 0x1405c2851, 0x1405c2875),
        ("DVS_DEVICE_YES", 1, 0x1405c2968, 0x1405c298d),
        ("DVS_DEVICE_HYBRID", 2, 0x1405c2a8e, 0x1405c2aa6),
        ("DVS_DEVICE_REQUIRES_AUTH", 3, 0x1405c2bbb, 0x1405c2bd6),
    ):
        require(cstring(rip(at(reference))) == label, "Wrong enum string bytes")
        at(store, "mov", f"dword ptr [rbp + 0xf], {'r15d' if value == 0 else str(value)}")
        require(f"uStack_50 = {value};" in initializer, "Enum integer missing in focused initializer")
        enum_rows.append({"name": label, "value": value, "stringCopyVA": hex(reference), "integerStoreVA": hex(store), "assembly": window(reference)})
    require(any(x.mnemonic == "xor" and x.op_str == "r15d, r15d" for x in function(0x1405c27d0)[:45]), "Enum zero register not established")

    fields = []
    for name, offset, reference, store, operands in (
        ("dvs_device", 0x464, 0x1405c9bf0, 0x1405c9c52, "dword ptr [rsi + 0x464], ecx"),
        ("dvs_only_device", 0x468, 0x1405c9c6b, 0x1405c9c91, "byte ptr [rsi + 0x468], al"),
        ("dvs_input_calibration_gain", 0x318, 0x1405c8d68, 0x1405c8d99, "qword ptr [rsi + 0x318], xmm0"),
        ("num_decks", 0x46c, 0x1405c9784, 0x1405c97b3, "dword ptr [rsi + 0x46c], eax"),
        ("audio_deck_setup_type", 0x5c4, 0x1405ca8ef, 0x1405ca951, "dword ptr [rsi + 0x5c4], ecx"),
    ):
        require(cstring(rip(at(reference, "lea"))) == name, "Wrong parser key")
        at(store, "movsd" if "xmm0" in operands else "mov", operands)
        require(f"0x{offset:x}" in parser, "Field absent in focused parser")
        fields.append({"name": name, "completeObjectOffset": hex(offset), "keyReference": hex(reference), "destination": hex(store), "assembly": window(reference, 1, 17)})
    at(0x1405c9be9, "mov", "dword ptr [rsi + 0x464], r15d")
    at(0x1405c8d61, "mov", "qword ptr [rsi + 0x318], r15")
    at(0x1405c89c3, "xor", "r15d, r15d")
    require("*(undefined4 *)(param_1 + 0x464) = 0;" in parser and "*(undefined8 *)(param_1 + 0x318) = 0;" in parser, "Parser zero defaults changed")
    require(any(x.mnemonic == "mov" and x.op_str == "rsi, rcx" for x in function(0x1405c7f90)[:100]), "Parser receiver changed")

    manager_type = rtti(0x1431c4488, ".?AVCDVSPluginManager@@")
    decoder_type = rtti(0x1431cca28, ".?AVCDVSDecoderInput@@")
    require(rip(at(0x142199a38, "lea")) == 0x1431cca28, "DVS decoder constructor vtable changed")
    require(rip(at(0x14214236c, "lea")) == 0x1431c4488, "Wrong manager vtable installation")
    require(struct.unpack("<Q", pe.get_data(0x1431c44a0-base, 8))[0] == 0x142142760, "Wrong manager handler vtable slot")
    at(0x14214270d, "mov", "ecx, dword ptr [rcx + 0x464]")
    at(0x1421426b9, "call", "0x1421426f0")
    getter = list(decoder.disasm(pe.get_data(0x14154a570-base, 5), 0x14154a570))
    require([(x.mnemonic, x.op_str) for x in getter] == [("movzx", "eax, byte ptr [rcx + 0x2c]"), ("ret", "")], "DVS state getter changed")

    imports = {i.address: (d.dll.decode(), i.name.decode() if i.name else str(i.ordinal)) for d in pe.DIRECTORY_ENTRY_IMPORT for i in d.imports}
    thunk = next(decoder.disasm(pe.get_data(0x1421203b0-base, 6), 0x1421203b0))
    resolved = imports[rip(thunk)]
    require(resolved == ("api-ms-win-crt-math-l1-1-0.dll", "powf"), "Gain math import changed")
    constants = [struct.unpack("<f", pe.get_data(a-base, 4))[0] for a in (0x1428163b8, 0x1428163a0, 0x14280f2b4)]
    require(constants == [10.0, 4.0, 20.0], "Gain constants changed")
    at(0x14219abd5, "call", "0x1421203b0")
    at(0x14219abf8, "xchg", "dword ptr [rax], ebx")

    endpoints = []
    for name, reference, vector_offset, map_offset in (
        ("output_endpoints", 0x1405cadb9, 0x4c8, 0x6c8),
        ("input_endpoint", 0x1405caff1, 0x4e0, 0x6b8),
    ):
        require(cstring(rip(at(reference, "lea"))) == name, "Wrong endpoint parser key")
        require(f"param_1 + 0x{vector_offset:x}" in parser and f"param_1 + 0x{map_offset:x}" in parser, "Endpoint containers changed")
        endpoints.append({"name": name, "keyReference": hex(reference), "endpointVectorOffset": hex(vector_offset), "endpointToHardwareIndexMapOffset": hex(map_offset), "assembly": window(reference, 2, 17)})
    for key in ("hw_src", "hw_dest", "Deck1In", "Deck2In", "USBInsertOut1", "USBInsertOut2"):
        require((key.encode()+b"\0") in raw, "Endpoint vocabulary changed")

    installed = Path("C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe")
    installed_sha = hashlib.sha256(installed.read_bytes()).hexdigest() if installed.exists() else None
    require(installed_sha in (None, SHA), "Installed Serato differs from analysed target")
    result = {
        "binarySha256": SHA, "installedBinarySha256": installed_sha,
        "scope": "Static descriptor/DVS enum, manager predicate, software calibration gain and endpoint containers; no runtime call trace, application patch, account change or DVS validation",
        "focusedReportSha256": reports, "enum": enum_rows, "descriptorFields": fields,
        "managerRtti": manager_type, "decoderRtti": decoder_type,
        "managerPredicateAssembly": window(0x1421426f0, 0, 40),
        "managerPredicate": {"descriptorPointerOffset": "0x90", "kindFieldOffset": "0x464", "nullOrKindZero": False, "kindOne": True,
                             "kindTwo": "manager byte +0xCC", "kindThree": "manager byte +0xCC AND byte +0x98",
                             "unknowns": "The two manager state-byte sources and wider product/account/support gates are not fully recovered; do not bypass them."},
        "decoderConstructorVtableAssembly": window(0x142199a38, 2, 8),
        "gain": {"function": "0x14219abb0", "descriptorDoubleOffset": "0x318", "decoderFloatBitsOffset": "0x3124", "formula": "powf(10, (float(gain) + 4) / 20)",
                 "nominalZeroGainMultiplier": math.pow(10, 4/20), "import": list(resolved), "assembly": window(0x14219abb0, 0, 30),
                 "physicalCalibrationVerified": False},
        "endpointContainers": endpoints,
        "sl3DefaultInference": "The previously verified zeroed allocation and identity-only discontinued stub leave DVS kind zero unless another component changes it. If that stub reached this predicate unchanged it would not enable DVS. Its current discontinued-support path may prevent reaching this manager at all.",
        "remaining": ["external descriptor injection/override mechanism", "verified physical stereo-pair/deck mapping", "legitimate current product/account connection contract", "physical two-deck DVS operation"],
        "officialSourcesChecked": ["https://support.serato.com/hc/en-us/articles/203401184-Does-my-mixer-controller-interface-support-DVS-in-Serato-DJ-Pro", "https://support.serato.com/hc/en-us/articles/4411117032975-Serato-software-operating-system-compatibility-for-discontinued-hardware"],
    }
    output = ROOT / "docs/evidence/serato500-dvs-contract.json"
    output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(f"Verified original PE/imports/RTTI/fields and wrote {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
