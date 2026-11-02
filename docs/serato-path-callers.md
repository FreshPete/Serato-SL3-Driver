# Current module-path state: checked callers and GPU preference query

Seven identified direct calls to the current module-path state accessor now have
checked call-site evidence. One enclosing function queries Windows per-application
GPU preference data using the module path as its value-name source. A separately
identified reference is a CRT-registered cleanup callback for the four-string
state. These findings supply no demonstrated external device-profile registration
route; they do not restore current SL3 admission.

The original and installed Windows 5.0.0.1278 executable match SHA-256
`66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`.
All addresses are preferred image VAs. Vendor code, its registry calls and the
application were not executed. No resource, application, account, registration,
driver, security policy or device identity was modified.

## Checked call boundaries

| Accessor call | Enclosing function | Checked use |
| --- | --- | --- |
| `1404a84fa` | `1404a84c0` | Saves the state pointer and checks its first string length before further interface/string operations. Full downstream semantics are not assigned. |
| `1404a9ca0` | `1404a9c30` | After a successful `GetModuleFileNameW` query, passes the state as input to `141cb3290`, writing the result to a separate output object. |
| `14153f868` | `14153f830` | Tests first-string length in the GPU-query caller. |
| `14153f9f6` | `14153f830` | Selects the module-path string storage, passes it through `1420fa120`, and supplies the resulting value-name object to registry-query helper `141540320`. |
| `14153fc91` | `14153f830` | Passes the state to string/logging helper `1404a19c0` on a conditional path. |
| `141cb2362` | `141cb2330` | Passes the module-path state to the existing directory-part helper and copies component `+0x40` into a separate string before joining/validation. |
| `141cb4c72` | `141cb4c40` | The previously verified resource-root builder uses component `+0x20`; its default is `.`. |

These are register/argument observations, not a general constness proof for every
callee or an exhaustive inventory of possible mutations. The
[earlier default-root result](serato-resource-loading.md#module-derived-root-default)
still applies within its stated scope.

## GPU query, not a discovered profile setting

At `14153f964`, RCX is the predefined `HKEY_CURRENT_USER` value. The adjacent RDX
literal is `Software\Microsoft\DirectX\UserGpuPreferences`; the call at
`14153f96b` resolves through the actual import table to `RegCreateKeyExW`, with
requested key access `0x2001f`. This API could create its branch if the application
executes that path. The analysis invokes none of it and reads no user's value.

Helper `141540320` has two actual `RegGetValueW` import calls at `141540384` and
`14154040c`. Both set R9D to 2 (`RRF_RT_REG_SZ`); the first uses null data with a
size output, then a later call supplies storage. Microsoft's
[RegGetValueW contract](https://learn.microsoft.com/en-us/windows/win32/api/winreg/nf-winreg-reggetvaluew)
defines those query/type semantics. The module path is the value-name source at
the checked caller boundary. A registry-create/open operation must not be
mislabelled as writing a profile value, and the query is not evidence that a
`userio` resource root can be set there. No GPU preference or resource override
is recommended or installed by this finding.

## Cleanup reference

The accessor initializer passes `1425e2340` at `14083e091` through wrapper
`142117e20`. The underlying helper dispatches through checked six-byte thunks to
`_crt_atexit` or `_register_onexit_function`. The callback addresses the four
strings at `143fe88c0`, `143fe88a0`, `143fe8880`, `143fe8860`, invoking the same
string cleanup helper three times and tail-jumping to it for the fourth.
This binds the lifecycle callback; it does not supply a runtime configuration
setter. Machine instructions are authoritative here: focused pseudocode expands
the tail helper beyond the callback's small original body.

## Reproduction and limits

Run `.venv/Scripts/python.exe scripts/export-serato-path-callers.py`. The
[deterministic report](evidence/serato500-path-callers.json) checks 50 exact
instructions, five OS-import sites, two exit thunks, literal/argument bindings,
the original and installed hashes, and seven fresh focused function results.
Actual execution and byte-identical regeneration pass. Navigation is recomputed
from the original PE each time.

The focused Ghidra imports were read-only, with whole-program analysis and library
loading disabled. Both processes exited zero, loaded no additional files and
discarded their temporary imports/projects. Complete pseudocode and logs remain
in ignored local analysis; only bounded machine facts and report hashes are
published. REA 6.8.0 remains the local analysis toolkit; this work uses the
existing focused Ghidra fallback described in [the workflow](analysis-workflow.md).

Direct-call candidates cover validated `E8 rel32` sites inside recovered PE
unwind ranges. Leaf callers without unwind entries, indirect callers, all possible
state writes and later provider mutations are **not exhausted**. RIP-reference
navigation also uses a limited instruction pattern. Focused decompilation
completion is not full ABI recovery or runtime confirmation. No universal
absence-of-extension claim follows from these seven sites.

The [first-reader/archive dispatch](serato-resource-loading.md),
[remaining reader inventory](serato-provider-tail.md), genuine SL3 descriptor,
current component/handshake interface, audio-driver selection and legitimate
product/account requirements remain independent boundaries. The current genuine
SL3 stub still has the previously checked discontinued route. A generic ASIO
registration, Phase connection or guessed path/registry edit does not demonstrate
the requested current two-deck DVS result. No such edit or identity substitution
was selected.

Native source/build pins remain unchanged; their prior tests were not rerun or
promoted to physical evidence. Current native/analogue audio, measured timing,
protected deployment and Serato/DVS validation remain unfinished. macOS remains
deferred and the full rebuild goal remains active.
