# Prepared normal Serato startup experiment

The next attended experiment is prepared: set up the [self-starting native package](asio-on-demand-deployment.md) and the genuine locally generated SL3 profile once, then open the original Serato application through its usual shortcut. There is **no startup shim, instrumentation manager, desktop automation, separately launched broker or automatic Serato launch** in this tool. The driver can start its owner only when an application initializes ASIO. Whether Serato selects it on ordinary startup remains the question this experiment must answer.

No production setup has run. The original executable/resources and live registration remain unchanged. The package still uses explicitly unmeasured 44.1 kHz / 128-frame timing and a maximum ten-minute owner lifetime. It is an engineering experiment, not the final public installer.

## Setup and restoration

`prepare-serato-on-demand-test.py` binds a reviewed version-2 native bundle, the current original Serato 5.0.0.1278 installation, public source recipes and verified Python/PowerShell runtime inventories. It reproduces the previously tested SL3 archive directly from the owner's installation, validates its schema and preserves all original encrypted resource members. It queries the original executable's existing signature; it does not patch the executable or introduce a signing certificate.

The prepared manifest pins every source and asset. Its inner archive wrapper reuses the existing guarded Windows file-replacement transaction, including the retained original backup. Native installation/removal uses the existing protected-file, exact-registration and journal primitives. The prepared resource archive is private application-derived material and is not published in the repository.

`serato-on-demand-test.py` defaults to **plan**, which reads the actual archive and native ownership state without changing either. Explicit **setup** and **restore** require an already elevated process; the tool never requests elevation itself. They refuse a running Serato instance and never kill or close applications.

Setup installs the native package first, then applies the SL3 resource profile. If the native package is already exactly installed following an interruption between steps, retry reuses it. If profile replacement fails, the observed native installation and archive state are preserved for a deliberate retry or restoration. A failure is not converted into an assumed successful rollback.

Restore first restores/cleans the original archive witnesses, then removes the exact native installation and owned registration. Unknown files, foreign registration values and unrecognized partial native states are preserved. Existing native installer recovery remains necessary for a failure inside native staging or removal; this coordinator does not guess missing receipt identities. Component failure reports and post-failure observations remain in its result.

These are **two guarded component transactions, not one atomic transaction**. Run one reviewed action at a time with Serato closed and no concurrent installer/update or privileged writer. The experiment does not establish abrupt-process-crash recovery, production protection on this package, native USB retirement or a clean Serato shutdown.

## Prepared host candidate

The current source-bound manifest is:

```text
analysis/sl3-on-demand-test-normal-start-reviewed-20261106/experiment.json
SHA256 f8e0033e57f82e5e54b0f62081033800a20ab2548f6f276c6d8d7a90a9299d14
```

Its native bundle is bound to `C:\Program Files\SL3 Rebuild\on-demand-diagnostic-v1`; no files have been installed there. The legacy reserved pointer remains unused. The native bundle manifest SHA-256 is `e7931b5da5f3a051676b595e7925c8c118a95291ef9d1978683e68177bb50094`.

The private Python runtime is `artifacts/build/embedded-python-on-demand-test-20261106`, inventory manifest SHA-256 `f11669fa63baa4c6d8fc167061f41cb369044e90624e70763d5ca7137b31c386`. The prior analysis directory contained five unlisted PE-analysis bytecode caches. Every declared file matched its reviewed hash and none was missing. The original directory was preserved; a new copy containing exactly the 125 reviewed files and manifest passed full verification. No extra-file exception, security-policy change or quarantine restoration was used. This tool imports no Frida runtime.

The portable PowerShell runtime remains `artifacts/build/portable-powershell-766-20261106`, manifest SHA-256 `4b4047e7a8153f0aab087356ad4e80f2b9a7855a21cebabe8430c27671d97881`.

The read-only invocation is:

```powershell
& artifacts/build/embedded-python-on-demand-test-20261106/python.exe -I -B scripts/serato-on-demand-test.py `
  --experiment analysis/sl3-on-demand-test-normal-start-reviewed-20261106/experiment.json `
  --expected-experiment-sha256 f8e0033e57f82e5e54b0f62081033800a20ab2548f6f276c6d8d7a90a9299d14
```

Do not use the earlier `sl3-on-demand-test-normal-start-20261106` manifest: source changes correctly made it stale. Do not restore old source or override its pins. Regenerate a fresh experiment after changing a bound source, asset, package, account or runtime.

## Verification and next live observation

All **15 isolated setup/restore scenarios** passed using actual workspace archive replacement, native file staging and private HKCU registration. They cover idle Plan, setup/restoration, repeats without reinstallation, failure between components and retry, typed native failure preservation, injected running-state refusal, and preservation/resolution of unknown archive bytes or foreign registration values. The archive bytes are synthetic in these tests, the registry roots are private fixtures, and packaged native code is not executed.

Another **12 real-host preparation checks** passed: the default and final read-only Plan, ordinary-token setup/restore refusal without a prompt, wrong manifest identity, altered candidate asset, excessive diagnostic lifetime, false shim/installed claims, foreign application/source paths and existing-output preservation. A separate check verified that the older source-bound manifest is refused. The [checkpoint evidence](evidence/on-demand-normal-start-preparation-20261106.json) binds the reports, current sources, prepared manifest, assets and runtimes.

The host Plan reports original archive, absent native installation and Serato stopped. Postchecks again found original Serato files, no occupied session paths or temporary registration, and no matching test/controller/worker or Serato process. Firmware and Windows security settings were unchanged.

The next attended test must actually set up the candidate, launch Serato normally and observe whether it selects and initializes this ASIO driver. Leave playback stopped initially. Do not click Download Driver as part of this comparison; record any notice instead. Close Serato manually before restoration. Successful preparation is not proof that this startup route works. Native restart/shutdown, actual output, longer reliability and timecode vinyl remain separate tests; Phase RCA and vinyl share the same audio path.
