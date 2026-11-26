# ADR-019 — Advanced protection-function model boundaries

- **Status:** Accepted
- **Increment:** ND-011

## Context

ND-010 provides topology-bound overcurrent/fuse protection, protection zones, fault scenarios and explicit backup relationships. Advanced functions require phasor data and characteristic-specific settings that are not represented by the scalar RMS current measurement used by ND-010.

## Decision

Introduce separate immutable settings, phasor measurement and operation-result contracts for:

- two-terminal biased differential 87L/87T;
- directional supervision 67/67N around an existing 50/51 relay;
- MHO and quadrilateral distance 21;
- steady-state CT excitation/burden screening.

Advanced functions are attached to an existing protection zone and physical equipment through `AdvancedProtectionFunctionBinding`. CT performance models are attached to an existing ND-010 overcurrent relay binding and must share its CT ratio. The existing `ProtectionNetworkAnalyzer` remains responsible for scalar phase/earth overcurrent and fuse operation; `AdvancedProtectionNetworkAnalyzer` owns phasor-function evaluation.

Advanced scenario measurements carry an explicit `expected_to_operate` boolean. The software does not infer intended differential/directional/distance tripping from connectivity or zone membership alone. Missing phasors and missing CT currents remain `NOT_EVALUATED`.

## Consequences

- Transformer differential compensation matrices and side current bases must be entered explicitly; vector-group compensation is not silently inferred.
- The differential model supports two-terminal line/cable and two-winding transformer applications only. Three-winding transformer differential and busbar differential are excluded.
- Directional decisions use supplied operating-current and polarizing-voltage phasors; memory polarization and vendor-specific polarizing algorithms are excluded.
- Distance settings are provided in relay-secondary ohms and require explicit CT/VT ratios, k0 compensation and zone characteristics. Full phase selection, load encroachment, power swing and teleprotection are excluded.
- CT screening compares the symmetrical steady-state secondary voltage requirement with a supplied knee point. Transient saturation and remanent flux are explicitly not evaluated.
- The function models are engineering calculation primitives. Their named ANSI function numbers and IEC references do not constitute type-test or conformity claims.

## Alternatives considered

1. **Extend `ProtectionCurrentMeasurement` with every phasor field.** Rejected because scalar RMS 50/51 inputs and advanced relay waveforms have different measurement contracts and should not be conflated.
2. **Infer transformer vector compensation from the vector group.** Rejected until winding-side current references, CT connections and phase compensation conventions are modelled and independently validated.
3. **Treat a CT knee-point check as a transient saturation calculation.** Rejected because the present input set does not include DC offset, X/R, remanence, flux history or secondary-loop transient parameters.
