# SL3 compatibility restoration

<!-- impeccable:product-schema 1 -->

## Platform

Windows native desktop (Win32). The skill's web/mobile platform vocabulary does not describe this target.

## Users and purpose

DJs who own a Rane SL3 and want to keep using it with current Serato DJ Pro. The owner wants setup to run once, followed by opening Serato normally with the SL3 connected. Phase and timecode vinyl are alternative control sources, not separate driver products.

## Operating context

Windows 11 x64, Serato DJ Pro 5.0.0.1278, an SL3 and the reviewed signed UsbDk filter. Phase A uses LINE inputs 3/4 and Phase B uses LINE inputs 5/6. Owner-confirmed two-deck tracking has been demonstrated with both remotes on one platter. Physical audible output, independent platters, sustained reliability and the refreshed package's live shutdown remain unverified.

## Capabilities and constraints

The existing native command entry verifies pinned session inputs, checks readiness, starts temporary integration, reports status and requests guarded recovery. Administrator prompts remain Windows-owned. No firmware changes, security-policy weakening, trust changes or automatic uploads. The current package is private and experimental. A GUI must preserve these boundaries and must not turn a command exit into a claim about physical audio or a clean Serato shutdown.

## Interface decision

The owner chose a simple Windows window on 6 November 2026, then clarified that normal use must be one-time setup followed by launching Serato normally. A per-session launcher is an interim engineering tool, not the final experience. General installation, ordinary Serato startup, automatic broker availability, clean repeated close/reopen and uninstall/recovery are required. Standard keyboard-accessible Windows controls and clear progress take precedence over decoration. Computer automation during audio caused lag in earlier sessions; the installed solution must not inspect or manipulate Serato's desktop during audio.
