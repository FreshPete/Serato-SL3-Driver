# Retaining the SL3 USB connection across ASIO opens

On 7 November 2026, two independent ASIO host processes each opened the rebuilt driver, streamed for three seconds at 44.1 kHz, and closed. Both used the same background controller and native worker. The first completed 1,031 callbacks and the second 1,032. Each host reported successful buffer release and confirmed that the driver could unload. The worker journal recorded one successful USB acquisition and one release, after both clients had finished. Output was silent. [Compact evidence](evidence/retained-normal-start-trial-20261107.json).

## Installed attempt and private proof

The temporary setup installed a diagnostic ASIO locator and a locally generated SL3 profile for the original Serato 5.0 executable. The worker started 7.418 seconds after Windows recorded the SL3 reconnect. It reached USB redirection and stalled before clock access. The controller published no locator and could not verify immediate worker exit or USB release. Once the worker was observed gone, restoration returned Serato's resource archive to its original hash and removed the temporary driver registration and stage. This attempt had no new USB trace. The timing overlaps the ten-second interval in the earlier port trace, which gives a reason to test a later first open. [Earlier release trace](attended-native-stream-release.md).

After another power cycle, Windows canceled the administrator prompt for the installed retry before setup began. The subsequent private proof used the same driver, controller and worker binaries with a private locator and registration-free COM activation. It began several minutes after the reconnect, so this trial cannot establish a minimum wait. At the end, the controller verified I/O retirement, device release and worker exit. The private locator was withdrawn, and the controller exited.

## Next Serato check

The setup scripts offer an explicit `--retained-broker` mode for the bounded 44.1 kHz, 128-frame diagnostic bundle. This mode requires the idle locator check before setup or restoration. It uses the existing external controller for the USB connection. The default setup path continues to require the on-demand bundle.

The next attended test needs a fresh SL3 recovery and temporary protected setup. Bring up the retained connection, then open the original Serato 5.0 executable normally and check whether it selects the SL3 and starts the rebuilt ASIO driver. Keep playback stopped for startup observation and close Serato before retiring the controller and restoring the installation. Normal Serato startup, automatic background startup and USB reacquisition after release remain open.

Use the refreshed retained comparison described in the [package handoff](asio-on-demand-deployment.md#application-bound-candidate). Its setup manifest pins the current helper sources and the same locator bundle as this trial.

### Observe the normal launch

With the reviewed retained package installed and the broker ready, start the [read-only module observer](../scripts/observe-asio-module-load.ps1) in 64-bit PowerShell under the ordinary desktop account. Open Serato from its usual shortcut after the observer reports that it is armed. The observer samples Windows process and module metadata without attaching to the desktop, launching Serato or setting trace environment variables.

```powershell
$app = Join-Path $env:ProgramFiles 'Serato\Serato DJ Pro\Serato DJ Pro.exe'
$dll = Join-Path $env:ProgramFiles 'SL3 Rebuild\on-demand-diagnostic-v2\sl3_asio.dll'
./scripts/observe-asio-module-load.ps1 -Application $app -Module $dll `
  -ApplicationSha256 66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265 `
  -ModuleSha256 38031e1750120deff2357db3a22623b2a6d3c7ab2b1f4501925056071d25bb36 `
  -TimeoutSeconds 45
```

A populated `modulePathObserved` records the exact installed DLL path in the sampled Serato process. The observer checks process creation time around the module query and checks the application and DLL files against their reviewed hashes before and after the observation. This samples a path reported by Windows. It does not hash mapped memory, observe ASIO calls or establish callbacks. If the field is empty, the sampling could have missed a short-lived load. Pair the result with Serato's visible hardware status and the retained broker's records. If the DLL loads but the audio outcome is unclear, the [existing private control-call trace](asio-control-observation.md) can distinguish initialization and start in a separate launch.

Five ordinary-user Windows checks passed. The observer detected a loaded system DLL in a new PowerShell fixture, distinguished the same DLL filename and bytes at a different path, ignored a pre-existing process, refused a wrong hash before arming, and sampled the actual Serato installation while Serato was closed. The read-only retained setup plan confirmed original Serato resources and absent temporary driver registration. The observer SHA-256 was `37112dd7dc325d4deb7be713fb83dcde9bf86b20dcb3856316c74a810ffb3a0b`. No normal Serato launch or new hardware test ran.
