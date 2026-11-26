# ADR-020 — Transient CT and protection dynamics

- Status: Accepted
- Increment: ND-012

## Context

ND-011 supplied steady-state phasor evaluators for 87, 67/67N and 21, plus an AC
excitation screen for CTs. It did not represent CT flux under DC-offset fault current,
relay timer evolution under a waveform, or breaker pole interruption timing.

## Decision

Add a separate `infrastructure.protection.transient` layer and immutable transient
study value objects. The CT simulator integrates a nonlinear single-phase flux-linkage
ODE using the existing CT excitation curve and burden data. The 50/51 transient evaluator
uses sliding RMS, the existing relay's static inverse-time characteristic as its local
operating-time law, a normalized timer accumulator, explicit dropout/reset and an output
delay. The breaker evaluator estimates per-pole current-zero interruption from supplied
three-phase time samples.

## Consequences

- Existing steady-state evaluators remain unchanged.
- The transient CT path requires engineer-supplied DC time constant, inception angle and
  remanent flux; no fault X/R is inferred silently.
- Manufacturer excitation data is required. Curve-domain overrun is `NOT_EVALUATED`.
- The CT magnetization model is single-valued and does not represent hysteresis or
  remanence evolution.
- Relay dynamics are an explicit sampled numerical model, not emulation of any relay
  manufacturer's firmware.
- Breaker interruption is an ideal current-zero estimate, not an arc/TRV simulation.
- No dependency was added; SciPy was already a project dependency.
