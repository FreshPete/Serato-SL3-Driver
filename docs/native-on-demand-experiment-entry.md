# Native entry for a reviewed setup record

Follow-up: the [current result-channel entry](setup-result-diagnostics.md) adds a one-way, process-authenticated diagnostic stream for explicit setup/restore. Ordinary-token refusals and owned IPC tests pass; an actual elevated action remains unvalidated.

The install-once follow-up passed 30 native entry cases. Three cases supplied a new matching record hash while changing the PowerShell folder, the PowerShell manifest hash or the Python manifest hash. The entry refused each before running the helper. The relocated kit's valid record still passed. The setup window rebuilt against this entry and passed its 18 contract cases. The native fixture report SHA-256 is `561ee225a0f20869f54ac9635f095cdadb9c4e1c6e78e2066d430e5ad50d0f03`. The rebuilt window SHA-256 is `206c799e8cd1c3e5fc1125d85db408330112f137cfd1fce82dbdc00412086a66`. [Install-once trial](return-to-testing.md#next-attended-test)

The native setup entry can now check a generated experiment and delegate its existing setup/restore actions to the fixed controller. **Only the read-only path and ordinary-token refusals have run. Elevated installation and restoration are unvalidated through this entry.** Twenty-three actual cases and two inert build checks pass. No prompt, installed change, Serato launch or native USB operation ran. [Current source/build evidence](evidence/native-on-demand-experiment-entry-20261106.json)

## Explicit prepared actions

In addition to verification/planning/preparation, the entry accepts `--check-experiment`, `--apply-experiment` and `--restore-experiment`. Each uses the existing `--kit` and `--app` selections plus `--experiment PATH --expected-experiment-sha256 SHA256`. The check delegates read-only Plan. Apply and restore require an already elevated token and delegate only `setup` or `restore` to the kit's fixed `serato-on-demand-test.py` through its fixed interpreter. The entry never requests elevation automatically or starts Serato. Unknown actions remain refused.

`--resume --kit DIRECTORY --app SERATO_EXE` returns the existing experiment path and hash for a previously prepared kit. It requires exactly one local record and checks its archive recipe, source and runtime identities, paired rebound directory and package identity for the current account. This path reads the original executable identity and can recover the setup record while the compatibility archive is installed. It writes no files and does not request elevation. The installed state still comes from `--check-experiment`, and restoring still requires the explicit restore action.

The relocated entry passed 38 checks. A fresh process reopened the exact record and preserved the prepared files byte for byte. The new cases also refused missing or ambiguous state and a rehashed, altered wrapper. These checks ran with Serato's original archive in place. The setup window still uses its reviewed record for this PC. The fixture report SHA-256 is `80abee11b6fca73ceecc2900ba097df2f63fe75daca2f8700aacac937baf1052`.

The experiment manifest/hash is an explicit review input. Its directory and rebound native package must be generated UUID-named directories directly below the selected kit's `analysis`. The native entry binds the root, application, interpreter and PowerShell directory to that kit. It compares both runtime manifest hashes with the compiled kit identities before starting the helper. All five archive assets and every known native-package payload are pinned through child completion. The four native binaries must also match the compiled kit hashes. Unexpected native package files are refused. The downstream controller still performs its full record, runtime, account and path checks, production action lock and component transaction protocol.

These remain two guarded component transactions, not a combined atomic install. This entry neither changes that recovery model nor supplies the final consumer installer/protected staging and graphical interface. The externally selected native executable and selected reviewed record remain trust inputs. The older ordinary-user/preparation-only entry is preserved as a historical checkpoint.

## Current private build

```text
artifacts/build/native-on-demand-entry-experiment-reviewed-20261106/build/Release/SL3_Setup_Engineering.exe
SHA256 916ac84c0f1077c8287a5717b1be841cecbcc6e4a2e6c0e93ad7cb0ad9acc0d3
```

It remains bound to the unchanged setup-only kit manifest `1d4f287974ddea51e74b5855270cf61268428e78eaff74069a8443349f2c2f38`. The intermediate `native-on-demand-entry-experiment-20261106` build predates the reviewed path-normalization correction and is not the current candidate. No binary is published as a public installer.

## Actual checks and remaining boundary

The moved-kit test, with spaces/Unicode and empty PATH, performs real native preparation followed by the native generated-experiment check. That check returns original archive, absent native package and Serato stopped. Wrong experiment hash, foreign scope/root, changed archive wrapper and changed rebound worker are refused natively. Apply/restore are tested only as ordinary-token refusals, before helper execution, without a prompt. The earlier source/runtime tamper, extra DLL, unsupported application/action/path and unchanged-state checks also pass. The final native experiment check and Plan pass; installed resources and live registration remain restored.

The normal-start candidate is still source-current. The next attended installation should exercise the explicit reviewed native action, inspect its actual receipt/state, then launch Serato through the normal shortcut. That test is still needed to establish native installation and genuine primary-device/ASIO selection. One-time normal operation, real lifecycle/output, timecode vinyl and the simple setup window remain open.
