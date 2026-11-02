# Known-input tone analysis for the next finite capture

`scripts/analyse-input-tone.py` now compares a declared single-tone input with
saved finite six-channel packed-24 PCM. It reports fitted amplitude, DC, phase
and residual error for every stream channel, alongside unchanged full-capture
statistics and four predetermined request windows. It opens no device, emits
no audio, modifies no input and creates no timing profile.

The existing [offline marker tool](offline-audio-markers.md) uses a 4,096-frame
template for longer saved captures and remains available for later route/loopback
work. The present finite capture holds fewer frames than that template. This
short-window tone fit adds level/content evidence for the planned input test;
neither tool turns a relative phase or file offset into physical latency.

This prepares the known-input investigation required by the
[archived startup-sample findings](capture-pcm-analysis.md). It does not resolve
the [release/readiness gate](sl3-release-port.md), acquire a new capture or prove
current native/analogue audio. The full Windows/current-Serato/DVS goal remains
active; macOS is deferred.

## Input and measurement scope

The tool accepts the existing successful finite UsbDk `capture.json` and
`capture.pcm` pair. It reuses all packet/status/retirement/cleanup, geometry and
exact byte/frame-coverage checks from `analyse-capture-pcm.py`. It does not
re-attest the old capture worker or recover unknown sample gaps.

A separate declaration binds both input hashes and records the nominal tone,
recorded getter rate, source, wiring and control state. Evidence is explicitly
`synthetic` or `operator_declared`; descriptions are statements, not independent
physical verification. Record source level if known, input jack and line/phono
state, source switches/gain and the actual worker/test identity in those
descriptions or their referenced attended record. No jack assignment, voltage
calibration or signal source is inferred from the sample values.

The fixed-frequency model is `DC + a*sin(w*n) + b*cos(w*n)`, using the nominal
recorded rate and retained frame index. It solves six columns together with
[NumPy's least-squares solver](https://numpy.org/doc/2.3/reference/generated/numpy.linalg.lstsq.html),
checks rank/conditioning, and reports `hypot(a,b)` in signed-24 container codes
and peak dBFS. Residual RMS and explained centred energy expose signal content
that the model does not explain. A large DC is separated from the sine fit;
constant/silent channels have no explained-energy fraction.

Each fit needs at least 32 frames and three nominal cycles; a declaration must
be finite, positive and at or below one quarter of the recorded sample rate.
The full fit must qualify. A shorter request window is marked ineligible rather
than silently extended or trimmed. The four windows follow actual packet-length
coverage, including variable lengths. They partition all retained frames once.
Full statistics and the full fit always include every original sample.

Phase refers only to retained frame zero. A periodic phase is not a unique delay
or measured round trip. A good fit does not prove physical wiring, analogue gain,
converter precision, clock accuracy, packet continuity or DVS. There is no
automatic channel-map decision, physical pass/fail result, startup discard rule,
ASIO timing-profile output or deployment approval. DVS timecode is not decoded.

## Declaration and command

Create a declaration for the **actual saved capture**, filling its exact hashes
and observed descriptions. This example is a schema illustration, not evidence
that a source has been connected or the SL3 tested:

```json
{
  "schema": "sl3.input-tone-declaration.v1",
  "evidenceKind": "operator_declared",
  "rateHz": 44100,
  "toneHz": 1000,
  "sourceDescription": "Record actual source, nominal tone and level if known",
  "wiringDescription": "Record actual input jack, cable and line/phono state",
  "controlStateDescription": "Record actual switches, gain and attended worker/test record",
  "captureRecordSha256": "<actual lowercase SHA-256 of capture.json>",
  "pcmSha256": "<actual lowercase SHA-256 of capture.pcm>"
}
```

```powershell
.venv/Scripts/python.exe scripts/analyse-input-tone.py `
  --capture <saved-capture-directory> --declaration <declaration.json> `
  --output <fresh-analysis-directory>
```

The output parent must exist and the output directory must be new. The only
output is `analysis.json`, with input/declaration/source hashes and NumPy version.
Wrong hashes, duplicate/unknown declaration fields, invalid descriptions,
nonfinite numbers or a failed capture are refused before output creation.
Input bytes are rechecked before writing. Existing output is never overwritten.

## Verification and next attended requirement

Nineteen synthetic tests cover known amplitudes/DC/phase at both rates, polarity,
silence, a mismatched tone, deterministic noise, a retained full-scale startup
spike, variable packet windows, inadequate cycles, malformed declarations/captures,
ordinary operator statements without physical promotion and actual CLI
preservation/refusal. The twelve existing PCM-analysis tests also pass.
Labelled synthetic CLI examples are retained privately; their compact summaries
and hashes are in [the verification record](evidence/input-tone-20261102.json).
The archived physical captures have not been relabelled as known-input evidence.

An owner-present test still needs established acquisition/readiness, a real known
source with documented wiring/control state and a fresh bound capture. Review
startup content and channel results before choosing any settling policy or
attempting nonsilent output/loopback. Measured native timing, output mapping,
protected deployment, current Serato admission and actual two-deck DVS remain
separate unfinished requirements.
