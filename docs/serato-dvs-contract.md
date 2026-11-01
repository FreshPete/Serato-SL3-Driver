# Current Serato: DVS capability, software gain and endpoint requirements

The current binary retains a DVS descriptor/manager/decoder path, but a working
ASIO stream alone does not enter it. The discontinued SL3 stub also lacks the
capability/deck/endpoint setup required by that path. This extends the previously
recovered [support contract](serato-supported-contract.md) and
[audio selector](serato-audio-routing.md); it does not establish a usable
external descriptor override or a completed current-Serato integration.

Target is original Windows x64 Serato DJ Pro 5.0.0.1278, SHA256
`66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`.
The installed application's hash still matches. Addresses are preferred image
VAs. All new findings are static; Serato, its account state and installed files
were not changed or executed during this investigation.

## Observed descriptor fields and DVS enum

Parser `0x1405C7F90` reads these keys into the complete descriptor object. Its
receiver/zero-register and destination instructions are checked against the PE:

| Key | Complete-object offset | Recovered interpretation |
| --- | --- | --- |
| `dvs_device` | +0x464 | Integer capability enum, default zero if absent/unmatched |
| `dvs_only_device` | +0x468 | Separate Boolean, default false |
| `dvs_input_calibration_gain` | +0x318 | Double parsed from text, default zero |
| `num_decks` | +0x46C | Integer deck count, default zero |

Global-map initializer `0x1405C27D0`, called by static initializer
`0x14020C3C0`, associates the following inline string bytes and integers. These
strings are copied into C++ strings rather than referenced by ordinary string
pointers, which explains the initial absence of direct string-pointer xrefs.

| Serialized name | Integer |
| --- | --- |
| `DVS_DEVICE_NO` | 0 |
| `DVS_DEVICE_YES` | 1 |
| `DVS_DEVICE_HYBRID` | 2 |
| `DVS_DEVICE_REQUIRES_AUTH` | 3 |

The parser queries this map at global `0x143EBEAD8` and writes the matching
node's integer into +0x464. The enum is not a channel count, an OS driver-status
value or the earlier per-application support value.

## Observed manager predicate

RTTI validates `CDVSPluginManager` at primary vtable `0x1431C4488`, with another
interface at complete-object +0x40. Constructor `0x142142330` installs those
tables and initializes a descriptor pointer at +0x90. Its message handler at
vtable +0x18 is `0x142142760`.

Predicate `0x1421426F0` reads that descriptor's +0x464 field. The checked machine
code, including the shared state getter, yields this local result:

| Input | Predicate result |
| --- | --- |
| Null descriptor or kind 0/unknown | False |
| Kind 1 | True |
| Kind 2 | Manager state byte +0xCC |
| Kind 3 | Manager state byte +0xCC AND byte +0x98 |

The machine code calls/tail-calls getter `0x14154A570` with manager +0xA0; that
getter reads its own +0x2C byte, giving manager +0xCC. Ghidra inlines this into
a direct +0xCC access. Update wrapper `0x1421426B0` calls the predicate and
passes its result to the existing state-update helper.

These are conditions within this manager, not proof that kind 1 bypasses all
application support, product/account, connection or deck setup. The exact
sources/meanings of the two manager state bytes are not fully recovered. They
must remain part of the legitimate integration contract. No enum, predicate,
state bit or account/product check was patched.

## Interpretation for the discontinued SL3 stub

The previously verified allocation zeroes the 0x740-byte complete descriptor
before construction. The identity-only SL3 helper fills names, VID/PID and its
discontinued application map, without supplying the supported-device audio/DVS
configuration. Thus kind zero is the predicted default unless another component
changes it. **If** this unchanged stub reached the predicate above, it would
not enable DVS. The current discontinued branch can prevent it reaching this
manager at all; this is not a runtime observation of that predicate on SL3.

Consequently, suppressing the dialog or changing application support alone is
insufficient. Changing just DVS kind would likewise not establish audio routing,
deck count, endpoint mapping, device controls or physical DVS operation. The
rebuild needs a genuine SL3 capability/connection integration, preserving its
identity and legitimate product/account requirements. There is still no
validated external injection/configuration mechanism for those descriptors.

## Observed software calibration path

Creation helper `0x142186AD0` creates a DVS input object through
`0x1421999F0`, obtains the current descriptor and forwards its +0x318 double
as a float to setter `0x14219ABB0`. RTTI independently validates
`CDVSDecoderInput` at vtable `0x1431CCA28`. The creation/forwarding path and
setter are checked in both focused reports and machine code.

The setter reads float constants 10, 4 and 20 and calls a thunk resolving to
`api-ms-win-crt-math-l1-1-0.dll!powf`. It stores the resulting float bits
atomically in the decoder's +0x3124 field:

`multiplier = powf(10, (float(descriptor_gain) + 4) / 20)`

For nominal descriptor gain zero, this is approximately **1.584893**, not zero
and not unity. This is software decoder calibration, not a recovered USB gain
write or measured SL3 analogue gain. A separate message-driven consumer also
forwards calibration changes to decoder inputs. Required physical calibration
values and their effect on timecode quality remain untested.

The transport should continue delivering unscaled signed 24-bit samples rather
than inventing an extra normalization to compensate for this formula. Successful
physical capture and DVS calibration must validate the complete gain chain.

## Observed endpoint schema; remaining mapping work

The same descriptor parser retains these separate containers:

| Key | Endpoint collection | Endpoint-to-hardware-index map |
| --- | --- | --- |
| `output_endpoints` | +0x4C8 | +0x6C8 |
| `input_endpoint` (singular) | +0x4E0 | +0x6B8 |

Output entries use `mixer_out` and optional `hw_dest`; input entries use
`mixer_in` and optional `hw_src`. Explicit hardware values can replace the
sequential defaults. Retained vocabulary includes `Deck1In`, `Deck2In`,
`USBInsertOut1` and `USBInsertOut2`. The audio subsection also parses
`audio_deck_setup_type` into +0x5C4; retained names include
`AUDIO_DECK_SETUP_RANE`.

These observations do **not** identify which physical SL3 sockets correspond to
the six logical driver channels, whether each hardware index denotes a mono
channel or stereo group at every consumer, or the exact decoder/deck assignment.
Those consumer paths and physical mapping tests remain necessary. No guessed
deck map was installed merely because the names are present.

The later [input-map consumer trace](serato-endpoint-consumers.md) resolves one of these units: the current mixer expands each `hw_src` into mono channels `2*h` and `2*h+1`. The historical SL3 order therefore predicts logical pairs Deck3=0, Deck1=1 and Deck2=2 if parsed with those defaults. Physical sockets, output expansion and actual decoder/deck attachment remain unverified; no descriptor was installed.

The subsequent [output graph trace](serato-output-routing.md) independently resolves the output pair units and graph destination direction: `hw_dest` selects `GraphOutNode` ports `2*h` and `2*h+1`. Current output enum keys differ from input keys. Final backend conversion, physical playback and a legitimate current-device connection remain outstanding.

## Sources, reproduction and next work

Run `.venv/Scripts/python.exe scripts/export-serato-dvs-contract-evidence.py`.
It verifies the original/installed PE identity, unwind boundaries, focused-report
identities/ranges, RTTI, parser destinations, enum stores, gain constants and
the actual imported math function. It exports bounded evidence to
[serato500-dvs-contract.json](evidence/serato500-dvs-contract.json). Retained
focused reports remain under ignored `analysis/`. No native implementation
changed, so this checkpoint adds analysis verification rather than repeating
unrelated native tests.

Official guidance checked on 27 October 2026 still describes DVS in terms of
supported hardware, and identifies SL3's last recommended software configuration
as Serato DJ Pro 2.5.5 with Windows 10/macOS Catalina. That is a statement of
vendor support, not proof that a rebuild cannot work. It also does not establish
that registering an arbitrary ASIO device supplies a DVS route.
[Serato DVS hardware guidance](https://support.serato.com/hc/en-us/articles/203401184-Does-my-mixer-controller-interface-support-DVS-in-Serato-DJ-Pro),
[discontinued-hardware configurations](https://support.serato.com/hc/en-us/articles/4411117032975-Serato-software-operating-system-compatibility-for-discontinued-hardware).

Next application work is to recover the descriptor-loading/override boundary and
endpoint/deck consumers, then implement the smallest legitimate integration
those interfaces support. Native physical driver admission, traced capture and
duplex/timing/recovery validation remain independent prerequisites. Two-deck
DVS calibration/playback/reverse/scratch/pitch and sustained current-Serato
operation remain unverified. The Windows-first and macOS workstreams stay in
the full rebuild goal.
