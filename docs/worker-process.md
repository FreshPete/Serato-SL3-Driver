# Windows worker-process supervision

An original process supervisor now provides the separate-process lifetime boundary needed by a future audio session. It launches a pinned executable into its own Windows job, observes that exact process handle, and can terminate its owned descendants without terminating the audio host. **It is not yet connected to the ASIO DLL or continuous audio buffers.** Subsequent [message-channel](worker-mailbox.md) and [typed finite-worker](typed-worker.md) checkpoints add real IPC and diagnostic commands; physical worker capture and continuous data flow remain unverified.

`src/windows/worker_process.cpp` builds as `sl3_worker_process.lib`. The executable used to verify it is a test fixture with explicit exit/hang/descendant modes; it contains no USB, ASIO, installer or firmware path. The component changes no device registration, trust or security setting.

## Launch and ownership

The caller supplies an absolute executable path, its expected SHA256 from a tested build, and an argument list. The component opens the file without write/delete sharing, hashes it, and retains that file handle through the child lifetime. Hashes establish consistency with the caller's expected bytes, not a signature, security boundary or code-integrity admission result. A matching hash also does not imply a valid executable; malformed images fail process creation.

Arguments use Windows CRT quoting, including empty strings, quotes, trailing backslashes and Unicode. The application path is supplied explicitly to `CreateProcessW`; no shell is involved. The child starts suspended and hidden, with handle inheritance disabled. It is assigned to a new unnamed job before being resumed. The job has `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and no breakaway flags; descendants remain contained. [Microsoft process-creation guidance](https://learn.microsoft.com/en-us/windows/win32/procthread/creating-processes), [job lifetime contract](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).

The job handle is never inherited. Owner destruction closes its sole handle and requests teardown of remaining child work. Windows also closes it after abrupt owner-process termination, without relying on C++ destructors. Destruction requests cleanup; it does not report that cleanup has completed.

If assignment fails after child creation, the supervisor retains the exact owned suspended-process handle and requests targeted termination. A resume failure likewise retains its owned job/process for observation. An exception therefore does not always mean no child exists; inspect `observe().started`. These assignment/resume failure branches are implemented but were not fault-injected in the current tests.

An instance launches at most once. A timeout does not discard its handle or start a replacement. The caller must continue observing/stopping the same instance and verify retirement before creating a new session.

## Exit, timeout and cleanup are separate

`ProcessState` reports process exit, a known exit code, job assignment, the job's associated-object count and job emptiness separately. A process's signalled handle establishes exit, including legitimate exit code 259; comparing the code with `STILL_ACTIVE` would be wrong.

Windows names its accounting field `ActiveProcesses`, but documents that decrements can depend on terminated process references being released. The wrapper calls it `associated_processes` and never treats it as an exact number of executing processes. A root process may have exited while the count remains nonzero. The tests therefore check containment and conservative cleanup rather than requiring an exact count of one after root exit. [Accounting contract](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_accounting_information).

`terminate_and_wait` requests termination only of this owner's job, or its own unassigned suspended child. It waits up to the supplied deadline and returns the actual state. The default is two seconds; explicit waits above five seconds are rejected. A zero-wait stop can report incomplete teardown, and a subsequent call continues observing the same handle. Completion requires both process exit and an empty job; a termination request alone never establishes completion.

The component is single-owner control-thread code. Hashing, launch, observation and termination must stay off audio callbacks. Windows' synchronous creation/control calls themselves have no application-provided wall-clock guarantee; the bounded wait interface is not a real-time scheduling promise.

A malformed-image test initially exposed Windows launch error UI blocking the call. Launch now temporarily suppresses those dialogs using a thread-local error mode and restores the caller's previous mode afterward. Successful and rejected launch paths both verify restoration. No global error/security policy is changed.

## Evidence actually obtained

All **12 native tests pass in Release and Debug**; the SDK-free build passes ten with a deliberately nonexistent SDK directory. Real-process tests cover expected/wrong identities, rejected relative/NUL/oversize arguments, malformed-image rejection, exact argument round trips, Unicode/space executable paths, write/delete pinning, disabled parent-handle inheritance, normal exit, exit 259, wait timeout, zero-wait termination, descendants, an unrelated sentry job surviving targeted termination, scope destruction and abrupt nested-owner death. No fixture process remains alive. [Build/source evidence](evidence/worker-process-build.json).

These are real Windows process/job tests, not physical USB tests. Job emptiness does not establish USB/device recovery, shared-buffer ownership or callback retirement. The read-only dependency preflight still reports UsbDk absent and no helper load/audio submission.

## Next integration layer

The [bounded message channel](worker-mailbox.md) now supplies framing and a fresh identity per session. Typed audio commands, the continuous data path and callback/buffer leases still need implementation before connecting the existing buffer component and real USB worker. Startup must distinguish process creation from a validated device/session handshake. Shutdown must invalidate callbacks and retire host buffer leases independently of child-process termination. The [ASIO DLL](asio-com-server.md) continues to fail initialization until that path exists. Clock/latency, physical audio and [current Serato routing](serato-audio-routing.md) remain open requirements.
