# ADR-015 — Interior-line fault location through immutable sequence-network splitting

- **Status:** Accepted
- **Increment:** ND-007

## Context

ND-006 solved faults at physical buses. Extending the solver to line-interior faults
requires a fault node to exist in each sequence network used by the selected fault.
The topology must be modified without mutating the originating network aggregate or
changing the pre-fault equivalent of the ND-005 branch model.

A generic two-terminal branch is not necessarily a line: a branch may represent a
lumped reactance or transformer. Interior locations therefore require explicit
physical line-length metadata.

## Decision

1. Add optional `length_km` metadata to `SequenceBranch`.
2. Populate it only for `Line` equipment and subclasses in `SequenceNetworkBuilder`.
3. Identify an interior-fault target by the line equipment UUID.
4. Require a strict interior fraction `0 < fraction_from < 1`.
5. Split the line's series impedance in proportion to the location fraction.
6. Retain the original nominal-\(\pi\) terminal shunts at the two physical terminals.
7. Insert a deterministic internal fault node into copies of only the sequence
   networks required by the fault type.
8. Reuse ND-006 for fault boundary calculations and recover the full nodal sequence
   voltage vectors to calculate line terminal currents and voltages.
9. Return an immutable result containing the fault-point solution and both line-end
   states. Terminal currents are directed from the physical bus into the line.

## Consequences

- The input network and sequence-network objects remain immutable.
- Splitting the series branch while keeping terminal shunts at their original nodes
  preserves the original lumped nominal-\(\pi\) pre-fault equivalent.
- Unsupported or incomplete sequence networks remain irrelevant when a fault type
  does not require them.
- Interior locations are available only for line/cable equipment with physical
  length metadata. Lumped reactances and transformer branches are rejected.
- The model remains a lumped sequence-domain approximation; distributed line
  physics and IEC 60909 correction factors are separate future work.
