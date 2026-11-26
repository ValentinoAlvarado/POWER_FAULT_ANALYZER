# ADR-028 — Engineering Validation and Benchmark Evidence

- **Status:** Accepted for ND-016 validation tooling; MVP release remains conditional.
- **Date:** 2026-11-22

## Context

The project has accumulated substantial functionality and regression coverage. Software tests establish behavior for implemented cases, but are not equivalent to independent electrical validation or IEC conformity.

## Decision

1. Store fixed, versioned, closed-form analytical reference cases separately from the solver implementation.
2. Compare sequence currents, phase currents, ground current and base-current conversion quantity-by-quantity with explicit units and absolute/relative tolerances.
3. Audit physical/per-unit conversions, symmetrical-component reconstruction and fault boundary constraints independently of benchmark matching.
4. Re-solve a declared passive Thevenin case over controlled impedance perturbations and check monotonic response plus finite-difference derivative refinement.
5. Define a provenance-labelled JSON interchange for third-party study-tool result data. The presence of an adapter must never be presented as proof that an external tool was run.
6. Mark iterative convergence as not applicable to the present direct sparse bus-fault solve path; do not invent iterative convergence metrics.
7. Keep missing result quantities unavailable rather than inferring branch or winding currents from nodal quantities.

## Consequences

- Analytical benchmark reports are reproducible and machine-readable.
- External tool evidence can be imported without a runtime dependency on a proprietary application.
- The scope of each validation claim is explicit and auditable.
- Native installer/executable packaging and genuine third-party result comparison remain release gates.
