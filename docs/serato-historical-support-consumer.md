# Historical support flag gates DriverAPI processing

In original Windows Serato DJ Pro 2.5.6.1001, the historical descriptor's declared-app support flag has a concrete consumer in `DeviceAggregationThread`. It is not merely an unused retained XML value. For the selected known-descriptor path, a false flag queues action **9** and skips the inspected downstream DriverAPI processing. A true flag admits that local continuation. The action's notification meaning has not been identified and is not equated with current discontinued-device or licensing handling.

This extends the [app-name/parser/getter check](serato-historical-app-support.md). That preceding result says the default constructed `AppConfig` name matches the retained SL3 declaration in both historical releases. Combined, these checks describe a **conditional static path** from a matched SL3 definition toward its retained DriverAPI factory. They do not establish that the real application selects that definition, retains that singleton, loads the library or connects successfully.

## Descriptor provenance and gate

| Link in the checked 2.5.6 path | Preferred VA / field |
| --- | --- |
| Parsed descriptor vector | Begin/end globals `144f4b450` / `144f4b458`; append path was checked separately. |
| Manager setup | `14015fef0` copies descriptors, supplies object `+0x10` as the typed shared interface and calls registration `1406a5f40`. |
| Manager type | Constructor at `1406a4580` installs RTTI-validated `serato::device::composite::DeviceManager`. |
| Descriptor matching | `1406a6820` iterates the manager's registered interfaces at `+0x48`, compares three identity words through the common descriptor interface and returns the selected interface. Exact third-word equality has a directly checked return; fallback selection is not interpreted as a physical match here. |
| Snapshot record | `1406a0240` passes the selected shared interface to constructor `14069fd50`, which retains it at record `+0x40` / ownership `+0x48`. |
| Notification processing | The selected known-record branch of `1406a13d0` copies its descriptor pointer through another call to that record constructor. It passes the record as the seventh argument to the aggregation-thread constructor. |
| Thread ownership | `1406a9030` installs validated `DeviceAggregationThread` RTTI, retains argument seven at thread `+0x58`, and binds work function `1406a96d0`. |
| Getter consumer | `1406a9d24` obtains the record's `+0x40` pointer; `1406a9d3b` invokes its slot `+0x20`. AL is preserved in EDI across shared-reference cleanup. |
| False notification | `1406a9d71` tests DIL. False constructs action 9 and queues it through `1406af100`. |
| Processing gate | `1406a9ee3` tests DIL again. False jumps to cleanup at `1406abd3c`; true continues, still subject to the descriptor and later checks. |
| Inspected factory call sites | `1406a9f31`, `1406aa18e`, `1406aa81e` call the previously checked factory `140681ae0`, which retains an SL3 case and loader. These are separate processing stages, not three demonstrated connections. |

The interface adjustment matters: the ControllerDescriptor getter at slot `+0x20` reads a Boolean. The **common** descriptor interface also has a slot `+0x20`, used for an identity word. The provenance and receiver conversions distinguish these calls; matching a virtual offset alone would misidentify the consumer.

The small shared-pointer copy helper without an unwind entry is checked against its exact instruction sequence and boundary. A separate debug hook is checked as stack stores followed by return; it does not replace the pointer in this path. These checks avoid assuming a neighboring unwind range describes either helper.

## Local flow model and verification

The [exporter](../scripts/export-serato-historical-support-consumer.py) revalidates the preceding app-name and SL3 API evidence, pins the original 2.5.6 executable, checks 59 selected instructions and two small helpers, validates manager/thread RTTI and checks the selected PE boundaries. Complete linear decoding covers the 2,206-instruction worker range `1406a96d0:1406abd8e`.

A range-local graph walk starts independently at the false branch target and true continuation. The false walk visits 20 instructions and reaches none of the three factory call sites. The true walk visits 1,718 instructions and can reach all three. Both walks retain unresolved exits explicitly; neither has an unresolved exit in this selected model. These counts describe possible local reachability, not a single executed path or successful operation.

The model **assumes calls return normally**. It does not enter callees or model their side effects, exceptions, callbacks, runtime dispatch or nonlocal transfers. Indirect branches, out-of-range branches, fallthrough outside the supplied range and jumps into instruction interiors remain unresolved rather than being silently treated as safe exits. Seven tests exercise guarded reachability, a back edge restoring reachability, unknown exits, call-return assumptions and invalid branch boundaries. Actual exporter regeneration is byte-identical.

Three focused function decompilations covering the worker, registration and notification processing completed their requested ranges and are pinned. They aid navigation and do not add runtime or complete program coverage. The native transport/ASIO sources and reviewed runtime dependencies are unchanged; their prior physical or software results are not reassigned by this static check.

The cutoff is still unresolved outside this conditional path. Later state, dispatch, readiness/library results, definition replacement, primary-device admission and current 5.0.0 integration remain independent questions. No binary, XML, account, identity, driver, registration or security predicate was changed. No vendor execution, USB acquisition, audio, UAC or firmware operation ran.

[Machine-checked evidence](evidence/serato-historical-support-consumer-20261101.json). See also the [retained SL3 factory/API](serato256-sl3-api-path.md), [local caller comparison](serato-cutoff-caller.md) and [current Serato integration boundary](current-serato-integration-decision.md).
