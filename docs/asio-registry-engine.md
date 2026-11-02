# Registry engine and read-only machine preflight

The x64 registration/removal engine is implemented and tested through real
Windows registry APIs inside fresh private HKCU test namespaces. It handles the
project's own COM/ASIO entries, typed ownership checks, creation conflicts and
partial failures. The command-line entry point offers only plan and read-only
inspection; it cannot register or unregister this host's live driver.

This supplies the registry part of the future protected installer. The complete
privileged install/uninstall workflow is still pending, and no install, host
activation, native audio or Serato/DVS success is implied.

## Public commands

```powershell
.venv/Scripts/python.exe scripts/asio-registry.py --plan
.venv/Scripts/python.exe scripts/asio-registry.py --inspect --bundle "C:\path\review-bundle" --expected-bundle-sha256 <reviewed-lowercase-manifest-sha256>
```

No arguments is also plan-only. Inspection first verifies the reviewed bundle,
then reads the proposed project entries under 64-bit HKLM. It separately checks
the current user's COM class overlay. Any overlay entry blocks the CLI's
`newRegistrationAllowed` result. Read errors are errors, not evidence of absence.
No machine mutation verb, elevation request, binary payload execution or device
operation is exposed by this CLI.

`newRegistrationAllowed` describes only the observed registry state and shared
container availability. It is not a reservation or an installation approval.
`installedFilesVerified` remains false: protected files, current ACLs and runtime
availability have not been validated by the registry inspector.

## Trusted-caller library

The mutating functions receive an explicitly opened root handle and a validated
deployment plan. They accept only the project's exact three expected nodes and
REG_SZ values: its CLSID parent, `InprocServer32`, and its ASIO name. The schema,
x64 view, DLL path and package markers must match the constrained bundle model.
Arbitrary keys supplied in the plan are rejected before mutation. The library
does not create shared `SOFTWARE\ASIO` or `SOFTWARE\Classes\CLSID` containers;
the caller must arrange those deliberately when needed.

`register_new` first requires every project entry to be absent. Each leaf is
created below an existing parent through `RegCreateKeyExW`, and its disposition
must be `REG_CREATED_NEW_KEY`. An existing/racing leaf is closed without setting
any value. Only newly created keys receive the expected strings. The final
complete tree must match the expected values, types and child lists.

If creation, a value write, flush, final validation or the caller's journal
fails, rollback considers only keys created by that invocation. It removes only
empty leaves whose actual data exactly matches the writes recorded as
successful. Unknown values or subkeys cause preservation, not blind cleanup.
The failure receipt lists created, rolled-back and preserved keys. The engine
never deletes a shared container or treats another invocation's new leaf as its
own rollback target.

`unregister_owned` requires the entire expected tree to match before any
deletion. Wrong package markers, changed paths/descriptions, different registry
types, extra values or unknown children cause refusal with no deletion. It then
removes only empty project leaves, checking each opened key again immediately
before removal. The order is `InprocServer32`, its CLSID parent, and the ASIO
leaf. A later failure reports the exact completed deletions and preserves the
remaining state; it does not call the operation an atomic uninstall or silently
re-create deleted keys.

The optional journal callback receives creation/write/deletion intent and
completion events. A future installer must durably retain its own journal and
serialize operations across installer processes. The engine is not a registry
transaction, concurrency reservation, privilege boundary or protection against
other privileged code. Matching package markers are consistency/ownership data,
not independent cryptographic attestation. A trusted wrapper must validate its
root, the current-user overlay and protected installation state before using
the mutating functions against HKLM.

Microsoft documents the create disposition in
[RegCreateKeyExW](https://learn.microsoft.com/en-us/windows/win32/api/winreg/nf-winreg-regcreatekeyexw)
and non-recursive leaf deletion in
[RegDeleteKeyExW](https://learn.microsoft.com/en-us/windows/win32/api/winreg/nf-winreg-regdeletekeyexw).

## Actual Windows tests

Run `.venv/Scripts/python.exe scripts/test-asio-registry.py`. The 26-case suite
uses a create-new UUID namespace below
`HKCU\Software\SL3RebuildRegistrationTests`. Its nested `SOFTWARE\Classes` and
`SOFTWARE\ASIO` test paths are not the live COM/ASIO registration roots. Test
snapshots and receipts are retained as files; the marked private registry
namespace is removed afterward and absence is checked.

The suite covers real REG_SZ creation and owned removal, repeat/foreign
registration refusal, a missing shared container, a different valid package
identity, ownership/value/type/subkey conflicts and failure after each of the
seven committed value writes. It also introduces a leaf between preflight and
creation, preserves a modified partial rollback target, and checks conflicts
before the first and last deletions. Two simultaneous registrations pass the
same preflight: exactly one native create-new winner succeeds, with no losing
invocation overwriting or rolling back the winner.

The CLI's default/read-only modes are exercised too. Snapshots of the real
planned HKLM entries and current-user overlay match before and after the suite.
The suite intentionally writes temporary registry data and verifies its cleanup;
it does not claim that no registry API or write occurred. It does not prove
machine ACL protection, crash recovery, cross-process uninstall serialization,
installed host enumeration or actual COM activation via machine registration.
Earlier registration-free COM tests retain their separate scope.

See [the verification record](evidence/registry-engine-20261102.json). The prior
26-case package preparation tests and 59-test Release/Debug native checkpoints
remain unchanged; those native tests were not rerun for this Python-only change.
The later [file-staging checkpoint](asio-file-staging.md) supplies tested workspace
copy/ACL primitives but records a production ancestor-policy refusal.
Production staging, the privileged wrapper, runtime checks, owned file
cleanup, measured timing, native/physical audio and current Serato/DVS admission
remain unfinished. No firmware, trust or security policy changed.
