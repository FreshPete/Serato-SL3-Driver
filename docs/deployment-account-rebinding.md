# Bind native package metadata to the current Windows account

Kit preparation now derives its installation and session-pointer destinations from the current token's Windows known folders. It creates a new native package under mutable session state, then prepares the shim and complete session against that package. The immutable kit and all four native binaries remain unchanged. The moved-kit native and direct preparation routes both passed their full session Plans with the rebound package. [Rebinding and regression evidence](evidence/deployment-account-rebinding-20261106.json)

This implements account-specific metadata preparation; it does not prove another Windows account or PC works. Tests used the current host and a synthetic foreign-pointer origin. No package installation, Serato process, administrator prompt, registry write, USB operation or firmware operation ran.

## Portable inspection and production admission

The deployment reader now separates byte capture, portable metadata inspection and production verification. `capture_bundle` verifies the externally selected manifest hash and exact captured file inventory. `inspect_portable_payloads` checks native payload hashes, PE roles/metadata, seed identity, locator consistency, registry plan and the existing ACL/no-service/no-automatic-start/no-rate-profile policy. It treats old destination names as local-path text and never follows them. Its result explicitly says production destinations are not admitted.

The existing `verify` and `verify_payloads` entry points still always apply `destinations` to the current account. The production file stager continues calling `verify_payloads` with no policy override. There is no new switch that disables production containment. A package with a foreign pointer can therefore be inspected for rebinding but still fails direct production verification.

`scripts/rebind-asio-deployment.py` captures and inspects the hash-reviewed origin, selects and validates new destinations, constructs replacement metadata in memory, and runs the mandatory production verifier before writing anything. Default mode is read-only. Explicit preparation requires a fresh direct `analysis/sl3-deployment-rebound-*` directory; existing results are preserved and the new manifest is published last.

The default protected destination is the current native Program Files known folder followed by `SL3 Rebuild/phase-diagnostic-v1`. The pointer uses the current Local AppData known folder followed by `SL3Rebuild/phase-session.txt`. No username or drive is inferred from the kit's original builder. Standard production containment remains an additional check; no destination is created by rebinding.

Only `provenance.json`, `deployment-plan.json`, `sl3-asio.conf` and their manifest identities change. The source builder/build-manifest hashes, native test count/log hash, PE metadata, binary/license payload hashes, timing mode and installation policy are retained. The seed records the original bundle, immediate parent bundle and rebinding-tool hashes. Every binary is compared byte-for-byte before publication. This is metadata lineage, not a new native build or physical test result.

## Kit integration

The immutable `native-package` is now an origin package. Plan validates a proposed current-account binding without writing state. Prepare writes a separate rebound package, points the startup shim at its new planned ASIO DLL location, and binds the capsule/complete plan to its new manifest hash. Neither route installs or starts the package. The kit's native launcher now pins 39 source/license/evidence files, including the rebinder, before helper dispatch.

The compact kit manifest labels its scope `destinations-bound-at-preparation`. It still pins the original immutable package. A copied kit can therefore prepare metadata without requiring the original account's pointer to be inside the current account's profile. The current regression run demonstrates this preparation pipeline and containment distinction; a real different-account/PC installation remains required.

## Checks and remaining work

Ten rebinding checks passed using the actual diagnostic package and a synthetic foreign-pointer variant: original production verification; portable inspection without admission; production rejection of the foreign pointer; read-only rebinding; saved rebinding with identical native binaries and preserved test provenance; existing-output preservation; unsafe destination refusal; changed native payload refusal; unsafe origin ACL refusal; and extra origin-file refusal.

The existing deployment workflow passed all 26 cases against the reviewed 71-test Windows return-validation build. Five pointer-redirection regressions passed. Thirteen native kit entry cases and ten direct moved-kit cases passed, with positive assertions that the package was rebound and every native binary hash stayed the same. Eleven capsule entry cases and eight Windows argument round trips passed: 83 targeted checks total.

The default old native-build checkpoint was correctly refused for a stale CMake source pin; the regression was rerun with the current reviewed return-validation manifest rather than changing a pin. A regression subprocess also created five Python cache files in the private runtime. The strict runtime verifier refused that inventory. Those generated files were moved into a private quarantine, the runner was corrected to use `-I -B`, and the unchanged runtime manifest passed again before and after the successful regression runs. No reviewed runtime file or trust policy was replaced.

The native audio DLL, controller, worker and helper are the previously recorded binaries. New destination paths and the new kit/installer context have not been exercised live. Normal startup, post-playback close/reopen, physical output, measured timing, filter prerequisites, simple recovery UI and another-account/PC testing remain outstanding. Previous hardware evidence must not be treated as validation of this new metadata binding. Source-bound capsules prepared before the deployment-reader change are stale against the updated checkout; fresh candidates were prepared without consuming the earlier results.
