# Phase archive generation from the installed Serato files

The Phase descriptor archive can now be reproduced directly from an owner's original Serato DJ Pro 5.0.0.1278 executable and its adjacent `userio_resources.bin`. The generated archive matches the tested Phase archive byte-for-byte: SHA-256 `d135e6f1c03601cc44b3e5f623eed36af81bbff585332a3fdc8d5d533b2cb66a`. It preserves all 229 original resource members and adds only the existing SL3 descriptor. [Preparation, isolated tests and wrapper Plan evidence](evidence/installed-phase-archive-preparation-20261106.json)

## What changed

The older `prepare-serato-sl3-phase-archive.py` starts with a private reviewed 48 kHz installer candidate. Rebuilding that intermediate through the older investigation workflow also requires historical executables and native-build provenance. Those are useful investigation records but unsuitable prerequisites for an end-user release kit.

`scripts/prepare-serato-installed-phase-archive.py` instead uses the explicitly selected original installation, seven public recipe/evidence files, the private Python analysis runtime and a selected verified portable PowerShell runtime. An actual isolated run contained no historical executables, native build, previous candidate archive or private analysis input. The copied application and recipe folders included spaces and Unicode.

The public historical evidence supplies the genuine SL3 facts already recovered and checked against both 2.5.5 and 2.5.6. The current installation supplies the resource schema and archive contents. The new recipe constructs the existing descriptor, adds its installer declaration and `connect_on_finish_install` flag, and selects the tested 44.1 kHz preference. Exact descriptor and final archive hashes prevent drifting into an untested variant. It retains the original 48 kHz buffer-alignment entry; this work does not introduce or validate a new latency model.

The executable and original archive must match the pinned versions before decoding. The resource key is derived transiently from the executable, never stored in the report. The builder validates the descriptor against the original current schema using the selected PowerShell executable with no profile, fixed argument vectors, disabled external schema resolution and its application-local modules. It does not change execution policy. Full portable-runtime inventory verification runs before that process starts.

The codec checks every original encrypted member, decoded CRC and inverse operation. Both original input hashes and recipe hashes are rechecked before publication. Default mode leaves no persistent output; schema validation uses an owned temporary directory which is removed. Explicit `--prepare` requires a fresh direct `analysis/sl3-archive-candidate-*` directory and writes only the derived archive and preparation report. An existing directory is refused and preserved. This is offline preparation: no Serato process, protected write, registration, driver or USB action occurs.

## Developer invocation

Run under the prepared private Python interpreter:

```text
python.exe -I -B scripts/prepare-serato-installed-phase-archive.py --app "ABSOLUTE_SERATO_DIRECTORY/Serato DJ Pro.exe" --portable-powershell ABSOLUTE_POWERSHELL_DIRECTORY --expected-powershell-manifest-sha256 REVIEWED_RUNTIME_MANIFEST_SHA256
```

Add `--prepare analysis/sl3-archive-candidate-NAME` to save a candidate. The builder deliberately refuses another Serato version rather than guessing a resource layout. Its output is private application-derived data and remains ignored; it is not included in the public repository.

## Verification and limits

Seven actual isolated checks passed: read-only generation, saved generation, existing-output refusal, altered original executable, altered original archive, altered public specification evidence and incorrect PowerShell runtime-manifest hash. Negative cases created no candidate directory, existing results remained intact and both copied original files were restored to their initial hashes. The saved archive contains 230 members, passes current-schema validation and matches the previously rehearsed archive exactly.

An additional actual native full-session Plan selected the newly generated archive and passed all current source, capsule, native package and installer-resource checks. Its executable was the existing fresh-session candidate; no rebuild or repack was necessary. It explicitly reported no application, broker or elevation start.

This removes the private intermediate archive and historical installer prerequisites from descriptor preparation. Integrating the recipe into release-kit preparation, shipping reviewed native components, whole-kit relocation, a simple launch/recovery interface and second-PC installation remain unfinished. The selected Serato version and archive format remain pinned. Physical Phase results belong to their recorded sessions; generating matching bytes and passing Plan do not validate a new live launch, post-playback shutdown, physical audio output or long-session reliability.

The subsequent [kit assembler and preparer](portable-kit-assembly.md) integrate this recipe and passed actual same-host relocation checks. A native user-facing bootstrap, another account/PC and live startup remain unfinished.
