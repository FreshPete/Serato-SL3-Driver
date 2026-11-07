# Retaining the SL3 USB connection across ASIO opens

On 7 November 2026, two independent ASIO host processes each opened the rebuilt driver, streamed for three seconds at 44.1 kHz, and closed. Both used the same background controller and native worker. The first completed 1,031 callbacks and the second 1,032. Each host reported successful buffer release and confirmed that the driver could unload. The worker journal recorded one successful USB acquisition and one release, after both clients had finished. Output was silent. [Compact evidence](evidence/retained-normal-start-trial-20261107.json).

## Installed attempt and private proof

The temporary setup installed a diagnostic ASIO locator and a locally generated SL3 profile for the original Serato 5.0 executable. The worker started 7.418 seconds after Windows recorded the SL3 reconnect. It reached USB redirection and stalled before clock access. The controller published no locator and could not verify immediate worker exit or USB release. Once the worker was observed gone, restoration returned Serato's resource archive to its original hash and removed the temporary driver registration and stage. This attempt had no new USB trace. The timing overlaps the ten-second interval in the earlier port trace, which gives a reason to test a later first open. [Earlier release trace](attended-native-stream-release.md).

After another power cycle, Windows canceled the administrator prompt for the installed retry before setup began. The subsequent private proof used the same driver, controller and worker binaries with a private locator and registration-free COM activation. It began several minutes after the reconnect, so this trial cannot establish a minimum wait. At the end, the controller verified I/O retirement, device release and worker exit. The private locator was withdrawn, and the controller exited.

At the later retry, the owner confirmed a 30-second power cycle and the read-only port query reported the expected SL3 descriptor. The original Rane binding still reported Code 39. Windows canceled the administrator launch before setup began. The postcheck showed the original Serato archive and no temporary driver installed. This retry made no UsbDk acquisition and did not open Serato.

## Next Serato check

The setup scripts offer an explicit `--retained-broker` mode for the bounded 44.1 kHz, 128-frame diagnostic bundle. This mode checks that the locator is absent and that neither staged runtime image is in use before setup or restoration. It uses the existing external controller for the USB connection. The default setup path continues to require the on-demand bundle.

The next attended test needs a fresh SL3 recovery and temporary protected setup. Bring up the retained connection, then open the original Serato 5.0 executable normally and check whether it selects the SL3 and starts the rebuilt ASIO driver. Keep playback stopped for startup observation and close Serato before retiring the controller and restoring the installation. Normal Serato startup, automatic background startup and USB reacquisition after release remain open.

The current retained comparison uses the client-observation build described below. Its refreshed private setup and broker input are in `analysis/sl3-on-demand-test-retained-idle-guard-20261107`. The setup passed the read-only Plan and the controller parsed the matching 44.1 kHz/128-frame profile against the workspace images. The earlier locator bundle is the one used in the physical two-client proof above. [Refreshed experiment identities](evidence/on-demand-idle-guard-20261107.json)

### Observe the normal launch

Take a short [libusb identity snapshot](serato-usb-discovery.md#what-the-retained-usb-connection-exposes) before acquisition and again while the broker is ready. Use the existing ordinary-user `scripts/supervise-usb-identity.py --run --seconds 5 --result-directory <fresh-local-directory>` for each snapshot. This distinguishes successful USB ownership from whether Serato's library can still discover the SL3 in that state. Keep the broker in the same session for the manual launch.

Once temporary setup has succeeded and the attended recovery check permits acquisition, use the prepared `retained-launch.json` with `scripts/asio-diagnostic-session.py start`. Its reviewed controller path and hash, input, session and pointer identify one bounded acquisition. After closing Serato normally, use `stop` with the same controller, hash, session and pointer, omitting the input. Verify the broker result and then run the separately approved restoration.

With the reviewed retained package installed and the broker ready, start the [read-only module observer](../scripts/observe-asio-module-load.ps1) in 64-bit PowerShell under the ordinary desktop account. Open Serato from its usual shortcut after the observer reports that it is armed. The observer samples Windows process and module metadata without attaching to the desktop, launching Serato or setting trace environment variables.

```powershell
$app = Join-Path $env:ProgramFiles 'Serato\Serato DJ Pro\Serato DJ Pro.exe'
$dll = Join-Path $env:ProgramFiles 'SL3 Rebuild\on-demand-diagnostic-v2\sl3_asio.dll'
./scripts/observe-asio-module-load.ps1 -Application $app -Module $dll `
  -ApplicationSha256 66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265 `
  -ModuleSha256 9d41ddcc0de481cd966d6786b15e656a3dcc6e4d71191815e6431a4009a9be55 `
  -TimeoutSeconds 45
```

A populated `modulePathObserved` records the exact installed DLL path in the sampled Serato process. The observer checks process creation time around the module query and checks the application and DLL files against their reviewed hashes before and after the observation. This samples a path reported by Windows. It does not hash mapped memory, observe ASIO calls or establish callbacks. If the field is empty, the sampling could have missed a short-lived load. Pair the result with Serato's visible hardware status and the retained broker's records. If the DLL loads but the audio outcome is unclear, the [existing private control-call trace](asio-control-observation.md) can distinguish initialization and start in a separate launch.

### Read the completed broker result

After Serato closes and the same retained controller retires, compare `process.pid` and `process.creationFileTimeUtc` from the module observer with the rows under `clientObservations` in that controller's `result.json`. Keep creation time as a string and require both fields to match. A PID alone can be reused. A creation time of `"0"` means the broker could not read it and the row cannot identify the observed process.

| Matching observation | What the broker verified |
| --- | --- |
| `admissionReplySent: true` | The exact process passed the pipe challenge and the broker sent its session reply after the worker's clock check. |
| `streamStartReplies > 0` | The worker reported entering the requested stream and the broker completed the corresponding pipe write. |
| `detachAcknowledged: true` | The client acknowledged its terminal detach reply. The controller separately verifies worker retirement and release. |

A session reply can come from a short ASIO enumeration open. The count of stream-start replies distinguishes it from a request that starts the worker. These observations do not establish callbacks, audible output or DVS. The result holds up to 16 challenged connections, with an explicit truncation flag. An absent row or missing final result is inconclusive. The broker records no audio or account data and writes this evidence with its existing final report.

The simulated controller tests compare the exact process identity and the sequence of three ASIO opens, with zero, two and two stream-start replies. They also check an interrupted application, where the completed stream-start reply survives and the final detach remains unacknowledged. The physically tested prior package predates these report fields. [Build and evidence](evidence/retained-client-observation-20261107.json)

If Serato stays offline and the DLL is absent from the observation, the [USB dispatch analysis](serato-usb-subscription.md) identifies where to check next. The original arrival must reach the queue, the manager must be in the listener snapshot when the message is dispatched, and its handler must receive the message. Comparing arrival construction with subscription time alone cannot tell which step was missed.

Five earlier ordinary-user Windows checks passed. The observer detected a loaded system DLL in a new PowerShell fixture, distinguished the same DLL filename and bytes at a different path, ignored a pre-existing process, refused a wrong hash before arming, and sampled the actual Serato installation while Serato was closed. The observer SHA-256 was `37112dd7dc325d4deb7be713fb83dcde9bf86b20dcb3856316c74a810ffb3a0b`. The current comparison remains uninstalled and still needs an attended Serato launch and a physical acquisition.
