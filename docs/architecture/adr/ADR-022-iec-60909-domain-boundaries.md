# ADR-022 — IEC 60909 calculation-domain boundaries

- **Status:** Proposed for ND-014
- **Date:** 2026-11-22
- **Decision owners:** POWER_FAULT_ANALYZER engineering

## Context

ND-008 introduced a deliberately restricted IEC 60909 network-feeder calculator in `infrastructure/numerical/iec60909.py`. ND-013 subsequently added source-superposition and explicit converter-current numerical capabilities, but the IEC calculator still rejects multiple active sources, synchronous/asynchronous machines and converter contributions. The `standards/iec60909/` package contains placeholder modules but no implemented standard-specific policies.

The current IEC 60909-0 edition is Edition 3.0 (2026). Its public contents distinguish equipment models, source classes, single-fed and multiple-fed peak/breaking procedures, unbalanced cases, steady-state current and thermal-equivalent current.

## Decision

1. Keep `ShortCircuitSolver` as the generic sequence-domain solver, independent of IEC rules.
2. Move normative policy/value-object responsibilities into `standards/iec60909/`.
3. Keep sparse Ybus assembly, factorization and numerical matrix solves in Infrastructure.
4. Represent voltage-source contributions, current-source contributions and passive network elements as distinct calculation concepts.
5. Use explicit strategies for peak, breaking, steady-state and thermal calculations by their applicable fault/source/topology class.
6. Extend the current IEC result with a complete immutable factor/provenance trace and explicit calculated/unavailable/not-applicable states.
7. Preserve the existing restricted IEC calculator API as a facade while incrementally delegating to the new standard package.
8. Do not encode unverified formulae, coefficients or equipment correction policies. Normative implementation is gated by clause-level review of the licensed IEC 60909-0:2026 text.

## Consequences

### Positive

- Normative rules are testable without importing GUI, API or persistence dependencies.
- The existing academic solver remains reusable and unaffected by IEC-specific assumptions.
- Source contributions and current-source models cannot be confused with Thevenin equivalents.
- The code can state precisely which source/fault/topology combinations are supported.
- Every factor can be traced to its inputs and standard clause.

### Negative / costs

- Requires an incremental refactor of the current IEC calculator and its tests.
- Requires additional model inputs for asynchronous motors, machine contributions, converters and three-winding transformers.
- Multi-fed and meshed procedures require additional topology/source contribution calculations; merely removing the current single-source guard is not sufficient.
- Exact standards clauses and applicable companion documents must be available for implementation review.

## Validation

- Preserve all 404 ND-013 regression tests.
- Add independent analytic tests for each new source and current strategy.
- Verify complex source-contribution reconstruction, per-unit base invariance and topology selection.
- Run Ruff, compileall and the full test suite.
- Reserve independent benchmarking and formal validation for ND-016.
