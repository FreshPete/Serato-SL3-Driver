# Startup-only SL3 interoperability shim

The attended one- and two-deck tests used a private investigation script with many observational hooks. The required application change in that script was narrower: Serato's installer panel had zero device identity fields after the genuine SL3 arrival and Download Driver click. Supplying the actual arrival identity allowed the normal local installer completion to select the SL3 and open the rebuilt ASIO driver. [Selection route](serato-archive-deployment.md) · [Two-deck result](evidence/phase-two-deck-session-20261105.json)

An original startup-only script and offline preparer now expose that part of the working recipe as reviewable source. This extracted version is not live-validated. It does not replace the complete session supervisor, installation transaction or recovery workflow, and it is not a permanent driver release.

## Scope and guards

`scripts/serato-sl3-startup-shim.js` installs three guarded application hooks:

1. Observe the scalar USB arrival message and retain the genuine SL3 identity `1cc5:0001`, revision zero. An unsupported later SL3 revision invalidates the saved identity and pending click.
2. Observe the actual Download Driver message from the known caller. Bind a single-use token to that UI thread and a five-second delivery interval.
3. Supply the observed identity only to the matching installer panel message when all three existing identity fields are zero. Existing identity values are preserved. A matching panel consumes the click even when its fields are already populated, and identity supply is allowed only once per process.

All three entry byte signatures must match before any application hook is installed. The launcher must independently verify the complete reviewed executable hash immediately before creating the process. The script is specific to the checked Windows x64 Serato 5.0.0.1278 build; no search for similar instructions or fallback version support is implemented.

The script also observes `DllGetClassObject`, factory creation and ASIO `start()` in the rebuilt DLL at the configured exact path. Factory and start method addresses must belong to that DLL. A successful start emits one completion event. It installs no buffer-switch or sample-reading hooks. The host must unload the script and detach the entire instrumentation session after that event, as the successful manual-only tests did.

The shim does not change the USB identity presented to Serato, account/product authorization results or application files on disk. The separate reviewed private descriptor and local installer bundle are still required. Serato's original executable remains unchanged.

## Offline preparation

The preparer reads the application without executing it, requires its exact reviewed SHA-256, checks x64 PE headers and all three entry signatures, and binds the template plus planned ASIO path into a prepared script. Existing output directories are refused. Outputs are restricted to a direct project-local `analysis/sl3-startup-shim-*` directory.

```powershell
# Read-only inspection. Use the exact planned DLL path from the deployment plan.
.venv/Scripts/python.exe scripts/prepare-serato-startup-shim.py `
  --app 'C:\Program Files\Serato\Serato DJ Pro\Serato DJ Pro.exe' `
  --asio-path 'C:\Program Files\SL3 Rebuild\phase-unmeasured-20261105\sl3_asio.dll'

# Produce a fresh private script and preparation manifest.
.venv/Scripts/python.exe scripts/prepare-serato-startup-shim.py `
  --app 'C:\Program Files\Serato\Serato DJ Pro\Serato DJ Pro.exe' `
  --asio-path 'C:\Program Files\SL3 Rebuild\phase-unmeasured-20261105\sl3_asio.dll' `
  --prepare analysis/sl3-startup-shim-YOUR-NAME
```

The preparation manifest explicitly leaves `liveShimValidated=false`. A configured DLL path is a binding input, not proof that a DLL is installed or verified. The host must reverify the application and exact staged DLL against the reviewed deployment package before launch. No original XML, archive, installer payload or resource codec material is emitted by this preparer.

## Validation and remaining work

Eight Node behavioral cases exercise entry mismatch before attachment, observed-device requirements, caller/thread/message/time guards, preservation of existing fields, single-use identity supply, invalidation by a new unsupported revision, refusal of a foreign factory vtable, and start-success-only notification. These tests mock the Frida boundary and do not attach to any process.

Four Python tests check path and guard inventories, read-only inspection, exact preparation hashes, no-overwrite behavior, and wrong-application/entry refusal before file creation. Actual offline preparation against the pinned installed application passed all three entry checks and produced a hash-bound script. [Sanitized evidence](evidence/startup-only-shim-20261105.json)

Run the software checks with:

```powershell
node tests/test_serato_startup_shim.cjs
.venv/Scripts/python.exe -m unittest discover -s tests -p test_serato_startup_preparation.py
```

The smaller shim has not yet been substituted into a live session. A reusable public launcher still needs the complete source-bound descriptor/installer preparation, protected staging, process ownership, bounded broker lifetime, full detach and verified rollback. Those responsibilities cannot be replaced by loading this script alone. The first live check must preserve the existing known-working package and distinguish this shim's validation from the separate [shutdown investigation](serato-shutdown-diagnostic.md).
