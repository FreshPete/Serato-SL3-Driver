# Retire the supervisor-owned manager before playback

The startup supervisor now owns a dedicated Frida device manager and closes it when startup instrumentation retires. Previously it obtained a device through the process-global manager and unloaded/detached only the script and session, leaving that manager open through the manual playback window. This is a resource-lifetime improvement; it does not establish the cause of the earlier Serato shutdown timeout. [Evidence](evidence/instrumentation-manager-retirement-20261106.json)

## Production behaviour

[WindowsProcess](../scripts/run-serato-startup-session.py) constructs its own manager. If device acquisition fails, it attempts manager cleanup and preserves the original error, including a cleanup note if needed. Retirement attempts script unload, session detach and manager close in order, retaining failures instead of claiming success. A successfully closed manager is not closed twice; the device reference is released.

The supervisor records `instrumentationManagerClosedBeforeViewing` immediately after startup detachment, with a matching flag on its detach event. Final process cleanup records `instrumentationManagerClosed`. Thus the next live trace can distinguish manager retirement before interaction from cleanup attempted only at the end. Process waiting and stop requests continue through retained Windows handles and the existing scoped stop channel.

## Validation without Serato or the SL3

- Seven focused tests cover retirement order/idempotence, failure handling and constructor cleanup.
- Sixteen supervisor regressions pass, including actual owned Windows process/job cleanup and the longer close grace.
- Six window-close selection and three action-payload checks pass.
- A bounded real candidate-SDK probe exercises the production manager method against an attached Python fixture. The fixture remains alive after retirement, then exits normally after its explicit stop. The source hash is recorded, and the job is empty without forced cleanup.
- Two real spawned-fixture environment cases confirm the manager closes while the resumed child is still alive. Both fixtures then exit normally; an enclosing job verifies retirement.
- Eight stop-channel cases pass with synthetic startup events and an owned headless Python target. The production manager is closed before the viewing phase, and the native stop entry still delivers the scoped request and permits normal fixture exit. No audio driver was loaded in this simulation.
- The passive single-process job fixture still passes with its mocked Frida boundary and explicit manager-retirement check.

The real-library fixture runs were bounded by outer jobs without breakaway. The stop-channel fixture uses a sixteen-process ceiling to include its known PowerShell/native/console helpers; the smaller probe uses four. These are test-local limits, not system-policy changes. These real-library fixtures retired without forced cleanup; separate supervisor regression cases intentionally exercise forced exit. No Serato process, device, UAC or audio test ran.

## Refreshed private kit

The production source change requires new launcher source pins, installer resource and complete plans. Those artifacts were rebuilt privately using the same 125-file integration SDK and unchanged native audio package:

| Artifact | SHA-256 |
| --- | --- |
| Native launcher | `bfd8d045e526f4f574d41890fda9a9443cf327f5a01cb0d62efbaeffd6bdd8d8` |
| Installer resource | `7360aabd17699f6f65ee3b5e7cd312ef6c827d26a70adc1fc4fa57bb78005a27` |
| Default complete plan | `1100616ecd4e47067d0f154693df14430c2b448fb16503075b9d6d9346db574d` |
| Optional-observer complete plan | `e5479c7e80047fc70ca52e81aa44fd9a7214edfbad53ddf2eda9537248762e68` |
| Kit manifest | `2bfd0e54705f50cda1fe4ab1ff43d6d906f4b4e58b0d80601832e8ec70b19361` |

The candidate is `artifacts/build/portable-serato-kit-manager-retirement-20261106`. Both complete native Plans and recovery checks pass. Eight fresh-session cases, ten copied-kit/relocation cases and eight native argument round trips pass. Earlier kits remain preserved as separate checkpoints; no binary artifact was uploaded to the public repository.

The post-check reports original installed resources and no temporary registration or occupied staging paths. No matching live session/helper process remains. Defender reported no detection events in the observed fixture window, with antivirus, real-time protection and behaviour monitoring enabled. The original stock-runtime hold remains intact.

## Next attended check

Use this refreshed default-off candidate for stopped-playback startup, manual Serato close and reopen. Inspect the new retirement flags and actual process/broker exit before testing Phase playback again. Clean shutdown of a Python fixture does not prove clean shutdown of Serato or resolve the earlier owner-report/log discrepancy.
