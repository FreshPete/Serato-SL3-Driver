# ASIO shutdown through a posted window close

Two new Windows integration cases exercise the real unregistered ASIO fixture DLL over an authenticated broker and a separate simulated worker. A parent process posts `WM_CLOSE` to one hidden window in its exact owned client process. The client owns an STA message loop and performs stop, buffer disposal and final interface release on that thread after the window closes. No Serato, physical USB or desktop automation is involved.

The target is the remaining discrepancy between successful owner-observed Phase playback/close and the saved supervisor's forced-exit result. These tests narrow the driver investigation; they do not reproduce that Serato session or establish its cause. [Evidence](evidence/asio-window-close-20261106.json)

## Code-path review

`DriverFacade::stop` rejects callback-thread reentry and reports failure if callback or worker I/O retirement is incomplete. `BrokerSession::stop` closes callback admission before requesting worker stop, shares one deadline between broker control and callback retirement, and closes its data mapping only after retirement. The control deadline is capped at five seconds. Pipe cancellation has a separate bounded retirement check; an unsafe cancellation outcome fails the owning process rather than freeing active I/O state.

`AudioOwner` retains callback state, buffers and its module reference until the actual thread retires. `disposeBuffers` refuses an executing callback. A failed stop is not evidence that those resources can be freed. The review found no demonstrated unbounded wait in this normal broker-backed stop path; it does not exclude a Serato interaction, USB-stack stall, different shutdown path or operating-system behaviour.

## New integration cases

The test parent retains the process it created and enumerates only windows matching that process ID and the fixture's fixed class. It requires exactly one accepted close post. The window is created only after callbacks have begun; it remains hidden throughout. The child must exit normally within the fixture's existing fifteen-second process bound.

**Normal callback:** at least twelve real ASIO callbacks complete before the window exists. After the posted close ends the message loop, `stop` must return `ASE_OK`, retired buffers must dispose, and the final interface must release. The broker must report no failure and the simulated audit must contain one stream begin/end and one worker acquisition/release.

**Blocked callback:** the first callback waits on a fixture-owned event. After the close message, stop must return `ASE_HWMalfunction` after a bounded wait (asserted between four and 7.5 seconds). Buffer disposal must still be refused while that callback executes. The test then releases its own event; exactly that callback must finish on its retained planes, buffer disposal must succeed after retirement, and final interface release must detach without a broker failure. This is an intentional callback fault, not hardware recovery or a successful stop result.

The existing destructive-release case remains distinct: destroying an object with a blocked callback seals the broker and preserves failure. Its expected pipe-disconnect diagnostic must not be attributed to the new normal close case.

The targeted broker-ASIO test passed, then the full 71-case Release suite passed with these modes included in the existing target. The fixture executable and evidence changed; production driver source and the four prepared audio-package binaries did not. The refreshed native build manifest records the new test executable, and the prior manifest is retained separately. A subsequent read-only host check reported original resources clean and temporary registration/staging absent.

## What remains to measure in Serato

The diagnostic session already prepared for an attended test allows twenty seconds for application exit and can enable the DLL-owned control-call log while startup hooks detach. Leave Serato under manual control during playback, then close it before the viewing limit. Check the actual process exit and broker result alongside the owner's observation.

The next evidence should distinguish: no delivered close request, application still waiting before calling ASIO stop, an ASIO stop/disposal call that returns an error, an observed incomplete call, or a process that exits cleanly. Missing or zero-record ETL data cannot prove which path occurred. No firmware operation, signing-policy change or additional audio hardware is needed for that shutdown test.
