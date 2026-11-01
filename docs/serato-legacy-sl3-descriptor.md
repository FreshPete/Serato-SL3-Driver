# Historical SL3 descriptor recovered from 2.5.5 and 2.5.6

Both historical Windows executables contain the same complete SL3 device
descriptor, byte for byte. Both also include its resource ID in the array
passed through their startup descriptor-parser loop. A simple deletion of
the descriptor at the 2.5.6 boundary is therefore ruled out. This establishes
retained data and a static registration path, not successful runtime support.

The recovered descriptor supplies concrete audio, handshake, deck and DVS
requirements missing from the current identity-only discontinued stub. It
extends the [current support contract](serato-supported-contract.md),
[DVS contract](serato-dvs-contract.md) and [resource-loading trace](serato-resource-loading.md).
No executable, archive, driver, registry or account state was changed or
executed for this recovery.

The subsequent [2.5.6 API-path inspection](serato256-sl3-api-path.md) also verifies a retained SL3 factory case, class constructor and seven-export loader in that original boundary release. Runtime eligibility and connection still remain unproved.

## Artifact identity and registration

| Item | 2.5.5.83 | 2.5.6.1001 |
| --- | --- | --- |
| Original EXE SHA256 | `ba8641d0329fe0c955147d2b45f247eeea82ac0f812fe30a339834dbe0c0a503` | `3b04472cd5597fd56266e1c2c86dc298431b0026001aefe4b43aa3b909ee35c5` |
| Descriptor resource ID | 203 | 207 |
| Embedded payload VA | `0x1420F47C0` | `0x142C5E930` |
| Resource reader | `0x14067FFF0` | `0x140681860` |
| Registration array | `0x1447D4810`, 156 entries | `0x1449E8DC0`, 157 entries |
| Array-producing function | `0x1402ABEA0` | `0x1402ACCE0` |
| Startup owner | `0x1402AFB50` | `0x1402B0990` |
| Descriptor parser | `0x140356CD0` | `0x140357B40` |

Both encrypted payloads are 2,968 bytes, SHA256
`66c4424b0f0e60a56bdce9cb973a30b1fcf77fcec96ccce639d317e9ef4b7a46`.
Both decoded resources have SHA256
`93e6539fcf6867f71b30528eb6e655d04c393d461c4905f0050a3b67de1e569c`.
The XML is 2,966 bytes followed by two zero bytes; its SHA256 is
`314e81ffb5d052e53280903d543107c8223e99ff1f4e200311a2b3d90e49154c`.

Resource IDs differ across releases. Comparing ID 203 in both would compare
the SL3 with an unrelated Pioneer descriptor. The verifier follows each
version's actual length/pointer tables and registration array.

The startup loops call the array-producing function and iterate those IDs
through the descriptor parser. Each parser reads its resource through the
function above before parsing XML. Array membership, table addressing,
function ranges and relevant direct calls are checked against machine code.
Runtime branch entry, connection success and any additional restrictions
remain unobserved.

## Observed descriptor contract

The following are values declared by the original descriptor, not measurements
or permission to change the physical device:

| Field | Declared value |
| --- | --- |
| Device class/name | `native_pro_device`, `Rane SL3` |
| VID / PID | `0x1CC5` / `0x0001` |
| Supported application entry | `Serato DJ` |
| USB requirement | `requires_usb=true` |
| Handshake | `HANDSHAKE_TYPE_DRIVER_API` |
| Windows audio | API `ASIO`, device-name selector `SL 3` |
| Mac audio | API `CoreAudio`, device-name selector `SL 3` |
| Sample-rate profile | `HZ48000` |
| Buffer alignment under that rate | `48` |
| Deck count | `3` |
| DVS capability | `DVS_DEVICE_YES` |
| Mixer/faders | `hardware_mixer=true`, `has_faders=false` |
| MIDI direction | `none` |
| Output calibration value | `-1.5` |
| Software through | `provides_software_through=true` |
| Talk-over | `provides_talk_over=false` |

The device-secret field is present and empty. This does not establish absence
of product, account, handshake or runtime requirements. The recovered
driver-API handshake and the separately recovered seven Rane exports must
be understood together. No field or wider check was altered.

The declared rate is distinct from the last physical getter result of
44,100 Hz. The original driver supports multiple rates, but these facts do not
show which setup step selected 48 kHz in a working Serato session. The rebuild's
current ASIO facade accepts only the observed rate and does not issue a rate
setter. Trace/implement the justified rate-control contract before claiming
equivalence to this profile. No rate change was sent during this investigation.

Likewise, `buffer_alignment=48` is not proof of a 48-frame ASIO bank request.
Its consumer and units must be traced before changing the facade's current
power-of-two bank sizes or synthesizing a production timing record.

## Observed logical endpoint order

Both endpoint collections use the same order and contain no explicit
`hw_src`/`hw_dest` override:

| Declared position | Mixer input | Mixer output |
| --- | --- | --- |
| First | `Deck3In` | `Deck3Out` |
| Second | `Deck1In` | `Deck1Out` |
| Third | `Deck2In` | `Deck2Out` |

The record-source map assigns CH1 to Deck1In, CH2 to Deck2In, CH3 to Deck3In,
and VIDEO_MIX to Deck3In. This narrows the logical mapping required for two
decks. It does not establish physical jack order, stereo index units or
analogue routing on the rebuilt transport. Preserve the captured six-channel
PCM order and verify the consumer/physical mapping before selecting channels.

The DVS input-calibration field is absent from this descriptor. The previously
recovered current parser supplies its own zero default, and its decoder maps
that through a software gain formula. Do not treat an absent historical field
as a measured gain or move that software gain into USB sample transport.

Other declared software mixer controls disable microphone gain, cue gain/mix,
crossfader/upfader curves, master cue, split cue and crossfader reverse. The
cue-crossfader type is `PER_CHANNEL_CUE`; braking uses the software start/stop
variant. These declarations describe application behavior, not hardware
commands discovered by this recovery.

Driver detection names the existing Windows `SOFTWARE\ASIO\Rane SL 3` key and
the historical Mac `/Library/Extensions/SL3.10.9.kext` path. A present key or
file still does not prove an admitted driver or working audio. Installer names
are historical references; they do not justify another installation attempt.

## Recovery method and limits

The earlier Qt resource callback was traced as a separate path. Its three
decoded bundles contain UI resources; they are not the source of this SL3
descriptor. Device registration instead reads integer-indexed embedded
payloads using a Blowfish-compatible ECB decoder and a fixed key supplied by
the application. An original Python reader reproduces that operation from
the pinned local PE, without loading its code or exporting the key.

The cipher implementation passes three independent published vectors in both
directions for each executable, using each image's independently hash-checked
initial constants. The vectors come from the
[Blowfish test vectors published by its designer](https://www.schneier.com/wp-content/uploads/2015/12/vectors-2.txt).
Successful decoding, exact identities and valid XML provide additional checks.
Full vendor XML and decoded bundles remain in ignored local analysis only;
the committed report projects the interoperability fields and their hashes.

Run `.venv/Scripts/python.exe scripts/export-serato-legacy-descriptors.py` to
reproduce the [comparison evidence](evidence/serato-legacy-sl3-descriptors.json).
It rejects changed input executables, table/call/range mismatches, missing
registration membership, changed constants, invalid block lengths, malformed
XML/termination and an unexpected device identity. It performs no installation,
application execution, device operation or product/account modification.

## Consequence for the rebuild

The next current-Serato integration must account for an audio-only descriptor
with USB/driver-API connection behavior, DVS/deck setup and the correct logical
endpoint order. A generic ASIO driver or a support-dialog edit alone does not
supply those requirements. Current descriptor insertion, duplicate identity
precedence, handshake/control adaptation, sample-rate selection and physical
two-deck DVS remain open.

The historical comparison is also narrower than an operational compatibility
claim: retained descriptor/registration/API code does not prove that 2.5.6
opens or streams on this host, nor does it override the official support
boundary. Determine any remaining runtime differences from evidence.

Further static tracing now establishes the [current handshake-map difference
and rate/alignment consumers](serato-clock-handshake.md). The current map lacks
the original DRIVER_API name; application alignment is a frame count separate
from ASIO bank reporting. This adds concrete adaptation requirements without
changing the original descriptor or executing a fallback path.
