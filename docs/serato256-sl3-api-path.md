# SL3 driver API retained at the 2.5.6 cutoff

The later [complete startup-resource inventory](serato-cutoff-registration.md) checks every listed XML in both versions and finds exactly one scalar SL3 identity per array, with unchanged XML. A checked Rane-specific product-range body does not select PID 1. Those findings narrow particular cutoff hypotheses without proving runtime eligibility or a current application integration route.

The original Windows Serato DJ Pro 2.5.6.1001 executable retains an SL3-specific driver-interface factory case, constructor, virtual table and seven-export loader. The [earlier descriptor recovery](serato-legacy-sl3-descriptor.md) already established that its full SL3 resource and startup registration array survived. Together these findings rule out simple deletion of the descriptor or all SL3 API code as the cutoff mechanism. They do not establish that an eligible device reaches this path or connects successfully.

Serato's [discontinued-hardware announcement](https://the-drop.serato.com/announcements/important-information-about-discontinued-hardware/) explicitly excludes SL boxes starting with 2.5.6, and its [SL3 hardware page](https://serato.com/dj/hardware/rane-sl3) still identifies 2.5.5/Windows 10 as the supported configuration. Retained code is compatible with deliberate runtime exclusion; it is not evidence overriding those support statements.

The [offline exporter](../scripts/export-serato256-sl3-api-path.py) checks the original executable SHA-256 `3b04472cd5597fd56266e1c2c86dc298431b0026001aefe4b43aa3b909ee35c5`, full boundary-aligned decoding of three unwind ranges, selected instructions, PE imports and MSVC RTTI. [Compact evidence](evidence/serato256-sl3-api-path.json). No vendor binary is loaded or executed.

| Link | Preferred image VA and observed behavior |
| --- | --- |
| Factory | `0x140681ae0`; selected case at `0x140683cc0` compares two descriptor getter results against preloaded DI/R12W. The recorded definitions are `0x1cc5` and `1`. Misses go to the next case. |
| Construction | The uncached matching branch requests `0xa8` bytes and calls constructor `0x140694100` at `0x140683d01`. The cached-object branch bypasses construction. |
| Class identity | Constructor installs vtable `0x1449cdff8`; its complete-object locator resolves the decorated `RaneSL3API` class, offset zero. |
| Loader | Constructor calls `0x14069d900`; the vtable's `+8` entry also names that function. |
| Module/API | Loader calls actual `LoadLibraryW` and `GetProcAddress` imports, retaining returned pointers in the SL3 object. The module filename comes from a runtime global wide string; its populated value was not observed. |
| Open result | After pointer checks, the selected success path calls member `+0x70` (`sl3_open`), stores its result at `+0x68`, and sets byte `+8` only on a nonzero result. |

The seven resolved names and members are:

| Export | Object member |
| --- | --- |
| `sl3_open` | `+0x70` |
| `sl3_close` | `+0x78` |
| `sl3_driver_timer` | `+0x80` |
| `sl3_get_usb_port_status` | `+0x88` |
| `sl3_get_audio_controls` | `+0x90` |
| `sl3_set_audio_controls` | `+0x98` |
| `sl3_set_thrustate_callback` | `+0xa0` |

This checks selected static factory conditions, not every control-flow predecessor or actual register state. The code is not an external registration interface for the current application. Runtime factory entry, global path initialization, DLL loading, USB acquisition, application eligibility and DVS remain unverified. Current 5.0.0's missing DRIVER_API handshake mapping remains a separate finding; no original interface is copied, loaded, injected or substituted here.

Verification: the actual exporter passes and regenerates identical bytes. Its strict input hash and instruction/import/RTTI assertions fail on different binaries or mismatched links. No production native input changed, so native hardware/build results were not rerun or reassigned. The next application-side question is where 2.5.6 excludes connection eligibility despite retaining these components, rather than assuming that restoring an XML file or DLL name is enough.


The later [current named-loader/fallback comparison](serato-generic-driver-fallback.md) now checks that both historical executables retain these nine patterns while the pinned current executable lacks them. It also verifies the current generic base object and local keyed-state operations. This is not a current seven-export integration hook, successful connection or universal absence proof.
