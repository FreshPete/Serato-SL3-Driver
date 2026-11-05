# Why driver detection alone does not reconnect the SL3

The checked original Serato 5.0.0.1278 startup branch selects case 6 both for the installed generic SL3 provider and for the same provider with only slot `+0x90` changed to true. Therefore changing that flag alone does not provide a different startup action in this branch. It is not a justified shortcut to automatic SL3 selection.

The new [execution-free inspector](../scripts/inspect-serato-startup-driver-cases.py) decodes and interprets the complete bounded decision block at `1421daef0:1421daf41` from the hash-pinned original executable. It enumerates all sixteen Boolean combinations of the four prior virtual results. Each path must reach the checked end with a selected case and pending flag; unsupported instructions, off-boundary branches and excessive execution are refused. No vendor instruction executes. [Complete branch table](evidence/serato-startup-driver-cases-20261105.json)

| Local inputs | Selected case |
| --- | --- |
| Generic provider, detection absent: all four false | 7 |
| Generic provider, detection present: `+0x50/+0x48/+0x58` true, `+0x90` false | 6 |
| Detection present, only `+0x90` changed: all four true | 6 |
| Detection absent, only `+0x90` changed | 5 |

The preceding [driver-detection analysis](serato-archive-deployment.md#driver-detection-after-installer-completion) separately ties case 6 to the existing `0x52` notice route and cases 3–5 to installer identity notifications. An observed empty-detection-field experiment already reached the case-6 notification route without named ASIO selection. Combining these facts narrows the next approach: a real installed driver needs a genuine connection/selection handoff, not merely an existing registration key or a capability Boolean override.

This is a local control-flow conclusion. It does not identify the complete semantics of slot `+0x90`, prove every upstream path, or establish that another event cannot select the device. No virtual method, product identity, entitlement state, installed resource, registry entry or executable was changed.

The working temporary route obtains the handoff through actual installer completion and the genuine SL3 descriptor. Before changing startup, the prepared attended manual-close test should establish whether the smaller shim and new shutdown diagnostics work. A future installed-driver reconnection experiment must verify the selected driver and live broker first, preserve the real registered descriptor and normal authorization checks, and report actual ASIO start. A permanent route has not been implemented or validated by this branch inspection.

Reproduce against the unchanged installed executable:

```powershell
.venv/Scripts/python.exe -I -B scripts/inspect-serato-startup-driver-cases.py `
  --application 'C:\Program Files\Serato\Serato DJ Pro\Serato DJ Pro.exe'
```
