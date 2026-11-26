# ND-006 — Bus short-circuit solver

## Scope

ND-006 calculates bus faults from the positive-, negative- and zero-sequence networks
produced by ND-005. It reduces each required sparse Ybus matrix to the fault-bus
Thevenin equivalent by solving

\[
Y_{bus}V_{pre}=I_N,\qquad Z_{th,kk}=e_k^T Y_{bus}^{-1}e_k.
\]

The calculation uses sparse LU factorization. It does not form a dense inverse of
the network matrix. Only the sequence networks required by a fault type are built
and factorized:

| Fault | Required sequence networks |
|---|---|
| Three-phase | Positive |
| Single-line-to-ground | Positive, negative, zero |
| Line-to-line | Positive, negative |
| Double-line-to-ground | Positive, negative, zero |

This selective requirement is intentional. For example, an unsupported three-winding
zero-sequence model does not prevent a three-phase or line-to-line calculation, but
it does prevent a single-line-to-ground or double-line-to-ground calculation.

## Fault boundary conventions

The first implementation uses canonical fault phases and a bus-level fault location:

- Three-phase: equal per-phase impedance from A, B and C to ground.
- Single-line-to-ground: phase A to ground.
- Line-to-line: impedance directly between phases B and C.
- Double-line-to-ground: phases B and C connected to a common fault junction, with
  one common impedance from that junction to ground.

`FaultSpecification.fault_impedance_pu` is expressed on the three-phase system
base and the line-to-line voltage base of the faulted bus. `from_ohms(...)` converts
physical ohms using \(Z_{base}=V_{LL,base}^2/S_{3\phi,base}\).

## Sequence-domain equations

Let \(E_0,E_1,E_2\) be the prefault sequence voltages at the faulted bus and
\(Z_0,Z_1,Z_2\) the corresponding driving-point Thevenin impedances.

Three-phase fault:

\[
I_1=\frac{E_1}{Z_1+Z_f},\qquad I_2=I_0=0.
\]

Single-line-to-ground fault on phase A:

\[
I_0=I_1=I_2=\frac{E_0+E_1+E_2}{Z_0+Z_1+Z_2+3Z_f}.
\]

Line-to-line fault between B and C:

\[
I_0=0,\qquad I_2=-I_1,\qquad
I_1=\frac{E_1-E_2}{Z_1+Z_2+Z_f}.
\]

Double-line-to-ground fault on B-C-G is solved from the three sequence-current
unknowns using the exact phase-domain boundary conditions: \(I_A=0\),
\(V_B=V_C\), and \(V_B=3Z_fI_0\). This small complex system is solved directly;
it is not approximated by a guessed sequence connection.

The phase quantities are reconstructed with the A-B-C symmetrical-component
transform. Reported phase voltages are line-to-neutral kV and phase currents are kA.
The ground-current result is \(3I_0\) for the two ground-fault types and zero for
the other fault types.

## Numerical and model safeguards

- Sparse Ybus LU factorization remains guarded by sequence-network ERROR diagnostics.
- Singular Ybus matrices and singular fault-boundary equations raise explicit errors.
- Converter-based sources are not silently treated as fixed impedances. If a required
  sequence network contains a converter current-capability source, the solver raises
  `NonlinearSourceCalculationRequiredError`.
- Fault impedance resistance must be non-negative and its components finite.
- The requested bus must exist in the system voltage-base map and in every required
  sequence network.
- The result carries the per-unit fault impedance, system bases, prefault sequence
  voltages, driving-point impedances, sequence currents and voltages, phase currents
  and voltages, and ground current.

## Deliberate limitations

ND-006 solves bolted or impedance bus faults using the supplied sequence equivalents.
It does not yet implement line-interior fault locations, phase-selectable fault
combinations, prefault load-flow voltage profiles, load and motor contributions,
IEC 60909 voltage / impedance correction factors, peak-current factors, DC offset,
arc models, fault clearing, or converter control/current-limit dynamics. No claim of
IEC 60909 compliance should be made from these results. Those are separate engineering
increments and require their own input contracts and validation cases.
