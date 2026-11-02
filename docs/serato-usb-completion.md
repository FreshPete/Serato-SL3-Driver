# USB identity attachment and composite completion

Current Serato has a checked handoff from its discovered USB identity record to the composite worker's acquired-component count. A nonempty taken record is retained at composite member `+0x20`, and the worker increments the count. Equal acquired/expected counts lead, on the selected ordinary branch, to setting composite byte `+0x60` before the minimum-version predicate. This identifies an internal aggregation milestone; it is not physical audio readiness. [Original-byte evidence](evidence/serato500-usb-completion.json).

Target is the unchanged installed/extracted Windows DJ Pro 5.0.0.1278, SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. Addresses below are preferred VAs. No application, hardware, resource, account, firmware or security operation ran.

## The selected ordinary component branch

The [supported-device contract](serato-supported-contract.md) already identifies support value 1 and the descriptor's MIDI/HID/USB expectation getters. This extension checks the local count calculation and its later consumer in worker `1421db390`:

| Boundary | Checked behavior |
| --- | --- |
| `1421db981` | Support value must equal 1 to enter this branch. |
| `1421db9c4` | Helper `140c00aa0` tests composite member `+0x30`; its present branch uses the ordinary count formula. The previously identified descriptor accessor `140c00570` copies that member and its shared owner at `+0x38`. |
| `1421db9e8`, `1421dba43`, `1421dba98` | Descriptor slots `+0x10`, `+0x18`, `+0x28` supply nonzero MIDI direction, HID and USB contributions. |
| `1421dbaa2` | Their sum is stored at stack `+0x98`. |
| `1421dbae6` | Acquired count ESI is initialized from the checked preserved zero register. Other component-acquisition branches can increment it before the USB branch. |

With a present descriptor, explicit no-MIDI, no HID and required USB, the ordinary expected count projects to **one**. That arithmetic is conditional on reaching this branch with those actual descriptor values. With the descriptor absent, the alternative branch instead counts HID presence through `140c00ad0`; it does not use the three-term formula. The unmodified SL3 stub remains support 2/discontinued. A schema-valid candidate is not proof that the application parsed, selected or instantiated it.

## A record take followed by ownership transfer

The USB acquisition branch first queries `requires_usb` and checks that composite member `+0x20` is absent. Its record-list take at `1421dc6cc` is the [previously verified VID/PID lookup](serato-usb-discovery.md). It returns identity metadata, not an open libusb device. A null result skips attachment and the corresponding increment.

For a nonempty result, the worker copies the two-word shared record to the setter argument. At `1421dc895` it calls `140c01ae0`, then increments ESI at `1421dc89a`. The setter's full unwind extent is `140c01ae0:140c01bb8`; the fresh isolated decompilation and original instructions identify stores of the record pointer to `+0x20` and its shared-owner pointer to `+0x28`, with reference-count retention/release. No USB open or claim is identified in this setter. This bounded observation does not exclude device access elsewhere, nor establish identity continuity while UsbDk redirects the hardware.

The matching record proves only what its discovery producer supplied. It cannot attest that the original kernel driver loaded, that our worker acquired the device, or that an ASIO stream works.

## Equal counts are followed by another gate

At `1421dc8ee`, ESI is compared with the expected count at stack `+0x98`; inequality branches elsewhere. The selected equal-count path tests member `+0x30` again. When absent, it skips the descriptor-based USB metadata lookup and reaches `1421dcbe3`, passes true to leaf `140bc8140` and sets composite byte `+0x60`. The present-descriptor branch performs a separate metadata lookup and also reaches the common flag store; that second lookup is not the earlier attachment/increment. The worker then calls `140c00af0`, the [previously verified minimum-version predicate](serato-usb-arrival.md), before choosing the deferred arrival/error action.

The helper leaf is a byte store, not an audio query. Do not use this completion byte as evidence of a working rate, sample format, driver trust, legitimate service result or DVS. Cancellation/waiting, other component branches, prior eligibility and later delivery remain independent. This report does not exhaust the worker's control flow.

For the SL3 hypothesis, this supplies a concrete identity-record contribution without inventing a MIDI/HID component or a second USB streaming connection. It does not implement the retired DRIVER_API handshake, validate the candidate's NONE control semantics, establish permitted service state, or admit current SL3 audio. Those requirements and actual ASIO/deck/channel behavior remain unfinished.

## Verification and reproduction

```powershell
.venv/Scripts/python.exe scripts/export-serato-usb-completion.py
# Optional fresh destination; an existing output is refused before analysis.
.venv/Scripts/python.exe scripts/export-serato-usb-completion.py --output analysis/usb-completion-NAME.json
```

The exporter checks selected instructions, three complete helper leaves, preserved zero-register provenance, the prior discovery/arrival/component evidence and its original instruction bytes. It binds one fresh complete focused function and the existing full worker report to exact PE unwind ranges. The fresh read-only import disables library loading and whole-program analysis; its log confirms zero additional libraries, discarded import and an empty temporary project. Regeneration is byte-identical and existing-output refusal preserves the report. Full vendor pseudocode remains private; no key, response or complete vendor descriptor is published.

Native source/build/image identities remain unchanged from the [ASIO-owned logging checkpoint](asio-owned-trace.md); native tests were not rerun for this static-only change. Actual current Serato execution, safe device reacquisition, physical mapping/levels/latency, protected deployment and two-deck DVS remain unverified. Mac is deferred.
