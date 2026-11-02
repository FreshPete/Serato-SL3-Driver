# Failed acquisition can select another port cycle inside UsbDk

The reviewed released x64 UsbDk driver contains a failure path that matters to
reopen diagnostics: after its initial reset succeeds, an attachment wait failure
or redirect-handle failure calls rollback **with another reset enabled**. A
failed initial reset instead selects rollback without another reset. These
arguments are now checked in the actual pinned binary, alongside exact source
and WPP format identities. They do not prove which branch caused an old stall.

Target driver SHA-256:
`c92b6c15bd550023312ae4cfe49a39757952a3c2ebdc7d1d143ac5e695f69a63`.
Preferred image base is `140000000`; these VAs are not runtime kernel addresses.
No driver/helper execution, tracing session, device operation or binding change
ran. The released binary is unchanged.

## Checked source and binary branches

The exact-commit [AddRedirect and rollback source](https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/UsbDk/ControlDevice.cpp)
is already bound by the existing lifecycle preparer's normalized source hashes.
The actual driver references the matching ControlDevice WPP GUID and message IDs
36–39 inside function `140002f10`. The new verifier follows selected checked
instructions through that function and rollback `1400031fc`.

| Failure | Binary rollback call | WithReset | Consequence in checked branch |
| --- | --- | --- | --- |
| Initial reset returns failure | `140003028` | false | Remove the redirection entry; skip the conditional reset |
| Attachment wait fails or times out | `1400030eb` | true | Remove the entry, then call reset with ForceD0 false |
| Redirect-handle creation fails | `1400030a1` | true | Same reset-enabled rollback; return device-not-connected |

Rollback passes ForceD0 false at `14000327d` before calling reset wrapper
`140005280` at `140003286`. That Boolean is carried through the wrapper to
`1400064b0`. False skips the conditional D0-request path; it still reaches the
cycle-IRP creation with literal `0x22001f` if the preceding lookup/setup succeeds.
The wrapper can fail its PDO lookup before reaching that operation. The pinned
source names it `IOCTL_INTERNAL_USB_CYCLE_PORT`. Thus ForceD0 false does not mean
no port cycle, and WithReset true does not prove that one was submitted.

The attachment branch calls event wait `14000c850` with a timeout-enabled flag,
nonalertable flag and signed relative interval `-1,200,000,000` in 100-ns units:
120 seconds. The event helper passes the selected pointer to the actual
`ntoskrnl!KeWaitForSingleObject` import. `STATUS_TIMEOUT` (`0x102`) follows
reset-enabled rollback and becomes `STATUS_DEVICE_NOT_CONNECTED` (`0xc000009d`).

That interval bounds only the attachment wait. The
[existing power/pending-cycle wait findings](usbdk-detachment.md#power-and-port-cycle-waits)
still prevent calling it a bound on all startup, rollback or kernel retirement.
No fixed delay, automatic retry or fresh acquisition is selected.

## Process containment and cancellation limits

An observed worker/job exit is not evidence that every previously submitted
kernel operation has reached quiescence or that the original stack can accept
another cycle. This finding strengthens the reason to keep those observations
separate; it is not a new claim that a delayed rollback happened after a specific
watchdog termination.

Microsoft distinguishes queued requests from requests already delivered to a
driver in its [WDF cancellation contract](https://learn.microsoft.com/en-us/windows-hardware/drivers/wdf/canceling-i-o-requests).
Delivered requests require driver handling of cancellation. The selected UsbDk
source/binary review does **not** exhaust every request wrapper, cancellation
callback, lower-stack path or arbitrary concurrent state. It therefore proves
neither cancellation immunity nor immediate cancellation on caller exit.

The saved failed experiment remains failed. The new evidence does not replace
the [observed post-release startup timeout](attended-port-lifecycle-20261101.md)
with a diagnosed rollback cause or establish a safe reopen/readiness condition.

## Offline decoder supplement

`scripts/export-usbdk-rollback-contract.py` verifies the contract and optionally
prepares two additional offline TMF definitions:

- ControlDevice message 34: rollback entry-deletion failure.
- ControlDevice message 35: rollback reset failure, with status.

Both have invariant definitions across the bundled architecture/OS repetitions,
the same GUID present/referenced in the driver, error level and the already
captured ControlDevice flag. The historical 32-format decoder and capture flags
are unchanged. The supplement is not silently installed into existing capture
plans or their validators.

```powershell
.venv/Scripts/python.exe scripts/export-usbdk-rollback-contract.py
.venv/Scripts/python.exe scripts/export-usbdk-rollback-contract.py `
  --prepare analysis/<fresh-direct-directory>
```

Preparation writes only `rollback-supplement.tmf` and `plan.json` into a new
direct analysis directory. Existing output is refused. Formats stay private;
the [bounded contract evidence](evidence/usbdk-rollback-contract-20261102.json)
publishes identities, hashes and selected instruction facts.

The actual SDK Tracefmt replay combines the unchanged captured definitions,
the earlier three observed-message additions and this supplement. It retains
the same 21 UsbDk records and selected lifecycle observations across 10,504 total
events, zero reported losses, zero format errors and zero unknown formats.
The original ETL and captured decoder remain unchanged. There are **zero
rollback-error records**, so this replay does not exercise those two new payload
formats. Successful rollback has no selected positive message; missing errors
cannot establish absence or completion of rollback.

## Verification and next decision

The new verifier checks 77 instructions, five fresh complete focused functions,
the actual wait import, six WPP GUID references, source branch order and the two
invariant formats. Seven new offline tests and four existing lifecycle-parser
regressions pass. Regeneration is byte-identical; a fresh read-only/no-analysis
Ghidra import loaded zero extra libraries and discarded its temporary project.
Full navigation, decompilation, decoder and replay output stay private. The
[verification record](evidence/usbdk-rollback-20261102-verification.json) binds them.

The next attended scenario should retain USB/WPP observation through a failed
startup's aftermath, distinguishing initial cycle, attachment wait, internal
rollback reset and original-stack restart. Neither an expired user-mode deadline
nor no error message authorizes another redirect. The existing one-acquisition
scope/control queue remains the physical prerequisite. Reliable reopening,
actual native/analogue audio/timing, protected deployment, current Serato/DVS
and remaining recovery gaps are unfinished. macOS remains deferred.
