# Next attended Windows test packet

The next useful physical test is one read-only control acquisition with simultaneous USB lifecycle/image tracing and ordinary-user port observation. A fresh packet is prepared against the current Release build and the 2 November cached PnP mapping. **It is unarmed and has not run.** [Preparation evidence](evidence/sl3-return-packet-20261102.json).

The cached PnP query found one present Rane SL3 entry using `strmdrv`, with problem Code 39, on root-hub port 4. It used Windows PnP properties and opened no SL3 handle. This is not a fresh descriptor read, proof of USB readiness or a new Code Integrity diagnosis. Full instance/parent identifiers stay in the private snapshot.

## Prepared files and scope

The private local collector plan is `analysis/logging-batch-return-20261102/controls-image.json`. The matching port observer is `analysis/hub-port-observer-return-20261102/plan.json`. Their future context paths agree and do not exist yet. The collector launcher has no launch record, the observer has no run record, and both default preparation/validation commands pass. Those facts describe preparation, not a qualified capture or permission to reopen.

The intended attended run requests one redirect, observed-rate and complete audio-control-table reads, then release. It starts no audio, writes no rate/control selection, changes no firmware/security/trust setting and performs no second acquisition. The collector needs one administrator launch; the native probe and port observer run under the ordinary user token. The scripts collect evidence and clean up their owned roles automatically. The owner must be available for approval and physical recovery if needed.

The port sampler is eighteen seconds at a requested 250 ms interval; it waits at most ninety seconds for the bound trace context. The USB trace is twenty seconds and the image collector is sixty seconds. These are configured bounds, not achieved timing or a readiness policy. The [existing observer](hub-port-observer.md) and [combined capture](combined-controls-image-capture.md) describe their source/process binding and independent result checks.

## Read-only review now

From the repository root, these default commands validate only and do not request UAC, trace or open the SL3:

```powershell
pwsh -NoProfile -File scripts/start-controls-image-capture.ps1 `
  -Plan analysis/logging-batch-return-20261102/controls-image.json
.venv/Scripts/python.exe scripts/observe-sl3-hub-port.py `
  --job analysis/hub-port-observer-return-20261102
```

Source/build or installed-image changes can invalidate the packet. Before an attended launch, recheck the connected SL3's PnP parent/port and stop if it differs. Do not edit a frozen plan to make it pass. Prepare a fresh packet after changed inputs, cancellation, a claimed attempt or a moved device. The existing launchers enforce single use and runtime pins; a successful default check does not grant hardware admission.

## Owner-attended execution only

When the owner is available and the recovery/one-acquisition scope is reviewed, start the observer in one normal terminal, then promptly launch the collector wrapper in a second normal terminal. The explicit runtime commands are:

```powershell
# Terminal 1: starts the ordinary-user observer waiting for its bound context.
.venv/Scripts/python.exe scripts/observe-sl3-hub-port.py `
  --job analysis/hub-port-observer-return-20261102 --run

# Terminal 2: requests the one administrator collector launch and coordinates
# the separately owned normal-user control probe. Do not run while unattended.
pwsh -NoProfile -File scripts/start-controls-image-capture.ps1 `
  -Plan analysis/logging-batch-return-20261102/controls-image.json -Run
```

No such command was executed in this checkpoint. A cancelled/expired attempt must not be relaunched with the same packet. Do not try a second acquisition merely because the process retired, `StopRedirect` succeeded, a descriptor reappeared or a timer interval elapsed. Preserve failures and establish resting/recovery state before any further hardware test.

After retirement, independently validate the controls result, complete USB/state retention, selected recovery and image window. Compare whole port-snapshot intervals with the mapped startup/release phases using `analyse-hub-port-phases.py`; a crossing or incomplete sample does not qualify. The normal-user observation must discriminate the relevant phases before a successive-acquisition design can be selected. Matching image version metadata remains separate from a loaded-memory hash.

## What follows this test

If recovery/readiness is established, the next stages are current-worker known-input capture, physical jack mapping/levels/routing and measured timing, then reviewed ASIO/archive deployment and a real current-Serato session. The [opt-in log controller](asio-owned-trace.md) and [offline call-log analyzer](asio-general-trace-analysis.md) are available for that later host test. Their existence is not evidence of admitted SL3 audio or two-deck DVS.

The ASIO host-contract review did not justify adding automatic reset/reopen behavior: the checked current host's [reset path](serato-asio-reset.md) can destroy and recreate interfaces, while the physical second-open problem remains unresolved. No production audio source or reset behavior changed in this preparation. The full Windows/current-Serato/two-deck objective remains incomplete; Mac stays deferred.
