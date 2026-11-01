# Bounded host/worker message channel

An original Windows shared-memory channel now exchanges bounded binary messages between the host and a supervised worker. Real processes verify ordered replies, ownership, timeout and worker-exit handling. **It does not yet implement audio-session commands, continuous audio, a USB worker or an ASIO connection.** The worker used here is an explicit test fixture that echoes bytes without accessing hardware.

## Wire and session ownership

The original version-1 transport had a checked 64-byte header plus separate 32,768-byte request and reply areas. Version 2 added [fixed input/output data queues](shared-audio-queues.md) and their metadata to a 196,800-byte mapping. Current `src/windows/mailbox_layout.hpp` is **version 3**, adding an active packet count for [shorter batches](audio-transfer-granularity.md) without changing the mapping size. The control payload limit remains 32,768 bytes. Old layouts are rejected by version/size checks. The mapping contains no process pointers or host buffer addresses. Size/layout assertions are compiled in both configurations. A successful message says nothing about device availability.

Each host creates a new `Local\SL3Mailbox-<128-bit-random-id>` identity. The original control layer has three named objects: a page-file-backed mapping and request/reply events. Current data queues add two ready events, for five objects in total. They have noninheritable handles and a protected DACL granting access to the current user's SID. Object-name collisions fail rather than attaching existing objects. Peer names must match the exact local namespace/hex format. The current process supervisor can launch the child without inheriting any handles.

The first peer claims its PID atomically; another attachment is rejected. Host replies must match the PID obtained from the retained expected worker process handle. These checks prevent accidental cross-session/peer use. They are not authentication against hostile code running as the same user, and there is no service/privilege boundary here.

Both control endpoints are single-owner, separate from the queues' data owners. A session permits one outstanding request. Sequence numbers start at one and cannot wrap into a new session. Header magic/version/size/reserved fields, opcode, sequence and payload bounds are validated before caller output is published. Unknown nonzero opcodes and status values remain opaque framing values; the typed dispatchers validate their semantics.

The phase moves through host writing → request → peer processing → reply → host reading → idle. Windows interlocked transitions publish ownership and order shared access; events wake waiters. Each process keeps its own mapped view alive. Closing the host seals the phase while a peer view remains valid; it does not unmap memory owned by the peer. [Microsoft shared-memory ownership and synchronization contract](https://learn.microsoft.com/en-us/windows/win32/memory/sharing-files-and-memory).

The [continuous-worker integration](continuous-worker.md) adds borrowed local command/output event access for combined I/O/control waits. `receive` checks published request ownership even if a preceding wait consumed its event edge. Stale late signals do not invent messages or extend the original timeout. Borrowed handles must never be closed and do not extend mailbox lifetime. The new consumed/stale-edge regression cases pass alongside the existing real-process framing suite.

## Failure handling

Host waits include both the reply event and the exact expected process handle. A worker exit is distinct from a reply. A valid published final reply can be collected even after the peer has exited; peer destruction therefore does not overwrite an already published reply with a close indication.

A host timeout seals the channel. Pending replies cannot reopen it, and no new request or automatic retry is permitted under that identity. Malformed/stale replies also seal it and leave the caller's previous output untouched. Invalid input publications fail before taking ownership. A peer's idle wait timeout can be retried because no request lease was acquired.

The API now bounds explicit waits to ten seconds so the finite capture operation and drain can fit within one request; the original framing checkpoint used five. It allocates/copies message storage and belongs on control/batch threads. This is not a callback-safe audio ring, measured low-latency transport or continuous scheduling implementation. Mapping close/worker termination does not by itself establish USB or host-callback retirement.

## Tests actually run

All **13 native tests pass in Release and Debug**. A separate SDK-free build passes eleven with an absent SDK path. The new test performs 100 cross-process round trips at sizes 0, 18, 18,432 and 32,768 bytes, preserving every byte, sequence, opcode and test status. It covers duplicate peers, invalid publications, one-request ownership, malformed request/reply lengths and sequences, bad reply version/opcode, wrong expected worker identity, peer exit, bounded timeout and explicit close.

A rendezvous test holds a real worker after it acquires a request, times out/seals the host, then releases the worker and verifies its late response is rejected. Another test destroys the host while the peer still owns a mapped request and verifies no reply can reopen that session. Graceful final replies survive peer exit. No fixture process remains alive. [Build/source evidence](evidence/mailbox-build.json).

These checks contain no USB or ASIO-driver path. Synthetic binary payloads are not captured audio. Owner-SID DACL construction is implemented; no cross-account penetration test or exhaustive allocation/Win32-failure injection is claimed.

## Remaining integration

A subsequent [typed diagnostic worker](typed-worker.md) adds hello, descriptor probe, finite input capture and quit. Its actual handshake/missing-driver error path is tested; physical capture remains unrun. Distinguish a worker being alive from a validated SL3 stream. Add the continuous data path, output and host callback/buffer leases, then connect the [ASIO component](asio-com-server.md) and real transport behind the [process supervisor](worker-process.md). Current Serato/DVS, clock/latency and physical audio still require their own validation.
