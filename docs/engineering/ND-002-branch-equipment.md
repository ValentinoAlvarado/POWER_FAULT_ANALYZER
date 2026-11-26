# ND-002 — Electrical Branch Modeling

## Scope

This increment introduces a two-terminal branch abstraction and concrete transmission branch models for the balanced three-phase domain.

## Domain contracts

- `BranchEquipmentBase` extends the existing two-terminal equipment base and requires `build_sequence_equivalent(SequenceType)`.
- `SequenceBranchModelProvider` is the structural port consumed by later network builders.
- `BranchEquivalentModel` contains one series impedance and independent shunt admittances at the from/to terminals.

## Parameter conventions

- Series impedance per length: ohm/km, represented by resistance and reactance.
- Shunt admittance per length: S/km, represented by conductance and susceptance.
- Line length: km.
- Reference frequency: Hz.
- Positive, negative, and zero sequence parameters are explicit and independent. No automatic equality `Z2 = Z1` is assumed.

## Supported equivalents

- `SERIES_ONLY`: uses length-scaled series impedance and zero shunt admittance.
- `NOMINAL_PI`: uses length-scaled series impedance and splits total shunt admittance equally between the two terminals.

## Equipment

- `Line`: common line behavior.
- `OverheadLine`: line plus conductor material and bundle count metadata.
- `UndergroundCable`: line plus conductor material, cross-section, insulation and screen-bonding metadata.
- `SeriesReactance`: lumped per-sequence series impedance; it is not scaled by length.

## Explicit non-goals

This increment does not calculate sequence parameters from conductor geometry, soil resistivity, conductor transposition, cable sheath geometry or bonding networks. Those require dedicated geometry and parameter-calculation services. It also does not implement distributed-parameter line models, frequency sweeps, thermal correction, or Y-bus stamping.

## Verification

Unit tests verify value-object validation, sequence independence, length scaling, nominal-pi shunt splitting, series-only behavior, equipment metadata, branch protocol conformance and integration with the `Network` aggregate.
