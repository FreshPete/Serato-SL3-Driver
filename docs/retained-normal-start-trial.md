# Retaining the SL3 USB connection across ASIO opens

On 7 November 2026, two independent ASIO host processes each opened the rebuilt driver, streamed for three seconds at 44.1 kHz, and closed. Both used the same background controller and native worker. The first completed 1,031 callbacks and the second 1,032. Each host reported successful buffer release and confirmed that the driver could unload. The worker journal recorded one successful USB acquisition and one release, after both clients had finished. Output was silent. [Compact evidence](evidence/retained-normal-start-trial-20261107.json).

## Installed attempt and private proof

The temporary setup installed a diagnostic ASIO locator and a locally generated SL3 profile for the original Serato 5.0 executable. The worker started 7.418 seconds after Windows recorded the SL3 reconnect. It reached USB redirection and stalled before clock access. The controller published no locator and could not verify immediate worker exit or USB release. Once the worker was observed gone, restoration returned Serato's resource archive to its original hash and removed the temporary driver registration and stage. This attempt had no new USB trace. The timing overlaps the ten-second interval in the earlier port trace, which gives a reason to test a later first open. [Earlier release trace](attended-native-stream-release.md).

After another power cycle, Windows canceled the administrator prompt for the installed retry before setup began. The subsequent private proof used the same driver, controller and worker binaries with a private locator and registration-free COM activation. It began several minutes after the reconnect, so this trial cannot establish a minimum wait. At the end, the controller verified I/O retirement, device release and worker exit. The private locator was withdrawn, and the controller exited.

## Next Serato check

The setup scripts offer an explicit `--retained-broker` mode for the bounded 44.1 kHz, 128-frame diagnostic bundle. This mode requires the idle locator check before setup or restoration. It uses the existing external controller for the USB connection. The default setup path continues to require the on-demand bundle.

The next attended test needs a fresh SL3 recovery and temporary protected setup. Bring up the retained connection, then open the original Serato 5.0 executable normally and check whether it selects the SL3 and starts the rebuilt ASIO driver. Keep playback stopped for startup observation and close Serato before retiring the controller and restoring the installation. Normal Serato startup, automatic background startup and USB reacquisition after release remain open.
