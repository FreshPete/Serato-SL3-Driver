# Current HID verifier: control sections and primary-device lookup

The current HID kind-6 branch constructs a dedicated `HidDeviceVerifier`, retains a connection and another shared object, and performs another numeric lookup in the existing primary-device manager. This is a concrete HID verification path, not a newly discovered generic-ASIO or external descriptor registration interface. No admitted SL3 connection or successful protocol result follows from these static checks.

Target: unchanged original/installed Windows Serato DJ Pro 5.0.0.1278, SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. The [instruction/resource evidence](evidence/serato500-hid-verifier.json) verifies 116 instructions, three RTTI tables, four complete small functions and four fresh focused decompilations. Device reports, keys, challenges and reply data are not exported.

## Two separate descriptor controls

The parser stores a control-section classification at complete descriptor `+0x314`. It queries `midi` and `hid` children of its stored parsed document root, rather than treating an absent `midi_direction` as a missing MIDI section. The checked branch gives:

| Root control sections | Stored classification | Current recognized resource-node projection |
| --- | ---: | ---: |
| MIDI only | 0 | 171 |
| HID only | 1 | 14 |
| Both | 2 | 11 |
| Neither | 3 | 1 |

The exporter checks all 229 member CRCs and projects 197 recognized descriptor nodes. Phase has a root HID section and is an `osa_device`; virtual audio has neither section and is a `native_pro_device`. These are structural projections through the checked parser branch, not observed runtime object state or connection predictions. The scan publishes section presence and hashes, without section contents.

Both unchanged historical SL3 XMLs (2.5.5 and 2.5.6) lack these root MIDI/HID sections. They use the separately documented historical DRIVER_API path. **Inference:** reusing that XML unchanged would not supply this current HID verifier's section/connection contract. That does not prove the absence of every other current engine or make a foreign device profile an appropriate substitute.

The HID callback `140546110`, bound to `HidManager` subobject +16, reads its incoming descriptor-shaped pointee's `+0x314`. Only values 1 and 2 continue at `140546604`; other values leave that initialization path. Full incoming descriptor provenance and all callers remain unexhausted, so this is not generalized into a universal connection rule.

## The preceding virtual check is now identified conditionally

Before the kind-6 comparison, the callback invokes the incoming object's +16 interface slot `+0x90`. For the separately RTTI-verified `ControllerDescriptor` implementation, this slot is complete leaf `1405c7f30`. It returns true only when complete-object byte `+0xd4` is nonzero and kind field `+0x20` equals 2.

The parser binds `+0xd4` to `has_hid`, default false with an additional parser-context gate, and kind 2 to `native_intro_device`. The application support/discontinued map is a different field. This leaf is therefore a descriptor capability/kind check under this concrete implementation, not by itself a newly found hardware-authentication or account-entitlement result.

When the virtual result is false, or manager byte `+0xc1` is nonzero, control reaches the kind-6 comparison at `140546ad1`. If the incoming descriptor's actual implementation differs, these concrete getter semantics cannot be assumed. Manager state, later mutation and actual virtual receivers remain unobserved.

## Verifier construction and the second descriptor lookup

The kind-6 branch passes the callback's preserved second argument to factory `140544620`. The factory allocates 120 bytes for a control block and contained object; its table `142810428` is RTTI-bound to `std::_Ref_count_obj2<HidDeviceVerifier>`. This allocation size is not asserted to be the verifier object's standalone size. Constructor `140628130` receives the object at allocation +16.

Checked stores retain the incoming connection at verifier `+0x20` and the second shared object at `+0x30`. Three complete four-byte getters read connection fields `+0x38`, `+0x3c` and `+0x40`. The constructor passes them as VID, PID and revision arguments to the previously verified [primary numeric lookup](serato-descriptor-precedence.md), `140505360`, and stores the returned descriptor at verifier `+0x40`. This is a separate lookup from the callback's incoming descriptor-shaped argument. Runtime equality, non-null lookup success and the actual chosen record are not established.

The callback later calls method `140628c30` on the stored verifier. That method checks its started byte `+0x1c`, sets it once, creates another object through `1406282f0`, stores it at `+0x48` and calls its virtual slot `+0x20`. The worker body, its messages, failure/success semantics and any physical HID traffic remain untraced. No protocol reply or device identity is fabricated.

## Consequence and reproduction

The new evidence adds required boundaries: root control sections, the separate `has_hid`/kind check, a connection-backed verifier and another existing primary descriptor selection. It supplies no arbitrary-ASIO primary-device route. Phase's accessory declaration does not supply the missing genuine SL3 primary-device contract or current two-deck DVS result. These conclusions remain separate from Windows transport/ASIO progress and the actual discontinued notification path.

Run `.venv/Scripts/python.exe scripts/export-serato-hid-verifier.py` with the pinned original inputs and ignored focused reports present. The four fresh unwind ranges are `140544620:140544787`, `140628130:1406282ea`, `140628c30:140628cd2` and `140505360:140505466`. The focused import used `-noanalysis`, `-readOnly` and disabled library loading; its successful log reports zero additional files and a discarded import. The temporary project is absent. Whole-program and indirect-call completeness are not claimed.

Export and byte-identical regeneration pass. Current native source/build pins remain unchanged; native tests were not rerun for this static-only checkpoint. No application, registry, driver, binding, trust, security, device or account change ran. Native/analogue audio and timing, stable reopening, protected deployment, genuine current SL3 admission and real two-deck DVS remain unfinished. The full Windows goal stays active and macOS remains deferred.
