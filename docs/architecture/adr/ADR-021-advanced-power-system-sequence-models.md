# ADR-021: Explicit advanced sequence-network equipment models

- **Status:** Accepted
- **Increment:** ND-013
- **Date:** 2026-11-21

## Context

The initial sequence-network builder can represent ordinary branches, two-winding transformers, positive/negative three-winding star equivalents, multiple Thevenin source shunts, and converter capability metadata. Three-winding zero-sequence behavior was intentionally blocked because pairwise leakage impedances and connection labels do not uniquely define delta circulating-current and core-return paths. Mutual sequence coupling, source-by-source superposition and explicit converter current-source injection were also not represented in the numerical model.

## Decision

1. Accept a three-winding zero-sequence three-port impedance matrix only as explicit manufacturer/test/validated-model input. Store port order HV/MV/LV, verify reciprocal/passive/nonsingular structure, convert its MVA base and stamp it as a multiport Ybus element.
2. Represent mutual impedance as a sequence-specific coupling between two explicitly identified line branches. Stamp the 2×2 series impedance matrix through branch incidence vectors. Restrict the initial implementation to lines with the same oriented terminal buses and unity taps.
3. Preserve independent Norton current-injection vectors in Ybus so the linear contribution of each Thevenin source can be quantified by superposition.
4. Preserve converter capability and connected-bus identity. Accept explicit three-sequence current commands, validate capability limits, and apply their fixed phasors in both the linear sequence-network solve and bus-fault Thevenin calculation. Do not infer control dynamics from capability magnitudes.

## Consequences

- Missing transformer zero-sequence port data remains an explicit error rather than an inferred equivalent.
- Mutual coupling is transparent, sequence-specific and reproducible, but currently relies on externally supplied per-unit data.
- Multiple Thevenin sources can be decomposed at a selected bus using one sparse factorization.
- Converter current commands are auditable and bounded and can contribute to bus-fault results as fixed phasors, but do not constitute a dynamic converter model or an IEC 60909 converter procedure.
- Existing single-source and uncoupled network construction remains backward compatible through optional fields and constructor defaults.
