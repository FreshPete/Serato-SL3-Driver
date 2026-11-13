"""Check or discover Windows in-memory descriptor entry points without launching Serato."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import runpy
import struct

import capstone
from capstone.x86 import X86_REG_RIP

HERE = Path(__file__).resolve().parent
IMAGE = runpy.run_path(str(HERE / "export-serato-clock-handshake-evidence.py"))
RTTI = runpy.run_path(str(HERE / "export-serato-aggregation-selection.py"))["rtti"]
ORIGINAL_ARCHIVE_SHA = "872fc4fdad2eab2ddd34387d2d3c04dd9731c84798d9fdc7bd05ca54e1567db8"
DEFAULT_EXE = Path("C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe")
RIP_LEA = re.compile(rb"[\x48-\x4f]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]")
RIP_POINTER_STORE = re.compile(rb"(?=[\x48-\x4f]\x89[\x05\x0d\x15\x1d\x25\x2d\x35\x3d])")
FOLDERS = ("userio/midi", "userio/audio", "userio/hid", "userio_partner/midi")
CLASSIFIER = ("native_pro_device", "Device type is missing", "product_id")
PARSER = ("root node missing", "supported_apps", "native_pro_device", "win_audio_device_name")
FACTORY = ("Error loading XML for device: ", "Error creating device descriptor: ")


def rip_references(app, targets):
    for section in app.pe.sections:
        if not section.Characteristics & 0x20000000:
            continue
        base = app.base + section.VirtualAddress
        raw = section.get_data()
        for match in RIP_LEA.finditer(raw):
            offset = match.start()
            if offset + 7 > len(raw):
                continue
            address = base + offset
            target = address + 7 + struct.unpack_from("<i", raw, offset + 3)[0]
            if target not in targets:
                continue
            try:
                rows = app.function(address)
            except ValueError:
                continue
            row = next((instruction for instruction in rows if instruction.address == address), None)
            if row is not None and row.mnemonic == "lea" and any(
                operand.type == capstone.CS_OP_MEM and operand.mem.base == X86_REG_RIP
                and address + row.size + operand.mem.disp == target for operand in row.operands
            ):
                yield target, rows[0].address, row


def literal_inventory(app, labels):
    addresses = {}
    for label in labels:
        literal = label.encode("ascii") + b"\0"
        for section in app.pe.sections:
            if section.Characteristics & 0x20000000 or not section.Characteristics & 0x40000000:
                continue
            for match in re.finditer(re.escape(literal), section.get_data()):
                addresses[app.base + section.VirtualAddress + match.start()] = label
    references = {label: {} for label in labels}
    for target, entry, row in rip_references(app, addresses):
        references[addresses[target]].setdefault(entry, []).append(row)
    return Counter(addresses.values()), references


def only(items, description):
    values = list(items)
    if len(values) != 1:
        raise ValueError(f"Expected one {description}, found {len(values)}")
    return values[0]


def anchored_function(references, labels, description):
    shared = set.intersection(*(set(references[label]) for label in labels))
    entry = only(shared, description)
    rows = [only(references[label][entry], f"{label!r} reference in {description}") for label in labels]
    if rows != sorted(rows, key=lambda row: row.address):
        raise ValueError(f"Unexpected literal order in {description}")
    return entry, rows


def direct_calls(rows):
    return [(row, row.operands[0].imm) for row in rows
            if row.mnemonic == "call" and row.operands[0].type == capstone.CS_OP_IMM]


def callers(app, target):
    for section in app.pe.sections:
        if not section.Characteristics & 0x20000000:
            continue
        raw = section.get_data()
        base = app.base + section.VirtualAddress
        for match in re.finditer(b"\xe8", raw):
            offset = match.start()
            address = base + offset
            if offset + 5 > len(raw) or address + 5 + struct.unpack_from("<i", raw, offset + 1)[0] != target:
                continue
            try:
                rows = app.function(address)
            except ValueError:
                continue
            for index, row in enumerate(rows):
                if row.address == address and direct_calls([row]):
                    yield rows, index
                    break


def installed_tables(app, rows, receiver, type_name):
    for address, store in zip(rows, rows[1:]):
        if (address.mnemonic != "lea" or not address.op_str.startswith("rax, [rip + ")
                or (store.mnemonic, store.op_str) != ("mov", f"qword ptr [{receiver}], rax")):
            continue
        table = app.rip(address)
        try:
            RTTI(app, table, type_name)
        except (ValueError, struct.error):
            continue
        yield table


def reader_calls(app, entry, first_literal):
    rows = [row for row in app.function(entry) if row.address < first_literal.address]
    # Both readers get the resource provider, then pass it with the native
    # output string and resource identifier as the first three arguments.
    for index in range(4, len(rows)):
        provider, identifier, output, receiver, call = rows[index - 4:index + 1]
        if (direct_calls([provider]) and identifier.mnemonic == "mov"
                and identifier.op_str.startswith("r8, ") and output.mnemonic == "lea"
                and output.op_str.startswith("rdx, ") and receiver.mnemonic == "mov"
                and receiver.op_str == "rcx, rax" and direct_calls([call])):
            yield provider.operands[0].imm, call.operands[0].imm, call


def member(row, index, register, width):
    if len(row.operands) > index:
        op = row.operands[index]
        if (op.type == capstone.CS_OP_MEM and row.reg_name(op.mem.base) == register
                and not op.mem.index and op.size == width):
            return op.mem.disp
    return None


def string_layout(app, constructor, destructor):
    rows = app.function(destructor)
    resets = []
    for length, capacity, storage in zip(rows, rows[1:], rows[2:]):
        length_offset = member(length, 0, "rbx", 8)
        capacity_offset = member(capacity, 0, "rbx", 8)
        if (all(row.mnemonic == "mov" for row in (length, capacity, storage))
                and length_offset is not None and capacity_offset is not None
                and length.operands[1].type == capacity.operands[1].type == capstone.CS_OP_IMM
                and length.operands[1].imm == 0 and storage.op_str == "byte ptr [rbx], 0"):
            resets.append((length_offset, capacity_offset, capacity.operands[1].imm))
    length, capacity, inline = only(resets, "native string reset layout")
    if length != inline + 1 or capacity != length + 8 or not 8 <= length <= 64:
        raise ValueError("Native string storage and metadata do not agree")
    _, preserve, compare, branch, heap = only(
        (rows[index:index + 5] for index, row in enumerate(rows[:-4])
         if row.mnemonic == "mov" and member(row, 1, "rcx", 8) == capacity
         and row.reg_name(row.operands[0].reg) == "rdx"), "native string capacity load")
    reset = only((row.address for row in rows if row.mnemonic == "mov" and member(row, 0, "rbx", 8) == length),
                 "native string length reset")
    if ((preserve.mnemonic, preserve.op_str) != ("mov", "rbx, rcx")
            or (compare.mnemonic, compare.op_str) != ("cmp", f"rdx, {inline:#x}")
            or branch.mnemonic != "jbe" or branch.operands[0].imm != reset
            or (heap.mnemonic, heap.op_str) != ("mov", "rcx, qword ptr [rcx]")):
        raise ValueError("Native string heap branch differs")
    writes = {member(row, 0, "rcx", 8) for row in app.function(constructor)
              if row.mnemonic == "mov" and row.op_str.endswith(", rax")}
    if writes - {None} != {length, capacity}:
        raise ValueError("Native string constructor metadata differs")
    return {"makeRva": hex(constructor - app.base), "destroyRva": hex(destructor - app.base),
            "bytes": capacity + 8, "lengthOffset": length, "capacityOffset": capacity, "inlineCapacity": inline}


def reader_result_layout(app, reader, string):
    rows = [row for row in app.function(reader) if row.mnemonic != "nop"]
    index = only((index for index, row in enumerate(rows[1:-1], start=1)
                  if row.mnemonic == "cmp" and member(row, 0, "rdi", 8) == string["lengthOffset"]
                  and row.operands[1].type == capstone.CS_OP_IMM and row.operands[1].imm == 0
                  and rows[index - 1].mnemonic == "call" and rows[index - 1].op_str == "qword ptr [rax + 0x20]"
                  and rows[index + 1].mnemonic == "jne"), "native text result check")
    success = rows[index + 1].operands[0].imm
    app.at(success, "mov", "rax, rdi")
    precheck = rows[:index]
    writes = [(row.mnemonic, row.op_str) for row in precheck
              if set(row.regs_access()[1]) & {capstone.x86.X86_REG_RBP, capstone.x86.X86_REG_RDI}]
    if writes != [("mov", "rbp, r8"), ("mov", "rdi, rdx")]:
        raise ValueError("Native text argument registers differ")
    stack = [row for row in precheck if capstone.x86.X86_REG_RSP in row.regs_access()[1]
             and row.mnemonic != "call"]
    if (len(stack) != 4 or any(row.mnemonic != "push" for row in stack[:3])
            or stack[3].mnemonic != "sub" or not stack[3].op_str.startswith("rsp, ")
            or stack[3].operands[1].type != capstone.CS_OP_IMM):
        raise ValueError("Native text stack frame differs")
    frame_bytes = stack[3].operands[1].imm
    if not 32 <= frame_bytes <= 4096 or frame_bytes % 16:
        raise ValueError("Native text stack allocation differs")
    output_writes = {member(row, 0, "rdx", 8): row.operands[1].imm for row in precheck
                     if row.mnemonic == "mov" and member(row, 0, "rdx", 8) is not None
                     and row.operands[1].type == capstone.CS_OP_IMM}
    if output_writes != {string["lengthOffset"]: 0, string["capacityOffset"]: string["inlineCapacity"]}:
        raise ValueError("Native text output initializes a different string layout")
    return {
        "checkRva": hex(rows[index].address - app.base),
        "nonemptyReturnRva": hex(success - app.base),
        "returnAddressStackOffset": hex(24 + frame_bytes),
        "identifierRegister": "rbp",
        "outputRegister": "rdi",
    }


def identifier_path(app, constructor, reader, result, string):
    rows = [row for row in app.function(reader) if row.mnemonic != "nop"
            and int(result["checkRva"], 16) < row.address - app.base < int(result["nonemptyReturnRva"], 16)]
    formatter = only((target for setup, receiver, call, output in zip(rows, rows[1:], rows[2:], rows[3:])
                      if setup.mnemonic == "lea" and setup.op_str.startswith("rdx, [rsp + ")
                      and (receiver.mnemonic, receiver.op_str) == ("mov", "rcx, rbp")
                      and (output.mnemonic, output.op_str) == ("mov", "rdx, rax")
                      for _, target in direct_calls([call])), "missing-resource identifier formatter")
    candidates = []
    formatted = [row for row in app.function(formatter) if row.mnemonic != "nop"]
    for inline, capacity, compare, branch, heap, length in zip(
            formatted, formatted[1:], formatted[2:], formatted[3:], formatted[4:], formatted[5:]):
        offset = member(inline, 1, "rcx", 8)
        if (offset is not None and inline.mnemonic == "lea" and inline.reg_name(inline.operands[0].reg) == "rbx"
                and capacity.mnemonic == "mov" and capacity.reg_name(capacity.operands[0].reg) == "r8"
                and member(capacity, 1, "rcx", 8) == offset + string["capacityOffset"]
                and (compare.mnemonic, compare.op_str) == ("cmp", f"r8, {string['inlineCapacity']:#x}")
                and branch.mnemonic == "jbe" and branch.operands[0].imm == length.address
                and heap.mnemonic == "mov" and heap.reg_name(heap.operands[0].reg) == "rbx"
                and member(heap, 1, "rcx", 8) == offset and length.mnemonic == "mov"
                and length.reg_name(length.operands[0].reg) == "rdx"
                and member(length, 1, "rcx", 8) == offset + string["lengthOffset"]):
            candidates.append(offset)
    offset = only(candidates, "resource path string member")
    writes = {(member(row, 0, "rcx", 8), row.op_str.split(", ")[-1]) for row in app.function(constructor)
              if row.mnemonic == "mov"}
    if not {(offset + string["lengthOffset"], "rax"),
            (offset + string["capacityOffset"], f"{string['inlineCapacity']:#x}")} <= writes:
        raise ValueError("Resource identifier constructor does not initialize the path string")
    return offset


def resource_mutators(app, folder_helper, reader, result, string):
    rows = [row for row in app.function(folder_helper) if row.mnemonic != "nop"]
    candidates = []
    for index in range(2, len(rows) - 6):
        constructor, identifier, output, receiver, provider, temporary, destructor = rows[index:index + 7]
        if (identifier.mnemonic != "mov" or identifier.op_str != "r8, rax"
                or output.mnemonic != "lea" or not output.op_str.startswith("rdx, [rsp + ")
                or receiver.mnemonic != "mov" or not receiver.op_str.startswith("rcx, ")
                or temporary.mnemonic != "lea" or not temporary.op_str.startswith("rcx, [rsp + ")
                or rows[index - 1].mnemonic != "lea" or rows[index - 1].op_str != temporary.op_str):
            continue
        calls = direct_calls([constructor, provider, destructor])
        if len(calls) == 3 and any(row.mnemonic == "call" and row.op_str == "qword ptr [rax + 0x28]"
                                   for row in app.function(calls[1][1])):
            candidates.append([target for _, target in calls])
    constructor, listing, destructor = only(candidates, "native identifier constructor/listing/destructor sequence")
    insert = only((target for previous, call in zip(rows, rows[1:])
                   if previous.mnemonic == "mov" and previous.op_str == "rdx, qword ptr [rcx + 8]"
                   for _, target in direct_calls([call])), "native append call")
    insertion = app.function(insert)
    strides = [row.operands[2].imm for row in insertion if row.mnemonic == "imul"
               and len(row.operands) == 3 and row.operands[2].type == capstone.CS_OP_IMM]
    stride = only(set(strides), "resource identifier stride")
    if len(strides) < 3 or not 32 <= stride <= 1024 or stride % 8:
        raise ValueError("Resource identifier stride is not corroborated")
    if destructor not in {target for _, target in direct_calls(insertion)}:
        raise ValueError("Native append does not use the identified resource destructor")
    path = identifier_path(app, constructor, reader, result, string)
    if not 0 < path <= stride - string["bytes"] or path % 8:
        raise ValueError("Resource path does not fit in the resource identifier")
    return {
        "makeIdentifierRva": hex(constructor - app.base),
        "listResourcesRva": hex(listing - app.base),
        "destroyIdentifierRva": hex(destructor - app.base),
        "appendRva": hex(insert - app.base),
        "identifierBytes": stride,
        "pathOffset": path,
    }


def primary_registry_layout(app, registry, factory_call):
    rows = [row for row in app.function(registry) if row.mnemonic != "nop"]
    if only((row.address for row in rows if (row.mnemonic, row.op_str) == ("mov", "r13, rcx")),
            "primary registry receiver assignment") >= factory_call.address:
        raise ValueError("Primary registry receiver was assigned after descriptor creation")
    appends = []
    for index, row in enumerate(rows[3:-3], 3):
        if row.address <= factory_call.address or row.mnemonic != "lea" or row.operands[0].reg != capstone.x86.X86_REG_RCX:
            continue
        vector = member(row, 1, "r13", 8)
        if vector is None:
            continue
        predicate, test, skip = rows[index - 3:index]
        load, compare, grow = rows[index + 1:index + 4]
        call = direct_calls([predicate])
        if (not call or (test.mnemonic, test.op_str) != ("test", "al, al") or skip.mnemonic != "jne"
                or (load.mnemonic, load.op_str) != ("mov", "rdx, qword ptr [rcx + 8]")
                or (compare.mnemonic, compare.op_str) != ("cmp", "rdx, qword ptr [rcx + 0x10]")
                or grow.mnemonic != "je" or not grow.address < grow.operands[0].imm < skip.operands[0].imm):
            continue
        stores = [ins for ins in rows[index + 4:] if ins.address < grow.operands[0].imm]
        if not stores or not any(ins.mnemonic == "mov" and member(ins, 0, "rdx", 8) == 0 for ins in stores):
            continue
        advance = [ins for ins in stores if ins.mnemonic == "add" and member(ins, 0, "rcx", 8) == 8
                   and ins.operands[1].type == capstone.CS_OP_IMM]
        if len(advance) == 1:
            appends.append((vector, advance[0].operands[1].imm, call[0][1]))
    if len(appends) != 2 or appends[0] != appends[1]:
        raise ValueError("Resource and later descriptor appends disagree on the primary vector layout")
    vector, width, predicate = appends[0]
    leaf = [(row.mnemonic, row.op_str) for row in app.dis.disasm(app.data(predicate, 8), predicate)]
    if (not 0 < vector <= 4096 or vector % 8 or width != 16
            or leaf != [("cmp", "qword ptr [rcx], 0"), ("sete", "al"), ("ret", "")]):
        raise ValueError("Primary registry append is not a null-checked shared pointer")

    tables = []
    for caller, index in callers(app, registry):
        initialized = {member(row, 0, "rdi", 8) for row in caller[:index]
                       if row.mnemonic == "mov" and row.op_str.endswith(", rsi")}
        if (index == 0 or (caller[index - 1].mnemonic, caller[index - 1].op_str) != ("mov", "rcx, rdi")
                or not {vector, vector + 8, vector + 16} <= initialized):
            continue
        tables.extend(installed_tables(app, caller[:index], "rdi", ".?AVPrimaryDeviceManager@@"))
    return {"managerVtableRva": hex(only(tables, "primary manager constructor table") - app.base),
            "vectorOffset": vector, "entryBytes": width}


def executable_matches(app, signatures):
    for section in app.pe.sections:
        if section.Characteristics & 0x20000000:
            raw = section.get_data()
            for signature in signatures:
                for match in re.finditer(re.escape(signature), raw):
                    yield app.base + section.VirtualAddress + match.start()


def readonly_matches(app, value):
    pattern = re.escape(value)
    for section in app.pe.sections:
        if section.Characteristics & 0xa0000000 or not section.Characteristics & 0x40000000:
            continue
        for match in re.finditer(pattern, section.get_data()):
            yield app.base + section.VirtualAddress + match.start()


def aggregation_transfer(rows, start, width):
    # The loop reads the primary vector in order and transfers a shared
    # pointer to an interface at a fixed offset within each descriptor.
    for index, adjustment in enumerate(rows[start:-6], start):
        if (adjustment.mnemonic != "add" or not adjustment.op_str.startswith("rax, ")
                or adjustment.operands[1].type != capstone.CS_OP_IMM):
            continue
        test, null_branch, _, alternate, null_value, pointer, owner, argument, insert = rows[index - 2:index + 7]
        if ([(row.mnemonic, row.op_str) for row in (null_value, pointer, owner, argument)] != [
                ("mov", "rax, r12"), ("mov", "qword ptr [rsp + 0x48], rax"),
                ("mov", "qword ptr [rsp + 0x50], rdi"), ("lea", "rdx, [rsp + 0x48]")]
                or (test.mnemonic, test.op_str) != ("test", "rax, rax")
                or null_branch.mnemonic != "je" or null_branch.operands[0].imm != null_value.address
                or alternate.mnemonic != "jmp" or alternate.operands[0].imm != pointer.address
                or not direct_calls([insert])):
            continue
        advance = [(row, branch) for row, compare, branch in zip(rows[index + 7:], rows[index + 8:], rows[index + 9:])
                   if (row.mnemonic, row.op_str) == ("add", f"rbx, {width:#x}")
                   and (compare.mnemonic, compare.op_str) == ("cmp", "rbx, r14") and branch.mnemonic == "jne"
                   and rows[start].address < branch.operands[0].imm < adjustment.address]
        if len(advance) != 1:
            continue
        loads = [member(row, 1, "rsi", 8) for row in rows[start:index]
                 if row.mnemonic == "mov" and row.operands[0].reg == capstone.x86.X86_REG_RCX
                 and member(row, 1, "rsi", 8) is not None]
        if len(loads) == 1:
            yield loads[0], adjustment.operands[1].imm, insert.operands[0].imm


def aggregation_registry_layout(app, primary):
    constructors = []
    vector = primary["vectorOffset"]
    getters = [b"\x48\x8d\x81" + struct.pack("<i", vector) + b"\xc3"]
    if vector <= 127:
        getters.append(b"\x48\x8d\x41" + bytes([vector]) + b"\xc3")
    for getter in executable_matches(app, getters):
        for body, index in callers(app, getter):
            if [(row.mnemonic, row.op_str) for row in body[index + 1:index + 4]] != [
                    ("mov", "rbx, qword ptr [rax]"), ("mov", "r14, qword ptr [rax + 8]"), ("cmp", "rbx, r14")]:
                continue
            if not list(installed_tables(app, body[:index], "rsi", ".?AVDeviceManager@@")):
                continue
            rows = [row for row in body if row.mnemonic != "nop"]
            start = rows.index(body[index])
            for slot, interface, insert in aggregation_transfer(rows, start, primary["entryBytes"]):
                constructors.append((rows, start, slot, interface, insert, getter))
    rows, start, slot, interface, insert, getter = only(constructors, "DeviceManager constructor and descriptor transfer")
    if not 0 < slot <= 4096 or slot % 8 or not 0 < interface <= 256 or interface % 8:
        raise ValueError("DeviceAggregator slot or descriptor interface is outside bounds")
    if not any(row.mnemonic == "mov" and member(row, 0, "rsi", 8) == slot and row.op_str.endswith(", rcx")
               for row in rows[:start]):
        raise ValueError("DeviceManager does not initialize the DeviceAggregator slot")

    insertion = app.function(insert)
    vector = only((offset for address, begin, end in zip(insertion, insertion[1:], insertion[2:])
                   if address.mnemonic == "lea" and address.op_str.startswith("r12, ")
                   and (offset := member(address, 1, "rdi", 8)) is not None
                   and (begin.mnemonic, begin.op_str) == ("mov", "rsi, qword ptr [r12]")
                   and (end.mnemonic, end.op_str) == ("mov", "rax, qword ptr [r12 + 8]")),
                  "DeviceAggregator descriptor vector")
    width = only((row.operands[1].imm for row in insertion if row.mnemonic == "add"
                  and member(row, 0, "r12", 8) == 8 and row.operands[1].type == capstone.CS_OP_IMM),
                 "DeviceAggregator entry size")
    if not 0 < vector <= 4096 or vector % 8 or width != primary["entryBytes"] or not any(
            (row.mnemonic, row.op_str) == ("add", f"rsi, {width:#x}") for row in insertion):
        raise ValueError("DeviceAggregator iteration and append disagree on entry size")

    tables = []
    for previous, call, result in zip(rows[:start], rows[1:start], rows[2:start]):
        if ((previous.mnemonic, previous.op_str) != ("mov", "rcx, rax")
                or (result.mnemonic, result.op_str) != ("mov", "rdi, rax") or not direct_calls([call])):
            continue
        try:
            constructor = app.function(call.operands[0].imm)
        except ValueError:
            continue
        initialized = {member(row, 0, "rsi", 8) for row in constructor
                       if row.mnemonic == "mov" and row.op_str.endswith(", r14")}
        if {vector, vector + 8, vector + 16} <= initialized:
            tables.extend(installed_tables(app, constructor, "rcx", ".?AVDeviceAggregator@composite@device@serato@@"))
    table = only(tables, "DeviceAggregator constructor table and vector initialization")
    receiver = rows[start - 1]
    if receiver.mnemonic != "mov" or not receiver.op_str.startswith("rcx, qword ptr [rip + "):
        raise ValueError("Primary vector getter receiver is not the primary manager global")
    return {"constructorRva": hex(rows[0].address - app.base), "vtableRva": hex(table - app.base),
            "managerSlotOffset": slot, "vectorOffset": vector, "entryBytes": width, "entryInterfaceOffset": interface,
            "insertionRva": hex(insert - app.base), "primaryVectorGetterRva": hex(getter - app.base),
            "primaryVectorGetterCallRva": hex(rows[start].address - app.base),
            "primaryManagerGlobalRva": hex(app.rip(receiver) - app.base)}


def descriptor_identity_lookup(app, primary):
    vector = primary["vectorOffset"]
    loads = [b"\x4c\x8b\x91" + struct.pack("<i", vector)]  # mov r10, [rcx + vector]
    if vector <= 127:
        loads.append(b"\x4c\x8b\x51" + bytes([vector]))
    candidates = []
    argument_registers = ("r13d", "r12d", "r15d")
    argument_moves = {"r13d, edx", "r12d, r8d", "r15d, r9d"}
    for address in executable_matches(app, loads):
        try:
            body = [row for row in app.function(address) if row.mnemonic != "nop"]
        except ValueError:
            continue
        if not any(row.address == address and row.mnemonic == "mov" and member(row, 1, "rcx", 8) == vector
                   for row in body):
            continue
        for index, row in enumerate(body):
            if (row.mnemonic, row.op_str) != ("mov", "rax, qword ptr [rsi + r10]") or row.address <= address:
                continue
            prologue = {ins.op_str for ins in body[:index] if ins.mnemonic == "mov"}
            if not argument_moves <= prologue or f"rax, qword ptr [rcx + {vector + 8:#x}]" not in prologue:
                continue
            fields = []
            for load, compare, branch, argument, jump in zip(body[index + 1:index + 9:3],
                    body[index + 2:index + 9:3], body[index + 3:index + 10:3], argument_registers, ("jne", "jne", "je")):
                offset = member(load, 1, "rax", 2)
                if (offset is None or load.mnemonic != "movzx" or not load.op_str.startswith("ecx, ")
                        or (compare.mnemonic, compare.op_str) != ("cmp", f"ecx, {argument}")
                        or branch.mnemonic != jump):
                    break
                fields.append(offset)
            if len(fields) == 3 and fields == list(range(fields[0], fields[0] + 6, 2)):
                candidates.append((body[0].address, fields))
    return only(candidates, "primary numeric descriptor lookup")


def descriptor_layout(app, parser, refs, primary, string):
    lookup, (vid, pid, revision) = descriptor_identity_lookup(app, primary)
    body = [row for row in app.function(parser) if row.mnemonic != "nop"]
    if not {("mov", "rsi, rcx"), ("mov", "r14d, r9d")} <= {(row.mnemonic, row.op_str) for row in body[:40]}:
        raise ValueError("Descriptor parser receiver or product argument differs")
    members = [(label, only(refs[label].get(parser, ()), f"{label} descriptor parser key"))
               for label in ("vendor_id", "bcd_device", "win_audio_device_name")]
    stores = []
    for label, anchor in members[:2]:
        index = body.index(anchor)
        field = only((member(store, 0, "rsi", 2) for call, store in zip(body[index + 1:index + 14], body[index + 2:index + 15])
                      if call.mnemonic == "call" and member(call, 0, "rip", 8) is not None
                      and store.mnemonic == "mov" and store.op_str.endswith(", ax")
                      and member(store, 0, "rsi", 2) is not None), f"{label} descriptor field write")
        stores.append(field)
    if stores != [vid, revision] or not any(row.mnemonic == "mov" and member(row, 0, "rsi", 2) == pid
                   and row.op_str.endswith(", r14w") for row in body):
        raise ValueError("Descriptor identity writes disagree with the primary lookup")

    label, anchor = members[-1]
    index = body.index(anchor)
    name = only((offset for source, destination, assign, check in zip(
                    body[index + 1:index + 13], body[index + 2:index + 14], body[index + 3:index + 15], body[index + 4:index + 16])
                 if (source.mnemonic, source.op_str) == ("mov", "rdx, rax") and destination.mnemonic == "lea"
                 and destination.op_str.startswith("rcx, ") and (offset := member(destination, 1, "rsi", 8)) is not None
                 and direct_calls([assign]) and check.mnemonic == "cmp"
                 and member(check, 0, "rsi", 8) == offset + string["lengthOffset"]
                 and check.operands[1].type == capstone.CS_OP_IMM and check.operands[1].imm == 0),
                f"{label} assignment and string length check")
    if not revision < name <= 4096 or name % 8:
        raise ValueError("Descriptor ASIO name offset is outside bounds")

    candidates = []
    for address in readonly_matches(app, struct.pack("<Q", parser)):
        if address % 8:
            continue
        table = address - 8  # Complete object's parser is the second slot.
        try:
            RTTI(app, table, ".?AVControllerDescriptor@dj@serato@@")
        except (ValueError, struct.error):
            continue
        candidates.append(table)
    table = only(candidates, "ControllerDescriptor complete vtable and parser slot")
    return {"vtableRva": hex(table - app.base), "numericLookupRva": hex(lookup - app.base), "vidOffset": vid, "pidOffset": pid,
            "revisionOffset": revision, "asioNameOffset": name}


def locator(app, table):
    address, = struct.unpack("<Q", app.data(table - 8, 8))
    signature, offset, displacement, type_rva, hierarchy, self_rva = struct.unpack("<6I", app.data(address, 24))
    if signature != 1 or displacement or app.base + self_rva != address:
        raise ValueError("Expected an x64 complete-object locator")
    return offset, type_rva, hierarchy


def secondary_tables(app, complete):
    _, type_rva, hierarchy = locator(app, complete)
    for match in readonly_matches(app, struct.pack("<3I", 0, type_rva, hierarchy)):
        address = match - 8
        signature, offset, _, _, _, self_rva = struct.unpack("<6I", app.data(address, 24))
        if signature != 1 or app.base + self_rva != address or not 0 < offset <= 4096 or offset % 8:
            continue
        for reference in readonly_matches(app, struct.pack("<Q", address)):
            if reference % 8 == 0:
                yield reference + 8, offset


def common_descriptor_interface(app, descriptor):
    complete = app.base + int(descriptor["vtableRva"], 16)
    fields = [descriptor[key] for key in ("vidOffset", "pidOffset", "revisionOffset")]
    candidates = []
    for table, offset in secondary_tables(app, complete):
        getters = struct.unpack("<3Q", app.data(table + 0x18, 24))
        if all(app.data(getter, 8) == b"\x0f\xb7\x81" + struct.pack("<i", field - offset) + b"\xc3"
               for getter, field in zip(getters, fields)):
            candidates.append((table, offset))
    return only(candidates, "common descriptor interface and USB identity getters")


def descriptor_transfer_table(app, descriptor, aggregation):
    complete = app.base + int(descriptor["vtableRva"], 16)
    offset = aggregation["entryInterfaceOffset"]
    candidates = []
    tables = {table for table, member_offset in secondary_tables(app, complete) if member_offset == offset}
    for _, entry, address in rip_references(app, {complete}):
        body = app.function(entry)
        index = body.index(address)
        if index + 1 == len(body):
            continue
        store = body[index + 1]
        if store.mnemonic != "mov" or store.op_str != "qword ptr [rdi], rax":
            continue
        for secondary, secondary_store in zip(body[index + 2:index + 6], body[index + 3:index + 7]):
            if (secondary.mnemonic == "lea" and secondary.op_str.startswith("rax, [rip + ")
                    and secondary_store.mnemonic == "mov" and secondary_store.op_str.endswith(", rax")
                    and member(secondary_store, 0, "rdi", 8) == offset and app.rip(secondary) in tables):
                candidates.append(app.rip(secondary))
    return only(candidates, "constructed descriptor interface at the transfer offset")


def aggregation_precedence(app, descriptor, aggregation, string, common):
    transfer = descriptor_transfer_table(app, descriptor, aggregation)
    common_table, common_offset = common
    insert = app.base + int(aggregation["insertionRva"], 16)
    body = [row for row in app.function(insert) if row.mnemonic != "nop"]
    append = only((index for index, row in enumerate(body) if row.mnemonic == "add"
                   and member(row, 0, "r12", 8) == 8), "DeviceAggregator fast append")
    expected_slots = [0x18, 0x20, 0x28]
    incoming = []
    compared = []
    for call, value, branch in zip(body[:append], body[1:append], body[2:append]):
        slot = member(call, 0, "rax", 8)
        if slot is None:
            slot = member(call, 0, "rdx", 8)
        if call.mnemonic != "call" or slot not in expected_slots:
            continue
        destination = member(value, 0, "rsp", 2)
        source = member(value, 1, "rsp", 2)
        if value.mnemonic == "mov" and destination is not None and value.op_str.endswith(", ax"):
            incoming.append((slot, destination))
        if value.mnemonic == "cmp" and source is not None and value.op_str.startswith("ax, ") and branch.mnemonic == "jne":
            compared.append((slot, source, branch.operands[0].imm))
    if ([slot for slot, _ in incoming] != expected_slots or len({field for _, field in incoming}) != 3
            or [(slot, source) for slot, source, _ in compared] != incoming
            or len({target for _, _, target in compared}) != 1):
        raise ValueError("DeviceAggregator duplicate identity comparisons differ")

    identity_mismatch = compared[0][2]
    name_call, length = only(((call, length) for call, length in zip(body[:append], body[1:append])
                             if call.mnemonic == "call" and member(call, 0, "rax", 8) == 0x30
                             and length.mnemonic == "mov" and length.op_str.startswith("rdi, ")
                             and member(length, 1, "rax", 8) == string["lengthOffset"]),
                            "DeviceAggregator existing interface name length")
    test, branch = only(((test, branch) for test, branch in zip(body[:append], body[1:append])
                         if length.address < test.address < identity_mismatch
                         and (test.mnemonic, test.op_str) == ("test", "rdi, rdi") and branch.mnemonic == "je"),
                        "DeviceAggregator empty existing name branch")
    fast_join = body[append + 1]
    if (not name_call.address < test.address < identity_mismatch < body[append].address
            or fast_join.mnemonic != "jmp"
            or not fast_join.address < branch.operands[0].imm < fast_join.operands[0].imm):
        raise ValueError("Empty existing name no longer bypasses the append")
    target = only((index for index, row in enumerate(body) if row.address == branch.operands[0].imm),
                  "duplicate suppression branch target")
    if ([(row.mnemonic, row.op_str) for row in body[target:target + 2]] != [
            ("test", "rbx, rbx"), ("je", hex(fast_join.operands[0].imm))]
            or not any(row.mnemonic == "jmp" and row.operands[0].imm == fast_join.operands[0].imm
                       for row in body[target:target + 18])):
        raise ValueError("Duplicate suppression does not rejoin after insertion")

    getter, = struct.unpack("<Q", app.data(common_table + 0x30, 8))
    offset = only((offset for row in app.function(getter) if row.mnemonic == "lea" and row.op_str.startswith("rdx, ")
                   and (offset := member(row, 1, "rcx", 8)) is not None), "common interface name member")
    name_member = common_offset + offset
    if not descriptor["revisionOffset"] < name_member < descriptor["asioNameOffset"]:
        raise ValueError("Common interface name member is outside the expected descriptor region")
    complete = app.base + int(descriptor["vtableRva"], 16)
    parser, = struct.unpack("<Q", app.data(complete + 8, 8))
    rows = app.function(parser)
    only((address.address for address, destination, call in zip(rows, rows[1:], rows[2:])
          if address.mnemonic == "lea" and address.op_str.startswith("rdx, [rip + ")
          and destination.mnemonic == "lea" and destination.op_str.startswith("rcx, ")
          and member(destination, 1, "rsi", 8) == name_member and direct_calls([call])
          and app.data(app.rip(address), 1) == b"\0"), "parser initialization of the empty interface name")
    return {"transferredVtableRva": hex(transfer - app.base), "interfaceNameOffset": name_member,
            "emptyExistingNameSuppressesEqualIdentity": True}


def message_sites(body, message, payload):
    for index, (value, receiver, call) in enumerate(zip(body, body[1:], body[2:])):
        if ((value.mnemonic, value.op_str) != ("mov", f"edx, {message:#x}")
                or (receiver.mnemonic, receiver.op_str) != ("mov", "rcx, rax")
                or index == 0 or (body[index - 1].mnemonic, body[index - 1].op_str) != ("mov", f"r8, {payload}")):
            continue
        if any((row.mnemonic, row.op_str) == ("call", "qword ptr [rax + 0x58]") for row in body[index + 3:index + 15]):
            yield from direct_calls([call])


def notice_layout(app, aggregation, common):
    manager = app.base + int(aggregation["constructorRva"], 16)
    constructor = app.function(manager)
    primary = only(installed_tables(app, constructor, "rsi", ".?AVDeviceManager@@"), "DeviceManager primary table")
    _, type_rva, hierarchy = locator(app, primary)
    candidates = []
    for address, store in zip(constructor, constructor[1:]):
        offset = member(store, 0, "rsi", 8)
        if (offset is None or not offset or (store.mnemonic != "mov" or not store.op_str.endswith(", rax"))
                or address.mnemonic != "lea" or not address.op_str.startswith("rax, [rip + ")):
            continue
        table = app.rip(address)
        try:
            if locator(app, table) != (offset, type_rva, hierarchy):
                continue
            handler, = struct.unpack("<Q", app.data(table + 0x38, 8))
            body = app.function(handler)
        except (ValueError, struct.error):
            continue
        if body[0].address != handler or not any((row.mnemonic, row.op_str) == ("mov", "rsi, qword ptr [rdx]") for row in body[:20]):
            continue
        for _, message_ctor in message_sites(body, 0x52, "rsi"):
            candidates.append((handler, message_ctor, table + 0x38))
    handler, message_ctor, slot = only(candidates, "DeviceManager driver notice publisher")
    message_body = app.function(message_ctor)
    ops = {(row.mnemonic, row.op_str) for row in message_body}
    if message_body[0].address != message_ctor or not {
            ("mov", "rbx, r8"), ("mov", "rdi, rcx"), ("mov", "qword ptr [rdi + 0x38], rbx")
    } <= ops:
        raise ValueError("Message constructor does not preserve the 64-bit payload")

    arrivals = []
    for body, index in callers(app, message_ctor):
        before = {(row.mnemonic, row.op_str) for row in body[max(index - 28, 0):index]}
        if not {("shl", "ecx, 0x10"), ("shl", "rbx, 0x20"), ("add", "rax, rcx"), ("add", "rbx, rax"),
                ("mov", "dword ptr [rsp + 0x20], 7")} <= before:
            continue
        arrivals.extend(call.address for call, _ in message_sites(body, 0x2d4, "rbx") if call.address == body[index].address)
    only(arrivals, "USB arrival publisher with packed descriptor identity")
    table, offset = common
    return {"arrivalRva": hex(message_ctor - app.base), "arrivalMessage": 0x2d4,
            "handlerRva": hex(handler - app.base), "commonVtableRva": hex(table - app.base), "commonOffset": offset,
            "callbackSlotRva": hex(slot - app.base)}


def selection_calls(app, publisher):
    for body, index in callers(app, publisher):
        if index < 3:
            continue
        payload, code, sink = body[index - 3:index]
        if ((payload.mnemonic, payload.op_str) != ("mov", "r8, rbx")
                or (code.mnemonic, code.op_str) != ("mov", "edx, 0x2ca")
                or sink.mnemonic != "mov" or not sink.op_str.startswith("rcx, qword ptr [rip + ")
                or not any((row.mnemonic, row.op_str) == ("mov", "dword ptr [rsp + 0x20], 7")
                           for row in body[max(0, index - 7):index - 3])):
            continue
        yield body, index, app.rip(sink)


def selection_guard(app, primary):
    table = app.base + int(primary["managerVtableRva"], 16)
    handler, = struct.unpack("<Q", app.data(table + 0x18, 8))
    getter, = struct.unpack("<Q", app.data(table + 0x30, 8))
    pointer = list(app.dis.disasm(app.data(getter, 8), getter))
    if (len(pointer) != 2 or pointer[0].mnemonic != "mov" or not pointer[0].op_str.startswith("rax, ")
            or pointer[1].mnemonic != "ret" or (selected := member(pointer[0], 1, "rcx", 8)) is None):
        raise ValueError("Primary selection pointer getter differs")

    # The compiler splits this method's unwind range at the first branch.
    # Follow only the entry and its contiguous next fragment.
    first = app.function(handler)
    continuation = app.function(first[-1].address + first[-1].size)
    body = first + continuation
    if not any((row.mnemonic, row.op_str) == ("cmp", "dword ptr [rdx + 0xc], 0x2ca") for row in first):
        raise ValueError("Primary manager callback does not consume the selection message")
    guard = only(((app.rip(load), target) for load, call, test, branch in zip(body, body[1:], body[2:], body[3:])
                  if load.mnemonic == "mov" and load.op_str.startswith("rcx, qword ptr [rip + ")
                  and (test.mnemonic, test.op_str) == ("test", "al, al") and branch.mnemonic == "jne"
                  and any(row.mnemonic == "mov" and member(row, 0, "rbx", 8) == selected
                          and row.op_str.endswith(", rdi") and branch.address < row.address < branch.operands[0].imm
                          for row in body)
                  for _, target in direct_calls([call])), "primary selection exclusion guard")
    gate, reader = guard
    flag = list(app.dis.disasm(app.data(reader, 8), reader))
    if (len(flag) != 2 or flag[0].mnemonic != "movzx" or not flag[0].op_str.startswith("eax, ")
            or flag[1].mnemonic != "ret" or (blocked := member(flag[0], 1, "rcx", 1)) is None):
        raise ValueError("Primary selection exclusion getter differs")
    return gate, selected, blocked


def message_system_table(app, sink):
    stores = []
    for section in app.pe.sections:
        if not section.Characteristics & 0x20000000:
            continue
        raw = section.get_data()
        base = app.base + section.VirtualAddress
        for match in RIP_POINTER_STORE.finditer(raw):
            offset = match.start()
            address = base + offset
            if offset + 7 > len(raw) or address + 7 + struct.unpack_from("<i", raw, offset + 3)[0] != sink:
                continue
            try:
                body = app.function(address)
            except ValueError:
                continue
            for index, row in enumerate(body):
                if (row.address == address and row.mnemonic == "mov" and
                        row.op_str.startswith("qword ptr [rip + ") and
                        app.rip(row) == sink):
                    stores.append((body, index))
    body, index = only(stores, "message system object publication")
    if not body[index].op_str.endswith(", rdi"):
        raise ValueError("Message system publication uses an unproven pointer source")
    # Track the constructed pointer along the non-null allocation branch and
    # distinguish it from the shared-pointer control block published next.
    constructor = only((target for position, (call, result, jump, zero) in
                        enumerate(zip(body, body[1:], body[2:], body[3:]))
                        if position + 4 < index and
                        (result.mnemonic, result.op_str) == ("mov", "rdi, rax") and jump.mnemonic == "jmp" and
                        (zero.mnemonic, zero.op_str) == ("xor", "edi, edi") and
                        jump.operands[0].type == capstone.CS_OP_IMM and
                        jump.operands[0].imm == body[position + 4].address and
                        not any(row.reg_name(register) in ("rdi", "edi", "di", "dil")
                                for row in body[position + 4:index] for register in row.regs_access()[1])
                        for _, target in direct_calls([call])), "published message system constructor")
    setup = app.function(constructor)
    if (not setup or setup[0].address != constructor or
            not any((row.mnemonic, row.op_str) == ("mov", "rsi, rcx") for row in setup[:16]) or
            not any((row.mnemonic, row.op_str) == ("mov", "rax, rsi") for row in setup[-12:]) or
            setup[-1].mnemonic != "ret"):
        raise ValueError("Message system constructor does not return its receiver")
    table = only(installed_tables(app, setup, "rcx", ".?AVMessageSystem@system@message@serato@@"),
                 "message system complete-object table")
    slot = app.data(table + 0x58, 8)
    if len(slot) != 8:
        raise ValueError("Message system dispatch slot is truncated")
    dispatch, = struct.unpack("<Q", slot)
    dispatch_body = app.function(dispatch)
    labels = set()
    for row in dispatch_body:
        if row.mnemonic == "lea" and row.op_str.startswith("rdx, [rip + "):
            try:
                labels.add(app.text(app.rip(row)))
            except (ValueError, UnicodeError):
                continue
    if (not dispatch_body or dispatch_body[0].address != dispatch or not {"Attemping to queue a null ptr...",
            "Attempting to fix invalid queue IDs: "} <= labels):
        raise ValueError("Message system dispatch slot does not match the pointer queue")
    return table, dispatch


def selection_helper_layout(app, primary, descriptor, notice):
    constructor = app.base + int(notice["arrivalRva"], 16)
    notice_handler = app.base + int(notice["handlerRva"], 16)
    lookup = app.base + int(descriptor["numericLookupRva"], 16)
    sink = only((app.rip(row) for row in app.function(notice_handler)
                 if row.mnemonic == "mov" and row.op_str.startswith("rdi, qword ptr [rip + ")),
                "driver notice message system global")
    publishers = []
    for body, index in callers(app, constructor):
        if [(row.mnemonic, row.op_str) for row in body[index - 3:index]] != [
                ("mov", "r8, rsi"), ("mov", "edx, ebp"), ("mov", "rcx, rax")]:
            continue
        if any((row.mnemonic, row.op_str) == ("call", "qword ptr [rax + 0x58]") for row in body[index + 1:index + 10]):
            publishers.append(body[0].address)
    publisher = only(publishers, "generic pointer-message publisher")
    installer = []
    managers = []
    for body, index, bus in selection_calls(app, publisher):
        if bus != sink:
            continue
        for code, load, call in zip(body[:index - 3], body[1:index - 3], body[2:index - 3]):
            if (load.mnemonic != "mov" or not load.op_str.startswith("rcx, qword ptr [rip + ")
                    or not direct_calls([call])):
                continue
            target = call.operands[0].imm
            if target == publisher and (code.mnemonic, code.op_str) == ("mov", "edx, 0x51") and app.rip(load) == sink:
                installer.append(body[index].address)
            if target == lookup:
                managers.append(app.rip(load))
    installer_call = only(installer, "installer completion selection publication")
    manager = only(managers, "USB selection publisher's primary manager global")
    gate, selected, blocked = selection_guard(app, primary)
    table, dispatch = message_system_table(app, sink)
    return {"publisherRva": hex(publisher - app.base), "installerSelectionCallRva": hex(installer_call - app.base),
            "noticeCallbackSlotRva": notice["callbackSlotRva"], "messageSystemGlobalRva": hex(sink - app.base),
            "messageSystemVtableRva": hex(table - app.base), "messageSystemDispatchRva": hex(dispatch - app.base),
            "primaryManagerGlobalRva": hex(manager - app.base), "gateGlobalRva": hex(gate - app.base),
            "selectedDescriptorOffset": selected, "gateFlagOffset": blocked}


def selection_runtime_contract(app, selection, primary, descriptor, notice, string):
    """Emit the notice helper's discovered inputs for an offline build review."""
    guards = {}
    for name, rva in (("noticeHandler", notice["handlerRva"]), ("messagePublisher", selection["publisherRva"]),
                      ("installerSelectionCall", selection["installerSelectionCallRva"])):
        raw = app.data(app.base + int(rva, 16), 8)
        if len(raw) != 8:
            raise ValueError(f"Truncated selection guard: {name}")
        guards[name] = {"rva": rva, "bytes": raw.hex()}
    return {
        "entryGuards": guards,
        "tables": {"primaryManager": primary["managerVtableRva"], "descriptor": descriptor["vtableRva"],
                   "commonDescriptor": notice["commonVtableRva"], "messageSystem": selection["messageSystemVtableRva"]},
        "offsets": {
            "commonInterface": notice["commonOffset"], "vendorId": descriptor["vidOffset"],
            "productId": descriptor["pidOffset"], "revision": descriptor["revisionOffset"],
            "asioName": descriptor["asioNameOffset"],
            "asioNameLength": descriptor["asioNameOffset"] + string["lengthOffset"],
            "asioNameCapacity": descriptor["asioNameOffset"] + string["capacityOffset"],
            "registryVectorBegin": primary["vectorOffset"], "registryVectorEnd": primary["vectorOffset"] + 8,
            "registryEntryBytes": primary["entryBytes"], "selectedDescriptor": selection["selectedDescriptorOffset"],
            "gateFlag": selection["gateFlagOffset"],
        },
    }


def factory_recipe(app, registry, factory, factory_call, primary, identifier):
    """Recover the factory arguments and their ownership cleanup from the caller."""
    rows = [row for row in app.function(registry) if row.mnemonic != "nop"]
    index = only((i for i, row in enumerate(rows) if row.address == factory_call.address), "factory call")
    options, resource, result, receiver = rows[index - 4:index]
    options_stack = member(options, 1, "rbp", 8)
    result_stack = member(result, 1, "rsp", 8)
    if (options.mnemonic != "lea" or not options.op_str.startswith("r9, ") or options_stack is None
            or result.mnemonic != "lea" or not result.op_str.startswith("rdx, ") or result_stack is None
            or (resource.mnemonic, resource.op_str) != ("mov", "r8, rax")
            or (receiver.mnemonic, receiver.op_str) != ("mov", "rcx, rbx")):
        raise ValueError("Descriptor factory argument setup differs")

    prep = rows[max(0, index - 25):index - 4]
    stores = {row.op_str.rsplit(", ", 1)[-1]: member(row, 0, "rbp", 8) for row in prep
              if row.mnemonic == "mov" and member(row, 0, "rbp", 8) is not None}
    if stores.get("rsi") != options_stack or stores.get("r12") != options_stack + 8:
        raise ValueError("Descriptor factory context slots differ")
    flags = only((row.operands[1].imm for row in prep if row.mnemonic == "mov"
                  and member(row, 0, "rbp", 2) == options_stack + 16
                  and row.operands[1].type == capstone.CS_OP_IMM), "descriptor factory options flags")
    context = only((member(row, 1, "rcx", 8) for row in rows[:index] if row.mnemonic == "mov"
                    and row.op_str.startswith("rsi, ") and member(row, 1, "rcx", 8) is not None),
                   "descriptor factory manager context")
    if not any(row.mnemonic == "mov" and row.op_str.startswith("r12, ") and member(row, 1, "rcx", 8) == context + 8
               for row in rows[:index]):
        raise ValueError("Descriptor factory manager owner differs")
    getter = only((target for left, right in zip(prep, prep[1:]) for _, target in direct_calls([left])
                   if (right.mnemonic, right.op_str) == ("mov", "rbx, rax")), "descriptor factory singleton getter")
    getter_rows = app.function(getter)
    load, test, jump = getter_rows[1:4]
    if (load.mnemonic != "mov" or not load.op_str.startswith("rax, ") or member(load, 1, "rip", 8) is None
            or (test.mnemonic, test.op_str) != ("test", "rax, rax") or jump.mnemonic != "jne"):
        raise ValueError("Descriptor factory singleton load differs")
    singleton = app.rip(load)
    stores = {app.rip(row) for row in getter_rows if row.mnemonic == "mov" and row.op_str.endswith(", rax")
              and member(row, 0, "rip", 8) is not None}
    storage = app.pe.get_section_by_rva(singleton - app.base)
    if stores != {singleton} or storage is None or not storage.Characteristics & 0x80000000:
        raise ValueError("Descriptor factory singleton is not published to its writable slot")

    result_rows = rows[index + 1:]
    begin, end = result_rows[:2]
    if (begin.mnemonic != "mov" or not begin.op_str.startswith("rbx, ") or member(begin, 1, "rsp", 8) != result_stack
            or end.mnemonic != "mov" or not end.op_str.startswith("r15, ") or member(end, 1, "rsp", 8) != result_stack + 8):
        raise ValueError("Descriptor factory result vector differs")
    release, release_index = only(((target, i)
        for i in range(3, len(result_rows) - 8) for _, target in direct_calls([result_rows[i]])
        if result_rows[i - 3].mnemonic == "lea" and result_rows[i - 3].op_str.startswith("r8, ")
        and member(result_rows[i - 3], 1, "rsp", 8) == result_stack
        and [(row.mnemonic, row.op_str) for row in result_rows[i - 2:i]] == [("mov", "rdx, r15"), ("mov", "rcx, rbx")]),
        "descriptor result destruction")
    capacity, allocation, size, mask, save, limit, branch = result_rows[release_index + 1:release_index + 8]
    if (capacity.mnemonic != "mov" or not capacity.op_str.startswith("rdx, ") or member(capacity, 1, "rsp", 8) != result_stack + 16
            or allocation.mnemonic != "mov" or not allocation.op_str.startswith("rcx, ") or member(allocation, 1, "rsp", 8) != result_stack
            or [(row.mnemonic, row.op_str) for row in (size, mask, save, limit)] != [
                ("sub", "rdx, rcx"), ("and", "rdx, 0xfffffffffffffff0"), ("mov", "rax, rcx"), ("cmp", "rdx, 0x1000")]
            or branch.mnemonic != "jb"):
        raise ValueError("Descriptor result allocation cleanup differs")
    free = only((target for row, target in direct_calls(result_rows) if row.address == branch.operands[0].imm),
                "descriptor result allocation free")
    if free not in {target for _, target in direct_calls(getter_rows)}:
        raise ValueError("Descriptor cleanup and singleton use different allocation release functions")

    vector = primary["vectorOffset"]
    loop = result_rows[:release_index]
    grow = only((grow for setup, load_end, compare, grow in zip(loop, loop[1:], loop[2:], loop[3:])
                 if setup.mnemonic == "lea" and setup.op_str.startswith("rcx, ") and member(setup, 1, "r13", 8) == vector
                 and (load_end.mnemonic, load_end.op_str) == ("mov", "rdx, qword ptr [rcx + 8]")
                 and (compare.mnemonic, compare.op_str) == ("cmp", "rdx, qword ptr [rcx + 0x10]")
                 and grow.mnemonic == "je"), "descriptor factory result append")
    append = only((i for i, row in enumerate(loop) if row.address == grow.operands[0].imm and row.mnemonic == "lea"
                   and row.op_str.startswith("r8, ") and member(row, 1, "rbp", 8) is not None), "factory append pair source")
    copy_pair = only((target for _, target in direct_calls(loop[append + 1:append + 2])), "descriptor pair copy")
    if any(app.function(target)[0].address != target for target in (copy_pair, release)):
        raise ValueError("Descriptor pair copy or release is not a function entry")

    factory_rows = [row for row in app.function(factory) if row.mnemonic != "nop"]
    registers = [(row.mnemonic, row.op_str) for row in factory_rows[:40]]
    if not {("mov", "rdi, r9"), ("mov", "r13, r8"), ("mov", "r12, rdx")} <= set(registers):
        raise ValueError("Descriptor factory argument ownership registers differ")
    destroy = app.base + int(identifier["destroyIdentifierRva"], 16)
    cleanup = only((i for i in range(1, len(factory_rows) - 7) if direct_calls([factory_rows[i]]) == [(factory_rows[i], destroy)]
                    and factory_rows[i - 1].op_str == "rcx, r13" and factory_rows[i + 1].op_str == "rbx, qword ptr [rdi + 8]"),
                   "descriptor factory consumes identifier and options owner")
    if ((factory_rows[cleanup + 4].mnemonic, factory_rows[cleanup + 4].op_str) != ("lea", "rcx, [rbx + 8]")
            or (factory_rows[cleanup + 7].mnemonic, factory_rows[cleanup + 7].op_str) != ("lock xadd", "dword ptr [rax], ecx")
            or not any((row.mnemonic, row.op_str) == ("mov", "rax, r12") for row in factory_rows[cleanup + 8:])):
        raise ValueError("Descriptor factory owner retirement or return differs")
    return {"singletonRva": hex(singleton - app.base), "factoryRva": hex(factory - app.base),
            "copyPairToVectorRva": hex(copy_pair - app.base), "releasePairsRva": hex(release - app.base),
            "freeVectorRva": hex(free - app.base), "optionsOffset": context, "optionsFlags": flags}


def discovery_image(executable):
    if not 0 < executable.stat().st_size <= 256 * 1024 * 1024:
        raise ValueError("Expected a bounded Windows executable")
    with executable.open("rb") as stream:
        expected = hashlib.file_digest(stream, "sha256").hexdigest()
    app = IMAGE["Image"](executable.resolve(), expected)
    if app.pe.FILE_HEADER.Machine != 0x8664 or app.pe.OPTIONAL_HEADER.Magic != 0x20b:
        raise ValueError("Expected a Windows x64 image")
    return app


def anchor_report(executable):
    app = discovery_image(executable)
    groups = {"registration": FOLDERS, "classifier": CLASSIFIER, "parser": PARSER, "factory": FACTORY,
              "sharedParserFields": ("supported_apps", "native_pro_device", "win_audio_device_name")}
    literals, references = literal_inventory(app, {label for group in groups.values() for label in group})
    results = {}
    for name, labels in groups.items():
        shared = set.intersection(*(set(references[label]) for label in labels))
        result = {"commonFunctionCount": len(shared),
                  "labels": {label: {"literalCount": literals[label], "referencingFunctions": len(references[label])}
                             for label in labels}}
        try:
            entry, _ = anchored_function(references, labels, name)
        except ValueError as error:
            result.update(outcome="unresolved", reason=str(error))
        else:
            result.update(outcome="uniqueOrderedAnchor", functionRva=hex(entry - app.base))
        results[name] = result
    return {"schema": "sl3.serato-descriptor-anchor-report.v1", "executableSha256": app.sha,
            "scope": "static anchor inventory only", "anchors": results}


def discover(executable):
    app = discovery_image(executable)
    _, refs = literal_inventory(app, set(FOLDERS + CLASSIFIER + PARSER + FACTORY + ("vendor_id", "bcd_device")))
    registry, folders = anchored_function(refs, FOLDERS, "audio resource registry")
    classifier, classify_refs = anchored_function(refs, CLASSIFIER, "descriptor classifier")
    parser, parse_refs = anchored_function(refs, PARSER, "full descriptor parser")
    factory, _ = anchored_function(refs, FACTORY, "descriptor factory")
    if len({registry, classifier, parser, factory}) != 4:
        raise ValueError("Expected distinct registration and parser functions")

    registry_calls = direct_calls(app.function(registry))
    blocks = [[(row, target) for row, target in registry_calls if start.address < row.address < end.address]
              for start, end in zip(folders, folders[1:])]
    if any(len(block) != 3 for block in blocks):
        raise ValueError("Expected three calls in each resource folder block")
    targets = [tuple(target for _, target in block) for block in blocks]
    if len(set(targets)) != 1 or len(set(targets[0])) != 3:
        raise ValueError("Resource folder call roles differ")
    folder_call, folder_helper = blocks[1][1]
    factory_call = only((row for row, target in registry_calls if target == factory), "registry-to-factory call")
    classifier_call = only((row for row, target in direct_calls(app.function(factory)) if target == classifier),
                           "factory-to-classifier call")
    provider, reader, classification_call, full_parse_call = only(
        ((provider, target, left, right)
         for provider, target, left in reader_calls(app, classifier, classify_refs[0])
         for other_provider, other_target, right in reader_calls(app, parser, parse_refs[0])
         if (provider, target) == (other_provider, other_target)),
        "shared descriptor text reader")
    make_string, _, destroy_string = targets[0]
    for target in (folder_helper, provider, reader, make_string, destroy_string):
        if app.function(target)[0].address != target:
            raise ValueError(f"Call target {target:#x} is not a function entry")
    string = string_layout(app, make_string, destroy_string)
    result = reader_result_layout(app, reader, string)
    identifier = resource_mutators(app, folder_helper, reader, result, string)
    primary = primary_registry_layout(app, registry, factory_call)
    aggregation = aggregation_registry_layout(app, primary)
    descriptor = descriptor_layout(app, parser, refs, primary, string)
    common = common_descriptor_interface(app, descriptor)
    notice = notice_layout(app, aggregation, common)
    try:
        selection = selection_helper_layout(app, primary, descriptor, notice)
        selection["runtimeContract"] = selection_runtime_contract(app, selection, primary, descriptor, notice, string)
        selection["outcome"] = "static candidate"
    except ValueError as error:
        selection = {"outcome": "unresolved", "reason": str(error)}
    try:
        late_factory = {"outcome": "static candidate", **factory_recipe(app, registry, factory, factory_call, primary, identifier)}
    except ValueError as error:
        late_factory = {"outcome": "unresolved", "reason": str(error)}

    def call_sites(call):
        return {"instructionRva": hex(call.address - app.base),
                "returnRva": hex(call.address + call.size - app.base)}

    return {
        "executableSha256": app.sha,
        "registrationRva": hex(registry - app.base),
        "folderHelperRva": hex(folder_helper - app.base),
        "folderCall": call_sites(folder_call),
        "factoryRva": hex(factory - app.base),
        "factoryCall": call_sites(factory_call),
        "classifierCall": call_sites(classifier_call),
        "readerRva": hex(reader - app.base),
        "classificationRead": call_sites(classification_call),
        "fullParseRead": call_sites(full_parse_call),
        "nativeString": string,
        "nativeTextResult": result,
        "resourceIdentifier": identifier,
        "primaryRegistry": primary,
        "aggregationRegistry": aggregation,
        "descriptor": descriptor,
        "notice": notice,
        "aggregationPrecedence": aggregation_precedence(app, descriptor, aggregation, string, common),
        "selectionHelper": selection,
        "lateFactory": late_factory,
        "entryReader": {"entryReaderRva": hex(reader - app.base), "entryReaderBytes": app.data(reader, 16).hex()},
        "scope": "static candidates only",
    }


def inspect(executable):
    app = IMAGE["Image"](executable.resolve(), IMAGE["CURRENT_SHA"])
    archive = executable.with_name("userio_resources.bin")
    archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    IMAGE["require"](archive_sha == ORIGINAL_ARCHIVE_SHA, "Original adjacent Serato archive required")
    checks = (
        (0x140503568, "call", "0x140503a40"),
        (0x140503b1b, "call", "0x1405037d0"),
        (0x1405038e8, "call", "0x1420f31c0"),
        (0x1405038f9, "call", "0x141771e50"),
        (0x141771ece, "call", "qword ptr [rax + 0x28]"),
        (0x14050399e, "mov", "rdx, qword ptr [rcx + 8]"),
        (0x1405039a2, "call", "0x140502de0"),
        (0x140502ef6, "imul", "r15, rcx, 0xe8"),
        (0x140503d34, "call", "0x1405ce9d0"),
        (0x1405cea6c, "call", "0x1405c7330"),
        (0x1405c73a4, "call", "0x141772090"),
        (0x1405c8056, "call", "0x141772090"),
        (0x141772095, "push", "rbp"),
        (0x141772096, "push", "rsi"),
        (0x141772097, "push", "rdi"),
        (0x141772098, "sub", "rsp, 0x80"),
        (0x1417720ae, "mov", "rbp, r8"),
        (0x1417720b1, "mov", "rdi, rdx"),
        (0x141772117, "call", "qword ptr [rax + 0x20]"),
        (0x14177211a, "cmp", "qword ptr [rdi + 0x10], 0"),
        (0x14177211f, "jne", "0x14177222c"),
        (0x14177222c, "mov", "rax, rdi"),
        (0x1404a3421, "call", "0x1404a1da0"),
        (0x1405c807b, "call", "0x1404a6a10"),
        (0x140503d72, "call", "0x140502ae0"),
        (0x140503da5, "add", "qword ptr [rcx + 8], 0x10"),
        (0x140504a63, "call", "0x1405d02e0"),
        (0x140504aaf, "add", "qword ptr [rcx + 8], 0x10"),
        (0x14213c695, "call", "0x1421bc060"),
    )
    for address, opcode, operands in checks:
        app.at(address, opcode, operands)
    folder = app.text(app.rip(app.at(0x140503afb, "lea")))
    IMAGE["require"](folder == "userio/audio", "Registration folder differs")
    return {
        "scope": "static Windows x64 Serato DJ Pro 5.0.0.1278; no runtime injection",
        "executableSha256": app.sha,
        "originalArchiveSha256": archive_sha,
        "folder": folder,
        "folderCall": "0x140503b1b",
        "textCallers": {"classification": "0x1405c73a4", "fullParse": "0x1405c8056"},
        "resourceIdentifierBytes": 0xe8,
        "originalDescriptorFactory": "0x1405ce9d0",
        "originalDescriptorAppend": "0x140503da5",
        "laterStubAppend": "0x140504aaf",
        "checkedInstructions": [f"{address:#x}: {opcode} {operands}" for address, opcode, operands in checks],
    }


def candidate_profile(executable):
    discovered = discover(executable)
    reference = (HERE / "serato-memory-descriptor-profile.json").read_text(encoding="utf-8")
    reviewed = json.loads(reference)
    late = {key: reviewed.pop(key) for key in ("lateFactory", "entryReader")}
    differences = []
    checked_fields = 0

    def select(candidate, expected, path=()):
        nonlocal checked_fields
        if type(candidate) is not type(expected):
            raise ValueError(f"Missing or incompatible candidate field at {'.'.join(path)}")
        if isinstance(expected, dict):
            return {key: select(candidate.get(key), value, (*path, key)) for key, value in expected.items()}
        checked_fields += 1
        if candidate != expected:
            differences.append({"field": ".".join(path), "reviewed": expected, "candidate": candidate})
        return candidate

    profile = select(discovered, reviewed)
    transfer = {key: discovered["aggregationRegistry"][key] for key in (
        "primaryVectorGetterRva", "primaryVectorGetterCallRva", "primaryManagerGlobalRva")}
    late_differences = [
        {"field": f"{section}.{key}", "reviewed": value, "candidate": discovered[section].get(key)}
        for section, fields in late.items() for key, value in fields.items()
        if type(discovered[section].get(key)) is not type(value) or discovered[section].get(key) != value
    ]
    return {"schema": "sl3.serato-memory-profile-review.v1", "scope": "static review only",
            "referenceProfileSha256": hashlib.sha256(reference.encode("utf-8")).hexdigest(),
            "fieldsCompared": checked_fields, "matchingFields": checked_fields - len(differences),
            "differences": differences, "candidateProfile": profile,
            "aggregationPrecedence": discovered["aggregationPrecedence"], "selectionHelper": discovered["selectionHelper"],
            "startupTransfer": transfer,
            "lateFactory": discovered["lateFactory"], "entryReader": discovered["entryReader"],
            "lateDifferences": late_differences,
            "lateMatchingFields": sum(map(len, late.values())) - len(late_differences)}


def check_profile(executable):
    report = candidate_profile(executable)
    differences = report["differences"] + report["lateDifferences"]
    if differences:
        raise ValueError(f"Probe profile differs at {differences[0]['field']}")
    return {"executableSha256": report["candidateProfile"]["executableSha256"],
            "staticProfileFieldsMatched": report["matchingFields"],
            "staticLateProfileFieldsMatched": report["lateMatchingFields"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--discover", action="store_true", help="Find static candidates from the executable alone")
    action.add_argument("--check-profile", action="store_true", help="Compare static candidates with the live probe profile")
    action.add_argument("--candidate-profile", action="store_true", help="Print a candidate profile and review differences")
    action.add_argument("--anchor-report", action="store_true", help="Report independent anchor matches and misses without a profile")
    args = parser.parse_args()
    try:
        inspect_executable = inspect
        if args.check_profile:
            inspect_executable = check_profile
        elif args.discover:
            inspect_executable = discover
        elif args.candidate_profile:
            inspect_executable = candidate_profile
        elif args.anchor_report:
            inspect_executable = anchor_report
        print(json.dumps(inspect_executable(args.exe), indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
