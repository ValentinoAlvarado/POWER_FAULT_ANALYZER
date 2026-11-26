# ND-004 — Electrical Source Models

## Scope

This increment introduces one-terminal source equipment and explicit contracts for source models. It does **not** implement the fault solver or stamp sources into sequence-network/Y-bus matrices.

## Implemented source families

- `ExternalGrid`: derives positive-sequence impedance magnitude from `U_LL² / S_sc`, decomposes R/X using the declared `R/X` ratio, and converts it to the requested system base. Negative- and zero-sequence impedance data are optional and remain `UNSPECIFIED` when omitted.
- `EquivalentSource`: accepts an explicit `SourceEquivalentSet` and converts all available sequence impedances to a requested base.
- `SynchronousGenerator`: supports separate positive-sequence subtransient, transient and synchronous impedances, plus independent negative- and zero-sequence impedances. The zero-sequence source path is blocked for delta or ungrounded stators. For grounded star/zigzag stators, the physical neutral impedance contribution `3 Zn` is added.
- `InductionGenerator`: supports an explicit initial sequence equivalent and stores a decay time constant. Only the initial/subtransient-like regime is exposed. Time-domain decay is not implemented.
- `ConverterBasedGenerator`: exposes control classification and explicit current limits by sequence. It deliberately does not implement `SourceModelProvider`, because it is not modelled as a fixed Thevenin impedance.

## Sequence availability semantics

`SourceSequenceStatus` distinguishes:

- `AVAILABLE`: an impedance is explicitly available.
- `BLOCKED`: the physical connection/model blocks the sequence path.
- `UNSPECIFIED`: required data have not been supplied.

`UNSPECIFIED` must never be silently interpreted as `BLOCKED`, zero impedance, or equality with positive sequence.

## Base convention

`ElectricalImpedanceBase` uses three-phase apparent power in MVA and line-to-line voltage in kV:

- `Z_base = V_LL_base² / S_3ph_base` in ohms.
- `I_base = S_3ph_base / (sqrt(3) V_LL_base)` in kA.

The legacy public name `TransformerImpedanceBase` remains as a backwards-compatible alias to the generic `ElectricalImpedanceBase`.

## Explicit limitations

- No Y-bus or sequence-network source stamping yet.
- No automatic derivation of generator sequence data from full machine equivalent-circuit test data.
- No induction-machine time-domain decay calculation; only an initial equivalent plus decay-time metadata.
- No converter control-loop simulation or phase-domain current injection; only declared current-capability limits.
- Converter per-unit limits require an explicit current base.
- IEC 60909 correction factors and normative source models are not implemented by this increment.
