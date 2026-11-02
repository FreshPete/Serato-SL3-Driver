# Stable ASIO location and explicit session pointer

The production ASIO provider now accepts a stable adjacent locator as an
alternative to the existing direct configuration. It resolves one explicit
pointer to an immutable broker configuration. There is no search, environment
expansion, recursion, automatic reconnect or private-worker fallback from a
locator. The controller has a separate metadata-only command to create a new
pointer. Nothing is installed by this checkpoint.

## Records

The stable DLL's adjacent `sl3-asio.conf` can contain this exact ordered format:

```text
SL3-ASIO-LOCATOR-1
session_pointer=C:\Users\you\AppData\Local\SL3\current-session.txt
broker=C:\SL3\reviewed\sl3_broker_controller.exe
broker_sha256=<64 lowercase hexadecimal characters>
worker_sha256=<64 lowercase hexadecimal characters>
```

The pointer contains:

```text
SL3-ASIO-SESSION-POINTER-1
configuration=C:\Users\you\AppData\Local\SL3\session-unique\sl3-asio.conf
configuration_sha256=<64 lowercase hexadecimal characters>
```

Both records require a final newline and strict field order. UTF-8 paths and
LF/CRLF line endings are supported. Unknown versions, BOMs, duplicate/extra
fields, relative paths, network/device paths and alternate data streams are
refused. Record size is bounded to 64 KiB. The loader now checks the resolved
handle path as well as the supplied path for all configuration/timing/file pins;
a local-looking path cannot resolve to a network location.

The pointer target must be the existing `SL3-ASIO-BROKER-CONFIG-1` format. Its
hash must match the pointer, its worker and broker hashes must match the stable
locator, and its broker image must be the same file identity (volume/file index)
as the locator's image. A byte-identical broker copy with a different file
identity is insufficient. The existing production loader still verifies the
worker/helper/timing/measurement pins and the session record's exact live broker
PID, process creation time, image identity and worker contract. Client admission
still requires a native worker and the existing pipe/process/token checks.

The locator and selected immutable records/files remain read-locked with
write/delete denied for the configuration lifetime. The mutable pointer is
locked while it is parsed and the target validated, then released. An existing
client retains its selected records and exact process reference: editing or
replacing the pointer cannot redirect it to a new session. A future object
resolves the current pointer again. A dead selected broker is an error, never
permission to reopen USB or launch a fallback worker.

These are consistency and identity checks. They do not attest a timing
measurement, authenticate arbitrary same-user code or make a writable test
directory an administrator-protected installation. A future installer must
protect the locator, DLL and pinned executable files while allowing the
appropriate user to publish their pointer in a separate directory.

## Explicit publication

After an explicitly started controller publishes a reviewed broker configuration:

```powershell
sl3_broker_controller.exe --publish-pointer --config "C:\path\session\sl3-asio.conf" --pointer "C:\path\existing-user-directory\current-session.txt"
```

This command runs as an ordinary non-elevated user. It validates and retains the
direct broker configuration, checks that its bound process is still live,
requires an existing local parent directory, and creates a new pointer with an
owner-only protected DACL. Publication uses a create-new `.pending` file,
write-through/flush, atomic rename without replacement, and exact-byte readback.
The directory is retained during publication and its resolved location checked.
The target SHA256 comes from the retained configuration; the command neither
accepts a private-worker configuration nor resolves another locator as input.

Existing pointer or pending files are refused and preserved. The command has no
replace flag and performs no acquisition, control request, helper load, rate
write, audio, registry write or elevation. It reports `deviceReadinessVerified:
false`: a live process and published metadata are not proof of device readiness.
A broker that exits after publication produces a stale pointer, which the
loader refuses. The pointer is retained for diagnosis after session exit.

[Explicit reviewed withdrawal](asio-pointer-withdrawal.md) now permits a separate
create-new publication at the same pointer path. It does not stop a broker or
redirect an attached client. There is no automatic cleanup, atomic replacement,
retry or second acquisition. Installation remains unfinished.

## Verification and remaining work

`sl3_driver_configuration_tests` covers direct-format compatibility, valid
locator resolution, file lease lifetimes, pointer changes while a selected
attachment is retained, malformed/version/hash/path failures, a same-byte broker
copy with a different identity, and refusal of cycles/private-worker targets.
The actual production DLL is loaded through registration-free `CoCreateInstance`
with a locator beside it and refuses a truthful simulated broker before client
clock/audio operations. That broker's worker audit remains exactly
`acquire`, `rate`, `release`; the helper is never loaded in the ASIO host.

The controller lifecycle tests use the real native publisher executable to
publish pointers for the separately built simulated controller. Separate STA and
MTA clients consume locator/pointer/immutable records through the production
loader, then explicitly use the simulated-provider test DLL. Each exercises
three COM-created objects and four SDK callback streams on one acquisition.
Existing-pointer preservation, stale-pointer refusal, refused stale publication
and private-input refusal are checked. Positive audio/timing is synthetic.

See [the verification record](evidence/session-locator-20261102.json).
Installation/registration, protected deployment directories,
genuine measured timing, native broker startup/analogue audio and
[current Serato/DVS admission](current-serato-integration-decision.md) remain
unfinished. No physical device or security settings were changed by these tests.
