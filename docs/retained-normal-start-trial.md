# Retaining the SL3 USB connection across ASIO opens

On 7 November 2026, two independent ASIO host processes each opened the rebuilt driver, streamed for three seconds at 44.1 kHz, and closed. Both used the same background controller and native worker. The first completed 1,031 callbacks and the second 1,032. Each host reported successful buffer release and confirmed that the driver could unload. The worker journal recorded one successful USB acquisition and one release, after both clients had finished. Output was silent. [Compact evidence](evidence/retained-normal-start-trial-20261107.json).

## Installed attempt and private proof

The temporary setup installed a diagnostic ASIO locator and a locally generated SL3 profile for the original Serato 5.0 executable. The worker started 7.418 seconds after Windows recorded the SL3 reconnect. It reached USB redirection and stalled before clock access. The controller published no locator and could not verify immediate worker exit or USB release. Once the worker was observed gone, restoration returned Serato's resource archive to its original hash and removed the temporary driver registration and stage. This attempt had no new USB trace. The timing overlaps the ten-second interval in the earlier port trace, which gives a reason to test a later first open. [Earlier release trace](attended-native-stream-release.md).

After another power cycle, Windows canceled the administrator prompt for the installed retry before setup began. The subsequent private proof used the same driver, controller and worker binaries with a private locator and registration-free COM activation. It began several minutes after the reconnect, so this trial cannot establish a minimum wait. At the end, the controller verified I/O retirement, device release and worker exit. The private locator was withdrawn, and the controller exited.

At the later retry, the owner confirmed a 30-second power cycle and the read-only port query reported the expected SL3 descriptor. The original Rane binding still reported Code 39. Windows canceled the administrator launch before setup began. The postcheck showed the original Serato archive and no temporary driver installed. This retry made no UsbDk acquisition and did not open Serato.

The subsequent handoff attempt added a baseline from Serato's installed libusb library. All four complete snapshots showed the same SL3 identity before acquisition. Windows canceled the handoff's administrator launch before setup began, and the read-only Plan again confirmed the original archive and no temporary driver. This records visibility before USB ownership. The comparison while the broker owns the SL3 still needs to run. [Handoff baseline](evidence/retained-normal-start-trial-20261107.json)

## Next Serato check

The setup scripts offer an explicit `--retained-broker` mode for the bounded 44.1 kHz, 128-frame diagnostic bundle. This mode checks that the locator is absent and that neither staged runtime image is in use before setup or restoration. It uses the existing external controller for the USB connection. The default setup path continues to require the on-demand bundle.

The next attended test needs a fresh SL3 recovery and temporary protected setup. Bring up the retained connection, then open the original Serato 5.0 executable normally and check whether it selects the SL3 and starts the rebuilt ASIO driver. Keep playback stopped for startup observation and close Serato before retiring the controller and restoring the installation. Normal Serato startup, automatic background startup and USB reacquisition after release remain open.

The current retained comparison uses the client-observation build described below. Its refreshed private setup and broker input are in `analysis/sl3-on-demand-test-retained-idle-guard-20261107`. The setup passed the read-only Plan and the controller parsed the matching 44.1 kHz/128-frame profile against the workspace images. The earlier locator bundle is the one used in the physical two-client proof above. [Refreshed experiment identities](evidence/on-demand-idle-guard-20261107.json)

### One approval for the attended comparison

The local **Approve temporary SL3 setup** shortcut starts the approval from the operator's own desktop. It calls `scripts/start-retained-setup.ps1 -Run`, which checks the pinned experiment, Python and handoff script before requesting one administrator launch. The default invocation is read-only. A canceled approval leaves setup untouched. A verified ready message means the exact launched process is still serving the temporary setup window. Leave Serato closed until the desktop runner and module observer are ready. [Launcher verification](evidence/retained-operator-launch-20261107.json)

`scripts/retained-setup-handoff.py` uses the exact retained experiment and its reviewed SHA-256. With the prepared Python runtime, the default action verifies the restored host without creating an output directory. The explicit `run` action requires an already approved administrator process. It runs the existing guarded setup, waits for the desktop session and then runs the existing guarded restore in the same elevated process. The helper does not launch Serato or the USB broker.

After a successful setup the handoff writes `attended-setup/window.json`. The window identifies the exact live handoff process, setup receipt and deadline. The handoff begins its idle check at the restore signal or after four minutes. It requires confirmation within two minutes that Serato and the broker have closed. It does not close either process. Verify the original setup in `restore-stdout.json` and the handoff's `result.json`.

The helper skips the viewing window if setup fails with a recognized partial state. It can restore that state using the same existing guards. Unknown outcomes and busy owners defer restoration, with records preserved for review. The handoff exits after this attempt and creates no scheduled task or service. Its decisions passed unit tests and a full round trip with isolated Windows staging, synthetic archive contents and private registry keys. The live elevated run remains pending. [Handoff verification](evidence/retained-setup-handoff-20261107.json)

### Observe the normal launch

The desktop runner can take both USB snapshots and start the retained broker once. Use the reviewed experiment and `retained-launch.json` hashes. Under the ordinary Windows account, `plan` checks the inputs, while `start --recovery-confirmed` requires the live setup window and a fresh complete snapshot that sees the SL3. Start it promptly after setup. It requires at least 170 seconds left when preparing and at least 135 seconds left when starting the two-minute broker. The report distinguishes SL3 visibility during the connection from an inconclusive snapshot. After normal Serato closure, `finish` retires the owned broker and signals restoration. The elevated handoff independently checks that the application, controller, worker and pointer are idle. The desktop runner never opens Serato or requests elevation. [Software verification](evidence/retained-desktop-trial-20261107.json)

```powershell
$desktopArgs = @('--experiment', $experiment, '--expected-experiment-sha256', $experimentSha,
                 '--expected-launch-sha256', $retainedLaunchSha)
& $python -I -B scripts/retained-desktop-trial.py start @desktopArgs --recovery-confirmed
# Arm the module observer, open Serato from its usual shortcut and close it normally.
& $python -I -B scripts/retained-desktop-trial.py finish @desktopArgs
```

If the broker becomes ready and a later step fails, the desktop runner attempts to retire that exact owner and then signals restoration. A failed acquisition is attempted once and retains its evidence. If the setup or cleanup outcome is uncertain, the existing administrator guards still determine whether restoration can run. The desktop runner writes its observations under `desktop-start`.

If the desktop runner is interrupted after broker publication, `finish` can use the existing ownership receipt even if `startup.json` is absent or incomplete. It waits for the desktop lifecycle lock and checks that Serato is closed before invoking the normal broker retirement checks. A Windows simulation ended the launcher at that boundary, then verified that `finish` withdrew the exact pointer, retired both owned processes and requested restoration. The observation following an interrupted startup has no earlier phase comparison. [Interruption evidence](evidence/retained-desktop-interruption-20261107.json)

After verified broker retirement, `finish` sends the restore signal immediately and then observes libusb for 15 seconds. The observation is independent of restoration. It records the observed retirement time and compares complete samples before acquisition, during ownership and after release using VID, PID, revision, bus and address. A phase with gaps or multiple identity sets gives an indeterminate comparison. An empty complete snapshot is an observation of absence. An observer error stays separate from the retirement result. The test performs one acquisition, and seeing the descriptor again establishes visibility only. The post-release observation has been checked with a live idle USB baseline and software cases. It still needs an attended broker release. [Comparison evidence](evidence/retained-release-identity-20261107.json)

For a manual run, use the following steps instead of the desktop runner.

Take a short [libusb identity snapshot](serato-usb-discovery.md#what-the-retained-usb-connection-exposes) before acquisition and again while the broker is ready. Use the existing ordinary-user `scripts/supervise-usb-identity.py --run --seconds 5 --result-directory <fresh-local-directory>` for each snapshot. This distinguishes successful USB ownership from whether Serato's library can still discover the SL3 in that state. Keep the broker in the same session for the manual launch.

Once temporary setup has succeeded and the attended recovery check permits acquisition, use the prepared `retained-launch.json` with `scripts/asio-diagnostic-session.py start`. Its reviewed controller path and hash, input, session and pointer identify one bounded acquisition. After closing Serato normally, use `stop` with the same controller, hash, session and pointer, omitting the input. Verify the broker result and then create the empty `attended-setup/restore.request` file for the active handoff.

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

For an offline readout, save the observer's stdout and keep the completed broker result from the same trial. Supply those two reviewed files and their SHA-256 hashes to `scripts/read-retained-start-result.py`. If available, supply `attended-setup/restore-stdout.json` and its hash with `--restore-report` and `--restore-report-sha256`. The readout keeps the matching process's admission, start and detach counts separate from the broker's worker-retirement flags and the restore receipt. It verifies the supplied file identities and joins both process identifiers. The operator still selects the records belonging to one trial.

```powershell
python scripts/read-retained-start-result.py `
  --module-report $moduleReport --module-report-sha256 $moduleReportSha `
  --broker-report $brokerReport --broker-report-sha256 $brokerReportSha
```

The readout matched an actual Windows module sample to three connections from one unregistered simulated ASIO host. It counted four stream-start replies and three detach acknowledgements, and kept the worker retirement result separate. The fixture did not launch Serato or open the SL3. [Readout verification](evidence/retained-start-readout-20261107.json)

The simulated controller tests compare the exact process identity and the sequence of three ASIO opens, with zero, two and two stream-start replies. They also check an interrupted application, where the completed stream-start reply survives and the final detach remains unacknowledged. The physically tested prior package predates these report fields. [Build and evidence](evidence/retained-client-observation-20261107.json)

If Serato stays offline and the DLL is absent from the observation, the [USB dispatch analysis](serato-usb-subscription.md) identifies where to check next. The original arrival must reach the queue, the manager must be in the listener snapshot when the message is dispatched, and its handler must receive the message. Comparing arrival construction with subscription time alone cannot tell which step was missed.

The [saved installer-assisted comparison](serato-primary-pointer.md#installer-assisted-selection-observed-in-serato-50) shows a separate primary-selection path reaching the rebuilt ASIO driver. If the normal launch does reach ASIO start, that is direct evidence for this test even without a USB manager event. If a delivery trace is needed, use the corrected handler check. The older probe cannot verify delivery.

Five earlier ordinary-user Windows checks passed. The observer detected a loaded system DLL in a new PowerShell fixture, distinguished the same DLL filename and bytes at a different path, ignored a pre-existing process, refused a wrong hash before arming, and sampled the actual Serato installation while Serato was closed. The observer SHA-256 was `37112dd7dc325d4deb7be713fb83dcde9bf86b20dcb3856316c74a810ffb3a0b`. The current comparison remains uninstalled and still needs an attended Serato launch and a physical acquisition.
