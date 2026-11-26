# ND-013 — Advanced power-system sequence models

## Scope

ND-013 extends the sequence-network representation with four explicit modelling capabilities:

1. A measured/vendor-derived three-port zero-sequence equivalent for three-winding transformers.
2. Mutual series coupling between parallel line branches in a selected sequence network.
3. Per-source Norton current vectors and linear source-superposition reporting.
4. Fixed, engineer/vendor-supplied sequence-current commands for converter-interfaced sources, validated against the capability registered on the physical equipment.

The increment does not infer missing transformer core/neutral paths, line geometry, or converter-control response.

## Three-winding transformer zero-sequence three-port model

`ThreeWindingZeroSequencePortModel` stores a reciprocal 3×3 impedance matrix in per unit, with port order **(HV, MV, LV)**. It requires:

- the same declared transformer reference base as the pairwise transformer test data;
- a non-empty manufacturer/test/validated-model reference;
- a finite, symmetric and nonsingular matrix;
- a positive-semidefinite real part, as a passivity check.

The matrix is interpreted as a three-port zero-sequence network whose entries already include the effects of the actual winding connections, accessible neutrals, delta circulating-current path and core-return path. It must be derived from manufacturer data, tests, or a separately validated electromagnetic model. ND-013 does not derive it from pairwise leakage impedances and vector groups.

The network builder converts the matrix to the system MVA base. The voltage bases are the rated line-to-line voltages of the HV, MV and LV windings. `SequenceMultiportElement` retains the three port-node IDs and impedance matrix. The sparse Ybus assembler inverts the small 3×3 port matrix and stamps its admittance matrix at those nodes.

If no explicit model is supplied, the previous incomplete-model diagnostic remains: the zero-sequence network is not guessed and cannot be used for a study that requires it.

## Mutual coupling between parallel lines

`SequenceMutualCoupling` references two physical branch IDs, one sequence and a per-unit mutual impedance. For the two series branches, the impedance matrix is

\[
Z_{series}=\begin{bmatrix}Z_1&Z_m\\Z_m&Z_2\end{bmatrix}.
\]

The assembler inverts this 2×2 matrix and stamps it through the two branch incidence vectors. The individual branch series admittances are not stamped a second time; terminal shunt admittances remain at the original physical terminals.

Current restrictions are deliberate:

- both branch IDs must exist in the same sequence model;
- both branches must be classified as lines;
- the two lines must share the same oriented FROM/TO bus pair;
- both branches must have unity taps;
- duplicate coupling pairs are rejected;
- mutual resistance and reactance matrices must be passive positive semidefinite.

The mutual impedance is supplied in per unit on the builder's common system base. The model does not derive it from conductor spacing, transposition, earth resistivity, Carson/Pollaczek parameters, sheath bonding or frequency. Those remain engineering inputs from a geometry/line-constant calculation.

## Multiple Thevenin source contributions

`SparseYBusAssembler` now preserves each non-passive Norton current-injection vector in `YBusMatrix.source_current_injections_pu`, keyed by source equipment UUID. The aggregate right-hand side remains unchanged.

`SourceVoltageContributionCalculator` factorizes the assembled matrix once, solves one right-hand side per independent source, and reports each source's contribution to the open-circuit voltage at a selected bus. It also reports the reconstructed and aggregate bus voltage and the numerical residual:

\[
V_k=\sum_s e_k^T Y^{-1}I_{N,s}.
\]

This is linear source superposition for the declared sequence-network model. It does not by itself add IEC 60909 multi-feed correction factors, source decay, or protection-zone current reconstruction.

## Converter current-source commands

A converter source is still not replaced by a fixed Thevenin impedance. The builder now retains both its declared `ConverterFaultCurrentCapability` and its physical connected-bus ID in each sequence model.

`ConverterSequenceCurrentCommand` requires explicit positive-, negative- and zero-sequence current phasors. `ConverterCurrentInjectionSolver` checks that:

- the command source ID exists in the model;
- the command bus is the registered connected bus;
- the capability object matches the registered equipment data;
- the per-sequence limits are respected;
- the reconstructed phase-current magnitudes respect the overall converter current limit.

It then solves

\[
Y_{seq}V_{seq}=I_{N,seq}+I_{converter,seq}.
\]

For a bus-fault equivalent at node \(k\), the fixed converter phasors are included in the open-circuit equivalent:

\[
V_{th,k}=e_k^T Y^{-1}(I_N+I_{converter}),\qquad
Z_{th,kk}=e_k^T Y^{-1}e_k.
\]

The usual sequence fault-boundary equations are then applied. A nonzero converter command in a sequence that is not part of the selected fault model is rejected rather than silently discarded. This is a fixed-phasor current-command network solver. The command is supplied by the engineer or vendor model and is held constant during the calculation. ND-013 does **not** infer PLL behavior, grid-forming control, active/reactive priority, fault-ride-through logic, current-reference dynamics, sequence-current control, or a closed-loop converter response. This is not an IEC 60909 converter contribution model and does not represent dynamic or voltage-dependent converter behavior.

## API examples

### Explicit three-winding zero-sequence model

```python
port_model = ThreeWindingZeroSequencePortModel(
    base=transformer.pairwise_impedances.base,
    impedance_matrix_pu=(
        (0.12 + 0.35j, 0.015 + 0.04j, 0.01 + 0.025j),
        (0.015 + 0.04j, 0.16 + 0.42j, 0.012 + 0.03j),
        (0.01 + 0.025j, 0.012 + 0.03j, 0.20 + 0.50j),
    ),
    reference="Vendor test report TR3-Z0-2026",
)
```

Pass `zero_sequence_port_model=port_model` to `ThreeWindingTransformer`. The matrix values above are illustrative only; actual values must come from engineering data.

### Mutual coupling

```python
coupling = SequenceMutualCoupling(
    sequence=SequenceType.ZERO,
    first_branch_id=line_1.id,
    second_branch_id=line_2.id,
    mutual_impedance_pu=0.015 + 0.06j,
)
sequence_networks = SequenceNetworkBuilder(
    system_base,
    mutual_couplings=(coupling,),
).build_all(network)
```

### Converter current injection

```python
command = ConverterSequenceCurrentCommand(
    source_id=converter.id,
    bus_id=connected_bus.id,
    capability=converter.fault_current_capability,
    sequence_currents_pu={
        SequenceType.POSITIVE: 0.5 + 0.0j,
        SequenceType.NEGATIVE: 0.1 + 0.0j,
        SequenceType.ZERO: 0.0 + 0.0j,
    },
)
operating_points = ConverterCurrentInjectionSolver().solve_all(
    sequence_networks,
    system_base,
    (command,),
)
```

For a bus-fault study, pass the command to the normal short-circuit entry point:

```python
result = ShortCircuitSolver().solve(
    sequence_networks,
    FaultSpecification(FaultType.SINGLE_LINE_TO_GROUND, fault_bus.id),
    system_base,
    converter_current_commands=(command,),
)
```

The command is held fixed for this calculation. It is not recalculated as the fault voltage changes.

These are examples of data contracts, not universal converter or transformer parameter recommendations.

## Verification

The ND-013 tests cover:

- three-winding zero-sequence port matrix conversion and stamping;
- rejection of non-reciprocal and singular port matrices;
- mutual-coupling matrix stamping and rejection of unsupported branch pairs;
- coupling selection by sequence through `SequenceNetworkBuilder`;
- linear superposition of independent Thevenin sources;
- converter sequence-current injection, residuals, per-sequence/overall current limits, bus-fault solver integration and rejection of mismatched physical bus bindings.

## Explicit exclusions

ND-013 does not include geometry-derived line constants, distributed-parameter lines, untransposed phase-domain coupling matrices, sheath/screen bonding models, three-winding zero-sequence matrix identification, detailed magnetic-core nonlinearity, IEC 60909 multi-feed procedures, induction-machine time-decay trajectories, or dynamic converter-control simulation. Those capabilities require separate physical inputs and solvers.
