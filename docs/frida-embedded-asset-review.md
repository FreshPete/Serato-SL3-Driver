# Embedded native payloads matched to the final image

The local Windows/QuickJS candidate's agent and helper descriptors now have an image-level review. Twelve compiled getters describe four non-empty x64 payloads and eight empty architecture placeholders. Each non-empty payload matches its staged file byte-for-byte inside the final `_frida.pyd`. The candidate and payloads were never loaded or executed during this review. [Evidence](evidence/frida-embedded-assets-20261106.json)

| Payload | Bytes | Role |
| --- | ---: | --- |
| `frida-agent-x86_64.dll` | 12,142,592 | Built native instrumentation agent |
| `frida-helper-x86_64.exe` | 8,640,000 | Built Windows process helper |
| `dbghelp-x86_64.dll` | 1,868,736 | Microsoft debugging dependency |
| `symsrv-x86_64.dll` | 256,456 | Microsoft symbol-server dependency |

Windows reports valid Microsoft Corporation Authenticode signatures on the two debugging DLL files. Their signed bytes are the same bytes embedded in the candidate. The rebuilt agent/helper and candidate are original build outputs; this observation does not make those outputs Microsoft-signed. No trust store was changed.

## How the check works

The original [asset inspector](../scripts/inspect-frida-embedded-assets.py) requires the candidate SHA-256 from the [completed build](frida-local-qjs-candidate.md). It compares the PE's RSDS GUID/age with the PDB summary. The matching PDB's public symbol dump supplies the internal getter addresses, which are not PE exports.

The decoder accepts only the observed five-instruction sequence that copies a 24-byte descriptor into the caller's output. It checks registers, operand widths, RIP-relative reads, destination offsets and the contiguity of the descriptor fields. It reads the name, data pointer and lengths from the final image, checks them against the generated inventory and staged file, and compares the full embedded payload. Every span must fit a single file-backed PE section; nonempty spans must not overlap. Native payloads must be AMD64 with the expected executable/DLL kind.

The four x64 payloads pass. All eight x86/ARM64 placeholders have zero lengths, matching their empty staged files. No Idun payload appears in this agent/helper inventory; the earlier configuration review separately found no Idun build target or file. This is a review of these listed native assets, not an attestation of every byte, icon, string, linked dependency or possible runtime behaviour in the image.

Nine independent machine-code fixtures exercise the decoder, including altered output fields/registers, noncontiguous descriptors, segment overrides, extra calls and missing/early returns. A full inspection with a deliberately mismatched PDB GUID was also refused. No actual binary was altered for that negative check.

## Reproduce without loading the candidate

Use the verified LLVM `llvm-pdbutil dump -summary` and `dump -publics` commands on the candidate's matching `_frida.pdb`, saving each output. Run the asset inspector with the build directory, explicit expected candidate hash and those two dump files, using the private interpreter with `-I -B`. It requires `pefile` and Capstone for data parsing, not the Frida Python package. The decoder tests are in [test-frida-embedded-assets.py](../scripts/test-frida-embedded-assets.py).

A subsequent [isolated candidate SDK and owned-process test](local-frida-owned-probe.md) now passes. The existing session kit, old diagnostic hold, Serato files and SL3 state remain unchanged. No new audio, Serato shutdown or DVS result is claimed.
