# ADR-026 — Keep the single-Thevenin R-L waveform supplement outside IEC 60909

- **Status:** Accepted
- **Date:** 2026-11-22

## Context

ND-014.4 has explicit unavailable results for DC and asymmetrical breaking quantities where the relevant normative source/topology methods have not been implemented and verified. A generic first-order R-L waveform model is physically useful, but it does not cover the source-specific, multiple-fed, unbalanced or meshed-network procedures needed for an IEC 60909 Clause 10 implementation.

## Decision

Implement a standalone numerical engineering model for one balanced Thevenin R-L equivalent. Do not route its output into `IEC60909Calculator`, `IEC60909QuantityResult`, or IEC method-reference traces. Label it as non-IEC and expose the limitations in its result documentation.

## Consequences

- The project gains a testable single-equivalent time-domain calculation.
- The model can support academic studies and later waveform comparisons.
- IEC Clause 10 remains explicitly unavailable in cases not covered by a clause-verified IEC strategy.
- Future IEC implementation must introduce separate strategies, normative references and independent benchmark cases.
