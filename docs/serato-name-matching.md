# Current Serato interface-name matcher

Static inspection of the unchanged Windows 5.0.0.1278 executable narrows the earlier interface-name branch in descriptor selection. This does not establish a discoverable descriptor provider or working SL3 integration.

Matcher `140b21c80` first passes its first string through `140b220c0`. That helper builds the literal expression `(\d+\s*-\s+)?(.+)`, obtains a match result and selects capture group 2. If matching fails, it copies the original input. This is consistent with removing a Windows instance prefix such as `2- ` while retaining the following device name. The required whitespace after the hyphen matters: a plain leading `2-` is not the same pattern. This interpretation comes from the expression and focused code, not an executed Serato trial.

The second string supplies the begin/end range to pattern construction `140b1c2c0`, with syntax argument 1. The normalized first string and compiled pattern then reach `140b1bc50`. It adds flag `0x10`, passes final boolean 1 to `140b1b170`, and the caller preserves the returned AL through cleanup into EAX. Focused decompilation incorrectly labels some wrappers as returning void; the actual return instructions resolve this ambiguity.

The local MSVC 14.29 regex header defines syntax 1 as ECMAScript and match flag `0x10` as `match_any`; its regex-match wrappers use a final true argument for full matching. The parser/helper layout is consistent with that library. This is a static interpretation, not exhaustive recovery of the engine, locale handling, malformed-pattern exceptions or all matching behavior. A substring comparison must not be substituted based only on the old descriptor's name.

At the already inspected descriptor wrapper `1405050b0`, this branch precedes numeric VID/PID/revision fallback and is conditional on a nonempty interface-name field. Real connection construction and provider availability still need tracing. Preserving the SL3's USB identity remains required; this finding does not justify changing VID/PID/revision or bypassing product/account checks.

Reproduce the bounded checks with `.venv/Scripts/python.exe scripts/export-serato-name-match.py`. The [evidence record](evidence/serato500-name-match.json) verifies original/installed application identity, actual unwind ranges, the literal bytes, call arguments and returned boolean. No vendor code was run, no application file was modified, and no audio or DVS operation was tested.
