"""Read the pinned historical SL3 descriptors without loading vendor code.

Only projects interoperability fields into evidence. No complete vendor XML,
resource key, decoded bundle, executable or installation is written to Git.
"""
import bisect
import hashlib
import json
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

import capstone
import pefile

ROOT = Path(__file__).resolve().parents[1]
CONSTANTS_SHA = "1b2102001d189daaf6da08d5655426cfb6f48aab720f6ee488ca754c16ff01f3"
TARGETS = [
    dict(version="2.5.5", sha="ba8641d0329fe0c955147d2b45f247eeea82ac0f812fe30a339834dbe0c0a503",
         resource_id=203, ids=0x1447d4810, count=156, lengths=0x140bc5e60, pointers=0x144c6f940,
         p=0x144939380, s=0x1449393d0, key=0x14068002a,
         reader=(0x14067fff0, 0x1406801a2), source=(0x1402abea0, 0x1402abfd7),
         startup=(0x1402afb50, 0x1402b28b4), parser=0x140356cd0,
         key_setup=0x1408bb790, decode=0x1408bb560),
    dict(version="2.5.6", sha="3b04472cd5597fd56266e1c2c86dc298431b0026001aefe4b43aa3b909ee35c5",
         resource_id=207, ids=0x1449e8dc0, count=157, lengths=0x140bc8fc0, pointers=0x144e84940,
         p=0x144b4e380, s=0x144b4e3d0, key=0x14068189a,
         reader=(0x140681860, 0x140681a12), source=(0x1402acce0, 0x1402ace1d),
         startup=(0x1402b0990, 0x1402b3724), parser=0x140357b40,
         key_setup=0x1408bed20, decode=0x1408beaf0),
]


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


class ResourceBlowfish:
    """Original small ECB reader; constants come from the verified input PE."""
    MASK = 0xffffffff

    def __init__(self, p, s, key):
        require(len(p) == 18 and len(s) == 1024 and 1 <= len(key) <= 56, "Invalid cipher setup")
        self.p, self.s = list(p), list(s)
        j = 0
        for i in range(18):
            word = 0
            for _ in range(4):
                word = (word << 8) | key[j]
                j = (j + 1) % len(key)
            self.p[i] ^= word
        left = right = 0
        for i in range(0, 18, 2):
            left, right = self.encrypt(left, right)
            self.p[i:i+2] = left, right
        for i in range(0, 1024, 2):
            left, right = self.encrypt(left, right)
            self.s[i:i+2] = left, right

    def f(self, x):
        s = self.s
        return ((((s[x >> 24] + s[256 + ((x >> 16) & 255)]) & self.MASK)
                 ^ s[512 + ((x >> 8) & 255)]) + s[768 + (x & 255)]) & self.MASK

    def encrypt(self, left, right):
        for i in range(16):
            left ^= self.p[i]
            right ^= self.f(left)
            left, right = right, left
        left, right = right, left
        return left ^ self.p[17], right ^ self.p[16]

    def decrypt_block(self, left, right):
        for i in range(17, 1, -1):
            left ^= self.p[i]
            right ^= self.f(left)
            left, right = right, left
        left, right = right, left
        return left ^ self.p[0], right ^ self.p[1]

    def decrypt(self, data):
        require(8 <= len(data) <= 4*1024*1024 and len(data) % 8 == 0, "Invalid resource block length")
        output = bytearray(len(data))
        for i in range(0, len(data), 8):
            struct.pack_into(">2I", output, i, *self.decrypt_block(*struct.unpack_from(">2I", data, i)))
        return bytes(output)


def inspect(target):
    binary = ROOT / f"artifacts/extracted/Serato DJ Pro {target['version']}/tree/Serato/Serato DJ Pro/Serato DJ Pro.exe"
    raw = binary.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == target["sha"], "Historical executable changed")
    pe = pefile.PE(data=raw, fast_load=True)
    pe.parse_data_directories(directories=[3])
    base = pe.OPTIONAL_HEADER.ImageBase
    spans = sorted((base+e.struct.BeginAddress, base+e.struct.EndAddress) for e in pe.DIRECTORY_ENTRY_EXCEPTION)
    starts = [s[0] for s in spans]
    dis = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    dis.detail = True

    def data(va, size):
        require(size >= 0 and base <= va and va+size <= base+pe.OPTIONAL_HEADER.SizeOfImage, "Image range invalid")
        result = pe.get_data(va-base, size)
        require(len(result) == size, "Truncated image data")
        return result

    def instructions(span):
        require(span in spans, "Function range disagrees with unwind table")
        return list(dis.disasm(data(span[0], span[1]-span[0]), span[0]))

    def containing(va):
        i = bisect.bisect_right(starts, va)-1
        require(i >= 0 and va < spans[i][1], "Missing function")
        return spans[i]

    reader = instructions(target["reader"])
    key_row = next(i for i in reader if i.address == target["key"])
    require(key_row.mnemonic == "movabs" and key_row.operands[1].type == capstone.CS_OP_IMM, "Key source changed")
    key = struct.pack("<Q", key_row.operands[1].imm)
    # The reader indexes tables from the preferred image base (R14).
    for address, scale in ((target["lengths"], 4), (target["pointers"], 8)):
        require(any(o.type == capstone.CS_OP_MEM and o.mem.base == capstone.x86.X86_REG_R14
                    and o.mem.index == capstone.x86.X86_REG_RAX and o.mem.scale == scale
                    and o.mem.disp == address-base for i in reader for o in i.operands), "Resource table changed")
    for callee in (target["key_setup"], target["decode"]):
        require(any(i.mnemonic == "call" and i.op_str == hex(callee) for i in reader), "Resource decoder call changed")

    source = instructions(target["source"])
    require(any(o.type == capstone.CS_OP_MEM and o.mem.base == capstone.x86.X86_REG_RIP
                and i.address+i.size+o.mem.disp == target["ids"] for i in source for o in i.operands), "Registration array source changed")
    require(any(i.mnemonic == "mov" and i.op_str == f"r8d, {hex(target['count']*4)}" for i in source), "Registration array size changed")
    ids = struct.unpack(f"<{target['count']}I", data(target["ids"], target["count"]*4))
    require(len(ids) == len(set(ids)) and target["resource_id"] in ids, "SL3 not in unique registration array")
    startup = instructions(target["startup"])
    source_call = next(i for i in startup if i.mnemonic == "call" and i.op_str == hex(target["source"][0]))
    parser_call = next(i for i in startup if i.mnemonic == "call" and i.op_str == hex(target["parser"]))
    require(source_call.address < parser_call.address < source_call.address+128, "Registration parser loop moved")
    parser = instructions(containing(target["parser"]))
    require(any(i.mnemonic == "call" and i.op_str == hex(target["reader"][0]) for i in parser[:60]), "Descriptor parser resource reader changed")

    constants = data(target["p"], 72) + data(target["s"], 4096)
    require(hashlib.sha256(constants).hexdigest() == CONSTANTS_SHA, "Cipher constants changed")
    p, s = struct.unpack("<18I", constants[:72]), struct.unpack("<1024I", constants[72:])
    # Independent published ECB vectors, checked in both directions.
    vectors = [
        ("0000000000000000", "0000000000000000", "4EF997456198DD78"),
        ("FFFFFFFFFFFFFFFF", "FFFFFFFFFFFFFFFF", "51866FD5B85ECB8A"),
        ("3000000000000000", "1000000000000001", "7D856F9A613063F2"),
    ]
    for k, plain, cipher in vectors:
        test = ResourceBlowfish(p, s, bytes.fromhex(k))
        words = struct.unpack(">2I", bytes.fromhex(plain))
        encrypted = struct.pack(">2I", *test.encrypt(*words))
        require(encrypted == bytes.fromhex(cipher), "Published encryption vector failed")
        require(test.decrypt(encrypted) == bytes.fromhex(plain), "Published decryption vector failed")
    rid = target["resource_id"]
    size = struct.unpack("<I", data(target["lengths"]+rid*4, 4))[0]
    payload_va = struct.unpack("<Q", data(target["pointers"]+rid*8, 8))[0]
    require(size == 2968, "SL3 resource length changed")
    cipher = data(payload_va, size)
    decoded = ResourceBlowfish(p, s, key).decrypt(cipher)
    xml, separator, padding = decoded.partition(b"\0")
    require(separator and not any(padding) and b"<!" not in xml, "Unexpected XML terminator/declaration")
    root = ET.fromstring(xml)
    device = root.find("native_pro_device")
    require(root.tag == "root" and device is not None and device.get("name") == "Rane SL3", "Wrong decoded device")
    fields = {e.tag: e.attrib["value"] for e in device if "value" in e.attrib}
    require(fields["vendor_id"] == "0x1CC5" and fields["product_id"] == "0x0001", "Wrong SL3 identity")
    # Record only that the original secret field is empty; never export key bytes.
    require(fields.pop("secret_key") == "", "Unexpected nonempty device secret field")
    result = {
        "version": target["version"], "binarySha256": target["sha"],
        "registration": {"arrayVA": hex(target["ids"]), "entries": target["count"],
                         "resourceId": rid, "index": ids.index(rid),
                         "sourceFunction": hex(target["source"][0]), "parser": hex(target["parser"]),
                         "startupAssembly": [f"{i.address:x}: {i.mnemonic} {i.op_str}" for i in startup
                                             if source_call.address <= i.address <= parser_call.address+20]},
        "resource": {"payloadVA": hex(payload_va), "bytes": size,
                     "cipherSha256": hashlib.sha256(cipher).hexdigest(),
                     "decodedSha256": hashlib.sha256(decoded).hexdigest(),
                     "xmlBytes": len(xml), "xmlSha256": hashlib.sha256(xml).hexdigest(),
                     "decoderFunction": hex(target["reader"][0]), "deviceSecretFieldEmpty": True},
        "supportedApps": [e.get("value") for e in root.findall("./supported_apps/app")],
        "type": device.tag, "name": device.get("name"), "fields": fields,
        "bufferAlignments": [{"sampleRate": e.get("sample_rate"), "values": [a.get("value") for a in e]}
                             for e in device.findall("buffer_alignments")],
        "outputsInDeclaredOrder": [e.get("value") for e in device.findall("./output_endpoints/mixer_out")],
        "inputsInDeclaredOrder": [e.get("value") for e in device.findall("./input_endpoint/mixer_in")],
        "recordSources": [e.attrib for e in device.findall("./record_sources/map")],
        "driverDetection": {e.tag: e.get("name") for e in device.findall("./driver/driver_detection/*")},
        "validation": {"publishedEcbVectors": len(vectors), "directionsPerVector": 2,
                       "cipherConstantsSha256": CONSTANTS_SHA,
                       "peAndVendorCodeExecuted": False, "physicalAudioVerified": False},
    }
    return result, cipher, decoded, xml


def main():
    records = [inspect(target) for target in TARGETS]
    comparison = {name: records[0][index] == records[1][index]
                  for name, index in (("sameCiphertext", 1), ("sameDecodedResource", 2), ("sameXml", 3))}
    require(all(comparison.values()), "Historical SL3 descriptor changed; reassess comparison")
    result = {"scope": "Static historical descriptor recovery and startup registration-array membership; no runtime admission, audio, handshake, account or current-Serato validation",
              "targets": [r[0] for r in records], "comparison": comparison,
              "vectorSource": "https://www.schneier.com/wp-content/uploads/2015/12/vectors-2.txt",
              "interpretation": "The SL3 descriptor and startup registration-array entry remain in both releases. Presence does not prove successful runtime connection or contradict an official end-of-support policy.",
              "remaining": ["Runtime selection and any additional historical product/connection restrictions",
                            "Current descriptor/driver-API integration boundary",
                            "Consumer units for endpoint indices and buffer alignment",
                            "Physical sample-rate, stereo-pair, gain, through and DVS validation"]}
    output = ROOT / "docs/evidence/serato-legacy-sl3-descriptors.json"
    output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(f"Verified both original PEs, registration, six cipher checks per target and identical SL3 XML; wrote {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
