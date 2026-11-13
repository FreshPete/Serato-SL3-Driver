"""Use the Windows loader in a bounded, owned Serato shortcut trial."""

import argparse
from contextlib import closing, nullcontext
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import struct
import time

HERE = Path(__file__).resolve().parent
PROBE = runpy.run_path(str(HERE / "run-serato-memory-descriptor-probe.py"))
SESSION = runpy.run_path(str(HERE / "run-serato-startup-session.py"))
ROOT, require, digest = PROBE["ROOT"], SESSION["require"], SESSION["digest"]
LIBRARY = PROBE["NATIVE_HOOK_LIBRARY"]
NOTICE = runpy.run_path(str(HERE / "serato-owned-notice-poll.py"))
SCHEMA = "sl3.native-descriptor-startup-plan.v1"
PACKAGED_PLAN = ROOT / "watcher-startup-plan.json"
TRANSFER_FIELDS = ("primaryVectorGetterRva", "primaryVectorGetterCallRva", "primaryManagerGlobalRva")
HOOK_EXPORTS = ("Sl3ArmDescriptorHooks", "Sl3RetireDescriptorHooks", "Sl3DescriptorHookPhase")


class ModuleEntry(c.Structure):
    _fields_ = [(name, w.DWORD) for name in ("size", "moduleId", "pid", "globalUsage", "processUsage")] + [
        ("base", c.c_void_p), ("imageSize", w.DWORD), ("handle", w.HMODULE),
        ("name", w.WCHAR * 256), ("path", w.WCHAR * 260),
    ]


class OwnedLoader:
    def __init__(self, owner, expected_creation):
        self.owner, self.k = owner, owner.k
        self.process = self.allocation = None
        self.in_flight = False
        for name, args, result in (
            ("GetModuleHandleW", [w.LPCWSTR], w.HMODULE),
            ("GetModuleHandleExW", [w.DWORD, c.c_void_p, c.POINTER(w.HMODULE)], w.BOOL),
            ("GetModuleFileNameW", [w.HMODULE, w.LPWSTR, w.DWORD], w.DWORD),
            ("GetProcAddress", [w.HMODULE, c.c_char_p], c.c_void_p),
            ("CreateToolhelp32Snapshot", [w.DWORD, w.DWORD], w.HANDLE),
            ("Module32FirstW", [w.HANDLE, c.POINTER(ModuleEntry)], w.BOOL),
            ("Module32NextW", [w.HANDLE, c.POINTER(ModuleEntry)], w.BOOL),
            ("VirtualAllocEx", [w.HANDLE, c.c_void_p, c.c_size_t, w.DWORD, w.DWORD], c.c_void_p),
            ("VirtualFreeEx", [w.HANDLE, c.c_void_p, c.c_size_t, w.DWORD], w.BOOL),
            ("WriteProcessMemory", [w.HANDLE, c.c_void_p, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)], w.BOOL),
            ("ReadProcessMemory", [w.HANDLE, c.c_void_p, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)], w.BOOL),
            ("CreateRemoteThread", [w.HANDLE, c.c_void_p, c.c_size_t, c.c_void_p, c.c_void_p, w.DWORD, c.c_void_p], w.HANDLE),
            ("GetExitCodeThread", [w.HANDLE, c.POINTER(w.DWORD)], w.BOOL),
        ):
            function = getattr(self.k, name)
            function.argtypes, function.restype = args, result
        require(owner.handle and not owner.wait(0), "A live owned Serato process is required")
        self.process = owner.checked(self.k.OpenProcess(0x10043a, False, owner.pid))
        try:
            times = [w.FILETIME() for _ in range(4)]
            owner.checked(self.k.GetProcessTimes(self.process, *(c.byref(value) for value in times)))
            creation = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
            require(str(creation) == expected_creation and not owner.wait(0), "Loader process identity differs")
        except BaseException:
            self.k.CloseHandle(self.process)
            raise

    def modules(self):
        snapshot = self.k.CreateToolhelp32Snapshot(8, self.owner.pid)
        require(snapshot != c.c_void_p(-1).value, "Owned module snapshot failed")
        try:
            require(not self.owner.wait(0), "Owned process exited during module snapshot")
            row = ModuleEntry()
            row.size = c.sizeof(row)
            self.owner.checked(self.k.Module32FirstW(snapshot, c.byref(row)))
            modules = {}
            while True:
                modules[Path(row.path)] = (row.base, row.imageSize)
                if not self.k.Module32NextW(snapshot, c.byref(row)):
                    require(c.get_last_error() == 18, "Owned module enumeration failed")
                    return modules
        finally:
            self.k.CloseHandle(snapshot)

    def system_export(self, name, modules):
        kernel = self.owner.checked(self.k.GetModuleHandleW("kernel32.dll"))
        address = self.owner.checked(self.k.GetProcAddress(kernel, name))
        module = w.HMODULE()
        self.owner.checked(self.k.GetModuleHandleExW(6, address, c.byref(module)))
        path = c.create_unicode_buffer(32768)
        self.owner.checked(self.k.GetModuleFileNameW(module, path, len(path)))
        base, size = modules[Path(path.value)]
        offset = address - module.value
        require(0 <= offset < size, "Windows loader export is outside the matching system module")
        return base + offset

    def allocate(self, size):
        require(self.allocation is None, "One bounded remote allocation is allowed")
        self.allocation = self.owner.checked(self.k.VirtualAllocEx(self.process, None, size, 0x3000, 4))
        return self.allocation

    def write(self, address, data):
        count = c.c_size_t()
        self.owner.checked(self.k.WriteProcessMemory(self.process, address, data, len(data), c.byref(count)))
        require(count.value == len(data), "Incomplete owned-process write")

    def read(self, address, size):
        require(0 < size <= 32768, "Owned-process read exceeds its bound")
        data, count = c.create_string_buffer(size), c.c_size_t()
        self.owner.checked(self.k.ReadProcessMemory(self.process, address, data, size, c.byref(count)))
        require(count.value == size, "Incomplete owned-process read")
        return data.raw

    def call(self, address, argument):
        require(not self.in_flight and not self.owner.wait(0), "Owned loader call is unavailable")
        thread = self.owner.checked(self.k.CreateRemoteThread(self.process, None, 0, address, argument, 0, None))
        self.in_flight = True
        try:
            require(self.k.WaitForSingleObject(thread, 2500) == 0, "Owned loader call timed out")
            self.in_flight = False
            code = w.DWORD()
            self.owner.checked(self.k.GetExitCodeThread(thread, c.byref(code)))
            return code.value
        finally:
            self.k.CloseHandle(thread)

    def close(self):
        try:
            if self.allocation and not self.in_flight and not self.owner.wait(0):
                self.owner.checked(self.k.VirtualFreeEx(self.process, self.allocation, 0, 0x8000))
        finally:
            self.k.CloseHandle(self.process)


def native_plan(profile, aggregation, image, allocation, xml, library_path):
    def address(rva):
        return image + int(rva, 16)

    getter = address(aggregation["primaryVectorGetterRva"])
    reader = address(profile["entryReader"]["entryReaderRva"])
    call = address(aggregation["primaryVectorGetterCallRva"])
    factory, primary, scope, receipt, text = (allocation + offset for offset in (72, 152, 216, 264, 296))
    string, identifier, late, descriptor = (profile[key] for key in ("nativeString", "resourceIdentifier", "lateFactory", "descriptor"))
    registry = profile["primaryRegistry"]
    require(string["bytes"] == 32 and string["lengthOffset"] == 16 and string["capacityOffset"] == 24 and
            string["inlineCapacity"] == 15 and identifier["identifierBytes"] == 232 and registry["entryBytes"] == 16 and
            late["optionsFlags"] == 0x101 and descriptor["pidOffset"] == descriptor["vidOffset"] + 2 and
            descriptor["revisionOffset"] == descriptor["vidOffset"] + 4, "Reviewed native ABI differs")
    getter_bytes = b"\x48\x8d\x81" + struct.pack("<I", registry["vectorOffset"]) + b"\xc3"
    reader_bytes = bytes.fromhex(profile["entryReader"]["entryReaderBytes"])
    text_bytes = xml.encode("utf-8") + b"\0"
    require(len(reader_bytes) == 16 and len(text_bytes) < 16384, "Native reader input exceeds its bounds")
    path_bytes = (str(library_path) + "\0").encode("utf-16-le")
    path_offset = (296 + len(text_bytes) + 1) & ~1
    payload = bytearray(path_offset + len(path_bytes))
    struct.pack_into("<3Q8s16s3Q", payload, 0, getter, reader, call + 5, getter_bytes, reader_bytes, factory, primary, scope)
    functions = [string["makeRva"], string["destroyRva"], identifier["makeIdentifierRva"], identifier["destroyIdentifierRva"],
                 *[late[key] for key in ("copyPairToVectorRva", "factoryRva", "releasePairsRva", "freeVectorRva")]]
    struct.pack_into("<10Q", payload, 72, 0, *map(address, functions), 0)
    struct.pack_into("<6Q4I", payload, 152, address(aggregation["primaryManagerGlobalRva"]), address(registry["managerVtableRva"]),
                     address(late["singletonRva"]), address(descriptor["vtableRva"]), 0, 0,
                     registry["vectorOffset"], late["optionsOffset"], descriptor["vidOffset"], descriptor["asioNameOffset"])
    struct.pack_into("<4Q4I", payload, 216, address(profile["classificationRead"]["returnRva"]),
                     address(profile["fullParseRead"]["returnRva"]), text, address(string["makeRva"]), 0, 0,
                     identifier["pathOffset"], identifier["identifierBytes"])
    payload[296:296 + len(text_bytes)] = text_bytes
    payload[path_offset:] = path_bytes
    return bytes(payload), receipt, allocation + path_offset, (getter, getter_bytes), (reader, reader_bytes), call


def read_primary(loader, profile, aggregation, image, published):
    registry, descriptor = profile["primaryRegistry"], profile["descriptor"]
    manager, = struct.unpack("<Q", loader.read(image + int(aggregation["primaryManagerGlobalRva"], 16), 8))
    begin, end, capacity = struct.unpack("<3Q", loader.read(manager + registry["vectorOffset"], 24))
    require(0 < begin < end <= capacity <= begin + 32768 and (end - begin) % 16 == 0, "Primary vector bounds differ")
    entries = []
    for entry, owner in struct.iter_unpack("<2Q", loader.read(begin, end - begin)):
        if not entry:
            entries.append(None)
            continue
        identity = list(struct.unpack("<3H", loader.read(entry + descriptor["vidOffset"], 6)))
        if identity == PROBE["SL3_IDENTITY"]:
            require((entry, owner) == published, "Live registry does not own the published SL3 pair")
            name = loader.read(entry + descriptor["asioNameOffset"], 32)
            pointer, length, capacity = struct.unpack_from("<Q8x2Q", name)
            require(length == len(b"SL3 Rebuild Development") and length <= capacity and
                    loader.read(pointer, length) == b"SL3 Rebuild Development", "Published ASIO name differs")
            identity.append(True)
        entries.append(identity)
    require(entries.count(PROBE["SL3_IDENTITY"] + [True]) == 1, "Expected one rebuilt SL3 registry entry")
    return entries


def export_rvas(path, names):
    import pefile

    with pefile.PE(str(path), fast_load=True) as pe:
        pe.parse_data_directories(directories=[0])
        exports = {symbol.name.decode("ascii"): symbol.address for symbol in pe.DIRECTORY_ENTRY_EXPORT.symbols
                   if symbol.name and not symbol.forwarder}
    return {name: exports[name] for name in names}


def prepare_plan(application, include_notice=True, retiring_notice=False):
    require(digest(application) == SESSION["APP_SHA"] and
            digest(application.with_name("userio_resources.bin")) == SESSION["ORIGINAL_RESOURCES"] and
            digest(LIBRARY) == PROBE["NATIVE_HOOK_LIBRARY_SHA"], "The original Serato files and reviewed native library are required")
    notice_export = None
    notice_sha = NOTICE["RETIRING_HELPER_SHA"] if retiring_notice else NOTICE["HELPER_SHA"]
    if include_notice:
        helper, entry = NOTICE["NOTICE_IMAGES"][notice_sha]
        require(digest(helper) == notice_sha, "The reviewed notice helper is required")
        notice_export = export_rvas(helper, (entry,))[entry]
    inspector = runpy.run_path(str(HERE / "inspect-serato-memory-descriptor.py"))
    candidate = inspector["candidate_profile"](application)
    require(not candidate["differences"] and not candidate["lateDifferences"], "Native startup profile differs from review")
    # The candidate review reports the profile fields. The startup loader also
    # needs the discovered getter and its unique caller outside that profile.
    transfer = candidate["startupTransfer"]
    selection = candidate["selectionHelper"]
    require(candidate["referenceProfileSha256"] == PROBE["PROFILE_SHA"] and selection["outcome"] == "static candidate" and
            selection["primaryManagerGlobalRva"] == transfer["primaryManagerGlobalRva"], "Native startup recipe differs from review")
    return {"schema": SCHEMA, "profileSha256": PROBE["PROFILE_SHA"], "applicationSha256": SESSION["APP_SHA"],
            "archiveSha256": SESSION["ORIGINAL_RESOURCES"], "librarySha256": PROBE["NATIVE_HOOK_LIBRARY_SHA"],
            "noticeLibrarySha256": notice_sha, "transfer": {key: transfer[key] for key in TRANSFER_FIELDS},
            "noticeCallbackSlotRva": selection["noticeCallbackSlotRva"],
            "hookExports": export_rvas(LIBRARY, HOOK_EXPORTS),
            "noticeArmRva": notice_export,
            "descriptorXml": PROBE["reviewed_xml"]()}


def read_plan(path, expected):
    require((path == PACKAGED_PLAN or path.parent.resolve() == (ROOT / "analysis").resolve()) and
            path.is_file() and not path.is_symlink() and not path.parent.is_junction(),
            "A regular private startup plan is required")
    with path.open("rb") as stream:
        raw = stream.read(32769)
    require(len(raw) <= 32768 and hashlib.sha256(raw).hexdigest() == expected, "Reviewed startup plan hash required")
    plan = json.loads(raw)
    pins = {"schema": SCHEMA, "profileSha256": PROBE["PROFILE_SHA"], "applicationSha256": SESSION["APP_SHA"],
            "archiveSha256": SESSION["ORIGINAL_RESOURCES"], "librarySha256": PROBE["NATIVE_HOOK_LIBRARY_SHA"]}
    require(isinstance(plan, dict) and set(plan) == set(pins) | {"transfer", "noticeCallbackSlotRva", "hookExports",
            "noticeArmRva", "descriptorXml", "noticeLibrarySha256"} and all(plan[key] == value for key, value in pins.items()) and
            isinstance(plan["noticeLibrarySha256"], str) and plan["noticeLibrarySha256"] in NOTICE["NOTICE_IMAGES"],
            "Startup plan identity differs")
    transfer, exports = plan["transfer"], plan["hookExports"]
    require(isinstance(transfer, dict) and set(transfer) == set(TRANSFER_FIELDS) and
            all(isinstance(value, str) and re.fullmatch(r"0x[0-9a-f]{1,8}", value)
                for value in (*transfer.values(), plan["noticeCallbackSlotRva"])) and
            isinstance(exports, dict) and set(exports) == set(HOOK_EXPORTS) and
            all(type(value) is int and 0 < value < 16 * 1024 * 1024 for value in (*exports.values(), plan["noticeArmRva"])) and
            isinstance(plan["descriptorXml"], str) and "\0" not in plan["descriptorXml"] and
            0 < len(plan["descriptorXml"].encode("utf-8")) < 16383,
            "Startup plan fields are invalid")
    return plan


def arm_owned_notice(loader, notice, address, load, offset):
    require(not notice.helper.is_symlink() and digest(notice.helper) == notice.helper_sha256,
            "Reviewed owned notice helper required before loading")
    require(notice.helper not in loader.modules(), "Owned notice helper was already loaded")
    loader.call(load, address)
    module, size = loader.modules()[notice.helper]
    require(0 < offset < size and loader.call(module + offset, 0) == 0, "Native notice helper refused startup")
    notice.bind(loader.owner, after_resume=True)


def wait_owned_notice(loader, notice, image, selection, profile, connected, keep_running=None):
    deadline = time.monotonic() + 50
    wake = connected or notice.helper_sha256 == NOTICE["HELPER_SHA"]
    while time.monotonic() < deadline and not loader.owner.wait(0):
        require(keep_running is None or keep_running(), "Watcher sign-in command was withdrawn during notice polling")
        if notice.poll(loader.owner, wake=wake):
            slot = image + int(selection["noticeCallbackSlotRva"], 16)
            original = image + int(profile["notice"]["handlerRva"], 16)
            require(loader.read(slot, 8) == struct.pack("<Q", original), "Native notice callback did not restore")
            events = notice.events()
            require(connected or not any(event in events for event in ("matching_installed_notice", "selection_requested")),
                    "An unplugged run unexpectedly matched a hardware notice")
            return
        time.sleep(.05)
    raise ValueError("Owned notice helper did not retire in the expected window")


def exercise(loader, profile, plan, logs, since, shortcut_clock, report, connected, notice, keep_running=None):
    aggregation, exports = plan["transfer"], plan["hookExports"]
    modules = loader.modules()
    image, image_size = modules[loader.owner.application]
    require(LIBRARY not in modules, "Native hook library was already loaded")
    load = loader.system_export(b"LoadLibraryW", modules)
    unload = loader.system_export(b"FreeLibrary", modules)
    memory = loader.allocate(32768)
    payload, receipt, library_path, getter, reader, call = native_plan(profile, aggregation, image, memory, plan["descriptorXml"], LIBRARY)
    if notice is not None:
        require(notice.helper_sha256 == plan["noticeLibrarySha256"], "Notice helper differs from the startup plan")
        payload += b"\0" * (len(payload) % 2)
        notice_path = memory + len(payload)
        payload += (str(notice.helper) + "\0").encode("utf-16-le")
    require(len(payload) <= 32768 and all(image <= location < image + image_size for location in (getter[0], reader[0], call)),
            "Trial addresses exceed their reviewed bounds")
    require(loader.read(getter[0], len(getter[1])) == getter[1] and loader.read(reader[0], len(reader[1])) == reader[1] and
            loader.read(call, 5) == b"\xe8" + struct.pack("<i", getter[0] - call - 5), "Owned Serato call sites differ")
    loader.write(memory, payload)
    if notice is not None:
        arm_owned_notice(loader, notice, notice_path, load, plan["noticeArmRva"])
        report["nativeNoticeArmedAfterShortcutMs"] = round((time.monotonic() - shortcut_clock) * 1000, 1)
    require(digest(LIBRARY) == PROBE["NATIVE_HOOK_LIBRARY_SHA"], "Native hook library changed before loading")
    loader.call(load, library_path)
    module, size = loader.modules()[LIBRARY]
    require(all(0 < rva < size for rva in exports.values()), "Trial export is outside the loaded library")
    arm, retire = (module + exports[key] for key in ("Sl3ArmDescriptorHooks", "Sl3RetireDescriptorHooks"))
    phase_rva = exports["Sl3DescriptorHookPhase"]
    require(phase_rva <= size - 8, "Native phase export exceeds its image")
    phase_address, = struct.unpack("<Q", loader.read(module + phase_rva, 8))
    require(module <= phase_address <= module + size - 4 and phase_address % 4 == 0,
            "Native phase address is outside the loaded library")
    armed = False
    safe_to_unload = True
    try:
        safe_to_unload = False
        status = loader.call(arm, memory)
        safe_to_unload = status == 0
        require(status == 1, f"Native hook library refused startup ({status})")
        armed = True
        report["armedAfterShortcutMs"] = round((time.monotonic() - shortcut_clock) * 1000, 1)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and not loader.owner.wait(0):
            phase, = struct.unpack("<i", loader.read(phase_address, 4))
            require(phase in (0, 1, 2), "Unexpected native transaction phase")
            if phase == 2:
                report["nativeCompletedAfterShortcutMs"] = round((time.monotonic() - shortcut_clock) * 1000, 1)
                break
            time.sleep(.05)
        require("nativeCompletedAfterShortcutMs" in report, "Native descriptor transaction did not complete in eight seconds")
    finally:
        if armed and not loader.in_flight and not loader.owner.wait(0):
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                if loader.call(retire, receipt) == 1:
                    safe_to_unload = True
                    break
                time.sleep(.05)
            require(safe_to_unload, "Native hook retirement did not complete")
        if safe_to_unload and not loader.in_flight and not loader.owner.wait(0):
            require(loader.call(unload, module) == 1 and LIBRARY not in loader.modules(), "Native hook library did not unload")
            report["nativeLibraryUnloaded"] = True
            report["nativeUnloadedAfterShortcutMs"] = round((time.monotonic() - shortcut_clock) * 1000, 1)

    result, hits, entry, owner, options = struct.unpack("<iI2QI4x", loader.read(receipt, 32))
    require(result == 1 and hits == 2 and entry and owner and options in (0, 1), "Native publication receipt differs")
    require(loader.read(getter[0], len(getter[1])) == getter[1] and loader.read(reader[0], len(reader[1])) == reader[1],
            "Restored native entry bytes differ")
    report["nativeReceipt"] = {"result": result, "readerHits": hits, "hadOptionsOwner": bool(options),
                               "ownerRefs": struct.unpack("<i", loader.read(owner + 8, 4))[0]}
    report["hookBytesRestored"] = True
    report["primaryRegistry"] = read_primary(loader, profile, aggregation, image, (entry, owner))
    if notice is not None:
        wait_owned_notice(loader, notice, image, plan, profile, connected, keep_running)
        report["nativeNoticeCallbackRestored"] = True
    if connected:
        return
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and not loader.owner.wait(0):
        log = PROBE["offline_log"](logs, loader.owner.pid, since)
        if log and log["offlineAudioStarted"]:
            report["applicationLog"] = log
            report["offlineObservedAfterShortcutMs"] = round((time.monotonic() - shortcut_clock) * 1000, 1)
            return
        time.sleep(.1)
    raise ValueError("Serato did not reach offline audio after native hook retirement")


def connected_verified(report):
    broker = report["broker"]
    return (not report["failure"] and report["inputsUnchanged"] is True and report["cleanup"]["jobEmpty"] is True and
            report.get("nativeLibraryUnloaded") is True and report.get("hookBytesRestored") is True and
            report["normalExitDuringManualClose"] is True and report["driverStageUnchanged"] is True and
            broker.get("nativeAcquisitionReported") is True and broker.get("streamStartReplies", 0) > 0 and
            broker.get("applicationExitRetirementReported") is True)


def run(output, detector=None, connected=False, manual_close_seconds=0, owned_notice_helper=False, prepared=None):
    require((connected and detector is None and 15 <= manual_close_seconds <= 180) or
            (not connected and manual_close_seconds == 0), "An attended close window is required for the connected trial")
    require(c.sizeof(c.c_void_p) == 8 and not c.windll.shell32.IsUserAnAdmin(), "Use ordinary-user 64-bit Python")
    require(output.parent.resolve() == (ROOT / "analysis").resolve() and not output.exists(), "Fresh private analysis output required")
    application = Path(os.environ["ProgramFiles"]) / "Serato/Serato DJ Pro/Serato DJ Pro.exe"
    resource = application.with_name("userio_resources.bin")
    shortcut = Path(os.environ["PUBLIC"]) / "Desktop/Serato DJ Pro.lnk"
    logs = Path(os.environ["USERPROFILE"]) / "Music/_Serato_/Logs"

    def hashes():
        return {key: digest(path) for key, path in (("application", application), ("archive", resource),
                                                   ("shortcut", shortcut), ("library", LIBRARY))}

    before = hashes()
    require(before == {"application": SESSION["APP_SHA"], "archive": SESSION["ORIGINAL_RESOURCES"],
                       "shortcut": PROBE["DESKTOP_SHORTCUT_SHA"], "library": PROBE["NATIVE_HOOK_LIBRARY_SHA"]} and
            not any(path.is_symlink() or path.parent.is_junction() for path in (application, resource, shortcut, LIBRARY)),
            "Original installation, reviewed shortcut and reviewed native library are required")
    require(PROBE["windows_state"](require) == connected,
            "Connect the SL3 before the attended trial" if connected else "Unplug the SL3 before the offline trial")
    watcher_state = PROBE["watcher_state"]()
    PROBE["require_watcher_state"](watcher_state, False, require)
    stage = Path(os.environ["ProgramFiles"]) / "SL3 Rebuild"
    native = PROBE["driver"]() if connected else None
    if native is not None:
        driver_before = native.observe()
        require(driver_before["state"] == "installed" and not (stage / "output-ready-trial-v1").exists(),
                "Only the reviewed standard 64-frame driver stage is permitted")
        transport = PROBE["transport_state"]()
        PROBE["require_connected_transport"](transport, require)
        local_appdata = native.s.known_folder("f1b32785-6fba-4fcf-9d55-7b8e7f157091")
    else:
        require(not any((stage / name).exists() for name in ("on-demand-diagnostic-v1", "output-ready-trial-v1")),
                "Remove any diagnostic driver stage before the offline trial")
    profile = PROBE["reviewed_profile"](before["application"], require)
    plan = prepare_plan(application, include_notice=owned_notice_helper) if prepared is None else prepared[0]
    notice = NOTICE["OwnedNoticePoll"](output, plan["noticeLibrarySha256"]) if owned_notice_helper else None
    owner = SESSION["WindowsProcess"](application, None)
    report = {"before": before, "reviewedProfileSha256": PROBE["PROFILE_SHA"], "watchersAtPreflight": watcher_state,
              "fridaAgentUsed": False, "connected": connected, "failure": None}
    if prepared is not None:
        report["preparedStartupPlanSha256"] = prepared[1]
    if native is not None:
        report.update(driverStage=driver_before, transportAtPreflight=transport, manualCloseSeconds=manual_close_seconds)
    manual_exit = False
    since = time.time()
    watchdog = SESSION["HardDeadline"]((100 if owned_notice_helper else 55) + manual_close_seconds)
    try:
        with (closing(PROBE["LaunchTimingObserver"]()) if detector is None else nullcontext(detector)) as watcher:
            watcher.arm(application)
            since = time.time()
            shortcut_clock = time.monotonic()
            watcher.begin_poll()
            owner.start_shortcut(shortcut, before["shortcut"])
            candidate = PROBE["timing_observer_candidate"](watcher, owner, None, require)
            report["process"] = {**candidate, "detectorPid": watcher.child.pid}
        delay = 3 - (time.monotonic() - shortcut_clock)
        require(not owner.wait(max(0, delay)), "Owned Serato process exited before native loading")
        with closing(OwnedLoader(owner, candidate["created"])) as loader:
            exercise(loader, profile, plan, logs, since, shortcut_clock, report, connected, notice)
        if connected and not owner.wait(0):
            print(f"Native hooks restored. Let Serato settle with playback stopped, then close it normally within "
                  f"{manual_close_seconds} seconds, including any exit confirmation.", flush=True)
            manual_exit = owner.wait(manual_close_seconds)
    except Exception as error:
        report["failure"] = str(error)
    finally:
        try:
            if notice is not None:
                try:
                    notice.close(owner)
                    report["ownedNotice"] = notice.report()
                except (OSError, ValueError) as error:
                    report["failure"] = report["failure"] or str(error)
            report["cleanup"] = owner.cleanup()
        finally:
            watchdog.close()
    if native is not None:
        cleanup = report["cleanup"]
        report["normalExitDuringManualClose"] = manual_exit and cleanup["exitCode"] == 0
        try:
            report["driverStageUnchanged"] = native.observe() == driver_before
        except (OSError, ValueError) as error:
            report["driverStageUnchanged"] = False
            report["driverStageVerificationError"] = str(error)
        report["broker"] = PROBE["broker_evidence"](native.destination, local_appdata, cleanup)
        if cleanup["pid"]:
            try:
                report["applicationLog"] = PROBE["offline_log"](logs, cleanup["pid"], since)
            except OSError as error:
                report["applicationLogError"] = str(error)
    report["after"] = hashes()
    report["inputsUnchanged"] = before == report["after"]
    if native is not None:
        report["connectedTrialVerified"] = connected_verified(report)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    summary = {key: value for key, value in report.items() if key != "primaryRegistry"}
    print(json.dumps(summary, indent=2))
    passed = (not report["failure"] and report["inputsUnchanged"] and report["cleanup"]["jobEmpty"] and
              (not connected or report["connectedTrialVerified"]))
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--output", type=Path, help="Save the owned launch report")
    action.add_argument("--prepare-plan", type=Path, help="Write a private verified startup plan without launching Serato")
    parser.add_argument("--retiring-notice-plan", action="store_true", help="Pin the notice helper that retires without UI messages")
    parser.add_argument("--startup-plan", type=Path, help="Use a previously prepared startup plan")
    parser.add_argument("--expected-plan-sha256", help="Exact SHA-256 of the reviewed startup plan")
    parser.add_argument("--reopen-output", type=Path, help="Verify a second owned shortcut launch with the same detector")
    parser.add_argument("--connected", action="store_true", help="Verify the staged standard 64-frame driver with the SL3 connected")
    parser.add_argument("--owned-notice-helper", action="store_true", help="Observe the matching SL3 notice within the owned launch")
    parser.add_argument("--manual-close-seconds", type=int, default=0, help="Allow a normal manual close in the connected trial")
    args = parser.parse_args()
    if bool(args.startup_plan) != bool(args.expected_plan_sha256) or (
            args.expected_plan_sha256 and not re.fullmatch(r"[0-9a-f]{64}", args.expected_plan_sha256)):
        parser.error("--startup-plan requires its lowercase --expected-plan-sha256")
    if args.prepare_plan and any((args.startup_plan, args.reopen_output, args.connected, args.manual_close_seconds,
                                  args.owned_notice_helper)):
        parser.error("--prepare-plan is a separate read-only preparation action")
    if args.retiring_notice_plan and not args.prepare_plan:
        parser.error("--retiring-notice-plan requires --prepare-plan")
    if args.owned_notice_helper and args.reopen_output:
        parser.error("The notice fallback uses one owned launch at a time")
    if ((args.connected and (not 15 <= args.manual_close_seconds <= 180 or args.reopen_output)) or
            (not args.connected and args.manual_close_seconds)):
        parser.error("The connected trial requires one launch and a manual close window of 15 to 180 seconds")
    try:
        if args.prepare_plan:
            output = args.prepare_plan.absolute()
            require(output.parent.resolve() == (ROOT / "analysis").resolve() and not output.exists(),
                    "A fresh private analysis path is required for the startup plan")
            application = Path(os.environ["ProgramFiles"]) / "Serato/Serato DJ Pro/Serato DJ Pro.exe"
            plan = prepare_plan(application, retiring_notice=args.retiring_notice_plan)
            with output.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(plan, stream, indent=2)
                stream.write("\n")
            print(json.dumps({"plan": str(output), "sha256": digest(output)}, indent=2))
            raise SystemExit(0)
        prepared = ((read_plan(args.startup_plan.absolute(), args.expected_plan_sha256), args.expected_plan_sha256)
                    if args.startup_plan else None)
        output = args.output.absolute()
        if args.reopen_output:
            reopen = args.reopen_output.absolute()
            require(reopen.parent.resolve() == (ROOT / "analysis").resolve() and not reopen.exists() and
                    reopen.resolve() != output.resolve(),
                    "A distinct fresh private analysis path is required for the reopen")
            with closing(PROBE["LaunchTimingObserver"]()) as detector:
                result = run(output, detector, prepared=prepared)
                if result == 0:
                    result = run(reopen, detector, prepared=prepared)
        else:
            result = run(output, connected=args.connected, manual_close_seconds=args.manual_close_seconds,
                         owned_notice_helper=args.owned_notice_helper, prepared=prepared)
        raise SystemExit(result)
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        parser.exit(1, f"{error}\n")
