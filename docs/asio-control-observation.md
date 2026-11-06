# Offline ASIO control-call observation

The next normal-start test now has an offline log reader. `scripts/inspect-asio-control-trace.py` reads a **completed** first-party private ETL file and its logger marker through the existing source/image-pinned decoder. It does not start a trace, launch an application, instantiate ASIO, acquire the SL3, modify registration or request elevation. No driver binary or prepared startup candidate was changed.

The existing driver has an explicit process-only logging opt-in, `SL3_ASIO_PRIVATE_TRACE=1`. Its ordinary-user logger records selected control calls, excludes audio callbacks/sample data and has a per-module 4,096-call budget and bounded private output. It is disabled for the current Serato experiment. No user/machine environment setting or shortcut was changed. A baseline launch through the usual shortcut remains separate from any later explicitly observed launch; logging in Serato and its performance have not been tested here.

## What the reader establishes

The reader pairs begin/end records by call identity within **one trace file and PID**, retaining each ASIO object's results separately. Interleaved control threads are supported. Duplicate ordinals/terminals, mixed PIDs/build kinds, changed pair identities, unknown fields/operations, Boolean integers and duplicate/nonfinite JSON are refused. Missing/orphan terminals and abandoned calls remain incomplete observations, with their operation/object IDs retained.

| Observation | Supported meaning | Limit |
| --- | --- | --- |
| Factory return | `DllGetClassObject` returned this HRESULT | Does not prove a device object was subsequently created |
| `initSuccessObserved` / `initRejectionObserved` | A completed `init` returned true / false | A begin event is never promoted to a completed result |
| `bufferCreationSuccessObserved` | `createBuffers` returned `ASE_OK` | Does not establish subsequent callback progress |
| `startReturnSuccessObserved` | `start` returned `ASE_OK` | Does not prove audible output, native USB progress or DVS |
| Stop/dispose success | The corresponding control method returned success | Does not prove physical device release or application shutdown |
| `controlMetadataComplete` | Recorded pairs have no reported losses, unfinished calls, budget saturation or indeterminate pair timing | Not proof that every relevant application action was observed |

Non-success returns remain in the report even if the same object previously succeeded. For example, diagnostic unavailability from `getLatencies` is preserved without assuming it was fatal to the host. The special `ASE_SUCCESS` value belongs to ASIOFuture calls; it is not accepted as successful `start`.

An empty capture cannot prove the driver was not selected. A compile-time `production` tag and PID are not independently verified application/image identities. The standalone summary explicitly leaves Serato identity, loaded-image identity, callback progress, physical audio and DVS unverified. An exact host/process/module context is still necessary before attributing a future capture to Serato. Logger completion is not a Serato-exit or USB-retirement result.

## Input and output

The source directory must contain `private.etl` and a stopped `session.json` marker. Marker losses/status are checked for internal consistency; an open logger is refused before decoding. Inputs are bounded and regular with no reparse ancestors. The decoder manifest, exact source set and executable hash are checked before execution and rechecked afterward. Inputs are copied into a fresh review directory and checked again for changes. Existing output is refused; every output file is create-new. Decode failure preserves partial review data.

Default or `--plan` is inert. Explicit completed-file inspection uses:

```text
python scripts/inspect-asio-control-trace.py --completed-directory ABSOLUTE_COMPLETED_LOG_DIRECTORY --decoder-build ABSOLUTE_DECODER_MANIFEST --expected-decoder-build-sha256 REVIEWED_DECODER_BUILD_SHA --output ABSOLUTE_NEW_ASIO_OBSERVATION_DIRECTORY
```

Output must be a new direct `analysis/asio-observation-*` directory. The current Release decoder manifest SHA-256 is `4195406df119dd573cde88eca8ac815549f349fd96470084c4dbb7535392f607`; its executable SHA-256 is `e6fe96f8e4363c28ac5704cadeaa269be738593194387d0b0fe5d1eada9d6c91`. These artifacts remain local. Raw ETL files and derived rows remain private; only metadata/hash evidence is published.

## Actual fixture evidence

All **24 interpretation checks and seven collector checks passed**. They include object separation, interleaved threads, incomplete/abandoned/orphan calls, losses, saturated budgets, empty input, indeterminate timing, malformed metadata, inert defaults, preservation of existing output, open/inconsistent logger markers and refusal of an altered decoder before execution.

Four fresh real private logs were produced by the existing **owned simulated ASIO fixture** and decoded through the new reader. Three show successful initialization/buffer/start returns; the fourth shows rejected initialization. The child's five simulated owners independently retired their I/O/process/jobs without forced termination; the fifth destructive-callback case retained its `client_control_abandoned` failure. The logger's four-attempt cap means that fifth case is **not** claimed as a captured control log. Environment opt-in and temporary LocalAppData apply only to that owned child, not the PC's persistent environment.

Separately, the exact current packaged production DLL passed the existing disabled/refused/enabled logger fixture with no configuration present. The completed enabled log has 16 events/eight pairs and shows `init` rejection, not a successful stream. That fixture loads an isolated DLL copy only after checking configuration absence. It neither starts Serato nor opens native hardware.

The [checkpoint evidence](evidence/asio-control-observation-20261106.json) binds the current reader/tests, captured ETL/marker identities, fixture outcomes and decoder. Postchecks found original Serato resources, no occupied session paths or temporary registration and no matching first-party worker/controller or Serato process. The prepared [normal-start experiment](on-demand-normal-start-test.md) remains source-current. Actual normal Serato selection/startup, output, DVS and shutdown still need the attended test.
