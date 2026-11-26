# ADR-016 — Restricted IEC 60909 network-feeder calculation

- **Status:** Accepted for ND-008
- **Date:** 2026-11-21
- **Decision owners:** POWER_FAULT_ANALYZER engineering

## Context

ND-006 provides sequence-domain bus-fault solutions; ND-007 adds line-interior
fault locations. Neither increment implements IEC 60909 correction factors or
short-circuit current magnitudes. The current standard edition is IEC 60909-0:2026.
A first standards-oriented increment must not misrepresent the existing component
models or silently invent missing machine, converter, multi-source or thermal data.

## Decision

Implement an explicit `IEC60909Calculator` alongside, not inside, the generic
`ShortCircuitSolver`. It composes the existing sparse Thevenin and sequence fault
solver and adds only the following bounded model class:

- one active positive-sequence `ExternalGrid` network-feeder source;
- bolted faults at physical buses;
- maximum/minimum voltage factors for modeled LV and HV ranges;
- two-winding transformer impedance correction using declared rated xT and LV
  rated-voltage metadata;
- explicit 50 Hz or 60 Hz study frequency;
- engineer-supplied separate minimum-case line resistance factors for positive/negative
  and zero sequence;
- positive/negative-sequence omission of line/transformer branch shunt admittances,
  with zero-sequence shunt treatment retained;
- optional utility source-impedance multiplier;
- initial symmetrical current for the four existing fault boundary types;
- radial maximum three-phase peak and thermal-equivalent current quantities.

For minimum studies, the two-winding transformer correction uses cmax. Two-winding
transformer metadata is attached to each sequence branch/grounding shunt so the
corrected network is created immutably. Transformer correction does not depend on
whether the fault lies on the high- or low-voltage side; its cmax reference voltage
is the transformer's rated LV winding voltage.

The peak-current radial method is withheld for meshed components. The calculator
returns no peak/thermal result when the radial method is not supported. It rejects
unsupported source families, multiple feeds and three-winding transformer correction.

## Consequences

### Positive

- IEC conventions are isolated from generic symmetrical-component calculations.
- Results contain standard edition, voltage factor, case, transformer correction
  factors, current values, durations and diagnostics.
- Unsupported study classes fail explicitly rather than returning plausible but
  unjustified values.
- The original ND-006 solver remains reusable by non-IEC and academic workflows.

### Negative / limitations

- This is not full IEC 60909 conformance and must not be marketed or certified as such.
- User-supplied line-temperature and utility feeder adjustments require engineering
  provenance outside this API. Positive/negative and zero-sequence line resistance
  temperature factors are independent inputs for unbalanced minimum studies.
- The system frequency must be supplied explicitly; the sequence-network snapshot
  does not yet carry a study-level frequency contract.
- Peak and thermal quantities are limited to radial maximum three-phase faults.
- Machine, converter, multiple-feed, line-interior IEC and three-winding corrections
  require future domain data and independently validated implementations.

## Validation

Analytical tests verify voltage factors, cmax transformer correction in minimum
studies, independent positive/negative and zero-sequence line resistance scaling,
shunt-admittance omission, the radial peak factor, thermal factors, and unsupported
topology/source rejection. ND-001 through ND-007 regression tests remain unchanged
except for sequence-equipment metadata needed by the correction engine.
