# Native verification and preparation entry

Follow-up: a [new reviewed-record entry](native-on-demand-experiment-entry.md) adds native experiment checking and explicit already-elevated setup/restore delegation. Its read-only/refusal cases pass; elevated mutation has not run. The preparation-only build and evidence below remain the earlier checkpoint.

The one-time setup engineering kit now has an ordinary native Windows entry. It verifies its **760 compiled kit-file bindings before starting Python**, then dispatches only the fixed setup-only interpreter and preparer. Fifteen actual moved-kit scenarios and two inert build checks pass. No installer, administrator prompt, Serato launch or device operation ran. [Source/build/runtime evidence](evidence/native-on-demand-entry-20261106.json)

## What is available

The entry offers `--verify`, `--plan` and `--prepare`, each with explicit `--kit ABSOLUTE_DIRECTORY --app ABSOLUTE_SERATO_EXE` arguments. No arguments display usage. Mutable installation/restoration and application-start actions are not exposed. It refuses an elevated token; this entry is for ordinary-user verification and preparation.

`--verify` performs native checks only. `--plan` runs the verified copied preparer's read-only path. `--prepare` runs its existing local generation and returns the reviewed Setup/Restore/Plan vectors. This removes the need to select Python for preparation; it does not yet provide the simple setup window or an installation action.

The native binary is separate from the immutable kit, avoiding a self-hash cycle. It binds exactly the setup-only kit manifest `1d4f287974ddea51e74b5855270cf61268428e78eaff74069a8443349f2c2f38`. Its private build is:

```text
artifacts/build/native-on-demand-entry-20261106/build/Release/SL3_Setup_Engineering.exe
SHA256 1a417b069bca40a86f7c5b39c59dcd4f0eb0a8c4a89d5f6c21fff2b7a30ae9b0
```

This is an engineering CLI build, not a shipped executable or final installer. The PE import inspection finds no CLR or external MSVC runtime import. PowerShell inside the kit still has its own bundled runtime.

## Before helper execution

The builder pins the exact existing kit manifest, inventory and payloads, then emits a compiled file/hash/size table. The native entry rejects redirects, unexpected payloads, altered sizes/hashes, unsupported paths and an unreviewed Serato executable. It opens known payload files read-only with sharing that denies writes/deletion, pins their directory ancestors against renaming and retains those handles through helper completion. Mutable `analysis` is excluded from the immutable inventory; its top-level entry must remain a normal directory. Generated experiments retain their own source/asset/account/runtime checks.

Child invocation uses the existing Windows argument quoting, exact handle inheritance and bounded output forwarding implementation. The interpreter, script and arguments are fixed by this entry, with `-I -B`; it never executes a command selected from arbitrary kit JSON. Its entry point does not dispatch through the older session-launcher modes, even though it reuses their helper implementation. Existing native/audio source and binaries are unchanged.

This establishes checks before helper execution for this reviewed build. The externally selected native executable remains a trust input. The kit is ordinary-user engineering material, not a protected consumer installation or proof against every concurrent directory writer. Do not equate these checks with signing, installation or real device selection.

## Actual verification

Tests ran with an empty PATH and a copied kit whose location includes spaces and Unicode. Native verification remained idle; Plan created no state; native preparation produced a real source-bound local experiment whose read-only controller reported original archive, absent package and Serato stopped. A changed preparer containing an execution marker was refused natively and never wrote the marker. Changed standard library, PowerShell, ASIO DLL and manifest, an extra DLL, unsupported application, unsupported action and unsupported path were refused without changing prepared state. Final Plan passed. Live registrations and installed resources remain restored.

Prepare a new bound build using `scripts/prepare-on-demand-entry.py`, build its source-manifest hash with `scripts/build-on-demand-entry.ps1`, then run `scripts/test-on-demand-entry.py` against the exact build manifest and selected kit. The evidence records those source and generated-file hashes. The existing [normal-start candidate](on-demand-normal-start-test.md) is still source-current and uninstalled. The next product-level test remains one-time setup followed by the original Serato shortcut; normal selection, physical vinyl/output and reliable native lifetime remain unverified.
