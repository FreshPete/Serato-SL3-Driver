# Candidate passes an owned-process runtime test

The reviewed local-only/QuickJS Frida candidate now imports and performs a complete attach → script/RPC → unload → detach → shutdown cycle against a Python process created solely for the test. Probe and fixture both exit normally, and the owned Windows job reports no active members without forced cleanup. This is ordinary-user runtime evidence for the replacement dependency, not a new Serato or SL3 audio result. [Source-bound evidence](evidence/local-frida-owned-probe-20261106.json)

## Separate SDK and explicit scope

[prepare-local-frida-probe-runtime.py](../scripts/prepare-local-frida-probe-runtime.py) first verifies the existing embedded Python manifest, the candidate source/configuration/image inspection and its embedded native assets. It stages only the interpreter's top-level files, generated Frida bindings, reviewed native extension and upstream component notices into a fresh private runtime. All three generated Python binding/stub files match the reviewed 17.25.2 wheel byte-for-byte. The stock native Frida wheel binary and unrelated packages are excluded.

The resulting runtime contains 47 inventoried files, with manifest SHA-256 `1cea6bb307991da6a36d03fa2bd59da4fbd6887b60b3e69a1a223e2836371175`. It has a candidate-test-only scope, isolated module search and no site initialization. It does not replace the existing session kit. The ordinary integration's additional inspection dependencies are intentionally not assembled into this small probe runtime yet.

The [probe runner](../scripts/run-local-frida-owned-probe.py) defaults to a read-only check. Explicit Run requires the fresh candidate SDK location, exact manifest and ordinary user token. It refuses the stock SDK before importing Frida. The child checks its interpreter/package paths and its actual Windows job limits before import. A successful source-bound result requires parent and child to report the same normalized runner source hash.

## Containment and measured lifecycle

The outer supervisor owns a non-inheritable job handle with kill-on-close, a four-process limit and no breakaway flags. A cooperative gate delays candidate import until assignment. The library's potentially blocking work runs in that child with a 35-second outer deadline. Cleanup uses retained process/job handles, never a PID-name kill. The fixture is a separate owned Python child whose creation time and retained process object are checked before/after attachment.

The initial plain-Python containment fixture caught extra `conhost.exe` members created by `CREATE_NO_WINDOW`. Their images were queried while they remained in the owned job; the failing diagnostic is preserved. Switching the Python launches to `DETACHED_PROCESS` removed those console hosts. The final fixture proved exactly four expected Python members, rejection of a fifth process with Windows error 1816, and an empty job after deliberate termination. Limits were not relaxed. Microsoft's [console creation documentation](https://learn.microsoft.com/en-us/windows/console/creation-of-a-console) describes detached console processes, and its [job-object documentation](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) covers inherited membership and breakaway.

The candidate test then observed Frida 17.25.2, local process backend readiness, successful attachment, and a QuickJS RPC reply containing the exact fixture PID, `x64` and `QJS`. Script unload, session detach, manager close and fixture exit all completed. The source-bound run exited zero, with two total job processes and zero active at cleanup. No helper process was needed in that observed run. Earlier exploratory runs are preserved separately.

Three payload-selection/refusal tests also pass. Post-probe inventory verification confirms all runtime files unchanged. Defender events 1116/1117 were queried over the recorded test window and none were observed; antivirus, real-time protection and behaviour monitoring remained enabled. This is a bounded observation, not a guarantee about future instrumentation behaviour. No exception, trust-store, quarantine-restoration or security-policy action was taken.

## What remains

The original stock-runtime security hold remains intact, and the old Frida-based Serato session path is still held. The new candidate has only the separately scoped owned-process proof described here. Original installed Serato resources and temporary-registration cleanup still pass a read-only check; no matching session/helper process remains.

Next, assemble a source-bound integration SDK with the required inspection dependencies and verify fresh session plans offline. A real Serato startup/close/reopen test still needs separate validation with the owner present. The existing playback shutdown discrepancy, sustained audio checks and packaging work remain unresolved. No device was opened, no USB or audio command was sent, and no DVS or firmware claim is added by this test.
