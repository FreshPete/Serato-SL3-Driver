# LicenseController binding for USB readiness messages

Message 0x692 is bound to a Boolean property owned by the RTTI-identified `serato::dj::LicenseController`. One checked update routine computes its value as the OR of two controller bytes. The adjacent property uses message 0x693, already seen carrying the authorization-service result. This identifies application state behind the USB helper; it does not identify SL3 clock lock, successful USB streaming or an admitted audio/DVS session. [Checked original-byte evidence](evidence/serato500-license-state-binding.json).

Target remains the original/installed Windows 5.0.0.1278 executable, SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. No account/license state was queried, code or message injected, service response fabricated, or application/device operation run.

## Property construction

Constructor `141538c70` installs RTTI-bound LicenseController tables `142f518a8` (complete offset zero) and `142f518d8` (offset +0x40). The checked initialization creates these Boolean message/property bindings:

| Message | Complete controller property | Checked initial value |
| --- | --- | --- |
| 0x692 | +0xc8 | false |
| 0x693 | +0x100 | false |

The constructor binds message 0x692 at `141538f04:141538f21` and 0x693 at `141538f46:141538f5e`. Factory `14154abf0` receives the message ID and Boolean, constructs the scalar message through `14185ec00`, calls the bound interface's +0x40, then builds the property handle. Message ID is carried into property metadata +0x18. Complete move helper `141549ff0:14154a047` transfers that metadata and value into the destination property. This is construction/binding; it does not prove initial notification delivery.

The exporter proves preservation of the relevant nonvolatile constructor registers on selected straight-line intervals, rather than assuming a decompiler's receiver type or retained register value. It separately verifies both controller vtable stores and complete-object locators.

## Checked update and notification routes

Updater `14153b280` checks controller bytes +0x288 and +0x289 and produces zero only when both are zero. It passes that Boolean to setter `14154bf30` on property +0xc8, with secondary numeric value zero. The constructor initializes the combined flag word to zero. No semantic names are assigned to those two bytes: their values and all input producers remain unexhausted.

One setter, `14153b500`, changes +0x288 only when its incoming byte differs, then calls the updater. The LicenseController handler `14153b470` has a selected message-0x694 branch which obtains the incoming low byte through message virtual +0x10 and forwards it to complete leaf `14153b5a0`. That leaf changes +0x289 only on difference and tail-calls the updater. This establishes one update route for each flag; it does not establish the upstream meaning or live value of every input.

The same handler's message-0x693 branch sends its low byte to property +0x100, then separately reaches the authorization service's +0xa8 method. That service call's full semantics and result are not inferred from the slot or type name. [The actual service receiver](serato-authorization-service.md) remains distinct from DriverAPI.

The generic Boolean-property setter `14154bf30` requires three non-null bindings. If its cached Boolean and secondary numeric value are both unchanged, it returns without notification. Otherwise it stores the new values, uses the bound metadata and calls interface virtual +0x60. These are conditional application-memory/message operations. No direct device I/O, actual message-delivery timing, eventual consumer state or audio readiness is established by this selected route.

## Consequence for the SL3 experiment

The [USB-arrival helper](serato-usb-arrival.md) reads complete CUSBAudioManager bytes +0x70 and +0x71, updated by messages 0x692 and 0x693 under its checked handler. This new source-side binding explains why their OR cannot be treated as a measured sample-clock/ASIO result. Two different OR operations exist: LicenseController combines its two flags into the 0x692 property; the USB helper later combines two stored message bytes.

A real current SL3 test must allow the original service/state path to operate and separately observe actual device/audio behavior. The NONE descriptor hypothesis does not supply an arbitrary true state, and a replacement Rane control DLL is not an identified substitute for these message properties. This work changes no flag, message, entitlement, key, token, product identity or licensing policy. It does not establish that any particular license purchase would admit SL3.

Current resource trust/parsing/selection, complete control/service behavior, measured ASIO deployment/timing, reliable reopening, physical mapping/levels and actual current two-deck DVS remain required. The reviewed [archive-test package](serato-archive-deployment.md) is still undeployed; its protected install/rollback and application results are unverified. Mac stays deferred.

## Verification

```powershell
.venv/Scripts/python.exe scripts/export-serato-license-state-binding.py
# Optional fresh output; existing evidence is refused before analysis.
.venv/Scripts/python.exe scripts/export-serato-license-state-binding.py --output analysis/license-binding-NAME.json
```

Seventy-six new instruction facts, 208 prior arrival checks, two RTTI tables, two constructor-register preservation intervals, two complete decoded leaves and a property-metadata prefix verify against original bytes. Seven fresh focused functions complete: six exact unwind ranges and the independently bounded move leaf. The isolated unchanged imports disable whole-program analysis/library loading; both logs confirm zero additional files and discarded read-only import, and both projects are empty afterward. Whole-program and licensing-semantic completeness are not claimed.

The report repeats identically after console newline normalization. Existing-output refusal preserves it. Private focused output/navigation and exact source/report hashes are preserved; public evidence contains selected interoperability facts and hashes rather than full vendor pseudocode or authentication material. Native audio/build inputs are unchanged, so no new native or physical test is claimed. No app/archive, driver/binding/trust/security, firmware or account change ran.
