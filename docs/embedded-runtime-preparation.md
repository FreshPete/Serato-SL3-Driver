# Private Python runtime for the launcher candidate

The packaging candidate now has an application-local Python runtime. The same reusable launcher passed two session Plans using it, and the complete wrapper passed two read-only Plans with all runtime files bound. No global Python installation, PATH, registry, Serato resource, device binding or hardware state was changed. This is preparation and software validation, not a live Serato result. [Evidence](evidence/embedded-runtime-preparation-20261106.json)

## Inputs and isolation

The staged runtime uses the official Python 3.15.2 Windows x64 embedded ZIP. Its SHA-256 matches the value published on the [Python release page](https://www.python.org/downloads/release/python-3152/), and Windows reports valid Python Software Foundation Authenticode signatures for the extracted interpreter and core DLL. The existing working development interpreter was left unchanged. Python documents this distribution as application-local and recommends supplying required third-party packages alongside it. [Embedding documentation](https://docs.python.org/3.13/using/windows.html#the-embeddable-package)

`scripts/prepare-embedded-python.py` reads an explicitly hash-bound ZIP and three local wheel RECORD files. It verifies recorded SHA-256 values and sizes for pefile, Capstone and Frida, preserves their notices/metadata, excludes bytecode caches, and refuses traversal, duplicate archive entries, links and out-of-scope dependency names. It stages only under a fresh `artifacts/build/embedded-python-*` directory and never executes the interpreter during preparation.

The generated `_pth` configuration admits only the embedded standard-library ZIP, runtime directory and bundled packages directory. Site initialization remains disabled. The actual child smoke test reported isolated mode, site disabled and every module search path inside the private runtime. All three required modules imported. The staged payload contains 129 files, approximately 205 MB uncompressed; most of the size comes from Frida. Generated/runtime binaries remain private, not committed release downloads.

## Runtime integrity before execution

The reusable-launcher builder accepts an explicit embedded-runtime directory and reviewed manifest hash when run under that interpreter. The resulting release pins all 129 runtime files plus their manifest, in addition to the interpreter, application, capsule and eighteen project-source hashes. These file leases are held before helper dispatch. A copied runtime passed the compiled launcher's Plan without a host Python installation path. Changing its helper module or standard-library ZIP caused refusal before Python started; a module containing a test execution marker never ran.

The complete session-plan builder includes the full private-runtime inventory. The PowerShell wrapper now pins these files **before** its first Python verification child, rather than after it. A complete Plan using a copied runtime passed; changing the copied module was then rejected by the wrapper before the Python verifier could import it. Ordinary non-embedded plans retain their existing explicit runtime bindings. Previously prepared full plans are stale after this wrapper/preparer change and must be regenerated.

## Actual checks and limits

Five preparer/refusal tests pass under both the development and private interpreter. Under the private interpreter, five pointer checks, thirteen supervisor checks and twenty-two session checks pass; four resource-transaction checks also pass. The compiled reusable launcher passed its ten Plan/refusal cases. Real Frida environment tests used owned Python children and verified normal exit/job retirement. Five copied-runtime/tamper checks passed, including both the compiled launcher and complete wrapper. Two fresh complete private-runtime Plans passed with the same native diagnostic package and shared installer payload.

No actual Serato process or SL3 was opened for these checks. The native audio binaries and earlier physical evidence are unchanged. The next attended candidate test still needs real installer-child environment propagation, ASIO start, full detach, manual exit before expiry and complete rollback.

PowerShell 7 and the reusable launcher's .NET 10 runtime remain external prerequisites, and the checkout/session data still need conversion into a relocatable release kit. This step removes the candidate's need to use the machine's development Python installation; it does not yet provide a complete end-user installer, remove Download Driver, validate a second PC or certify long-session/physical-output behaviour.
