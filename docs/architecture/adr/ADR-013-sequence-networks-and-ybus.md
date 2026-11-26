# ADR-013 — Sequence Network Construction and Sparse Ybus

- Status: Accepted for ND-005
- Context: The physical equipment model must be transformed into positive-, negative- and zero-sequence nodal networks without coupling the equipment domain to SciPy or NetworkX.

## Decisions

1. Use one three-phase MVA base and a separate line-to-line voltage base for each physical bus.
2. Keep immutable sequence-network nodes, branches and shunts separate from physical equipment entities.
3. Use structural sequence-equipment providers and explicit adapters for lines, sources and transformer families.
4. Represent Thevenin sources through Norton equivalents in the Ybus right-hand-side vector.
5. Represent converter sources as declared current-capability elements; do not invent a fixed Thevenin impedance.
6. Assemble matrices using SciPy COO accumulation and expose CSR matrices.
7. Diagnose unreferenced components and expose sparse LU factorization; never insert arbitrary small shunts to hide singularity.
8. Treat unsupported zero-sequence transformer arrangements as diagnostics, not as guessed circuits.
9. Reject mixed declared equipment reference frequencies rather than silently applying frequency scaling.
10. Refuse numerical factorization when the sequence-network model contains ERROR diagnostics.

## Consequences

The sequence-network model can be tested independently of the numerical backend. A different sparse solver can be introduced behind an adapter. Three-winding transformer positive/negative sequence networks are supported using an auxiliary star node; their zero-sequence port model remains deferred until manufacturer/model-specific data and core/connection behavior are represented explicitly.
