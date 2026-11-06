# Shareable support summaries

The standalone exporter selects observations from saved readiness, recovery and startup-supervisor JSON reports. It does not collect a whole log folder, run a session, load an audio driver or open USB. This is a building block for the eventual package's support experience; it is not yet included in the immutable development kit or wired into its native launcher.

The [host example](evidence/support-summary-20261106.json) combines a fresh read-only readiness observation on 6 November 2026 with the saved manager-retirement recovery check from that day. All six prerequisites passed. Original resources and temporary registration were clean, while `previousSessionShutdownVerified` remained false. These observations do not prove that the new launcher starts or closes Serato successfully.

## Developer use

Run from the repository with Python; the exporter uses only the standard library:

```text
python scripts/export-sl3-support-report.py --readiness SAVED_READINESS.json --recovery SAVED_RECOVERY.json --supervisor SAVED_SUPERVISOR_RESULT.json --output NEW_SUPPORT_SUMMARY.json
```

Choose at least one input. Omit inputs that do not exist. Without `--output`, the summary is printed. An explicit output must be a new file; existing files are never overwritten. Sources are read only, with a two-MiB bound per input. The exporter does not launch the commands that originally produced them.

Only the three exact source schemas are accepted. The allowlist retains prerequisite statuses, selected boolean observations, bounded process exit codes, known supervisor end reasons and counts/presence of errors. It omits free-form error text, events, window titles, process IDs, timestamps, local paths, device identities, music metadata and audio. Recovery issue contents are replaced by a count. Unknown fields are omitted; malformed selected values, duplicate JSON members, non-finite numbers and inconsistent readiness claims are refused.

Each selected source has a SHA-256 digest of its exact bytes. This permits local comparison with the original report; it is not authentication or evidence of an actual device test. Reports can describe different sessions or times, and the exporter deliberately does not join them into a new success verdict. In particular, clean restored files do not establish a clean application exit, and a supervisor fixture does not establish Serato or Phase behaviour. Missing observations remain absent.

## Validation and package follow-up

Nine focused tests cover omitted private content, retained blocked/unknown prerequisites, inconsistent/incomplete checks, the cleanup/shutdown distinction, strict value types and schemas, exact source digests, duplicate/non-finite/oversized JSON and exclusive output creation. The example was generated from actual host reports after those tests passed. The initial readiness attempt under the ordinary system Python lacked the analysis dependency `pefile`; the successful host observation used the already prepared integration interpreter. The exporter itself needs neither that dependency nor Frida.

The next package revision should offer this as an explicit support action after collecting the appropriate saved reports. It should show the generated summary for review and let the owner choose whether to share it. Nothing is uploaded automatically. Inclusion in a rebuilt kit requires new inventory/source bindings and its normal checks; the existing attended-test candidate has not been modified by adding this standalone helper.
