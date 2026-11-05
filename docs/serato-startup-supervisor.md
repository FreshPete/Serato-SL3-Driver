# Public startup process supervisor

`scripts/run-serato-startup-session.py` now implements the process-owning part of the temporary Serato session as public source. It consumes the [prepared startup-only shim](serato-startup-only-shim.md) and reviewed native deployment package. It does not install the driver, acquire USB directly, stage proprietary resources, issue installer permits or restore files. Those operations still belong to the external protected transaction and broker coordinator.

This is an experimental component, not an end-user installer. Its full Frida/Serato path has not run. The existing attended two-deck result used the earlier private supervisor and remains preserved separately.

## Read-only plan

The default operation, also selectable with `--plan`, checks:

- The exact pinned Serato executable and original or reviewed Phase resource archive.
- The caller-supplied preparation manifest hash, prepared script hash and exact reconstruction from the current template and planned ASIO path. An arbitrary script cannot be substituted by changing only its manifest hash.
- The complete reviewed deployment bundle, its caller-supplied manifest hash and its agreement with the prepared DLL path.
- Canonical installer-bundle SHA-256 input for the separately staged launcher resource.

Plan does not import Frida, start an application, create output, access USB or modify registration. It accepts the original resource state so it can be checked before elevation or staging. Input verification does not mean a live session is already staged or validated.

Required arguments are `--prepared`, `--expected-preparation-sha256`, `--app`, `--bundle`, `--expected-bundle-sha256` and `--expected-installer-bundle-sha256`. A live invocation additionally requires `--run` and a fresh `--output analysis/sl3-startup-session-NAME` directory. An optional `--frida-directory` selects the reviewed existing Python dependency directory for that process only; no dependency is installed by the supervisor.

## Live contract

Run refuses before launch unless the reviewed Phase archive and installer resource are already staged, the temporary ASIO files and 64-bit registry entries are absent, and the caller has an ordinary user token. This matches the installer-completion route: the application starts first, then the user clicks Download Driver and the approved local installer publishes the ASIO package. The protected transaction must already be supervising those resource changes and own rollback.

The process supervisor creates a private Windows job, spawns the application suspended through Frida, retains its process handle, assigns it to the job, loads the reviewed script, waits for readiness and resumes it. Children silently break away so that the installer/broker's separate ownership domains are not accidentally terminated with the application. The application hash is checked again immediately before creation.

The host waits up to 180 seconds for the real installer action and 60 seconds afterward for successful ASIO start. It then checks the newly staged DLL file against the reviewed deployment package, unloads the script and detaches the complete Frida session before permitting manual viewing. The file check does not attest loaded memory. Installer provenance/protection is owned by the external transaction.

The viewing window is at most nine minutes. Closing Serato manually ends it; creating `stop.txt` in the fresh output directory also requests an end. Startup events and the detach marker are published to bounded `events.jsonl` output, without desktop automation or audio callback instrumentation. A separate 840-second hard deadline contains a blocked library call by exiting the supervisor with code 70. That path does no logging and publishes no fabricated successful cleanup result; its owned job closes, while separate broker retirement and resource restoration still require external verification.

## Shutdown evidence

Cleanup operates only on the retained application process object. If still running, it requests window closure, waits eight seconds, then terminates that exact process only if needed. The result records whether closure was requested, whether forced termination occurred, the application exit code, creation/exit FILETIMEs and independent job accounting. Frida detach failure is retained as a diagnostic.

`supervisionCompleted` requires verified startup, full tracer detachment, no host error, process exit, empty job, exit code zero and no forced termination. It is not a broker success result, device-release proof, physical audio measurement or resource-restoration claim. In particular, a forced-close fallback cannot become success merely because the process exited.

If a retained process object could not be obtained after spawning, the result explicitly marks ownership unproven and does not claim an empty job or clean supervision. It does not terminate a potentially recycled PID. External recovery must prove that Serato is stopped before changing its resources.

The output contains `intent.json`, `events.jsonl` once instrumentation begins and `result.json` on completed reporting. The external protected supervisor must inspect failed or missing results and its own application/broker state before rollback. Running this component by itself is not a substitute for that transaction.

## Validation and remaining integration

Twelve supervisor tests cover valid preflight, manifest/script tampering, startup/cleanup faults, missing events and deadlines, explicit installer-action gating, DLL verification failure, shim error, event publication failure, hard-deadline exit and owned Windows process behavior. The Windows cases use actual test Python processes and real job/wait/termination APIs, with the Frida interface mocked. Both graceful exit and the eight-second forced fallback are distinguished, and a changed application hash refuses before process creation.

All four preparer tests and eight shim behavioral cases also pass. A fresh script was prepared against the actual pinned application; the supervisor's real Plan passed with original resources. An unstaged Run was refused before output creation or process launch. No Serato instance, real Frida attach or SL3 acquisition occurred for these checks. [Evidence](evidence/startup-supervisor-20261105.json)

The next engineering work is to make the descriptor/installer preparation and protected transaction consume this component without hardcoded private workspace paths, then live-validate the smaller shim and supervisor. The existing known-working package must remain available for comparison. Shutdown, physical audible output, independent turntables, sustained reliability and permanent installation remain open requirements.
