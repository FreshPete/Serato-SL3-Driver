# Live helper output from the native launcher

The ordinary-child launcher now forwards stdout and stderr while the helper is running. Previously it accumulated up to four MiB per stream and printed only after child exit. For combined kit Start this could hide readiness/preparation output for the lifetime of the session. The change makes those existing messages available to the caller immediately; it does not add a graphical window or new live-state claims. [Evidence](evidence/native-launcher-progress-20261106.json)

## Behaviour

Each existing pipe reader forwards bytes directly with `WriteFile`. A second CRT text-mode conversion would duplicate carriage returns in nested native launches, so the forwarding path preserves the child's bytes. There is no duplicate replay at exit. Stdout and stderr remain separate streams; ordering between them is not promised.

The four-MiB bound applies independently to each stream. The exact prefix is forwarded regardless of pipe read boundaries, then excess output is discarded while reading continues. A limit or output-write error makes the relay fail after child completion instead of claiming success or abandoning the pipe. Native output forwarding uses bounded stack storage rather than retaining the full logs in memory.

If Serato supplies no stdout/stderr handles to its installer, the launcher drains silently with the same bounds and preserves the helper exit code. A present but failing output handle remains an error. The elevated transaction route remains unchanged: no privileged process is terminated or given a new deadline.

This change is event-driven pipe handling. It adds no Serato inspection, desktop automation, polling of the audio process, USB access or audio callback work. It does not make an administrator prompt appear, automate Download Driver, or certify startup/shutdown. It only exposes output that a helper has already flushed. A caller that does not read its output pipe can still block forwarding.

## Verification

Three actual native parent/child fixtures passed:

* Both streams were observed before releasing a waiting child. Exact CRLF bytes, no duplicated output and exit code 7 were verified.
* A child produced more than four MiB. Exactly four MiB reached stdout, the child still finished, and the relay refused success.
* Null/invalid console handles were substituted. The helper's output was drained and exit code 9 survived without forwarded output.

Eight Windows argument round trips passed. The refreshed copied-kit suite passed nineteen native entry checks with an empty PATH, including complete offline preparation, Status, recovery no-op and integrity refusals. A current host recovery check reported original resources restored and no temporary registration or occupied staging paths.

The native release still pins 46 source/license/evidence files, both complete runtimes and the original application; full plans pin 34 sources. A newly bound installer resource, plans and private kit were assembled. Audio binaries are unchanged. No Serato startup, UAC prompt, broker or device open was attempted. A graphical interface, attended combined Start and clean post-playback shutdown remain unfinished or unverified.
