# Ordinary-user on-demand broker activation

**Follow-up:** the [ASIO activation entry](asio-activation-entry.md) now connects this component to a validated stable record and lazy driver/session creation. The initial component checkpoint below remains separate; no installed Serato/SL3 test is inferred from the new software path.

The initial native `BrokerActivation` component starts and owns the existing audio controller without a session launcher or Windows service. Its simulated integration test obtains a broker-backed configuration, initializes the real ASIO facade and performs two callback-stream start/stop cycles. At that checkpoint it was not connected to production ASIO creation. The existing installed setup and attended-test kit still do not invoke the new activation mode.

## Activation and identity

The caller supplies an explicitly reviewed controller image/hash, a private-worker input configuration/hash, a fresh output path, timing policy, expected worker kind and bounded startup/lifetime limits. Input loading retains the existing worker, helper and timing-file checks and read-only leases. A broker input cannot recursively activate another broker. Current paths must be absolute local fixed-drive paths without traversal or reparse components; output must be fresh.

The component requires a non-elevated token. The existing controller/pipe performs its further ordinary-user, integrity, logon/session and client admission checks. The controller is started with the existing exact-image `Process` owner: suspended creation, private kill-on-close job assignment before resume, no inherited handles and no shell or elevation. Startup creates no global locator, registry entry, service, scheduled task or process watcher. The existing controller receives only its fixed run/input/output/lifetime options and, for a bound keepalive profile, the existing explicit keepalive option.

After the controller's readiness file appears, the normal configuration loader validates its immutable configuration and broker record. The returned process reference must match the exact retained owned controller process, and worker/helper/profile bindings must match the retained input. A readiness filename alone is not trusted as hardware success. The later ASIO/broker greeting still checks the expected native/simulated kind and worker identity. The fixture uses the explicit simulated kind; this adds no simulation switch to the production DLL or controller.

## Lifetime

`configuration()` returns a configuration carrying a shared activation lease. Closing the activation while that lease survives defers retirement and sends no stop request. An invalid close-grace request cannot bypass this protection. Configuration copies share the lease; dropping the last one can retire the activation even when the original caller has already released its own reference.

After all configuration leases retire, close signals only the bound controller's existing private stop event and waits for both exact process exit and an empty owned job. A normal close is repeatable. Startup failure and close error preserve the owned process/job boundary; containment never uses a process name or recycled PID. Graceful close is bounded to fifteen seconds plus a separate two-second containment wait. Forced containment and cleanup errors remain distinct observations; controller exit by itself is not independent proof of physical USB release. The controller's own typed retirement record remains necessary.

Failed startup throws `BrokerActivationError` carrying cleanup observations, including whether containment was forced. Its explicit cleanup grace defaults to five seconds and cannot exceed fifteen seconds. These observations remain available even though no activation object was returned.

The existing diagnostic timing limits remain intact: unmeasured mode cannot request a lifetime over ten minutes. No timing measurement is fabricated to obtain a longer session. This component does not establish long-session readiness or replace that remaining measurement/reliability work.

## Software validation

The owned native fixture tests wrong input/controller hashes, occupied output, an excessive diagnostic lifetime and an owned child that deliberately misses readiness but then exits normally. Positive cases use the separately compiled simulated controller and worker, the existing authenticated pipe and the actual ASIO facade. One case streams through two start/stop cycles, disposes buffers and detaches before activation close. A second case drops the original activation reference while retaining its configuration, then verifies retirement on final lease release. Both controller records report successful simulated worker I/O/device retirement, process exit and empty jobs without forced termination; neither loaded the USB helper or acquired native hardware.

Another failed-startup child is intentionally terminated before its delayed operation; its typed error must show forced containment and an empty job, rather than normal shutdown. This negative case is separate from the two clean simulated audio owners.

The dedicated runner pins source/image hashes, preserves fixture and controller results, bounds the fixture process, and checks both actual retirement records. CTest includes this case when the explicit diagnostic build option is enabled. No Serato, UAC, device, firmware or Windows policy change runs in this test.

The final Release build passed all 72 CTest checks, including this new case and the existing audio, broker, COM and callback-retirement tests. Its source/image pins and simulated retirement results are in the [checkpoint evidence](evidence/broker-activation-20261106.json). A post-test read-only recovery check found original resources and temporary registration clean; no matching test/controller/worker or Serato process remained. This does not establish the earlier real Serato shutdown result.

## Remaining integration

The [stable activation record and lazy ASIO factory/scope integration](asio-activation-entry.md) are now implemented in source. Its unregistered software tests cover lazy ordinary initialization/reopen, failed initialization retained by a host and blocked-callback lifetime. Real native startup/reopen, process interruption and multiple native clients still need validation before installed-use claims. Serato must still select the SL3 first: this component cannot cause an application to load a driver it has not selected. The [normal-start selection investigation](installed-startup-investigation.md) remains a separate dependency. Phase and vinyl remain sources for the same audio path.
