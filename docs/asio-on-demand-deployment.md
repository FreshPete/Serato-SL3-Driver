# Protected on-demand ASIO package

The [application-bound follow-up](#application-bound-candidate) adds a separate opt-in mode. The original per-session package remains the default.

The persistent-install route now has a separate, versioned native diagnostic package. Its ASIO entry, private worker configuration and timing record reference the same final protected installation directory. It does not depend on a prepublished session pointer. The [earlier configuration review](asio-activation-configuration-review.md) could only bind a writable engineering bundle; this package carries all three records for normal installer staging and owned removal.

This implements package construction and installer-library support, not the finished install-once experience. No production installation, SL3 acquisition or normal Serato startup has been performed through this package. A current Serato profile/admission route, native activation/reopen/shutdown tests, latency measurement and longer reliability tests remain required.

## Package contract

`prepare-asio-activation-deployment.py` converts a reviewed native diagnostic locator bundle only when it matches the exact current tested native build. It reuses the source-pin and lazy-ASIO lifecycle checks from the configuration preparer, and separately matches the native diagnostic DLL/controller identities. Native binaries, the unchanged reviewed UsbDk helper and licenses are preserved. The result is `sl3.deployment-bundle.v2` with `activationMode: asio-init-v1`; the existing locator package remains version 1.

The version-2 inventory is the fixed version-1 inventory plus `sl3-worker.conf` and `sl3-timing.conf`. The configuration binds all generated records and native binaries by hash. Verification regenerates the exact expected records from the protected destination; editing hashes in the manifest cannot legitimize a different executable, timing, mode or path. Only the explicit diagnostic timing is admitted: 44.1 kHz, 128 frames, unmeasured latency and a maximum ten-minute audio-owner lifetime. No measurement, signing approval or public-release readiness is inferred.

The deployment plan still uses the existing machine-registration schema and project CLSID. It records `activationTrigger: IASIO.init`, no service and no runtime session-pointer use. `automaticStart` means activation upon ASIO initialization, not login startup. The older `pointerPath` field is retained as installer/account-binding metadata; these audio records neither read nor write it. Each user's runtime directory is instead chosen by the native lazy-activation path. Removing this unused metadata field can be a later schema change; it is not a runtime dependency.

The installer file reader now selects one of two fixed inventories by validated manifest version/mode before opening payload names. When a stage receipt precedes its captured manifest, only either exact fixed set is admitted; arbitrary extra or traversal names are not accepted. Normal hash/identity/ACL checks then verify the captured manifest and payload. The existing copy journal, runtime direct-import admission, protected-stage receipt, registry ownership and cleanup primitives apply to the extra records. Neither public installer CLI exposes unattended machine mutation.

Rebinding regenerates the activation entry and private worker configuration for the destination while preserving native binaries and timing. The temporary Serato session capsule explicitly refuses on-demand plans: its independently launched broker and the new ASIO-owned broker must not both acquire the SL3. The existing temporary route continues to require a locator package.

## Preparation and verification

Use the local analysis Python with the existing PE-analysis dependency:

```text
python scripts/prepare-asio-activation-deployment.py --bundle ABSOLUTE_REVIEWED_LOCATOR_BUNDLE --expected-bundle-sha256 ORIGIN_SHA --native-build ABSOLUTE_BUILD_MANIFEST --expected-build-sha256 BUILD_SHA --output ABSOLUTE_NEW_BUNDLE_DIRECTORY
python scripts/prepare-asio-deployment.py --verify --bundle ABSOLUTE_NEW_BUNDLE_DIRECTORY --expected-bundle-sha256 NEW_BUNDLE_SHA
```

The output must be a fresh child under `artifacts/build/deployment-bundles`. Preparation writes only that review bundle, with the manifest published last. It does not install files at the protected destination, modify registration, load package code or open hardware. A trusted future installer must still coordinate application/profile changes, remove/repair ownership and verify actual normal-start behavior.

## Verification scope

The installer tests can now take an explicit test-package pointer, with the existing default retained. Expected stage/file counts and all copy/delete interruption boundaries derive from the fixed package inventory. Tests run as an ordinary user with workspace ACLs and fresh private HKCU subtrees; they preserve unrelated siblings and check that planned Program Files/user-pointer paths and live registrations remain unchanged. They do not register a class in the real COM/ASIO roots, load the packaged DLL or claim production protection/activation. Windows system DLL loading for direct-import admission remains part of the existing runtime checker.


## Verified checkpoint

All **21 contract checks and 261 isolated Windows installer/recovery checks passed**: staging 24, cleanup 26, installation 20, removal 20, interrupted-install recovery 41, partial-registration removal recovery 22, file recovery 37 and journaled-copy recovery 71. The additional configuration files participate in every copy/delete boundary, including preservation of foreign data and exact partial results. Interruption tests inject exceptions at journal boundaries and release their contexts; they do not demonstrate abrupt-process-crash recovery or physical device retirement.

Another **100 legacy checks** passed: preparation 26, diagnostic rebinding 10, staging 24, installation 20 and removal 20. The earlier 73-check native Release build was reused only after rechecking all its native source/build-script pins; these packaging changes did not require or claim a new native run. The [checkpoint evidence](evidence/asio-on-demand-deployment-20261106.json) binds current Python sources, each suite report, the final package identity and the precise temporary-session refusal reason.

A preliminary copy suite exceeded the wrapper's 180-second observation limit. Its result was not counted as a pass; its marked private registry branch was verified and removed, and fixture files were preserved. The complete final run used a 900-second per-suite limit and verified source hashes remained unchanged throughout. A legacy staging check also hit a shared-input file lock when run concurrently; its isolated rerun passed. Neither harness issue involved production registration, package execution or the SL3.

The final bundle is private engineering material under `artifacts/build/deployment-bundles/activation-deployment-78bb2eb631de46599c927f8327dd9b8b`, manifest SHA-256 `5a2114b125da044bb827e8efccd2b0d261ba0deedff09f19f58755df77400e6b`. It remains **uninstalled**. Read-only postchecks found original Serato resources, no occupied session paths and no temporary registration; no matching test/controller/worker or Serato process remained. Windows trust/security policy and firmware were unchanged.

## Application-bound candidate

Add `--application-bound` to the preparation command to select `asio-init-application-v2`. The package still uses the same fixed version 2 inventory and binds the same three record paths. The activation mode participates in the package identity, and the verifier regenerates the corresponding `SL3-ASIO-ACTIVATION-2` entry. Rebinding preserves the mode and all native images. A package with the other activation header and recomputed file hashes is refused.

Preparation runs the exact build's passive native configuration inspector on temporary records pointing at the workspace binaries. The inspector checks that the build can parse version 2 before the package is emitted. The package retains the 44.1 kHz, 128-frame, ten-minute diagnostic limit. Its controller [follows the application's lifetime](application-bound-broker.md#automatic-asio-activation) within that limit.

The no-shim Serato setup checks for held controller and worker images in the application-bound installation before changing the setup. This is an idle check at the start of the action. Existing archive and uninstall checks still verify actual ownership and final cleanup. The diagnostic package is prepared locally and remains uninstalled.

All 22 package checks, 261 isolated installer and recovery checks, 20 paired setup and restoration checks, and 13 read-only preparation checks passed. The paired tests held each runtime image in turn and verified that the guard preserved the staged files and registration. The earlier per-session bundle still verifies. [Test counts, scope and exact manifest hashes](evidence/application-bound-deployment-20261107.json).

Two separate setup manifests passed the read-only host plan. The prestarted retained broker comparison uses the earlier locator bundle to test Serato's normal selection path. The application-bound package tests automatic activation only when Serato actually requests ASIO. The retained comparison has a fresh source-bound manifest and a refreshed local probe. The live comparison still needs a fresh SL3 power cycle and an attended administrator approval for temporary setup.
