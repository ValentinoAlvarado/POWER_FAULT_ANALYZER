# ND-014 — IEC 60909 calculation completion matrix

**Snapshot:** 2026-11-22  
**Implemented code baseline:** ND-014.1 through ND-014.4A plus the current completion patch.  
**Status:** software regression-tested subset; not full IEC conformity.  
**Current regression snapshot:** 480 tests pass in the build environment; Windows Ruff/formatting must be reconfirmed after integration.

## Implemented and exposed by the current IEC calculator

| Area | Current implementation | Boundary
|---|---|---|
| Maximum/minimum initial current | Four bolted bus-fault types using sequence networks and the selected voltage factor | Only external network-feeder voltage-source equivalents are accepted by the IEC calculator
| Transformer impedance correction | Two-winding transformer correction | Three-winding IEC correction is not integrated; three-port zero-sequence model/data readiness alone does not mean IEC correction is applied
| Minimum line resistance | Explicit positive/negative and separate zero-sequence factors | Factors are user supplied; not inferred from temperature/conductor data
| Multiple sources | Combined sequence-network equivalent for multiple network feeders | Converter, synchronous- and asynchronous-machine source procedures are rejected
| Breaking current, three-phase | Single feeder (9.1.5) and multiple network feeders (9.2) | Network-feeder-only method class; no machine/converter decrement
| Breaking current, unbalanced | Maximum phase RMS from the sequence-network solution for network-feeder-only cases (9.3 subset) | No rotating-machine or converter contributions; must be benchmarked against licensed Clause 9.3 examples
| Steady-state current, three-phase | Single network feeder (11.2.5) and multiple network feeders (11.2.6) | Network-feeder-only method class
| Steady-state current, unbalanced | Maximum phase RMS from the sequence-network solution for network-feeder-only cases (11.3 subset) | No rotating-machine or converter contributions; must be benchmarked against licensed Clause 11.3 examples
| Peak current | Existing radial single-fed three-phase network-feeder subset (8.1) | No 8.2 multiple-fed, 8.3 unbalanced, or meshed peak strategy
| Thermal equivalent current and Joule integral | Existing maximum, single-fed, radial, three-phase feeder subset | No generalized source-dependent Annex B `m`/`n` treatment
| DC/asymmetrical waveform supplement | Additional R/X exponential estimate for single-fed radial three-phase feeder with explicit first-pole time | Engineering supplement only; not marked as verified IEC 2026 Clause 10 output

## Not implemented as normative IEC methods

1. Clause 8.2: multi-fed three-phase peak current.
2. Clause 8.3: unbalanced peak current.
3. Source-specific Clauses 9.1.1–9.1.4: synchronous machines, asynchronous machines, doubly-fed generators and full-size converters.
4. Full source-aware Clause 9.3 beyond network-feeder-only cases.
5. Clause 10: final-edition DC-component and unbalanced asymmetrical breaking procedures for all relevant source/topology combinations. The software may expose a separate engineering R/X estimate, but not as a normatively calculated value.
6. Source-specific Clause 11.2.1–11.2.4 and full Clause 11.3 beyond network-feeder-only cases.
7. Clause 14 generalized thermal equivalent current and Joule integral, including applicable `m`/`n` methods and source-dependent conditions.
8. Clause 6.3.3 three-winding transformer correction integrated into the IEC calculator.
9. IEC calculation at interior line/cable fault locations. ND-007 line-interior models are not automatically IEC 60909 methods.
10. Independent engineering validation against licensed worked examples, manually solved reference cases and a second commercial/reference solver.

## Interpretation of status

`pytest`, `ruff`, formatting and compilation establish software quality for the cases exercised. They do not prove that equations, coefficient selection, source classifications or exception handling comply with the entire final IEC 60909-0:2026 text. The public 2026 catalogue identifies the clause structure but does not supply the full final standard text.

The current result should be presented as a **restricted IEC 60909 network-feeder calculation engine**, not as a complete IEC-compliant short-circuit package. A complete claim requires implementation and independent verification of every applicable source/fault/topology method above.
