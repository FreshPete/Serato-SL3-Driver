# Reviewed broker session binding

The production configuration loader now has an explicit broker format. It keeps
the existing worker/helper/timing/measurement checks and adds an immutable session
record plus a pinned broker image. The facade can resolve that record to a live
server reference and use the [broker-backed ASIO session](broker-asio.md).
No production configuration was installed, no controller was started against the
SL3, and no registry, driver binding or security setting changed.

## Configuration and session records

The existing `SL3-ASIO-CONFIG-1` format retains its private-worker behavior.
The separate broker format requires these exact ordered fields, a final newline,
absolute local paths and lowercase SHA256 values:

```text
SL3-ASIO-BROKER-CONFIG-1
worker=<reviewed worker path>
worker_sha256=<worker SHA256>
helper=<reviewed helper path>
timing_record=<reviewed timing record path>
timing_record_sha256=<timing record SHA256>
broker=<reviewed broker executable path>
broker_sha256=<broker executable SHA256>
session_record=<immutable session record path>
session_record_sha256=<session record SHA256>
```

This is a schema illustration, not an installable configuration or timing
approval. All prior fixed-rate/buffer, eight-interval/four-request pipeline,
reviewed helper and measurement-file bindings still apply. Record consistency
does not establish that a claimed measurement is physically valid.

`windows/broker_record.{hpp,cpp}` formats the current process's session record:

```text
SL3-BROKER-SESSION-1
endpoint=<private SL3Broker pipe name>
server_pid=<decimal process ID>
server_created=<decimal Windows FILETIME creation value>
worker_sha256=<actual owner's worker SHA256>
```

The formatter is pure metadata generation. It does not publish a file, create a
pipe, launch a process or acquire a device. A future explicit controller must
publish a fresh record only after its independently reviewed owner is ready,
then produce the corresponding pinned configuration. Restarting a controller
requires a fresh record/configuration; old files are not silently refreshed.

## Binding and runtime checks

The binder opens the record read-only while denying write/delete and verifies
its hash before parsing. It rejects unknown fields/order, noncanonical numbers,
trailing/NUL/BOM data, records over 4,096 bytes and malformed pipe names. The
record's worker hash must equal the configuration's already pinned worker.

It opens the stated process with synchronize/query rights and requires that
exact object to be live with the recorded creation time. It queries the process
image path, pins the configured image bytes and compares the configured and
queried image files by volume/file identity. The record and image handles remain
held through both the configuration lease and retained server reference. The
new record/image file checks resolve their final paths and reject nonlocal or
non-fixed-drive targets, including a remote reparse destination.

This validates file/process consistency. It does not attest running memory,
isolate hostile code using the same account, prove endpoint availability or
certify USB readiness. The existing pipe admission still verifies the actual
server/client process references, tokens and exact-process event challenge.

Reviewed broker configuration also requires the worker hash in the greeting.
The server compares it with the hash used to launch its retained worker before
granting a client lease or making its fresh clock query. A mismatch refuses;
there is no downgrade to an unbound greeting. The optional extension preserves
the old direct component-test greeting, but production broker configuration
always supplies the contract. An older server that cannot parse it fails closed.

After the file/process binding checks, both native facade and explicit scope
construction select the broker. Runtime admission completes during initialization
before ASIO readiness is published. Kind remains native-only in production; there is no
`simulated` configuration field. A missing, stale, mismatched or failed broker
does not fall back to a private worker, launch another process or reacquire USB.

## Verification

`sl3_broker_record_tests` checks a real live process/image binding, held file
leases, a confirmed exited process, creation-time mismatch, same bytes in a
different image file, bad hashes, malformed/oversized records and canonical
identity parsing. It runs without the ASIO SDK and acquires no device.

The real pipe/process tests now use the expected worker hash in their positive
connections and verify that a wrong contract reaches no client device operation.
The production configuration tests load valid synthetic records, keep all timing
and session bytes locked, and reject changed record/image pins.

An isolated copy of the actual production DLL reads the new adjacent broker
configuration and connects to a truthful simulated broker. Its native-only
greeting is refused before client admission. The broker audit must be exactly
`acquire, rate, release`: only its explicit simulated startup getter occurs, with
no client clock refresh, audio start or helper load in the host. The test verifies
that failed initialization publishes no ASIO channel readiness and releases all
configuration/module resources. This is a production-path refusal test, not a
positive native audio test or in-memory attestation.

Exact build/test counts, hashes and the private checkpoint are recorded in
`docs/evidence/broker-binding-20261101.json`. Synthetic timing inputs remain
labelled as such and are never installed as measured SL3 profiles.

## Remaining work

The explicit controller/record publication lifecycle, native startup journal and
deployment workflow are still unfinished. There is no installed broker service,
automatic discovery, new production registration or positive native broker run.
Reviewed real timing and attended physical audio tests remain necessary. Current
Serato's discontinued-device/audio/API/DVS admission is a separate unresolved
requirement; macOS remains deferred until Windows works.
