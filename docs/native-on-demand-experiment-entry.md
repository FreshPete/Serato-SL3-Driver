# Native entry for a reviewed setup record

The native setup entry can now check a generated experiment and delegate its existing setup/restore actions to the fixed controller. **Only the read-only path and ordinary-token refusals have run. Elevated installation and restoration are unvalidated through this entry.** Twenty-three actual cases and two inert build checks pass. No prompt, installed change, Serato launch or native USB operation ran. [Current source/build evidence](evidence/native-on-demand-experiment-entry-20261106.json)

## Explicit prepared actions

In addition to verification/planning/preparation, the entry accepts `--check-experiment`, `--apply-experiment` and `--restore-experiment`. Each uses the existing `--kit` and `--app` selections plus `--experiment PATH --expected-experiment-sha256 SHA256`. The check delegates read-only Plan. Apply and restore require an already elevated token and delegate only `setup` or `restore` to the kit's fixed `serato-on-demand-test.py` through its fixed interpreter. The entry never requests elevation automatically or starts Serato. Unknown actions remain refused.

The experiment manifest/hash is an explicit review input, not a discovery scan or an automatically trusted file. Its directory and rebound native package must be fresh generated UUID-named directories directly below the selected kit's `analysis`. The root, application and interpreter must match that kit. All five archive assets and every known native-package payload are pinned through child completion. The four native binaries must also match the compiled kit hashes; metadata rebinding cannot select a different worker or driver. Unexpected native package files are refused. The downstream controller still performs its full record/runtime/account/path checks, production action lock and component transaction protocol.

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
