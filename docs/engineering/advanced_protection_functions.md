# ND-011 — Advanced protection functions

## Scope

ND-011 adds steady-state function models for:

- 87L / 87T two-terminal biased differential protection;
- 67 / 67N directional supervision of an existing 50/51 relay;
- 21 distance protection using phase-ground and phase-phase impedance loops;
- a steady-state AC excitation/burden screening calculation for protection CTs.

These are engineering calculation models, not relay type-test implementations and not a declaration of conformity with the named standards.

## 87L / 87T differential function

`DifferentialProtectionSettings` contains exactly two current sides. Each side declares:

- a unique side identifier;
- rated primary current base;
- CT ratio;
- current polarity, with positive current defined into the protected zone;
- an explicit 3x3 complex phase-compensation matrix.

The function accepts fundamental phase-current phasors in primary amperes and applies the CT conversion, current-base normalization, polarity and compensation matrix. The normalized per-unit differential quantity is the magnitude of the compensated vector sum. Restraint is the arithmetic mean of the compensated side-current magnitudes.

The operating threshold is a two-slope characteristic:

\[
I_{op,threshold}=I_{pickup}+k_1 I_{restraint}
\]

below the declared breakpoint, and

\[
I_{op,threshold}=I_{pickup}+k_1 I_{breakpoint}
+k_2(I_{restraint}-I_{breakpoint})
\]

above it. An optional unrestrained high-set pickup can override second-harmonic blocking. The optional second-harmonic ratio is an input from the relay measurement chain; this increment does not derive harmonics from sampled waveforms.

For transformer differential, the engineer must provide the phase-compensation matrices and current bases. Automatic vector-group compensation, zero-sequence elimination, inrush waveform detection, overexcitation restraint, CT transient-error modelling and three-winding transformer differential are not implemented. The current binding accepts a two-terminal transformer only.

For line differential, both currents must be oriented into the protected line zone. The calculation is the generic two-terminal biased differential principle. IEC 60255-187-1:2021 covers longitudinal restrained/unrestrained differential functions for motors, generators and transformers, and expressly excludes line differential protection. IEC 60255-187-3 for line current differential was still in development at the time of this increment; ND-011 therefore must not be represented as compliance with that draft or a final line-differential standard.

## 67 / 67N directional supervision

`DirectionalOvercurrentSettings` wraps the existing 50/51 `OvercurrentRelay` and adds:

- maximum torque angle (MTA);
- minimum polarizing voltage;
- required forward or reverse direction.

The input is a complex operating-current phasor and a complex polarizing-voltage phasor. The idealized steady-state comparator is:

\[
T=\cos(\angle I_{op}-\angle V_{pol}-MTA)
\]

The sign of the torque determines forward or reverse. If overcurrent pickup does not occur, polarizing voltage is below the declared minimum, current is negligible, or torque is on the characteristic boundary, the directional decision is not asserted. The function does not synthesize the polarizing quantity: phase, positive-sequence, negative-sequence or residual-voltage selection and memory polarization must be provided by the measurement/interface layer.

The calculation does not model voltage memory, cross-polarization, transient polarization, CVT transients, weak-infeed logic or manufacturer directional characteristic tolerances. It is a configurable phasor comparator, not an IEC 60255 performance certification.

## 21 distance function

`DistanceProtectionSettings` contains CT and VT ratios, a residual compensation factor and ordered impedance zones. Supported characteristics are:

- MHO circle defined by a complex reach impedance;
- quadrilateral rectangle defined by explicit R/X boundaries.

The evaluator converts primary phasors to relay-secondary quantities and calculates:

\[
Z_{AG}=\frac{V_A}{I_A+k_0(I_A+I_B+I_C)}
\]

with equivalent expressions for B-G and C-G, and

\[
Z_{AB}=\frac{V_A-V_B}{I_A-I_B}
\]

for phase-phase loops (BC and CA similarly). In the ground-loop expression, the residual current is \(3I_0=I_A+I_B+I_C\); `ground_compensation_factor` is the configured \(k_0\), not \(3k_0\).

Loops below the declared minimum current or voltage are marked not evaluated. The first configured zone containing the apparent impedance is reported for each loop; the fastest reached zone is returned as the relay operation. The user must supply the k0 compensation, CT/VT ratios, zone shapes, reaches and delays.

The current model does not implement phase-selection logic, directional supervision of quadrilateral zones, load encroachment, power-swing blocking, weak-infeed, mutual coupling, line charging compensation, CVT transient response, teleprotection schemes or dynamic relay performance. It is not a complete IEC 60255-121 conformance model.

## CT steady-state excitation screen

`CurrentTransformerPerformanceModel` records CT ratio, secondary winding resistance, complex burden impedance, knee-point voltage, rated frequency and a manufacturer-supplied excitation curve. The screen calculates:

\[
I_s=\frac{I_p}{CTR},\qquad
V_{required}=|I_s(R_{ct}+Z_b)|
\]

and compares the required symmetrical steady-state secondary voltage with the declared knee-point voltage. The excitation current is interpolated log-log only inside the supplied curve domain; no extrapolation is performed.

This is a preliminary AC burden/excitation screen only. The transient status is always `NOT_EVALUATED`: DC offset, system X/R, remanent flux, secondary-loop time constant, fault inception angle, core flux integration and TPX/TPY/TPZ transient performance are not simulated. A `PASS` from this screen is not evidence that the CT will remain unsaturated during an asymmetrical fault. Use complete CT test data and the applicable instrument-transformer standard for a protection design review.

## Network integration

`ProtectionNetworkBuilder.build()` accepts:

- `advanced_function_bindings`: function model, protected equipment, zone and monitored terminal IDs;
- `ct_performance_bindings`: a CT performance model linked to an existing ND-010 overcurrent-relay binding.

The builder validates equipment family, terminal ownership/connectivity and zone membership. Differential functions require a two-terminal matching line/cable or two-winding transformer; distance requires a transmission branch; directional supervision currently accepts a supported transmission or transformer branch. CT performance models must use the same CT ratio as the linked 50/51 relay.

`AdvancedProtectionNetworkAnalyzer` evaluates supplied phasor measurements for each scenario. `expected_to_operate` is an explicit study/test expectation supplied by the engineer, not inferred from fault location alone. This is deliberate: the present network model does not contain enough settings to infer all directional, distance and differential zone reach semantics automatically. Missing inputs return `NOT_EVALUATED`; they are not interpreted as successful protection.

## Standards and public references

- IEC 60255-187-1:2021 — differential protection for motors, generators and transformers: <https://webstore.iec.ch/en/publication/32570>
- IEC 60255-121:2014 — functional requirements for distance protection: <https://webstore.iec.ch/en/publication/1162>
- IEC 60255-167 — directional overcurrent function: draft work item in development at the date of ND-011; see the BSI project timeline: <https://standardsdevelopment.bsigroup.com/projects/2023-02829>
- IEC 60255-187-3 — line-current differential function: work item in development at the date of ND-011; see the BSI project timeline: <https://standardsdevelopment.bsigroup.com/projects/2025-00625>
- IEC 61869-2:2012 — additional requirements for current transformers, including excitation characteristic, knee point, remanence and transient-performance concepts: <https://webstore.iec.ch/en/publication/6050>
