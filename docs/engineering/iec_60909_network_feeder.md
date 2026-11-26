# ND-008 — IEC 60909-0:2026 network-feeder short-circuit method

## Standard edition and intent

ND-008 adds a bounded IEC 60909 calculation path on top of the symmetrical-component
solver. The implementation targets IEC 60909-0 Edition 3.0 (2026-07), the current
edition at the time this increment was authored. The standard covers maximum and
minimum bolted short-circuit currents in three-phase AC systems at 50 Hz and 60 Hz.
It includes separate modeling and calculation provisions for network feeders,
rotating machines, converters, breaking current, steady-state current, peak current,
and thermal equivalent current.

**This implementation is not a full IEC 60909 implementation, certification, or
compliance declaration.** It is a single-network-feeder subset with explicit
rejection of unsupported source families and model topologies. Use the licensed
standard and applicable national implementation for design approval and equipment
rating.

## Implemented study class

The supported calculation is a bolted bus fault supplied by exactly one `ExternalGrid`
network-feeder equivalent. The calculator uses the sequence-network Thevenin
impedances already assembled by ND-005 and the fault boundary equations implemented
in ND-006.

The equivalent voltage source is imposed at the fault location through a sequence
voltage override:

\[
E_1=c,\qquad E_2=E_0=0.
\]

The selected voltage factor is returned in `IEC60909StudyResult.voltage_factor`.
For the implemented voltage ranges, the factors are:

| Nominal system voltage | Tolerance choice | \(c_{max}\) | \(c_{min}\) |
|---|---:|---:|---:|
| 0.1 kV to 1.0 kV | 6% | 1.05 | 0.95 |
| 0.1 kV to 1.0 kV | 10% | 1.10 | 0.90 |
| Above 1.0 kV to 420 kV | — | 1.10 | 1.00 |

Below 0.1 kV and above 420 kV are rejected by this implementation. The optional
`equipment_max_voltage_kv` input checks that the selected fault-bus value
\(c U_n\) does not exceed the supplied equipment voltage limit. The engineer must
supply the correct `Um` value for the equipment at the fault location.

## IEC sequence-network assumptions

For the required positive- and negative-sequence networks, branch shunt admittances
of lines/cables and network transformers are removed before the short-circuit solve.
This follows the IEC calculation assumption that these non-rotating equipment shunt
admittances are neglected in the positive- and negative-sequence systems. The
calculator emits `IEC60909-POSITIVE-NEGATIVE-SHUNTS-NEGLECTED` when non-zero branch
shunts were present. Zero-sequence shunt data is retained because its treatment is
topology- and grounding-dependent. The three sequence-network objects are not
mutated; corrected immutable copies are assembled for the study.

## Transformer correction

Two-winding network transformers are corrected in both maximum and minimum studies.
The correction uses \(c_{max}\), even for a minimum-current study, and the
transformer's rated low-voltage winding as the voltage-factor reference:

\[
K_T=\frac{0.95\,c_{max}}{1+0.6x_T},\qquad Z_{TK}=K_T Z_T.
\]

Here \(x_T\) is the positive-sequence rated transformer reactance in per unit on
the transformer nameplate base. The correction is applied to the positive-,
negative- and modeled zero-sequence transformer impedances, including a modeled
zero-sequence grounding shunt. `SequenceBranch` and `SequenceShunt` therefore
retain the transformer reactance and LV rated voltage as explicit metadata.

Three-winding transformer corrections are deliberately rejected. Their correction
and zero-sequence representations need a separate validated three-port model.

## Maximum and minimum cases

The study specification requires an explicit system frequency of 50 Hz or 60 Hz;
there is no silent default. The frequency is used in the DC-component thermal
factor and must match the system represented by the sequence-network data. The
calculator cannot infer it from the sequence-network snapshot, so the study author
is responsible for supplying the correct system frequency.

### Maximum case

The selected `cmax` is applied at the faulted bus. The sequence resistance values
are used as entered. The input line resistance must represent the reference
conductor temperature required by the applicable study. ND-008 does not infer this
temperature from conductor geometry or construction metadata; it emits a warning
asking the engineer to verify it.

### Minimum case

The selected `cmin` is applied at the faulted bus. For the positive- and
negative-sequence networks, `minimum_line_resistance_factor` is mandatory whenever
a required network contains a modeled line or cable. It is the engineer-supplied
ratio

\[
F_{R1,2}=\frac{R_{1,2}(\theta_{end})}{R_{1,2}(input)}.
\]

For a fault requiring zero sequence (A-G or B-C-G), a line in the zero-sequence
network additionally requires `minimum_zero_sequence_line_resistance_factor`:

\[
F_{R0}=\frac{R_0(\theta_{end})}{R_0(input)}.
\]

The zero-sequence factor is separate because earth-return and mutual-impedance
terms are not assumed to follow the positive/negative phase-conductor resistance
temperature ratio. The calculator scales only the corresponding real impedance
part and leaves reactance unchanged. A three-phase fault does not require or inspect
the unused zero-sequence correction. No conductor temperature or resistance factor
is automatically estimated.

`network_feeder_impedance_multiplier` scales the declared external-grid Thevenin
impedance. This is an explicit utility-data adjustment, **not** an IEC correction
factor. Its default is 1.0. A warning is returned for minimum studies when the
source multiplier remains 1.0, reminding the engineer that minimum network-feeder
fault-level data may need to be entered separately.

## Initial, peak, breaking and steady-state currents

`ShortCircuitSolver` calculates the sequence/phase fault solution with the selected
voltage factor and corrected impedances. `initial_symmetrical_current_ka` is the
maximum RMS phase-current magnitude in the result, in kA. The result records the
Clause 7 method reference selected for the requested fault connection: 7.2 for
three-phase, 7.3 for line-to-line, 7.4 for line-to-line with earth, and 7.5 for
line-to-earth.

For a three-phase network-feeder study, the initial, symmetrical breaking and
steady-state RMS currents are treated as equal for the source model classes currently
accepted by the calculator. For multiple-fed three-phase network feeders, the
breaking-current method is identified separately under Clause 9.2 and the steady-state
method under Clause 11.2.6. The single-feeder steady-state method is identified under
Clause 11.2.5:

\[
I_b=I_k=I''_k.
\]

This equality is not transferred to rotating machines or converter/current-source
installations. For unbalanced faults supplied exclusively by network-feeder voltage
sources, the calculator exposes the maximum phase RMS current from the sequence
solution under the Clause 9.3 and 11.3 network-feeder subset. Machine and converter
contributions remain unavailable, and the unbalanced subset still requires independent
comparison against licensed worked examples before any broader conformity claim.

The peak-current calculation remains narrower. It is returned only for a maximum
three-phase fault whose positive-sequence component is radial and has a passive
positive-sequence Thevenin impedance with \(X>0\). The preserved baseline radial factor is:

\[
\kappa=1.02+0.98e^{-3R/X},\qquad i_p=\kappa\sqrt{2}I''_k.
\]

Multiple-fed, meshed and unbalanced peak-current methods are not inferred from this
radial single-fed calculation. Their quantities remain unavailable with diagnostics.

The study may declare `first_pole_contact_separation_time_s`. The value is validated
and preserved for traceability. For one maximum, single-fed, radial, three-phase
network-feeder case, the result may additionally expose an R/X exponential estimate
of the DC envelope and asymmetrical RMS combination. This is stored as a supplementary
engineering estimate, not as a verified IEC 60909-0:2026 Clause 10 result. The normative
`iDC` and `Ibasym` quantities remain marked unavailable until the final-edition Clause 10
equations and applicability conditions are verified.

## Thermal equivalent current

Thermal quantities are returned only for a maximum three-phase fault in the same
supported radial network-feeder class. The implemented far-from-generator
simplification uses \(n=1\) for the AC component and calculates the DC heat factor
\(m\) from the radial peak factor, frequency and fault duration:

\[
m=\frac{e^{4fT_k\ln(\kappa-1)}-1}
        {2fT_k\ln(\kappa-1)},\qquad n=1,
\]

\[
I_{th}=I''_k\sqrt{m+n},\qquad
J=I''_k{}^2(m+n)T_k.
\]

The result reports `thermal_factor_dc=m`, `thermal_factor_ac=n`,
`thermal_equivalent_current_ka=Ith`, and `joule_integral_ka2s=J`. These values are
not returned for minimum studies, unbalanced faults, or meshed positive-sequence
components. The implementation does not calculate the generator-dependent or
converter-dependent forms of the AC heating factor.

## API

```python
from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.iec60909 import (
    IEC60909CurrentCase,
    IEC60909LowVoltageTolerance,
)
from power_fault_analyzer.domain.value_objects.fault_specification import FaultSpecification
from power_fault_analyzer.domain.value_objects.iec60909_study import (
    IEC60909StudySpecification,
)
from power_fault_analyzer.infrastructure.numerical.iec60909 import IEC60909Calculator

study = IEC60909StudySpecification(
    current_case=IEC60909CurrentCase.MAXIMUM,
    fault_duration_s=1.0,
    frequency_hz=60.0,  # Required: match the studied system.
    low_voltage_tolerance=IEC60909LowVoltageTolerance.PERCENT_10,
)
result = IEC60909Calculator().calculate(
    sequence_networks,
    FaultSpecification(FaultType.THREE_PHASE, fault_bus_id, 0.0j),
    system_base,
    study,
)

initial_current_ka = result.initial_symmetrical_current_ka
peak_current_ka = result.peak_current_ka
thermal_equivalent_current_ka = result.thermal_equivalent_current_ka
```

## Explicit exclusions

ND-008 rejects or omits the following rather than inventing missing parameters:

- synchronous- and asynchronous-machine IEC correction models;
- converter current-source contributions and full-size-converter treatment;
- multiple network feeders and multi-fed peak-current methods;
- three-winding transformer IEC correction;
- meshed-network peak-current methods;
- peak and thermal results for unbalanced faults;
- short-circuit faults inside a line or cable (ND-007 remains a non-IEC sequence model);
- arc impedance and full normative DC/asymmetrical-breaking-current procedures;
- protection-device operating curves within this IEC calculator;
- automatic derivation of conductor final temperature, positive/negative and
  zero-sequence resistance correction factors, and utility minimum/maximum
  short-circuit level from external data;
- generator-dependent breaking/steady-state current decay and converter dynamics.

Three-winding transformer zero-sequence modeling remains governed by ND-005's
explicit unsupported-model diagnostic. Converter sources remain nonlinear and are
not treated as Thevenin impedances.

## Validation strategy

Tests include analytical single-bus source cases, selected voltage-factor values,
maximum/minimum current comparison, transformer correction for the minimum case,
minimum line-resistance adjustment, radial peak and thermal formulas, network-feeder
breaking/steady-state quantities for balanced and unbalanced faults, and a supplementary
R/X DC-envelope estimate. They also verify explicit rejection or unavailability for
unsupported source families, converters, multi-fed peak, meshed peak and three-winding
correction cases. The project regression suite runs the complete test tree.

## References

- IEC, *IEC 60909-0:2026, Short-circuit currents in three-phase AC systems — Part 0:
  Calculation of currents*, Edition 3.0, July 2026.
- DIgSILENT PowerFactory FAQ, *Why are the results of Short-Circuit calculation
  depending on Max. Voltage Tolerance?*, describing the 2026 low-voltage factors and
  two-winding transformer correction factor.

This document is an implementation note, not a reproduction of the standard.
