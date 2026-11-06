# Startup integration candidate passes offline kit checks

This records the initial integration-kit checkpoint. The [manager-retirement update](instrumentation-manager-retirement.md) contains the subsequent production supervisor change and refreshed private kit/plan identities for the next attended test.

A fresh private kit now carries the reviewed local-only Frida build, the startup inspection dependencies and a newly bound native launcher/installer resource. Both default and optional-observer session plans pass the complete native/PowerShell verification path. A moved copy also prepares and checks a fresh session using its own runtimes with an empty PATH. Serato and the SL3 were not started. [Evidence](evidence/local-frida-integration-kit-20261106.json)

## Runtime and launcher binding

The [runtime preparer](../scripts/prepare-local-frida-probe-runtime.py) now has an explicit `--integration-dependencies` profile. It copies Capstone and pefile through their reviewed wheel records, preserving recorded hashes and notices. It refuses a Frida payload hidden in those dependency records, collisions and missing records. The generated Frida bindings and rebuilt extension remain the only Frida package. Six selection/refusal tests pass.

The integration runtime has 125 inventoried files and manifest SHA-256 `f11669fa63baa4c6d8fc167061f41cb369044e90624e70763d5ca7137b31c386`. Capstone 5.0.7 and pefile 2024.8.26 import from this private runtime. Its separately bounded owned-process Frida test also passes with normal cleanup and an empty job. This extends the [earlier small probe SDK](local-frida-owned-probe.md); that 47-file SDK remains unchanged.

The first Python-verified plans still referenced the old native release. Its complete-plan entry refused the integration runtime, as expected: the native launcher independently pins its runtime file inventory. Those initial plans and the refusal log remain preserved. A Python-only plan pass was not sufficient to admit that combination.

A fresh native release now pins 49 source/license/evidence files, 126 Python runtime files including its manifest, and 659 PowerShell files. Its Release build completed with warnings treated as errors. The native launcher SHA-256 is `3a5675b935f38f1a9635603728a3e23aa418434aa6c98891ed53918b913d5d57`; the matching installer resource is `fd1aa3d2ac13bf192d753b90434c30fc266cd5d935e7a931c41ead93ab1feca8`. The Phase archive remains the existing `d135e6f1…` bytes. Native audio binaries are unchanged.

The final complete-plan identities are:

| Private plan | SHA-256 | Optional receiver diagnostic |
| --- | --- | --- |
| `local-frida-default-20261106` | `8458a39a701ccf585873b848b11c30b77b2aba4d38ff54720f3d48b415d4f322` | Off |
| `local-frida-observed-20261106` | `703c3037b4a8e2983b3813bed4b68ba46bccbc3850876d4c4b1a8f55401a299c` | On |

Both use the new native release/resource and pin 37 plan sources. Both native complete Plans and read-only recovery checks exit zero. Neither check requests elevation or starts an application/broker/device.

## Private kit and verification

The assembled `artifacts/build/portable-serato-kit-local-frida-20261106` kit selects 849 payload files (329,290,334 bytes), plus its two inventory/manifest files. Manifest SHA-256 is `f050474f810f7fa6e447d220e846459e21b23b0902684afb9537e202fefb37b2`. It excludes Serato executables, derived Serato archives and kernel drivers. It remains a private development candidate; binaries were not published to the repository.

All checks passed:

- Six runtime-selection/refusal cases.
- Eight native Windows argument round trips.
- Eleven portable-launcher Plan/refusal cases, including two capsule bindings with one executable.
- Three native output/drain cases.
- Eight fresh-session preparation/verification cases, retaining the optional observer selection.
- Ten copied-kit cases, including spaces/Unicode, empty PATH, source/runtime tampering refusal and fresh destination rebinding. Normal copied-kit preparation keeps the optional observer off.

The relocation check ran on this Windows account and PC. A different account, second PC, actual installation and live audio remain untested for this candidate kit. The post-check still reports original installed Serato resources, no temporary driver registration or occupied staging paths, and no live session/helper processes. No Defender detection events appeared in the observed window; protections remained enabled and the original stock-runtime hold is retained.

## Next attended test

Use a fresh session prepared from the new kit/default plan for a stopped-playback startup → manual close → reopen check. The existing manual driver-action/Windows approval flow remains part of that test. Once startup and cleanup pass with this SDK, repeat Phase control and sustained playback checks. The earlier Serato shutdown discrepancy is not resolved by these offline checks or by successful shutdown of the owned Python fixture.
