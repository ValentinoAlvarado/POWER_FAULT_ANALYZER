# ADR-023 — Separate Source Contribution Attribution from IEC Source Corrections

- **Status:** Accepted for ND-014.2
- **Date:** 2026-11-22

## Context

The project now contains explicit Thevenin sequence models for external grids and rotating machines, and a separate fixed-phasor current-command path for converter-interfaced sources. The product needs to expose each source's contribution at the faulted bus without confusing physical network-model superposition with source-specific normative IEC 60909 correction procedures.

## Decision

1. Build a deterministic source inventory from the source models actually stamped in the sequence networks.
2. Attribute source contributions by linear superposition on the common sequence-network Ybus matrices.
3. Preserve source identity, source family, representation mode and model reference in each contribution and calculation trace.
4. Reconstruct and compare the sum of source contributions against the total sequence and phase currents; reject an analysis if the residual exceeds configured tolerances.
5. Keep source-specific IEC correction policies separate. No correction factor is inferred merely because a physical synchronous/asynchronous machine or converter model exists.
6. Accept multiple external network-feeder equivalents for the initial symmetrical current only when the IDs are consistent across the sequence networks required by the declared fault. Do not expose multi-feed peak, breaking, steady-state or thermal quantities without the corresponding validated procedure.

## Consequences

- Existing sequence-network and fault-solving code is reused rather than duplicated.
- Source contribution reports can be traced back to the physical equipment models and current commands.
- The calculated decomposition remains explicitly distinct from a complete IEC 60909 machine/converter contribution calculation.
- Multiple network-feeder studies have a deliberately restricted set of available quantities until the relevant multi-feed methods are implemented and verified.
