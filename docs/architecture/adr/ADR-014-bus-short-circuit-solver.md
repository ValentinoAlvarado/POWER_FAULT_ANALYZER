# ADR-014 — Bus short-circuit solver and sequence Thevenin reduction

- Status: Accepted
- Increment: ND-006

## Context

ND-005 provides immutable sequence-network models and sparse Ybus matrices. It does
not compute fault currents. A fault calculation needs the driving-point Thevenin
voltage and impedance at a selected bus, and a fault-specific interconnection of
positive-, negative- and zero-sequence networks.

## Decision

1. Use sparse LU solves to calculate the prefault bus voltage and driving-point
   Thevenin impedance. Do not form a dense inverse of Ybus.
2. Model faults as immutable `FaultSpecification` values located at physical buses.
3. Implement the canonical three-phase, A-G, B-C and B-C-G bus-fault boundary
   conditions in `ShortCircuitSolver`.
4. Assemble and factorize only the sequence networks needed by the requested fault.
5. Convert per-unit phase currents and voltages to kA and line-to-neutral kV using
   the faulted bus's system base.
6. Reject required networks containing ERROR diagnostics, singular matrices, missing
   buses or nonlinear converter sources without a dedicated current-limit solver.

## Consequences

- Three-phase and line-to-line studies remain possible when zero-sequence modelling
  is incomplete, provided the positive and negative networks are valid.
- Ground faults require all three sequence networks and therefore stop when zero
  sequence data is unavailable or explicitly unsupported.
- The solver is bus-fault-only and is not an IEC 60909 implementation.
- Future extensions can add line-interior faults, prefault load-flow states, fault
  phase selection, IEC 60909 factors and converter-specific nonlinear solvers without
  changing the Ybus data model.
