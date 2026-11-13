"""One bounded UI message hook for an owned Serato diagnostic process."""
import ctypes as c
from ctypes import wintypes as w
from hashlib import sha256
import json
from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "artifacts/build/native-owned-notice-selection-20261110/build/Release/sl3-owned-notice.dll"
HELPER_SHA = "e88f4d16e90b1e6f5edf4567f2b7e38fa350a46ece7451b3627f524d54cb8014"
RETIRING_HELPER = ROOT / "artifacts/build/native-notice-retirement-20261110/Release/sl3-owned-notice.dll"
RETIRING_HELPER_SHA = "eb4dfc407a8e9b26ccd2a575e2776ce40c99652b38702932c14dede3514e3a45"
NOTICE_IMAGES = {HELPER_SHA: (HELPER, "Sl3ObserveEarly"),
                 RETIRING_HELPER_SHA: (RETIRING_HELPER, "Sl3ObserveWithRetirement")}
WAKE_TAG = 0x534C3301


class OwnedNoticePoll:
    helper_sha256 = HELPER_SHA

    def __init__(self, report, helper_sha256=HELPER_SHA):
        source, _ = NOTICE_IMAGES[helper_sha256]
        self.helper_sha256 = helper_sha256
        self.directory = report.with_suffix(".notice")
        if source.is_symlink() or sha256(source.read_bytes()).hexdigest() != helper_sha256:
            raise ValueError("Reviewed owned-notice helper required")
        journal = self.directory / "notice-hook-4294967295-18446744073709551615.log"
        if len(str(journal.absolute()).encode("utf-16-le")) // 2 >= 260:
            raise ValueError("Owned notice journal path exceeds the native helper's limit")
        self.directory.mkdir()
        self.helper = self.directory / source.name
        shutil.copyfile(source, self.helper)
        if sha256(self.helper.read_bytes()).hexdigest() != helper_sha256:
            raise ValueError("Owned-notice helper copy differs")
        self.k = c.WinDLL("kernel32", use_last_error=True)
        self.u = c.WinDLL("user32", use_last_error=True)
        self.visitor = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        for dll, name, args, result in (
            (self.k, "LoadLibraryW", [w.LPCWSTR], w.HMODULE),
            (self.k, "GetProcAddress", [w.HMODULE, c.c_char_p], c.c_void_p),
            (self.k, "FreeLibrary", [w.HMODULE], w.BOOL),
            (self.k, "OpenThread", [w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            (self.k, "GetProcessIdOfThread", [w.HANDLE], w.DWORD),
            (self.k, "WaitForSingleObject", [w.HANDLE, w.DWORD], w.DWORD),
            (self.k, "CloseHandle", [w.HANDLE], w.BOOL),
            (self.u, "SetWindowsHookExW", [c.c_int, c.c_void_p, w.HMODULE, w.DWORD], w.HHOOK),
            (self.u, "UnhookWindowsHookEx", [w.HHOOK], w.BOOL),
            (self.u, "PostThreadMessageW", [w.DWORD, w.UINT, w.WPARAM, w.LPARAM], w.BOOL),
            (self.u, "EnumWindows", [self.visitor, w.LPARAM], w.BOOL),
            (self.u, "GetWindowThreadProcessId", [w.HWND, c.POINTER(w.DWORD)], w.DWORD),
            (self.u, "IsWindowVisible", [w.HWND], w.BOOL),
        ):
            function = getattr(dll, name)
            function.argtypes, function.restype = args, result
        self.module = self.hook = self.thread = self.tid = self.journal = None
        self.removed = False
        self.posts = 0
        self.next_poll = 0

    def startup_script(self):
        _, entry = NOTICE_IMAGES[self.helper_sha256]
        return (
            "\n(() => {\n"
            f"  const helper = Module.load({json.dumps(str(self.helper))});\n"
            f"  const arm = new NativeFunction(helper.getExportByName('{entry}'), 'uint32', ['pointer']);\n"
            "  const status = arm(ptr(0));\n"
            "  if (status !== 0) throw new Error('Owned notice observer refused: ' + status);\n"
            "  send({event: 'native_notice_helper_armed', result: status});\n"
            "})();\n"
        )

    def bind(self, observer, after_resume=False):
        times = [w.FILETIME() for _ in range(4)]
        observer.checked(observer.k.GetProcessTimes(observer.handle, *(c.byref(value) for value in times)))
        created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        self.journal = self.directory / f"notice-hook-{observer.pid}-{created}.log"
        armed = ["notice_observer_armed"]
        allowed = [armed]
        if after_resume:
            # A genuine notice can arrive while the script returns from arming.
            match = ["matching_installed_notice"]
            allowed.extend((armed + match, match + armed))
        if self.events() not in allowed:
            raise ValueError("The owned process did not provide a valid notice observer receipt")

    def events(self):
        if self.journal is None or not self.journal.is_file():
            return []
        with self.journal.open("rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise ValueError("Owned notice journal exceeds its bound")
        return raw.decode("ascii").splitlines()

    def install_hook(self, observer):
        threads = set()

        @self.visitor
        def visit(window, _):
            pid = w.DWORD()
            tid = self.u.GetWindowThreadProcessId(window, c.byref(pid))
            if tid and pid.value == observer.pid and self.u.IsWindowVisible(window):
                threads.add(tid)
            return True

        observer.checked(self.u.EnumWindows(visit, 0))
        if len(threads) != 1 or observer.wait(0):
            return
        self.tid = next(iter(threads))
        self.thread = observer.checked(self.k.OpenThread(0x100800, False, self.tid))
        if self.k.GetProcessIdOfThread(self.thread) != observer.pid or observer.wait(0):
            raise ValueError("Visible window thread does not belong to the owned process")
        self.module = observer.checked(self.k.LoadLibraryW(str(self.helper)))
        callback = observer.checked(self.k.GetProcAddress(self.module, b"Sl3PollOwnedMessage"))
        self.hook = observer.checked(self.u.SetWindowsHookExW(3, callback, self.module, self.tid))

    def poll(self, observer, wake=True):
        rows = self.events()
        if "notice_page_protection_restore_failed" in rows:
            raise ValueError("Native notice callback page protection restoration failed")
        if "notice_observer_restore_failed" in rows:
            raise ValueError("Native notice callback restoration failed")
        if "notice_observer_retired" in rows:
            self.close(observer)
            return "selection_publisher_returned" in rows or "selection_window_expired" in rows
        if not wake:
            return False
        now = time.monotonic()
        if now < self.next_poll:
            return False
        self.next_poll = now + .1
        if not self.hook:
            self.install_hook(observer)
        if self.hook and not observer.wait(0) and self.k.WaitForSingleObject(self.thread, 0) == 258:
            self.posts += bool(self.u.PostThreadMessageW(self.tid, 0, WAKE_TAG, 0))
        return False

    def close(self, observer):
        if self.hook:
            observer.checked(self.u.UnhookWindowsHookEx(self.hook))
            self.hook = None
            self.removed = True
        if self.module:
            observer.checked(self.k.FreeLibrary(self.module))
            self.module = None
        if self.thread:
            self.k.CloseHandle(self.thread)
            self.thread = None

    def report(self):
        return {
            "helperSha256": self.helper_sha256,
            "threadId": self.tid,
            "taggedWakesPosted": self.posts,
            "threadHookRemoved": self.removed,
            "events": self.events(),
        }
