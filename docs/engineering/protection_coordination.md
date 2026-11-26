# ND-009 — Protection coordination and short-circuit duty

## Scope

ND-009 adds a protection-analysis layer on top of the ND-008 short-circuit results. It introduces immutable models for current transformers, phase/earth overcurrent relays, fuse links, circuit-breaker ratings and conductor adiabatic limits. Numerical services calculate relay response, sample time-current coordination, check breaker ratings, check fuse breaking capacity and compare short-circuit Joule energy with a conductor withstand limit.

This increment is a calculation framework, not an automated protection-setting package and not a declaration of compliance with IEC 60255, IEC 60947-2 or IEC 60364. Device tolerances and manufacturer-specific behavior must be supplied or assessed separately.

## Relay model: 50/51

`CurrentTransformerRatio` stores primary and secondary rated currents. Its ratio is

\[
 n_{CT}=\frac{I_{CT,p}}{I_{CT,s}}, \qquad I_s=\frac{I_p}{n_{CT}}.
\]

`OvercurrentRelay` stores its 51 pickup and time multiplier on the CT secondary side. The current supplied to `operate()` is primary amperes. The inverse-time characteristic is evaluated only when the relay current multiple is greater than one:

\[
 M=\frac{I_s}{I_{pickup,s}}>1, \qquad
 t=TMS\frac{k}{M^\alpha-1}.
\]

The supported IEC inverse curve constants are:

| Curve | \(k\) | \(\alpha\) |
|---|---:|---:|
| Standard inverse | 0.14 | 0.02 |
| Very inverse | 13.5 | 1 |
| Extremely inverse | 80 | 2 |
| Long-time inverse | 120 | 1 |

These curve families and constants follow the commonly implemented IEC 60255-151 inverse-time characteristics. The equations do not include manufacturer tolerance bands, minimum operating-time floors, reset behavior, directional polarization, CT saturation or relay firmware-specific logic. See [DEIF Designer's Handbook, standard inverse overcurrent curves](https://deifmarineinstruments-cdn-umbraco-gycff5f5hqdnc0bw.a03.azurefd.net/media/cnjbolnd/ie-250-marine-core-designers-handbook-4189341383-uk.pdf) and [Overcurrent Protection for Phase and Earthfaults](https://elec-engg.com/wp-content/uploads/2021/08/Overcurrent-Protection-for-Phase-and-Earthfaults.pdf).

An optional instantaneous pickup implements a basic 50 stage. When its secondary current threshold is reached, its configured delay supersedes the 51 curve. A zero delay is represented as zero seconds. It is an idealized operation time, not a complete breaker clearing time.

The `function` field labels the current channel as phase or earth. The caller must supply the corresponding current (phase current or residual/ground current) in primary amperes; the model does not infer wiring, summation CT connections or residual calculation from a physical network.

## Fuse model

`FuseLink` requires at least two strictly increasing manufacturer current/time points. Each point carries both pre-arcing time and total-clearing time. Both curves must be non-increasing with current, and total-clearing time cannot be shorter than pre-arcing time.

The interpolation is linear in logarithmic current/logarithmic time coordinates. No values are extrapolated outside the supplied manufacturer range. This is deliberate: a generic gG, aM or other fuse characteristic is not fabricated. Fuse time-current conventions distinguish pre-arcing and total operating/clearing time; see [IEC 60127-1 definitions](https://standards.iteh.ai/catalog/standards/clc/415e3017-2a6a-4f14-bfff-add33168778f/en-iec-60127-1-2024).

The fuse duty check compares operating voltage with rated voltage and prospective symmetrical RMS current with the declared AC breaking capacity. The manufacturer must still confirm utilization category, voltage/frequency applicability, current-limiting let-through and fuse-holder coordination.

## Circuit-breaker duty

`CircuitBreaker` requires an explicit `standard` argument when selecting the breaking-current nameplate field. Two non-interchangeable rating contracts are supported:

| Standard | Voltage domain represented | Required breaking-current field | Optional service field |
|---|---|---|---|
| `IEC_60947_2` | Low-voltage AC, up to 1 kV | `ultimate_breaking_capacity_ka` (Icu) | `service_breaking_capacity_ka` (Ics) |
| `IEC_62271_100` | Three-phase AC systems above 1 kV | `rated_short_circuit_breaking_current_ka` | Not represented as Ics |

The official IEC scope pages are [IEC 60947-2:2024](https://webstore.iec.ch/en/publication/66277) and [IEC 62271-100:2021+AMD1:2024](https://webstore.iec.ch/en/publication/99635). The current model intentionally represents one AC rated voltage per breaker; it does not model the special multi-rated IEC 60947-2 case or DC ratings.

Both families can additionally carry `making_capacity_peak_ka` (Icm), `short_time_withstand_current_ka` and its rated duration (Icw), and opening/arcing times for coordination. Icu/Ics and the IEC 62271 rated breaking current are symmetrical AC RMS nameplate quantities; Icm is a peak making rating. The evaluator compares the IEC study's supported breaking duty against the appropriate standard-specific rated field, compares Ics only where that LV field is provided, compares peak current against Icm, and compares Joule energy against Icw withstand energy. The model does not evaluate transient recovery voltage (TRV), pole scatter, out-of-phase switching, capacitive switching or manufacturer-specific test sequences.

For the Icw comparison this increment uses the Joule integral in kA²s:

\[
 J_{actual}=\int i^2dt, \qquad
 J_{rated}=I_{cw}^2t_{rated}.
\]

Both the energy margin and the actual fault duration relative to the declared Icw duration are checked. If the IEC study does not provide the required peak, breaking or thermal quantity, the corresponding check is `NOT_EVALUATED`; no missing duty is replaced by an assumed value.

The breaker opening and arcing times are user-provided catalog/engineering inputs. The model does not simulate mechanical travel, pole scatter, restrike, TRV, asymmetrical interruption or manufacturer trip-unit tolerances.

## Thermal withstand of conductors

`ConductorThermalLimit` requires a user-supplied conductor cross-section \(S\) in mm² and thermal coefficient \(k\) in A·s½/mm². For the short-duration adiabatic approximation, the allowable Joule integral is

\[
 J_{allow}=k^2S^2.
\]

The evaluator compares the IEC-study Joule integral with this withstand and reports utilization \(J_{actual}/J_{allow}\). It rejects fault durations above 5 s because this simplified adiabatic method is not applicable beyond that declared limit. The coefficient \(k\) is not guessed from material alone: initial/final conductor temperatures, insulation and applicable conductor construction affect it. See [IEC 60364-4-43:2023 Formula (4)](https://previewnorm.com/iec/IEC%2060364-4-43-2023%20PDF.pdf) and [Schneider Electric cable short-circuit withstand guidance](https://www.electrical-installation.org/enwiki/Verification_of_the_withstand_capabilities_of_cables_under_short-circuit_conditions).

## Sensitivity and coordination

The relay sensitivity ratio is

\[
 K_s=\frac{I_{fault,min}}{I_{pickup,primary}}.
\]

The required ratio is an explicit study input; ND-009 does not hard-code a universal design threshold.

For a downstream relay and upstream relay, the sampled coordination margin is

\[
 \Delta t(I)=t_{upstream}(I)-\left[t_{downstream}(I)+t_{CB,clear}\right].
\]

For a fuse downstream of a relay:

\[
 \Delta t(I)=t_{upstream,relay}(I)-t_{fuse,total-clear}(I).
\]

The analyzer evaluates a user-declared current range on a logarithmic grid and compares the minimum sampled margin with a user-declared required interval. The breaker clearing time includes opening plus arcing time. The required interval is not defaulted to a universal value; the engineering margin depends on relay technology, breaker time, CT/relay tolerances and operating practice. For context only, some facility guidance uses 0.3–0.4 s for inverse-time electromechanical coordination, but smaller or larger intervals require a project-specific basis; see [UFC 3-520-01, coordination time intervals](https://www.constructionknowledge.net/public_domain_documents/Div_16_Electrical/Interior_Electrical_Systems_UFC_2002.pdf).

The result is a sampled coordination check, not a mathematical proof over a continuous current domain. Increase `sample_count` around steep curve intersections and compare against approved manufacturer time-current bands before issuing settings.

## Example

```python
from uuid import uuid4

from power_fault_analyzer.domain.enums.protection import IECInverseCurveType, ProtectionFunction
from power_fault_analyzer.domain.value_objects.protection_devices import (
    CircuitBreaker,
    CurrentTransformerRatio,
    OvercurrentRelay,
)
from power_fault_analyzer.infrastructure.protection import ProtectionCoordinationAnalyzer

ct = CurrentTransformerRatio(primary_rated_current_a=600, secondary_rated_current_a=5)
relay = OvercurrentRelay(
    id=uuid4(),
    name="FEEDER-51",
    current_transformer=ct,
    function=ProtectionFunction.PHASE,
    pickup_secondary_a=1.0,
    curve_type=IECInverseCurveType.STANDARD_INVERSE,
    time_multiplier=0.15,
    instantaneous_pickup_secondary_a=8.0,
)
```

## Limitations and next work

ND-009 does not yet automatically place protection devices on the electrical network graph or derive relay currents from a complete protection zone. The study caller supplies through-fault current ranges. Directional 67/67N, differential 87, distance 21, negative-sequence 46, thermal overload 49, motor protection, autoreclosing, breaker-failure 50BF, CT transient saturation, arc-flash energy, manufacturer curve tolerances and optimal setting selection remain outside this increment.
