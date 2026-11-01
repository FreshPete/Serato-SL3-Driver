# One-open continuous bridge probe

The staged post-power-cycle test established a concrete sequence: one redirect, clock inspection and close succeeded, then the immediate next redirect stalled. The next continuous-bridge probe can now avoid those preliminary open/close cycles. Its worker opens the SL3 once, reads and validates the clock on that handle, activates audio and runs the existing request engine through the same redirection. This is a tested software path awaiting hardware validation, not a working production ASIO lifecycle.

**Later physical result:** the single-open probe subsequently passed a real one-second 44.1 kHz callback/USB session after validated capture and silent duplex. [Actual result, retained packet failure and limits](first-real-single-open-bridge.md). This supersedes preparation-only statements below without establishing production ASIO or Serato compatibility.

## Evidence driving the change

The owner acknowledged a full power cycle, Windows recorded a new SL3 arrival at 17:22:30 UTC, and the staged diagnostic ran at approximately 17:23. Worker 1 completed all 17 startup/cleanup markers, including the getter and redirect close. Worker 2 polled enumeration until the unit appeared, read the configuration and entered `UsbDk_StartRedirect` without returning. Thus enumeration readiness was insufficient to establish redirect readiness. The second redirect entry followed the first close return by the interval recorded in [checked run metadata](evidence/inspect-reopen-after-power-cycle-20261030.json).

Exactly one clock inspection completed. The older probe overwrote the first rate value when launching its second worker, so its final rate zero means unknown; it does not mean the first successful getter returned zero. The new probe separately preserves `initial_reported_rate_hz` to prevent that diagnostic loss. No current post-power-cycle rate is invented from the older record.

The complete trace has 14,368 events with no event/buffer loss; Secure Boot remained enabled and the selected before/after state contract matched. The second worker missed bounded retirement and remained visible afterward before disappearing later. The later reconnect at 17:28:17 produced a descriptor-request failure, problem 43, at the recorded SL3 ACPI USB location. The normal SL3 identity was absent. A longer all-power-off interval and a different direct USB port were requested before further hardware access; that recovery is not confirmed at this checkpoint.

## Software contract

`HostSession::start_checked(expected_rate_hz, intervals)` is an explicit diagnostic entry. It requires prepared SDK buffer ownership, valid supported metadata and a fully retired prior process/audio owner. It rejects callback reentry, invalid interval shapes, prior inspection state and a prior failed session. It does not invoke the temporary inspector or silently retry failure.

It launches the same hash-pinned native worker, performs the existing protocol/kind handshake, starts the audio owner waiting for input, and sends the typed start request. The unchanged native `NativeStreamTarget` remains responsible for opening the exact fixture-matched SL3 and calling the real clock getter **before** alternate activation or isochronous submissions. A mismatch throws before those audio operations. Only the worker's successful running reply publishes observed clock metadata to the host. Merely supplying a rate does not publish inspection success or device readiness.

The original `start()` / production facade path remains separate. This change neither creates a timing profile nor registers a COM driver. Keeping one native lease across the complete IASIO object's initialization, dummy-host probes, stop/start and buffer recreation still needs implementation and validation. Repeated sessions cannot simply reuse stale shared audio queues whose frame positions belong to the previous stream.

## Explicit probe mode

The standalone probe accepts `--single-open-44100` or `--single-open-48000` with the same pinned worker/helper/output arguments as its other explicit modes. It records `single_open=true`, the expected rate, zero completed temporary inspections and `inspection_succeeded=false`. A successful stream must still meet the existing one-second callback, completed native I/O, zero-output, retirement and buffer-disposal contracts. The actual verified rate must match the explicit expectation.

The traced wrapper exposes this through `-SingleOpenRate 44100/48000`. This remains an audio test, so current same-worker capture and silent-duplex prerequisites are still required, as are enabled Secure Boot, a reviewed running transport, exact source/binary identities, a normal exact SL3 identity, no remaining native test process and a complete bounded trace. There is no rate setter or audio fallback. Once enumeration recovers, the fresh capture's observed rate should select the expected-rate argument; the prior stored setting is not assumed to survive a power cycle.

The initial physical probe used 64 intervals and 128-frame banks. The later block-size extension below adds an explicit eight-interval software path. Neither setting by itself establishes an approved timing profile, analogue routing, measured latency, real application open, DVS operation or stability result.

## Validation

Release and Debug each pass **33/33** native checks; the SDK-free configuration passes **23/23** and Python passes **51/51**. New host tests prove the temporary inspector is not invoked by using a fixture whose inspector deliberately hangs. They exercise SDK callbacks and independent retirement, reject invalid metadata before launch, reject a factory clock mismatch with zero callbacks/observed-rate claims, prevent silent retry after failure, and retain the real native absent-helper gate. The simulated worker now checks its actual fixture clock before creating the stream target.

The probe lifecycle test exercises a successful simulated single-open session and a mismatched expected-rate failure, while retaining explicit simulated identity. These are software results only. [Build evidence](evidence/single-open-build.json) binds sources, executables and logs. The native worker is unchanged at SHA-256 `f29720369d443f7ec9b6ee4bf9c20a766f174ea02879b0727e28576a2077ab66`; the new probe and manifests are archived locally in `artifacts/build/checkpoints/single-open-20261030/`.

## Explicit eight-interval block size

Single-open modes now optionally accept trailing `--intervals 8` or `--intervals 64`; the default remains 64. The traced wrapper exposes this as `-SingleOpenRate 44100/48000 -BlockIntervals 8/64`. Eight intervals match the production facade's block count, while the SDK bank remains 128 frames. No latency profile is generated from choosing that shape.

Other shapes, malformed values and interval arguments on inspection/legacy modes are rejected before output-directory creation. Release and Debug each pass 33/33 checks, including a real private-process/SDK callback lifecycle with an explicitly simulated eight-interval worker and normal retirement. The prior 64-interval paths and kind/rate gates remain tested. [New software checkpoint](evidence/eight-interval-probe-build.json).

The native worker is byte-identical to the first real bridge checkpoint. Current same-worker capture/duplex records remain applicable prerequisites, and the new wrapper still validates them. Only the probe's requested stream configuration changes. The new binaries/manifests/logs are archived in `artifacts/build/checkpoints/eight-interval-probe-20261030/`.

The attempted eight-interval physical launch was canceled by Windows before its script started. Its result directory was not created, so there is **no physical eight-interval result** at this checkpoint. The last real continuous result is still the one-second 64-interval run above.

The first physical-result exporter now verifies that historical result against its immutable `single-open-20261030` binaries, manifests and archived runner bytes. For tracked source files changed by later work, it reconstructs LF/CRLF text from exact Git commit `13fd6c4950053f37f2aeef9d03e4f7699e4ff3b8` and requires the recorded byte hash to match. Unchanged external headers remain checked directly. Developing a new probe must not cause old hardware evidence to be attributed to its new binary or silently make its original verification unreproducible.

## Subsequent eight-interval result and retained-worker work

The owner-requested relaunch passed the actual eight-interval test: one second at 44.1 kHz with 341 callbacks, complete independent retirement and a loss-free trace. [Physical result and limits](eight-interval-physical-test.md). This supersedes the canceled-launch status above.

A separate retained-device worker now implements acquire/fresh-clock/start/stop/final-release using a fresh audio mapping per stream. Its positive lifetime tests are simulated; native hardware validation and host ASIO integration remain pending. [Contract, tests and next integration](retained-device-worker.md). The new worker binary does not inherit the archived single-open hardware result.

The later [retained ASIO host checkpoint](retained-asio-host.md) connects that lifetime to the owner/facade and production configuration provider. Positive simulated host and actual COM/IASIO tests cover repeated starts, buffer recreation and blocked callback/module retirement. The dedicated retained native hardware test and timing-profile/application validation still remain.
