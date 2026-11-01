# PLA system-logger mode: inspected static path

The installed PLA disk image contains a viable conditional path for the prepared image source's `0x02000000` system-logger mode. The inspected `TraceSession::get_Mode` reads the collector's raw `ExtendedModes` value and adds flags with OR/bit-set operations. It does not narrow that value to the older flags named in the public property description. This resolves the specific static concern that the bit would necessarily be discarded. Actual dynamic dispatch and effective logger settings remain unverified.

The [reproducible evidence](evidence/pla-image-mode-path-20261031.json) binds the copied Microsoft disk image, its matching public PDB, cached symbol enumeration and generator. The image is version `10.0.26100.8115`, SHA-256 `c36da0d945877ac66f1cf5761f93e4ca593d9ce01433a2941129449338ca3740`. The saved read-only disk observation reports a valid Microsoft Windows signature. That observation does not attest the PLA service's loaded image or the historical USB hub image.

| Inspected link | Exact local evidence |
| --- | --- |
| Property storage | Setter RVA `0x53cc0` stores the supplied 32-bit value at object `+0xb4`; getter `0xa7460` returns it. |
| Mode assembly | `TraceSession::get_Mode` at `0x8bbb0` uses collector slot `+0x150` to fill a raw mode local at stack `+0x74`. Boolean properties use a separate local at `+0x70`; the selected successful path adds bits and returns the raw mode. |
| Properties construction | Internal `TraceSession::Commit` at `0x87690` receives the properties pointer as its second argument and calls mode slot `+0x268` with output at properties `+0x40`. This offset uses the Windows x64 `EVENT_TRACE_PROPERTIES` ABI. |
| Start | `TraceSession::Start` calls properties-builder slot `+0x278`, then passes the same properties pointer as the third argument of `StartTraceW` at RVA `0x17c8b`. |

The exporter checks the exact five unwind ranges, complete boundary-aligned decoding, 31 selected instructions and three base-class vtable entries. The imported call is seven bytes long because of its prefix; the `FF 15` bytes start inside the instruction. A search requiring those bytes to be the instruction boundary would miss this real call. The existing direct-call navigation helper does not enumerate indirect IAT calls, so its earlier empty result is not absence evidence.

These are base-class links, conditional on the actual objects and virtual dispatch. They are not a complete proof of every derived implementation, alias or branch. Internal `TraceSession::Commit` builds properties and is distinct from the public validation-only collector-set `Commit(4096)` used in the [actual preflight](hub-image-source-validation.md). The original compile-only attempt checked an Enterprise compiler path which was unavailable. A later [Build Tools/SDK compile check](pla-source-properties.md) now passes eighteen ABI assertions; this supersedes the original report's missing-layout-check limit without changing its original static evidence or establishing dynamic dispatch.

Run `.venv/Scripts/python.exe scripts/export-pla-image-mode-path.py` from the repository root to reproduce the offline inspection. The exporter reads local image/PDB bytes and saved symbols. It does not execute PLA, start a logging session, query a live session, acquire the SL3 or change system settings.

The next evidence requirement remains an attended, source-only logging test with effective session properties, an actual kernel image rundown and independently confirmed bounded stopping. This finding supports pursuing that route; it does not authorize a USB redirect or resolve the failed successive open. The [prepared source](hub-image-source-preparation.md) and existing [image-rundown checker](kernel-image-rundown.md) remain separate from physical USB readiness admission.
