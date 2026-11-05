# Recovery when broker startup fails before publication

The prepared live-session sources remain unchanged. The accompanying [review patch](patches/unpublished-broker-retirement-candidate.patch) is an unselected candidate, not an installed driver or a hardware-validated fix.

The diagnostic coordinator currently records controller ownership only after readiness. A controller that fails before readiness can retire its worker successfully yet leave cleanup unable to prove which controller process it launched. Refusing cleanup is appropriate without that proof, but prevents automatic recovery from this known startup case.

The candidate records the retained Windows process handle's creation time, process ID, controller hash, input hash and session bindings immediately after launch, before waiting for readiness. Recovery checks those bindings, refuses conflicting pointers, and waits for the exact controller instance to exit. A reused process ID receives no command. A result file claiming worker retirement cannot substitute for controller exit. All four worker-release facts must also be true. The original failed-start result remains a failure after successful cleanup.

Eight targeted tests pass, including an actual owned Windows Python process that must exit before recovery is accepted. The tests also cover malformed identities, conflicting pointers, changed input, missing release facts and an exit racing the stop request. A separate exercise ran the existing simulated controller and worker through their clock-mismatch failure: baseline cleanup refused; candidate cleanup verified retirement and preserved the original failure. Only the inspection response was replaced by a test double because that simulated executable does not offer the diagnostic inspection command. No SL3 was opened. [Evidence](evidence/unpublished-retirement-candidate-20261105.json)

The patch includes a regression test file. It passes a dry-run applicability check against the current source. Applying it will change source hashes, so existing prepared session plans and deployment prerequisites must be regenerated before selecting it for live use. Do not apply it over a prepared or running session.

This addresses pre-readiness recovery only. It does not explain or fix the two-deck session's `owner_failure` during application shutdown. The next attended check remains a manual Serato close with the prepared first-failure diagnostics and detached tracer. Physical output, sustained operation and permanent installation remain unverified.
