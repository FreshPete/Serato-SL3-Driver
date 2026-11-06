# Shareable support summaries

The standalone exporter selects observations from saved readiness, recovery, startup-supervisor and ASIO call-analysis JSON reports. It does not collect a whole log folder, run a session, load an audio driver or open USB. This is a building block for the eventual package's support experience; it is not yet included in the immutable development kit or wired into its native launcher.

The [host example](evidence/support-summary-20261106.json) combines a fresh read-only readiness observation on 6 November 2026 with the saved manager-retirement recovery check from that day. All six prerequisites passed. Original resources and temporary registration were clean, while `previousSessionShutdownVerified` remained false. These observations do not prove that the new launcher starts or closes Serato successfully.

## Developer use

Run from the repository with Python; the exporter uses only the standard library:

```text
python scripts/export-sl3-support-report.py --readiness SAVED_READINESS.json --recovery SAVED_RECOVERY.json --supervisor SAVED_SUPERVISOR_RESULT.json --asio SAVED_ASIO_ANALYSIS.json --output NEW_SUPPORT_SUMMARY.json
```

Choose at least one input. Omit inputs that do not exist. Without `--output`, the summary is printed. An explicit output must be a new file; existing files are never overwritten. Sources are read only, with a two-MiB bound per input. The exporter does not launch the commands that originally produced them.

Only the five exact source schemas are accepted (completed and marker-free ASIO analyses have separate schemas). The allowlist retains prerequisite statuses, selected boolean observations, bounded process exit codes, known supervisor end reasons and counts/presence of errors. Window-close summaries preserve enumeration and post counts separately from actual process exit. It omits free-form error text, events, window titles, process IDs, timestamps, local paths, device identities, music metadata and audio. Recovery issue contents are replaced by a count. Unknown fields are omitted; malformed selected values, duplicate JSON members, non-finite numbers and inconsistent readiness claims are refused.

ASIO summaries retain method pair/error counts, unmatched-record counts, known unmatched operation names and the source's explicit completeness/identity limits. Unknown logger loss counts remain `null`. Missing methods are not invented as successful or failed calls. A marker-free unmatched stop remains an observed missing terminal, not proof of a blocked driver. Raw call/thread/object identities and argument/result arrays are omitted. The [shutdown-gaps example](evidence/support-shutdown-gaps-20261106.json) exports the saved looped-run supervisor's forced exit alongside a **separate, older markerless ETL analysis** with zero recoverable records. These are not a matched trace/session and do not identify the cause of that exit.

Each selected source has a SHA-256 digest of its exact bytes. This permits local comparison with the original report; it is not authentication or evidence of an actual device test. Reports can describe different sessions or times, and the exporter deliberately does not join them into a new success verdict. In particular, clean restored files do not establish a clean application exit, and a supervisor fixture does not establish Serato or Phase behaviour. Missing observations remain absent.

## Validation and package follow-up

Fourteen focused tests cover omitted private content, retained blocked/unknown prerequisites, inconsistent/incomplete checks, the cleanup/shutdown distinction, strict value types and schemas, exact source digests, duplicate/non-finite/oversized JSON, exclusive output creation, incomplete/empty ASIO observations, method errors and window-close observations. Nine completed-trace and five marker-free analyzer tests also pass. The examples were generated from actual saved reports. The initial readiness attempt under the ordinary system Python lacked the analysis dependency `pefile`; the successful host observation used the already prepared integration interpreter. The exporter itself needs neither that dependency nor Frida.

The next package revision should offer this as an explicit support action after collecting the appropriate saved reports. It should show the generated summary for review and let the owner choose whether to share it. Nothing is uploaded automatically. Inclusion in a rebuilt kit requires new inventory/source bindings and its normal checks; the existing attended-test candidate has not been modified by adding this standalone helper.
