# Automatic fresh-session preparation

The native launcher can now create a fresh session from a hash-reviewed complete plan without recompiling the launcher or repacking the installer resource. Two successive preparations produced independent capsule, plan and supervisor-output bindings; both passed the actual complete wrapper Plan. No Serato, broker, administrator prompt or USB operation ran. [Recorded evidence](evidence/fresh-session-preparation-20261106.json)

## Contract

`scripts/prepare-fresh-serato-session.py` defaults to read-only verification. It verifies the reviewed complete plan and capsule using the existing helpers. Explicit preparation creates a UUID-named `analysis/sl3-session-capsule-fresh-*` directory atomically, writes a preparation-start record, creates the new capsule and complete plan, reverifies them and writes a completion receipt last. Existing directories are never reused. A failure after directory creation leaves its partial records for diagnosis; it does not remove or launch them.

The session changes only its state-directory binding and the corresponding supervisor output path. The same application, native deployment package, interpreter, prepared startup shim, Phase descriptor archive, launcher and installer resource are retained and reverified. Recording-enabled templates are refused before directory creation. Ordinary interactive preparation does not silently enable output/music capture.

The native `--prepare-session` mode accepts the same complete-plan/hash/PowerShell-directory arguments as `--plan-session`. Before invoking the preparer it pins thirty release sources, both runtime inventories, the application, and its own executable against the reviewed plan's launcher hash. This prevents a template bound to a different launcher release from being used to prepare a session through that entry. The returned preparation record includes separate argument vectors for read-only Plan and explicit Start; these are passed as arguments, never shell command text.

The native `--start-fresh-session` mode uses the same preparation route, then invokes the prepared session's `--start-session` entry. The existing staging, approvals, startup-only instrumentation, detach, retirement and rollback remain in the session wrapper. **This start mode is implemented but has not been run live.** Its preparation receipt describes preparation only and is not evidence that the later session started, exited cleanly or reached hardware.

The public Python preparer also exposes explicit `--prepare` and `--start` switches. Starting requires both explicit preparation and PowerShell selection. Developers should use the native entry for its pre-execution release/runtime pinning. Its read-only default never creates a session or starts a child process.

## Verification

Eight actual preparation checks passed: default read-only verification; two fresh preparations; complete wrapper Plans for both; wrong reviewed-plan hash; a mismatched launcher release; and a recording-enabled template. Negative cases created no new fresh-session directory. The two positive sessions each contained only their four preparation/configuration files before the Plan checks, with no run lock, install receipt or broker session. Their distinct hashes are preserved in the evidence; local directories remain ignored and available for review.

The updated executable also passed the thirteen full-session entry checks, eleven capsule entry checks and eight Windows argument round trips. These cover the earlier relocated runtime and changed-code refusals as well as the retained installer entry. The native audio DLL, USB worker and diagnostic deployment package were not rebuilt or changed.

## Remaining deployment work

This removes per-launch session assembly, not all release preparation. A reviewed complete plan remains the development template and refers to this checkout and private Serato-derived resources. Whole-kit relocation, generating the resource adaptation from the user's own installed Serato, simple launch/recovery UI, removing the repeated Download Driver click and second-PC installation remain unfinished. The new native installer/context path, actual fresh startup and post-playback manual-close/rollback still require an attended test. Existing physical Phase results do not validate these new entry points.
