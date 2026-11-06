"""Shutdown diagnostics: synthetic selection/errors and real hidden-window APIs."""
import ctypes as c
from ctypes import wintypes as w
import os
from pathlib import Path
import runpy
import unittest

API = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/run-serato-startup-session.py'))


class Function:
    def __init__(self, call): self.call = call
    def __call__(self, *args): return self.call(*args)


class Selection:
    def __init__(self, failure=False, enum_failure=False):
        self.posts = []
        self.EnumWindows = Function(lambda visit, unused: False if enum_failure else all(visit(h, 0) for h in (1, 2, 3, 4)))
        def owner(hwnd, pointer):
            c.cast(pointer, c.POINTER(w.DWORD)).contents.value = 999 if hwnd == 1 else 123
            return 42
        self.GetWindowThreadProcessId = Function(owner)
        self.IsWindowVisible = Function(lambda hwnd: hwnd != 4)
        self.IsWindowEnabled = Function(lambda hwnd: hwnd != 2)
        def post(hwnd, *unused):
            self.posts.append(hwnd)
            if failure:
                c.set_last_error(5)
                return False
            return True
        self.PostMessageW = Function(post)


def backend(pid=123, wait=lambda unused: False):
    value = API['WindowsProcess'].__new__(API['WindowsProcess'])
    value.c, value.w, value.pid, value.wait = c, w, pid, wait
    return value


class WindowCloseTest(unittest.TestCase):
    def test_only_owned_visible_windows_receive_close_including_disabled_main(self):
        selection = Selection()
        report = backend().window_snapshot(True, selection)
        self.assertEqual(selection.posts, [2, 3])
        self.assertEqual(report['ownedTopLevelWindows'], 3)
        self.assertEqual(report['visibleWindows'], 2)
        self.assertEqual(report['enabledVisibleWindows'], 1)
        self.assertEqual(report['closeMessagesPosted'], 2)
        self.assertTrue(report['enumerationSucceeded'])

    def test_access_denied_is_preserved_without_claiming_delivery(self):
        report = backend().window_snapshot(True, Selection(failure=True))
        self.assertEqual(report['closeMessagesPosted'], 0)
        self.assertEqual(report['closePostFailures'], 2)
        self.assertEqual(report['closePostErrors'], [5, 5])

    def test_observation_does_not_post_again(self):
        selection = Selection()
        report = backend().window_snapshot(False, selection)
        self.assertEqual(selection.posts, [])
        self.assertEqual(report['closeMessagesPosted'], 0)
        self.assertFalse(report['postCloseRequested'])

    def test_exited_owner_never_targets_a_window(self):
        selection = Selection()
        report = backend(wait=lambda unused: True).window_snapshot(True, selection)
        self.assertEqual(selection.posts, [])
        self.assertEqual(report['ownedTopLevelWindows'], 0)

    def test_enumeration_and_callback_failures_remain_explicit(self):
        report = backend().window_snapshot(True, Selection(enum_failure=True))
        self.assertFalse(report['enumerationSucceeded'])
        def failed_wait(unused): raise ValueError('Owned wait failed')
        report = backend(wait=failed_wait).window_snapshot(True, Selection())
        self.assertFalse(report['enumerationSucceeded'])
        self.assertEqual(report['callbackError'], 'Owned wait failed')

    def test_real_hidden_window_metadata_and_posted_message(self):
        # No visible UI. Selection for the post test alone is synthetic; actual
        # HWND ownership, PostMessage and queue retrieval use Windows APIs.
        u = c.WinDLL('user32', use_last_error=True)
        k = c.WinDLL('kernel32', use_last_error=True)
        u.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, c.c_int, c.c_int,
                                     c.c_int, c.c_int, w.HWND, w.HMENU, w.HINSTANCE, c.c_void_p]
        u.CreateWindowExW.restype = w.HWND
        u.DestroyWindow.argtypes = [w.HWND]; u.DestroyWindow.restype = w.BOOL
        u.PeekMessageW.argtypes = [c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT]
        u.PeekMessageW.restype = w.BOOL
        k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; k.OpenProcess.restype = w.HANDLE
        k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]; k.WaitForSingleObject.restype = w.DWORD
        k.CloseHandle.argtypes = [w.HANDLE]; k.CloseHandle.restype = w.BOOL
        process = k.OpenProcess(0x100000, False, os.getpid())
        self.assertTrue(process)
        hwnd = None
        try:
            hwnd = u.CreateWindowExW(0, 'STATIC', 'SL3 hidden test fixture', 0, 0, 0, 1, 1, None, None, None, None)
            self.assertTrue(hwnd)
            owner = backend(os.getpid(), lambda unused: k.WaitForSingleObject(process, 0) == 0)
            native = owner.window_snapshot(False)
            self.assertTrue(native['enumerationSucceeded'])
            self.assertGreaterEqual(native['ownedTopLevelWindows'], 1)
            self.assertFalse(u.IsWindowVisible(hwnd))
            selected = Selection()
            selected.EnumWindows = Function(lambda visit, unused: visit(hwnd, 0))
            selected.GetWindowThreadProcessId = u.GetWindowThreadProcessId
            selected.IsWindowVisible = Function(lambda unused: True)
            selected.IsWindowEnabled = u.IsWindowEnabled
            selected.PostMessageW = u.PostMessageW
            report = owner.window_snapshot(True, selected)
            self.assertEqual(report['closeMessagesPosted'], 1)
            self.assertEqual(report['closePostFailures'], 0)
            message = w.MSG()
            self.assertTrue(u.PeekMessageW(c.byref(message), hwnd, 0x10, 0x10, 1))
            self.assertEqual(message.hWnd, hwnd)
            self.assertEqual(message.message, 0x10)
        finally:
            if hwnd: self.assertTrue(u.DestroyWindow(hwnd))
            k.CloseHandle(process)


if __name__ == '__main__':
    unittest.main()
