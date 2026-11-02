# Current Serato clock, alignment and handshake contract

The original SL3 descriptor cannot be copied unchanged into the current
application as a complete integration. Its `HANDSHAKE_TYPE_DRIVER_API` name
is absent from the recovered current handshake map. The current parser leaves
an unmatched name at its default zero, `HANDSHAKE_TYPE_NONE`. Substituting that
default or another device's handshake does not implement the original SL3
connection behavior.

The current application also converts requested latency into an aligned frame
count. That count is distinct from an ASIO driver's advertised bank size.
These findings refine the [original descriptor comparison](serato-legacy-sl3-descriptor.md)
and [audio routing](serato-audio-routing.md); no native bank/rate rules,
application files, account state or driver configuration changed.

## Verified input identities

| Input | SHA256 |
| --- | --- |
| Current Windows Serato 5.0.0.1278 | `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265` |
| Historical Windows Serato 2.5.5.83 | `ba8641d0329fe0c955147d2b45f247eeea82ac0f812fe30a339834dbe0c0a503` |
| Original x64 Rane ASIO 1.3.5f2 | `e3d88039547b70915b1a9bc9e3e3f7dba32aaa9bc3ce8fd51616565ea1734141` |

All addresses are preferred image VAs. Static parsing/decompilation was used;
none of these binaries was executed or loaded as code for this work. No
physical control, rate change or PCM transfer occurred.

## Observed handshake-map difference

Historical initializer `0x140353040` copies the actual
`HANDSHAKE_TYPE_DRIVER_API` string from `0x14476DEB8` at instruction
`0x140353381`, and associates integer **5** at `0x1403533AA`.

Current initializer `0x1405C1750`, called by `0x14020C300`, populates the
map used by the current descriptor parser at global `0x143EBEA98`:

| Name suffix after `HANDSHAKE_TYPE_` | Current integer |
| --- | --- |
| NONE | 0 |
| SERATO_DJ | 1 |
| NUMARK | 2 |
| VESTAX | 3 |
| NOVATION | 4 |
| AKAI | 5 |
| SERATO_DJ_HID | 6 |
| ATC_HID_PIR | 7 |

The complete recovered initializer has no DRIVER_API entry, and that literal
is absent from this current PE. Numeric 5 now means AKAI in this map. Enum
integers are therefore not portable between these binaries.

Current parser `0x1405C7F90` zeroes EDI at `0x1405C8365`, writes that default
to descriptor +0x154 at `0x1405C84E8`, reads the `handshake_type` attribute,
and looks it up in the map above. It overwrites +0x154 only on a found entry
at `0x1405C8550`. **With that map unchanged**, the original DRIVER_API name
would retain zero. This is a static consequence, not an executed descriptor
injection or a successful runtime connection.

The broader product/account/support and device-readiness requirements remain
independent. This finding neither identifies all current handshake engine
implementations nor excludes later runtime map changes. It specifically rules
out assuming that the original XML name or raw numeric kind recreates the
historical driver-API path through this map. No fallback, substituted kind,
account check or handshake predicate was patched or exercised.

## Observed rate and latency fields

The current full parser retains these complete-object fields:

| Field | Offset | Meaning established here |
| --- | --- | --- |
| `sample_rate` | +0x400 | Mapped integer rate/preference, zero default |
| `buffer_alignments` | +0x408 | Rate-keyed alignment vectors |
| Legacy audio flag | +0x35C | Enables alignment branch in the getter |
| `latency_overhead` | +0x438 | Boolean, defaults true |

The descriptor's audio interface starts at complete-object +0x10. Its vtable
`0x14281CAF0` slot +0xA0 is leaf `0x1405C7180`, which returns an optional
double for integer rates 44,100, 48,000 or 96,000; zero/unknown returns an
absent optional. Current SL3's identity-only stub is still predicted to leave
the rate at zero unless another component fills it. The SL3 transport itself
is only established for 44.1/48 kHz; the generic getter's 96 kHz case adds no
SL3 hardware capability.

Connection setup `0x141379A70` queries the optional rate at `0x141379C87`.
After selecting a connection, it uses that preference when present; otherwise
it asks the connection's current-rate getter at slot +0x28. It then calls the
descriptor's alignment getter at slot +0xA8 (`0x1405C6670`). At checked call
`0x141379E51`, RCX is the descriptor interface, XMM1 carries latency in
milliseconds, and XMM2 carries rate in Hz. Ghidra drops arguments from that
indirect call; the assembly preserves both floating-point inputs.

The getter computes, for normal positive inputs:

```text
adjusted_ms = latency_ms + (latency_ms < 5 and latency_overhead ? 1 : 0)
frames = trunc(adjusted_ms / 1000 * rate_hz + 0.5)
```

On the legacy branch it queries the rate's alignment vector through
`0x1405C6540`, tests divisibility, and rounds up when needed using the
alignment reached by that loop. The final result is capped at 4,096. For the
original SL3's single declared alignment 48, this reduces to rounding up to
a multiple of 48. The rate lookup has a generic fallback alignment path;
that is not used to invent a missing SL3 profile.

The following are arithmetic examples, assuming 48 kHz, the legacy branch,
default overhead true, a single alignment 48 and no earlier device-latency
adjustment:

| Input latency | After overhead | Computed aligned frames |
| --- | --- | --- |
| 1 ms | 2 ms | 96 |
| 2 ms | 3 ms | 144 |
| 4 ms | 5 ms | 240 |
| 5 ms | 5 ms | 240 |
| 10 ms | 10 ms | 480 |

These are not measured latency, observed host requests or device-clock results.
Setup can first adjust latency through helper `0x141377D50`, which consults
connection latency. The original descriptor's 48 kHz profile also does not
prove a successful rate setter or explain the last physical 44.1 kHz readback.

## Observed original ASIO bank reporting

The original Rane COM/IASIO table at `0x1801B8CE8` points its buffer-size slot
+0x58 to `0x180010080`. It obtains a configured value through helpers,
then stores **the same frame count** into minimum, maximum and preferred
outputs. It reports granularity 1 and success. This is verified at
`0x1800100D9` through `0x1800100E5`; the helper is not a constant
power-of-two bank chooser.

That establishes the original API contract, not the configured bank value
on this machine. Serato's application buffer and the ASIO host bank can be
separate layers. The retained backend's adaptation between them must be
traced or tested before changing the rebuild's current bank-size rules.
No arbitrary profile was installed or treated as measured timing.

## Implementation consequence and next work

The current rebuild's observed-rate-only ASIO behavior remains explicit:
there is no physical rate setter and no verified native timing profile. The
next control work is to trace the legitimate historical driver-API handshake
and rate-setting sequence, then supply their necessary behavior through the
new transport/integration. The 48 kHz preference alone does not authorize
replaying unrelated startup commands.

For application compatibility, resolve the PortAudio application-buffer versus
ASIO-bank adaptation, and identify a usable current descriptor/connection
extension boundary. Preserve the original SL3 identity and legitimate product
requirements. USB admission, PCM correctness, physical stereo mapping,
analogue scaling, latency and two-deck DVS still need separate validation.

## Reproduction

Run `.venv/Scripts/python.exe scripts/export-serato-clock-handshake-evidence.py`.
It checks all three original image hashes, map labels/integer stores, parser
defaults/destinations, rate leaf/table slots, floating-point call arguments,
arithmetic constants/instructions and original ASIO output stores. It also
pins the focused reports to their exact image and unwind ranges. The rate
leaf has an explicit checked extent because it has no PE unwind entry.

The [bounded evidence](evidence/serato500-clock-handshake-contract.json)
contains assembly, report hashes and clearly labeled synthetic arithmetic
examples. It does not claim complete control-flow recovery or runtime success.

The [original driver-timer exchange and native control codec](native-control-frames.md)
are now recovered/implemented separately. The exchange requires a real device
reply; the codec supplies framing without fabricating or verifying that reply.

## Later scoped consumer tracing

[The current MIDI response path](serato-handshake-consumers.md) now has a checked
descriptor-to-processor chain, nonempty-vector construction gate and branches for
current kinds 1/2. A separate RTTI-bound HID callback compares 6, with fuller
incoming provenance still unexhausted. This does not establish a universal
dispatcher, historical driver-API restoration or an admitted SL3 handshake.
