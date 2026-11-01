# Production native ASIO provider and configuration

The production COM DLL now delegates its ASIO operations to `DriverFacade` after
loading an adjacent reviewed configuration. It can no longer initialize from a
compiled placeholder alone. On this host no production configuration is
installed, so initialization still fails. Native driver admission and positive
physical streaming remain untested; the DLL remains unregistered.

## Location, records and ownership

The only configuration location is `sl3-asio.conf` beside the actual loaded DLL.
The provider derives that directory from an address inside its containing
module. There is no current-directory, environment-variable or registry
fallback, no shell command and no production simulated-provider option.

Configuration and timing records use strict UTF-8 paths and ASCII keys/values,
with either LF or CRLF, a final newline, exact field order, no BOM, duplicate or
unknown fields, and lowercase SHA256 strings. Integers are canonical unsigned
decimal. All referenced files must be on local fixed drives with absolute,
NUL/control-free paths; UNC/device paths, relative paths and alternate streams
are rejected before opening them. Configuration/timing files are limited to
64 KiB, measurement reports to 1 MiB and worker/helper files to 256 MiB.

The config record has exactly these lines; angle-bracket values are placeholders,
not a ready-to-install configuration:

```text
SL3-ASIO-CONFIG-1
worker=<absolute path to reviewed sl3_usbdk.exe>
worker_sha256=<lowercase SHA256 of that worker>
helper=<absolute path to reviewed UsbDk 1.0.22 x64 helper>
timing_record=<absolute path to timing record>
timing_record_sha256=<lowercase SHA256 of timing record>
```

The referenced timing record has exactly these lines:

```text
SL3-ASIO-TIMING-1
review=approved
worker_sha256=<same worker SHA256>
helper_sha256=<reviewed helper SHA256>
rate_hz=<44100 or 48000>
buffer_frames=<one power of two from 64 through 1024>
intervals=8
requests_per_direction=4
input_extra_frames=<reviewed extra input delay beyond one ASIO bank>
output_extra_frames=<reviewed extra output delay beyond one ASIO bank>
measurement_file=<absolute path to reviewed measurement report>
measurement_sha256=<lowercase SHA256 of that report>
```

The helper hash must equal the already reviewed fixed x64 UsbDk 1.0.22 helper
hash in `driver_configuration.hpp`; configuration cannot select an arbitrary
helper implementation. The timing record must bind the same worker/helper and
fixed native pipeline. The provider checks the hashes of the timing record,
measurement report, worker and helper before constructing a native facade.

Read handles deny write/delete and remain retained through facade lifetime.
Hashes are computed while those handles hold the same files stable; worker
launch and the isolated native backend retain their existing independent hash,
service and exact-device gates. The ASIO host does not load the helper. Missing,
unreadable, changed, inconsistent or malformed records yield failed ASIO
initialization with a bounded error message and no claimed device availability.
COM construction remains separate from configuration I/O, which occurs at init.

These are consistency checks, **not a signature, security boundary or automatic
physical-measurement validator**. `review=approved` records an operator's review;
the loader cannot prove the report's accuracy or turn an assertion into a real
measurement. The report must establish the actual transport/device delays and
applicability. No such physical SL3 measurement report has been produced here,
and synthetic test reports must not be installed as production calibration.

## Bound timing mode

A production profile binds one observed rate and one ASIO bank size. Init rejects
an observed device rate outside that profile. The facade offers only that bank
size, with equal minimum/maximum/preferred sizes and zero granularity. Other
sizes are rejected before buffer preparation; timings are not extrapolated from
one measured mode to another. The existing native start also rechecks the clock.

Since the configured bank size is already known, its profile can report latency
before buffers are created. Totals remain one bank plus the respective extra
input/output frame delay. Component/simulation profiles can remain unrestricted
for testing, but the production parser requires both mode bindings. See the
[facade timing derivation](asio-driver-facade.md).

## Verification and current limits

Release/Debug pass 26/26 native tests; SDK-free builds pass 18/18 with an absent
SDK root. The new configuration tests use clearly labelled synthetic reports
and the real reviewed helper **bytes**, never loading that helper. They check
Unicode paths, all retained file locks and their release, missing/trailing/BOM
records, changed measurement/timing bytes, worker/helper/pipeline mismatches,
invalid rates/bank sizes/frame integers, and rejected non-local/relative paths.
Facade tests verify profile-bound rate rejection, a single fixed bank size and
known pre-buffer latency arithmetic.

A second test copies the actual production DLL to an isolated temporary folder,
places a synthetic config beside it and calls its COM/IASIO entrypoints. The
config points to the test worker, which truthfully reports simulated kind. The
native provider consumes the config and retains its file lease, then rejects
the kind handshake before any clock query, helper load or device open. The test
verifies the resulting failure message, preserved unavailable outputs and
release of COM/module/configuration ownership. It creates no native happy-path
claim. Ordinary production COM negative tests now require an absent adjacent
config before calling init, so an already configured host cannot accidentally
be probed by that test.

The separate actual-ASIO simulated test DLL still has its own compile-time test
provider. The production DLL exports only its two COM entrypoints; it has no
test configuration export or registration entrypoint. All tests leave zero
project workers alive, and temporary configs/reports/DLL copies are removed.
[Matching source/build/export evidence](evidence/asio-configuration-build.json)
is reproducible with `scripts/export-asio-configuration-build-evidence.py`.

Next is physical runtime admission and capture-first verification under the
existing traced owner-present sequence, followed by validated duplex/timing and
an actual reviewed profile. Registration/deployment and an external host trial
follow that evidence. Current Serato's discontinued-device/audio-routing
contract and macOS preparation remain separate requirements. No configuration,
driver, trust, security-policy or installed Serato changes were made here.
