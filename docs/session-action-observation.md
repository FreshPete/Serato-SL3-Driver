# Opt-in action observation in a supervised session

The passive Download Driver receiver probe can now be prepared in the same script as the startup-only interoperability shim. This removes their competing arrival hooks and lets the existing supervisor retain the diagnostic fields. It still requires the genuine user click and normal installer approvals. No automatic callback invocation was added. [Evidence](evidence/session-action-observation-20261106.json)

## Combined preparation

`prepare-serato-startup-shim.py --observe-download-action` enables the diagnostic explicitly. Ordinary preparation leaves it off. The manifest binds the Boolean, exact generated script and the observer/inspector/image-reader source hashes. Opt-in preparation also performs the original-image RTTI and receiver checks. The supervisor reconstructs the selected script and checks those source bindings rather than trusting an arbitrary prepared script.

The observer first verifies its four original entries and exposes a deferred activation API. The startup shim verifies its three entries before activating it. There are six unique application entries because arrival is shared. A bad entry in either component prevents every attachment. With observation enabled, three observer hooks and three ordinary startup hooks are installed; the existing arrival hook publishes the observation to both consumers. The standalone observer remains available separately.

The observer has no vendor-callback invocation API. The original click-caller, thread, identity and interval checks still control the panel correction. Neither an arrival nor successful observation supplies a click token. All hooks in the combined script belong to the same instrumentation session, so the existing unload/detach after observed ASIO start also removes the passive startup probes.

## Retained evidence

Previously the supervisor retained event names and timestamps only. It now retains an `actionObservation` object for the six declared passive event types. Exact fields, Boolean constants, ordinal sequence and bounded controller/thread/message values are checked; extra fields or malformed values fail startup and run the existing cleanup path. This prevents a raw pointer or arbitrary object from entering these diagnostic records.

The 128-event observer limit and the supervisor's existing queue/event bounds remain in force. Contiguous ordinals cover the observed prefix before detachment; they do not prove a complete application lifetime. Observer faults are retained as explicit diagnostic events. Controller ordinals correlate addresses and do not establish object lifetime or permission to call a retained pointer.

## Verification and limits

* Ten combined/default JavaScript boundary cases passed, including both guard groups failing before any hook, exactly one arrival hook, preserved manual-click requirement and the existing identity/start guards.
* Nine standalone observer boundary cases passed.
* Five preparation and sixteen supervisor regressions passed, including the existing owned-process shutdown fixtures.
* Three payload tests passed with typed-field, unknown-field, bound and sequence-gap checks; simulated supervision retained the fields and ran cleanup on refusal.
* Eight fresh-session preparation cases preserved the opt-in prepared shim. Nineteen copied-kit checks passed with an empty PATH and explicitly verified that normal kit preparation leaves the probe off.
* Eight native argument round trips passed. Actual offline opt-in/default preparation and both complete-plan checks passed against the original installed image. A final read-only check reported original resources clean and temporary staging/registration absent.

The refreshed native release pins 49 source/license/evidence files and both complete private runtimes; full plans pin 37 sources. The new installer resource and private kit are bound to that release. Native audio binaries are unchanged. No Serato process, UAC prompt, broker or device open ran in this checkpoint. The combined live probe, callback readiness/thread observations, automatic action delivery and clean post-playback Serato shutdown remain unverified or unfinished.

The private opt-in preparation is `analysis/sl3-startup-shim-action-observed-20261106`; the default-off comparison is `analysis/sl3-startup-shim-action-default-20261106`. A fresh opt-in complete session can be derived from `analysis/sl3-session-capsule-20261106-account-rebind-a/session-plan-action-observed.json`; ordinary kit preparation remains the default-off route. These are private test artifacts, not a public installable release.

```powershell
artifacts/build/embedded-python-3152-20261106/python.exe -I -B scripts/prepare-serato-startup-shim.py --app 'C:\Program Files\Serato\Serato DJ Pro\Serato DJ Pro.exe' --asio-path 'C:\Program Files\SL3 Rebuild\phase-unmeasured-20261105\sl3_asio.dll' --observe-download-action
```

This command inspects without launching. For the next attended observation, leave playback stopped, use the normal click/approval route and let the supervisor detach before any manual Phase use. The routine playback/shutdown comparison can keep this optional observation off.
