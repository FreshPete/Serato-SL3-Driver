# Session window

Mode: Operate. This is an interim engineering window for a prepared session. The owner clarified that the final product must be one-time setup followed by normal Serato launch; this window does not satisfy that target. Code-led native controls are the implementation reference; no bitmap comp substitutes for actual Windows rendering.

## Direction contract

THESIS: make one prepared SL3 session understandable without a command prompt. Present a short action sequence, not a dashboard.

OWN-WORLD: standard Windows controls, Segoe UI, system window/background/text colours, visible keyboard focus and a generous single-column layout. The desktop use scene calls for familiar high-contrast system presentation rather than a performance-themed skin.

STORY: first check the prepared setup, then explicitly start it. Close Serato normally to finish. Status and recovery remain separate actions; restored files are not proof of successful playback or shutdown.

FIRST VIEWPORT: title and version context at the top, current action/status beneath, a short wiring/start instruction, then Check setup and Start session. Status, recovery and optional diagnostic details follow. Progress is inline and the window stays responsive.

FORM: native task window, pinned by the owner's choice rather than a random concept roll. Start is gated on a successful check and limited to one launch per prepared window. While a command runs, competing actions and window exit are disabled; no desktop polling or Serato automation is added.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
