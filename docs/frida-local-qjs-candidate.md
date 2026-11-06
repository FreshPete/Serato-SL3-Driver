# Local Windows candidate builds successfully

A project-local Frida 17.25.2 build produces an x64 Python extension with the local Windows backend and QuickJS enabled. Nonlocal device backends and V8 are disabled. Static inspection and an on-demand Defender file scan completed at this build stage. A subsequent [owned-process runtime test](local-frida-owned-probe.md) now passes in a separate private SDK; no new Serato test or session-kit replacement has occurred. The existing session-path hold remains in place. [Build evidence](evidence/frida-local-qjs-build-20261106.json)

## What resolved the link failures

The startup supervisor calls `create_script` without requesting an engine. In the pinned upstream agent, `get_script_backend(DEFAULT)` tries QuickJS first; the Gum backend follows the same preference. Retaining QuickJS and excluding unused V8 removes the prebuilt V8 library's dependency on newer Microsoft STL symbols without changing the shim's requested script runtime. This does not establish that every script or the whole integration works with the new binary.

The [combined Gum portability patch](../patches/frida-gum-17.25.2-windows-portability.patch) retains the three reviewed includes and adds a Clang-only implementation of the existing x64 GS-relative TLS store. Other compilers retain the Microsoft intrinsic. The replacement uses Clang's documented [address space 256 for GS-relative memory](https://clang.llvm.org/docs/LanguageExtensions.html#memory-references-to-specified-segments), preserving the existing offset and slot width. Microsoft's [intrinsic documentation](https://learn.microsoft.com/en-us/cpp/intrinsics/writegsbyte-writegsdword-writegsqword-writegsword?view=msvc-170) describes the reference operation. The earlier [agent declaration patch](../patches/frida-core-17.25.2-windows-agent-declarations.patch) is unchanged.

An owned-process [TLS fixture](../tests/native/frida_gs_store_test.c) compares the candidate store with an independently MSVC-compiled [intrinsic reference](../tests/native/frida_gs_store_reference.c) and Windows `TlsSetValue`/`TlsGetValue`. Four concurrent threads and 62 allocated keys completed 190,464 comparisons with no failures, including zero/high-bit values, main-thread isolation and error-value preservation. Both sources compile with warnings treated as errors. The actual patched Gum object also emits a direct GS-relative store at `0x1480 + key * 8` and has no unresolved `__writegsqword`. This covers the modified first-64-slots branch, not the unchanged expansion-slot path or whole Frida runtime.

The initial QuickJS build then exposed a CRLF checkout conversion inside a multiline Vala string. Restoring `src/linux-kernel-image.vala` byte-for-byte from the pinned Git blob fixed generated C without changing the upstream implementation. The inspector now requires that exact LF blob when accepting the reviewed Windows changes.

## Static result and limits

The completed extension is 34,133,504 bytes, SHA-256 `8ed5bdde028c484463fc536fa1678b4b5bbfd99d99c387eb40436d18a8d82da3`. The nonexecuting inspector verifies the source pins, exact reviewed changes, QuickJS-only/local-only configuration, AMD64 image, `PyInit__frida` export and `python3.dll` stable-ABI dependency. It records 2,389 exports and no Idun-named or Fruity-host-session exports. No Idun-named build files or targets were found. These checks do not attest every byte of the embedded assets.

Defender events 1000/1001 record a matching on-demand scan ID and the candidate file path. No detection events appeared in the observed scan window, and the file retained the same hash afterward. Antivirus, real-time protection and behaviour monitoring remained enabled. This file-scan result does not prove that later instrumentation behaviour will be accepted.

The current inspector's explicit option is `--allow-reviewed-windows-portability` (the earlier includes option remains an alias). It accepts only the encoded source changes; twenty-two configuration and exact-patch tests pass. Earlier failed attempts and their separate patch files remain preserved.

An [image-level native asset review](frida-embedded-asset-review.md) matches all twelve agent/helper descriptors and the four non-empty payloads to the final image. The separate SDK's [bounded owned-process test](local-frida-owned-probe.md) also passes. No new binary has replaced the working session kit, no Serato/device test ran, and no further audio, Serato shutdown or DVS validation is claimed.
