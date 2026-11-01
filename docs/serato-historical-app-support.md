# Historical declared-app match reaches the descriptor getter

The original SL3 declaration names `Serato DJ` in both 2.5.5.83 and 2.5.6.1001. A new original-byte check follows that declaration's match flag through the parser, descriptor copy constructor and getter. Under the **constructed default `AppConfig` path**, the declared app matches in both releases. This identifies an unchanged conditional name-match path; it does not demonstrate executed parser acceptance, device eligibility or connection.

## Checked path

The parser looks up `supported_apps`, iterates `app` entries and obtains the `value` attribute. It calls the application singleton accessor, takes its object's vtable slot `+0x98`, compares the declared string length with the returned string length, then calls the actual `VCRUNTIME140.dll!memcmp` import. A length or byte mismatch selects false. A match selects true; the accumulated low-byte flag stays true if any entry matches.

The accessor's default allocation installs a validated `AppConfig` vtable. Its slot `+0x98` names a leaf that builds the nine-byte string `Serato DJ`, using the checked `VCRUNTIME140.dll!memmove` import and a terminating zero. The construction path stores its object pointer into the same singleton reference returned by the accessor. The runtime contents of that reference, later table mutation/replacement and actual virtual dispatch have not been observed.

| Link | 2.5.5 | 2.5.6 |
| --- | --- | --- |
| Parser | `140356cd0` | `140357b40` |
| AppConfig accessor | `1402c4880` | `1402c56f0` |
| Constructed AppConfig table | `14475aac8` | `14496eaf8` |
| Name getter at slot `+0x98` | `1402c7d60` | `1402c8bd0` |
| Temporary descriptor base / support byte, relative to RBP | `+0x700` / `+0xbd8` | `+0x720` / `+0xc10` |
| Resulting complete-object support offset | `+0x4d8` | `+0x4f0` |
| Copy constructor | `1400f0230` | `1400f0c40` |
| Final ControllerDescriptor interface table | `1447420d0` | `144956120` |
| Support getter at slot `+0x20` | `1400e9810` | `1400ea220` |

The parser stores the accumulated byte into its temporary descriptor and passes that descriptor base to the append helper. Its direct copy path calls the checked constructor, which copies the byte at the corresponding complete-object offset. The final table installed at object `+0x10` has validated `ControllerDescriptor` RTTI with receiver offset `+0x10`. Its slot `+0x20` reads receiver-relative `+0x4c8` or `+0x4e0`, respectively—exactly the complete-object byte above after accounting for that receiver adjustment.

The constructor temporarily installs another base-class table earlier. The verifier checks the later `ControllerDescriptor` table installation rather than attributing a construction-phase table to the final getter. The support getter is an eight-byte leaf without its own unwind range; its exact bytes and validated table slot provide its boundary/type evidence. A displacement-only search limited to unwind functions would miss it.

## Scope and consequence

The [exporter](../scripts/export-serato-historical-app-support.py) independently revalidates both pinned original images and the recovered SL3 XML, then checks the literals, selected parser/accumulation/copy instructions, singleton reference, both CRT imports, locator signatures/self-RVAs/types/receiver offsets, final vtable slots and exact leaf bytes. It records a **conditional static match**, with runtime observation and admission explicitly false. Actual regeneration is byte-identical. No native runtime inputs changed and no physical or native-build pass is inferred from these checks.

This removes the unsupported assumption that 2.5.6 simply renamed the default application string away from the retained SL3 declaration on this path. It does not exclude later filtering, descriptor replacement, another AppConfig instance, changed callees/state or different runtime dispatch. The complete consumer path deciding whether to connect remains unfinished. This historical Boolean is also not the current 5.0.0 application's `supported_apps` map value or its discontinued-state enum; the layouts and mechanisms must not be conflated.

The remaining integration requirements still include genuine current Serato descriptor/handshake admission, transport lifetime across ordinary host activity, measured audio timing, physical analogue validation and two-deck DVS. No XML, executable, account, identity or support predicate was changed. No vendor code, hardware acquisition, audio, UAC, installation, registration, firmware or security-policy operation ran.

[Machine-checked evidence](evidence/serato-historical-app-support-20261101.json). See the preceding [local caller comparison](serato-cutoff-caller.md), [complete resource inventory](serato-cutoff-registration.md) and [current application boundary](current-serato-integration-decision.md).
