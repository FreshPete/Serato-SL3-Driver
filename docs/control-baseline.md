# Same-owner baseline before a native setting

The selected-target native adapter requires a move-only, single-use observation from a successful getter on the same live software device owner. Supplying only a target does not admit selection. The subsequent [single-target diagnostic](native-control-selection-diagnostic.md) connects it to NativeHeldDevice while normal ASIO configuration remains getter-only. No setting was sent to hardware.

`ControlBaselineOwner` in `src/windows/control_baseline.hpp` owns a private process-local lifetime/generation. Its token has no public field setters or serialization format. Only the native adapter can issue one, after receiving and parsing a complete valid `0x32` reply within the getter's lifetime budget. A malformed, short, failed or late getter does not issue one. Extraction from the getter succeeds once.

| Boundary | Rule |
| --- | --- |
| Construction | Consume the token, even on refusal; require matching live owner/generation and monotonic age strictly below 1,500 ms. |
| Reuse | A token cannot be copied. A moved/consumed token cannot reserve a second transaction. |
| Owner lifetime | A weak lifetime identity distinguishes a destroyed owner from a new object even at the same address. |
| Invalidation | A newer successful getter invalidates earlier observations/reservations. Native audio activation and device close invalidate before their USB operations. |
| Before setter | The fresh transaction's entire initial 22-byte table must match the baseline, including unknown bytes. Recheck age and generation before preparation and again immediately before submission. |
| After setter | The existing 4,500 ms transaction deadline and read-back verification still apply. Crossing the baseline freshness window after a timely setter does not by itself suppress verification. |
| No-op | If the fresh getter already observes the requested value, it may complete without a setter even if other baseline bytes changed. This does not assert baseline equality. |

The 1,500 ms freshness window is a conservative software admission policy, reused from the bounded getter budget. It is not measured device latency or a hardware guarantee. The caller must maintain exclusive idle ownership and use the same monotonic clock domain. Lifetime/generation checks do not provide synchronization for concurrent callers.

The token proves a local observation path, **not permission to write**, current firmware identity, continuous physical attachment, a fresh clock read, or a traced/security/recovery baseline. The original ABI has no transaction nonce or atomic compare-and-set. A physical switch or independent actor can still change state between inspection and submission. The subsequent diagnostic adds explicit target admission/journal wiring; the current-worker read-only physical baseline, clock check and supervised setting launcher/recovery test are still required.

A rejected setter is never submitted to the native transfer backend. The outer transaction nevertheless retains its conservative possible-write state once it has taken a setter request. For a full-table mismatch, it also retains the newly observed initial table; the adapter's `ERROR_REVISION_MISMATCH` explains the refusal. No retry or automatic rollback is introduced.

The existing fake-transfer tests now mint their baselines through the same getter adapter before each selected scenario. Added tests cover unissued/wrong-owner/reused tokens, age boundary and clock regression, new observations and explicit revocation, destroyed/reused owner storage, changes in an unknown table byte, expiry during inspection/preparation, verification after a timely setter, write-free no-op and malformed getter refusal. The preceding all-target/frame/error/timeout tests remain. These tests do not open the SL3 or validate physical settings/cancellation.

Build-bound source/binary/log identities and these limits are in [native adapter evidence](evidence/native-control-adapter.json). The underlying production `Transfer` submission/cancellation/drain code is unchanged. Protocol remains v3; no production configuration, ASIO registration, driver/service/trust/security or firmware operation is part of this change.

Fresh verification passes **39/39 Release, 39/39 Debug, 25/25 SDK-free and 125/125 Python**. Seven exporters pass. The current-worker CLI rejects old physical capture/duplex prerequisites with exit 1 and `Build/security mismatch`. The local `artifacts/build/checkpoints/control-baseline-20261031` checkpoint preserves exact sources, binaries, checks and evidence. No new hardware operation ran.
