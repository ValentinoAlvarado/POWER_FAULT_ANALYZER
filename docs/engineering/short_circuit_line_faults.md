# ND-007 — Interior-line short-circuit faults

## Scope

ND-007 extends the ND-006 short-circuit solver from physical buses to an interior
point of a modeled transmission line or underground cable. The user identifies the
line by its equipment UUID and specifies a normalized location measured from the
line's `FROM` terminal:

\[
0 < \lambda < 1,\qquad d_{FROM}=\lambda L,\qquad d_{TO}=(1-\lambda)L.
\]

The two endpoints are excluded. A fault at an endpoint is represented as a bus fault
using the ND-006 `FaultSpecification`.

## Domain and topology model

`SequenceBranch.length_km` carries physical line length into each sequence-network
model. `SequenceNetworkBuilder` sets this metadata only when the equipment is a
`Line` or a subclass, including `OverheadLine` and `UndergroundCable`. A lumped
`SeriesReactance` and transformer branch have no such metadata and are not accepted
as an interior-fault target.

`LineFaultSpecification` contains:

- `fault_type`: one of the four ND-006 fault categories;
- `branch_id`: the line/cable equipment UUID;
- `fraction_from`: location fraction measured from `FROM`;
- `fault_impedance_pu`: complex fault impedance on the local three-phase base.

The `from_ohms(...)` factory converts physical impedance using the voltage base
shared by the two line terminals.

The solver does not mutate the input sequence networks. It creates an immutable
copy for each sequence network required by the selected fault, inserts a deterministic
internal fault node, and replaces the original branch with two series sections:

\[
Z_{LEFT}=\lambda Z_{LINE},\qquad
Z_{RIGHT}=(1-\lambda)Z_{LINE}.
\]

Both sections retain unity tap. The original nominal-\(\pi\) terminal shunts remain
at the physical line terminals and are not moved to the internal fault point. This
preserves the exact ND-005 pre-fault lumped branch equivalent when the internal
fault injection is zero. This is a split of the existing lumped model, not a
frequency-dependent distributed-parameter line model.

Only the sequence networks required by the fault type are split and factorized:

| Fault | Required sequence networks |
|---|---|
| Three-phase | Positive |
| A-G | Positive, negative, zero |
| B-C | Positive, negative |
| B-C-G | Positive, negative, zero |

A missing or incomplete unused sequence network does not block a fault that does
not depend on it, matching the ND-006 solver policy.

## Numerical solution

ND-007 reuses `ShortCircuitSolver` at the generated internal node. The existing
sparse Ybus is assembled after splitting the selected branch, and sparse LU is used
to obtain the fault-node Thevenin equivalents and solve the sequence fault boundary
conditions.

After the sequence fault currents are known, the full sequence voltage profile is
recovered from the modified network:

\[
Y_{seq}V_{seq}=I_{N,seq}-e_f I_{seq,f},
\]

where \(e_f\) is a unit vector at the internal fault node and \(I_{seq,f}\) is the
sequence current delivered into the fault. No dense inverse of Ybus is formed.

For unity-tap line sections, the currents directed from each physical bus into the
line are:

\[
I_{FROM}=\frac{V_{FROM}-V_f}{Z_{LEFT}}+Y_{sh,FROM}V_{FROM},
\]

\[
I_{TO}=\frac{V_{TO}-V_f}{Z_{RIGHT}}+Y_{sh,TO}V_{TO}.
\]

The existing terminal shunt currents are included. Current directions at both ends
are defined into the line; therefore, their complex values are not assumed to have
opposite signs. Sequence voltages/currents are transformed into A-B-C phase values.

## Usage

```python
from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.value_objects.line_fault_specification import (
    LineFaultSpecification,
)
from power_fault_analyzer.infrastructure.numerical.line_fault import LineFaultSolver

location = LineFaultSpecification(
    fault_type=FaultType.THREE_PHASE,
    branch_id=line_equipment_id,
    fraction_from=0.35,
    fault_impedance_pu=0.0j,
)
study = LineFaultSolver().solve(sequence_networks, location, system_base)

# Both current tuples use A-B-C order and point from the bus into the line.
from_end_current_ka = study.from_terminal.phase_currents_into_line_ka
to_end_current_ka = study.to_terminal.phase_currents_into_line_ka
fault_phase_current_ka = study.fault_result.phase_currents_ka
```

## Results

`LineFaultStudyResult` contains the ND-006 `ShortCircuitResult` at the generated
fault node and two `LineTerminalState` objects. For each line terminal, the result
contains:

- sequence voltage and current into the line in p.u.;
- phase voltages in p.u. and line-to-neutral kV;
- phase currents into the line in p.u. and kA;
- local voltage and current base quantities.

The top-level result also reports the physical line length, normalized fault
position, distance from `FROM`, distance from `TO`, endpoint bus UUIDs and fault-node
UUID.

## Validation and safeguards

- Only branches with declared physical line length can be selected.
- The branch must be present exactly once in each required sequence network.
- Required-sequence copies must agree on physical endpoints and line length.
- Both terminal buses must have configured and equal voltage bases.
- A non-unity tap is rejected; transformer taps are not interpreted as line length.
- Fault position must be finite and strictly inside the line.
- Existing ND-006 diagnostics, singularity guards and converter nonlinear-source
  restrictions remain active.
- Input sequence networks are immutable and remain unchanged after the study.

## Deliberate limitations

ND-007 uses the supplied lumped series impedance split linearly with physical
length. It does not calculate distributed-parameter propagation, earth-return
impedance from geometry, mutual coupling among parallel circuits, sheath/screen
bonding networks, transposition sections, faults between cable conductors, arbitrary
faulted phase pairs, arc dynamics, prefault load-flow profiles, load/motor
contributions, IEC 60909 correction factors or converter current-limit dynamics.
It is not an IEC 60909-compliant calculation engine.
