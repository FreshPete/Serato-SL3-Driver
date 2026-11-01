# ASIO facade and real vtable session tests

**Update:** the production native provider and bound timing configuration are now implemented; [current contract](asio-native-configuration.md). The checkpoint below describes the original facade tests.

The SDK-facing `DriverFacade` now maps ASIO lifecycle and metadata operations to
the host coordinator. A separate unregistered test DLL uses the same COM server
source to run actual IASIO vtable calls through a simulated private worker. The
production DLL still fails initialization: reviewed production path/timing
configuration is not installed, and physical transport has not been validated.
There is no runtime production simulation switch or registration entrypoint.

## Implemented contract

Initialization performs temporary worker/clock inspection and retains the
observed rate. Repeated initialization is idempotent. Buffer creation selects
real SDK planes for up to six logical input and six output channels, packed
24-bit little-endian samples, power-of-two sizes 64 through 1024 and preferred
size 128. Active-channel bits are published only after successful preparation
and cleared only after successful disposal. Physical connector labels and
gain/routing controls are not inferred from logical channel numbers.

Only the currently observed rate is accepted by rate selection. Requesting the
other nominal rate, zero/external sync or NaN returns no clock; selecting the
existing rate performs no write. One device clock is reported, with no associated
input/group. Selecting index zero is a no-op; other indices are rejected. The
native worker still checks the actual rate before submitting audio. An eventual
rate setter requires its own control/rollback and physical validation.

Start uses the fixed eight-interval worker session and requires buffers. A
duplicate start is rejected without disturbing the existing stream. A failed
start invalidates initialized metadata, while buffer disposal remains available
after actual retirement. Stop reports a hardware error if cleanup is incomplete
or the session failed. Initialization/start/stop/buffer/rate/clock mutation from
inside the audio callback is rejected immediately, while metadata and position
queries are callback-safe. Control operations otherwise have one owner.

Sample position returns the current input bank's logical first-frame index and
its backend publication observation in nanoseconds, split into the SDK's two
32-bit fields. It resets to zero on a fresh start. Before the first callback and
after stop it returns `ASE_SPNotAdvancing` without publishing invented outputs.
This is the existing software position/observation pair, not a measured DAC
playhead, interpolated sample clock or demonstrated physical timestamp accuracy.
Eight-interval batches avoid multiple minimum-size bank callbacks within one
input batch; backlog can still cause callbacks to arrive in bursts.

Optional time-info negotiation, output-ready optimization and a control panel
return unsupported. The copied legacy callback table remains the processing
contract. Error messages have a bounded 124-byte output, and uninitialized
methods preserve caller outputs while returning not present.

## Timing input and limits

The official local SDK header specifies that reported latencies include device
delays. Its host-buffer definition also distinguishes input age from the delay
after the callback before the newly filled output bank sounds. Buffer size
alone does not establish either complete SL3 latency.

The facade therefore requires an explicit `LatencyProfile` containing additional
input/output frame delays beyond the bridge's one input bank and one output
bank. It must cover the selected native transport and device FIFOs, for the
fixed eight-interval/four-request pipeline. There is no default unknown profile;
zero is a supplied value, not a marker for missing calibration. Out-of-range
frame values are rejected. The provider is responsible for provenance and
applicability; constructor acceptance is not a physical-validation check.

After buffer creation at size `B`, reported input/output delays are respectively
`B + input_extra` and `B + output_extra`. Latencies are unavailable before a
buffer size has been prepared. Two blocks of initial output silence are already
tested in the bridge/queue path: the first callback arrives after the first
input block, and its output enters the output timeline after the second block.
That establishes a two-block software round trip, not a two-block output delay
after the callback. Native/physical extra delays and continuity remain unproved.

The test provider supplies explicitly synthetic extras of 7 input/11 output
frames. At 64 frames, expected totals are 71 and 75. These values are not a Rane
calibration and must not be copied into production configuration. Physical
capture/loopback and timing evidence are still needed to establish a usable
SL3 profile and timestamp accuracy.

## Verification and configuration boundary

Release and Debug pass 25/25 native CTest cases; the SDK-free build passes 18/18
with an intentionally absent SDK root. New facade tests cover initialization,
invalid pointers, observed-rate-only selection, clock enumeration capacity,
channel activity, real SDK planes, supplied latency arithmetic, preserved
unavailable outputs, callback position/rate, rejected callback mutation,
duplicate start, repeated fresh worker sessions, safe failed-start disposal and
actual native rejection through an asserted absent helper.

The additional DLL test calls the official COM factory and IASIO vtable, performs
two actual prepare/start/callback/stop cycles and disposes buffers. It verifies
logical position resets, callback reentry rejection and eventual DLL unload
after COM/audio ownership retires. The earlier blocked-callback/owner-destruction
and DLL retain/unload tests continue to pass in the full suite.

`sl3_test_configure` is compiled only into `sl3_asio_session_fixture.dll`; its
provider can create only an explicitly simulated facade with the supplied
executable hash. The production DLL exports only the two COM entrypoints and
does not link this provider or the facade. Build evidence checks exports/imports,
all source/header/definition inputs, logs and matching binaries. No helper is
imported by the test DLL. [Reproducible evidence](evidence/asio-facade-build.json)
is generated by `scripts/export-asio-facade-build-evidence.py`.

Next is reviewed production worker/helper/timing configuration and its native
provider, including tests that reject missing/stale/unproved configuration
without presenting a device. Physical driver admission, traced input capture,
output/timing/recovery tests and current Serato's separate device-support/audio
routing contract remain necessary. Windows security, bindings and the installed
Serato application have not been changed by these tests. macOS follows Windows.
