"""Verify static rate/alignment/handshake differences; never execute vendor code."""
import bisect
import hashlib
import json
import math
from pathlib import Path
import struct

import capstone
import pefile

ROOT = Path(__file__).resolve().parents[1]
CURRENT_SHA = "66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265"
OLD_SHA = "ba8641d0329fe0c955147d2b45f247eeea82ac0f812fe30a339834dbe0c0a503"
DRIVER_SHA = "e3d88039547b70915b1a9bc9e3e3f7dba32aaa9bc3ce8fd51616565ea1734141"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


class Image:
    def __init__(self, path, expected):
        self.raw = (ROOT / path).read_bytes()
        require(hashlib.sha256(self.raw).hexdigest() == expected, "Input image changed")
        self.sha = expected
        self.pe = pefile.PE(data=self.raw, fast_load=True)
        self.pe.parse_data_directories(directories=[3])
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.spans = sorted((self.base+e.struct.BeginAddress, self.base+e.struct.EndAddress)
                            for e in self.pe.DIRECTORY_ENTRY_EXCEPTION)
        self.starts = [s[0] for s in self.spans]
        self.dis = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.dis.detail = True
        self.cache = {}

    def data(self, va, length):
        return self.pe.get_data(va-self.base, length)

    def text(self, va):
        return self.data(va, 128).split(b"\0", 1)[0].decode("ascii")

    def function(self, va):
        i = bisect.bisect_right(self.starts, va)-1
        require(i >= 0 and va < self.spans[i][1], "No unwind function")
        span = self.spans[i]
        if span not in self.cache:
            self.cache[span] = list(self.dis.disasm(self.data(span[0], span[1]-span[0]), span[0]))
        return self.cache[span]

    def at(self, va, op=None, operands=None):
        row = next(i for i in self.function(va) if i.address == va)
        require(op is None or row.mnemonic == op, f"Opcode mismatch at {va:x}")
        require(operands is None or row.op_str == operands, f"Operand mismatch at {va:x}")
        return row

    def window(self, va, before=0, after=12):
        rows = self.function(va)
        i = next(i for i, r in enumerate(rows) if r.address == va)
        return [f"{r.address:x}: {r.mnemonic} {r.op_str}" for r in rows[max(0, i-before):i+after]]

    def rip(self, row):
        refs = [row.address+row.size+o.mem.disp for o in row.operands
                if o.type == capstone.CS_OP_MEM and o.mem.base == capstone.x86.X86_REG_RIP]
        require(len(refs) == 1, "Ambiguous RIP reference")
        return refs[0]


def main():
    app = Image("artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe", CURRENT_SHA)
    old = Image("artifacts/extracted/Serato DJ Pro 2.5.5/tree/Serato/Serato DJ Pro/Serato DJ Pro.exe", OLD_SHA)
    driver = Image("artifacts/extracted/rane-windows/x64/RaneAsioSL3.dll", DRIVER_SHA)
    reports = {}

    def focused(image, file, start):
        path = ROOT / "analysis" / file
        report = json.loads(path.read_text(encoding="utf-8-sig"))
        require(report["binary_sha256"] == image.sha, "Report identity mismatch")
        row = next(r for r in report["functions"] if r["start"] == start)
        require(row["complete"] and (int(start, 16), int(row["end_exclusive"], 16)) in image.spans, "Report incomplete/range mismatch")
        reports[file] = hashlib.sha256(path.read_bytes()).hexdigest()
        return row["pseudocode"].replace("\r", "")

    enum = focused(app, "serato500-clock-enums-03.json", "1405c1750")
    align = focused(app, "serato500-clock-accessor-02.json", "1405c6670")
    setup = focused(app, "serato500-audio-clock-setup-04.json", "141379a70")
    old_enum = focused(old, "serato255-handshake-enum-12.json", "140353040")
    sizes = focused(driver, "rane-asio-buffer-sizes-01.json", "180010080")
    require("uStack_18 = 5;" in old_enum and "14476deb8" in old_enum, "Historical enum interpretation changed")
    require("param_2 /" in align and "param_3" in align and "0x34c" in align, "Alignment interpretation changed")
    require("+ 0xa0" in setup and "+ 0xa8" in setup, "Connection setup accessors changed")
    require("*param_4 = uVar1;" in sizes and "*param_3 = uVar1;" in sizes and "*param_2 = uVar1;" in sizes, "Original fixed bank contract changed")

    labels = ["NONE", "SERATO_DJ", "NUMARK", "VESTAX", "NOVATION", "AKAI", "SERATO_DJ_HID", "ATC_HID_PIR"]
    literal = [0x14281ccd8, 0x14281ccf0, 0x14281cd10, 0x14281cd28, 0x14281cd40, 0x14281cd58, 0x14281cd70, 0x14281cd90]
    refs = [0x1405c17df, 0x1405c190b, 0x1405c1a29, 0x1405c1b5f, 0x1405c1c5f, 0x1405c1ccf, 0x1405c1d23, 0x1405c1d77]
    stores = [0x1405c1802, 0x1405c1926, 0x1405c1a4a, 0x1405c1b80, 0x1405c1c8b, 0x1405c1cdf, 0x1405c1d33, 0x1405c1d87]
    names = []
    for value, (label, address, ref, store) in enumerate(zip(labels, literal, refs, stores)):
        name = "HANDSHAKE_TYPE_"+label
        require(app.text(address) == name and app.rip(app.at(ref)) == address, "Enum label reference changed")
        app.at(store, "mov", f"dword ptr [rbp + 0xf], {'r15d' if value == 0 else str(value)}")
        require(f"uStack_50 = {value};" in enum, "Enum integer missing")
        names.append({"name": name, "value": value, "labelReferenceVA": hex(ref), "integerStoreVA": hex(store)})
    require(any(i.mnemonic == "xor" and i.op_str == "r15d, r15d" for i in app.function(0x1405c1750)[:40]), "Enum zero not established")
    require(b"HANDSHAKE_TYPE_DRIVER_API\0" not in app.raw, "Historical name now appears in current PE")
    require(old.text(old.rip(old.at(0x140353381))) == "HANDSHAKE_TYPE_DRIVER_API", "Historical label changed")
    old.at(0x1403533aa, "mov", "dword ptr [rbp - 0x10], 5")
    app.at(0x1405c8365, "xor", "edi, edi")
    app.at(0x1405c84e8, "mov", "dword ptr [rsi + 0x154], edi")
    app.at(0x1405c8550, "mov", "dword ptr [rsi + 0x154], ecx")
    require(app.text(app.rip(app.at(0x1405c84ee))) == "handshake_type", "Wrong handshake parser key")
    require(app.rip(app.at(0x1405c8531)) == 0x143ebea98, "Wrong handshake lookup map")

    app.at(0x1405c92a2, "mov", "dword ptr [rsi + 0x400], ecx")
    require(app.text(app.rip(app.at(0x1405c9240))) == "sample_rate", "Wrong rate key")
    require(struct.unpack("<Q", app.data(0x14281caf0+0xa0, 8))[0] == 0x1405c7180, "Rate accessor slot changed")
    require(struct.unpack("<Q", app.data(0x14281caf0+0xa8, 8))[0] == 0x1405c6670, "Alignment accessor slot changed")
    # This complete leaf has no PE unwind entry. Use its explicit bounded extent.
    rate_rows = list(app.dis.disasm(app.data(0x1405c7180, 0x66), 0x1405c7180))
    require(rate_rows[0].op_str == "eax, dword ptr [rcx + 0x3f0]" and rate_rows[-1].address == 0x1405c71e5 and rate_rows[-1].mnemonic == "ret", "Rate leaf extent changed")
    returned_rates = [struct.unpack("<d", struct.pack("<Q", i.operands[1].imm))[0] for i in rate_rows if i.mnemonic == "movabs"]
    require(sorted(returned_rates) == [44100.0, 48000.0, 96000.0], "Optional rate values changed")
    app.at(0x141379c87, "call", "qword ptr [rax + 0xa0]")
    app.at(0x141379e4a, "movaps", "xmm2, xmm7")
    app.at(0x141379e4d, "movaps", "xmm1, xmm9")
    app.at(0x141379e51, "call", "qword ptr [rax + 0xa8]")
    constants = [struct.unpack("<d", app.data(a, 8))[0] for a in [0x1428050a0, 0x142805098, 0x142805a60, 0x14280a410]]
    require(constants == [5.0, 1.0, 1000.0, 0.5], "Latency arithmetic constants changed")
    for va, op, args in [(0x1405c66c4, "cvttsd2si", "edi, xmm6"), (0x1405c66cc, "cmp", "byte ptr [rcx + 0x35c], 0"),
                         (0x1405c66f9, "idiv", "r9d"), (0x1405c6719, "add", "edi, r9d"),
                         (0x1405c9513, "mov", "byte ptr [rsi + 0x438], 1")]:
        app.at(va, op, args)
    require(app.text(app.rip(app.at(0x1405c951a))) == "latency_overhead", "Wrong overhead key")
    app.at(0x1405c9540, "mov", "byte ptr [rsi + 0x438], al")
    require(struct.unpack("<Q", driver.data(0x1801b8ce8+0x58, 8))[0] == 0x180010080, "Original ASIO slot changed")
    for va, args in [(0x1800100d9, "dword ptr [rdi], eax"), (0x1800100db, "dword ptr [rsi], eax"),
                     (0x1800100dd, "dword ptr [r14], eax"), (0x1800100e5, "dword ptr [rax], 1")]:
        driver.at(va, "mov", args)
    driver.at(0x1800100d4, "call", "0x18000af70")

    examples = []
    for milliseconds in [1, 2, 4, 5, 10]:
        adjusted = milliseconds + (1 if milliseconds < 5 else 0)
        raw_frames = math.trunc(adjusted/1000*48000+0.5)
        examples.append({"latencyInputMs": milliseconds, "adjustedMs": adjusted,
                         "computedFrames": min(4096, ((raw_frames+47)//48)*48)})
    result = {
        "currentBinarySha256": CURRENT_SHA, "historicalBinarySha256": OLD_SHA, "raneAsioSha256": DRIVER_SHA,
        "scope": "Static enum, parser, optional-rate accessor, alignment arithmetic and original buffer-size reporting; no runtime or physical operations",
        "focusedReportSha256": reports,
        "currentHandshakeEnum": names, "historicalDriverApiValue": 5,
        "currentUnknownHandshakeDefault": {"completeObjectOffset": "0x154", "value": 0, "meaning": "HANDSHAKE_TYPE_NONE",
                                           "assembly": app.window(0x1405c8531, 0, 13)},
        "handshakeConsequence": "Old DRIVER_API XML is not recognized by this current map; copying old numeric 5 would select AKAI. Neither fallback nor a substituted kind is an implemented SL3 handshake.",
        "optionalRate": {"completeObjectOffset": "0x400", "interfaceOffset": "0x10", "slot": "0xA0",
                         "recognizedHz": sorted(returned_rates), "assembly": [f"{i.address:x}: {i.mnemonic} {i.op_str}" for i in rate_rows]},
        "alignment": {"slot": "0xA8", "function": "0x1405c6670", "inputAbi": "RCX descriptor interface, XMM1 latency milliseconds, XMM2 rate Hz",
                      "legacyFlagCompleteOffset": "0x35C", "alignmentMapCompleteOffset": "0x408",
                      "latencyOverheadCompleteOffset": "0x438", "latencyOverheadDefault": True,
                      "formulaBeforeAlignment": "trunc(((latencyMs + (latencyMs < 5 && overhead ? 1 : 0)) / 1000) * rateHz + 0.5)",
                      "maximumFrames": 4096, "assembly": app.window(0x1405c6684, 0, 45),
                      "examples": examples, "exampleAssumptions": "Synthetic arithmetic only: rate 48000, overhead true, legacy true, single alignment 48, no earlier device-latency adjustment",
                      "asioHostBankEquivalenceProven": False},
        "originalAsioBuffers": {"function": "0x180010080", "contract": "min=max=preferred=computed configured value, granularity=1", "assembly": driver.window(0x18001009e, 0, 26),
                                "physicalOrConfiguredValueMeasured": False},
        "remaining": ["Legitimate current driver-API/connection adaptation", "PortAudio application-buffer versus ASIO host-bank adaptation",
                      "Hardware rate-selection sequencing and recovery", "Physical PCM, latency, routing and two-deck DVS"],
    }
    output = ROOT / "docs/evidence/serato500-clock-handshake-contract.json"
    output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(f"Verified handshake/rate/alignment and original fixed ASIO buffer reporting; wrote {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
