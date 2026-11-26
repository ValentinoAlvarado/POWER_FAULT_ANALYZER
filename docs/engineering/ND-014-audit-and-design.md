# ND-014 — IEC 60909 Calculation Completion

**Status:** Design and implementation audit — not an IEC compliance declaration  
**Baseline:** ND-013, 404 local regression tests reported by the project owner  
**Standard target:** IEC 60909-0:2026, Edition 3.0  

## 1. Purpose

ND-014 extends the existing restricted IEC 60909 network-feeder calculation into a source-aware calculation engine. It must preserve the academic symmetrical-component solver as a separate calculation path and reuse the existing sparse sequence-network infrastructure.

This document records the current code boundary, the missing capabilities, the proposed responsibilities and the validation gates. It deliberately does not specify new normative equations. Formula implementation must be checked against the licensed IEC 60909-0:2026 text and the applicable companion documents before code is written.

## 2. Scope from the project roadmap

ND-014 is expected to cover:

- maximum and minimum short-circuit studies;
- initial symmetrical current `I''k`;
- peak short-circuit current `ip`;
- symmetrical breaking current `Ib`;
- steady-state short-circuit current `Ik`;
- thermal equivalent current `Ith` and Joule integral, when applicable;
- impedance correction factors;
- contributions from motors and generators;
- multiple-fed and meshed-network procedures;
- traceability of all calculation factors and source assumptions.

The 2026 standard's public contents additionally identify equipment modelling for two- and three-winding transformers, synchronous and asynchronous machines, power electronic converters, power-station units, power plants and converter-fed motors. Its calculation sections distinguish single-fed/multiple-fed and balanced/unbalanced cases for peak and breaking-current calculations. These topics must be mapped explicitly to the ND-014 scope before being claimed as implemented.

## 3. Baseline audit

### 3.1 What can be reused

| Existing component | Observed capability | ND-014 treatment |
|---|---|---|
| `network/sequence_networks/models.py` | Immutable positive-, negative- and zero-sequence networks; branches, shunts, multiport elements and mutual coupling | Reuse and extend only where IEC source metadata is missing |
| `infrastructure/numerical/ybus.py` | Sparse Ybus assembly, Norton equivalents for Thevenin sources, source RHS vectors, sparse LU | Reuse as numerical infrastructure |
| `infrastructure/numerical/short_circuit.py` | Four bus-fault sequence-boundary solutions; Thevenin reduction | Preserve as the generic academic / sequence-domain solver |
| `infrastructure/numerical/source_contributions.py` | Source-voltage superposition for linear Thevenin sources; fixed-phasor converter injection solver | Reuse underlying linear algebra, but add a faulted-network IEC contribution model |
| `equipment/sources/synchronous_generator.py` | Positive subtransient/transient/synchronous and negative/zero sequence impedance data | Reuse machine data; add standard-specific operating and correction data only where required |
| `equipment/sources/induction_generator.py` | Initial sequence equivalent and a decay-time-constant datum | Reuse initial model; do not infer missing breaking/steady-state characteristics |
| `equipment/sources/converter_based_generator.py` | Converter current-capability metadata | Do not equate a capability limit or fixed phasor command with the IEC current-source model |
| `equipment/transformers/three_winding_transformer.py` | Three-port sequence-zero model based on explicit input data | Reuse electrical model; add IEC 3-winding correction only after its data contract is specified |

### 3.2 Current IEC implementation boundary

`infrastructure/numerical/iec60909.py` currently:

- accepts bolted faults at physical buses only;
- requires exactly one active positive-sequence network-feeder source;
- accepts only the same single `NETWORK_FEEDER` source in required sequence networks;
- rejects synchronous, asynchronous, explicit-Thevenin and converter-source contributions;
- rejects three-winding transformer IEC correction;
- applies the existing two-winding transformer correction and user-supplied minimum line-resistance ratios;
- computes a radial maximum three-phase peak-current result only;
- returns `Ib = Ik = I''k` only for the existing three-phase single-feeder model class;
- leaves unbalanced breaking/steady-state currents and unsupported peak/thermal cases unavailable with diagnostics.

At the start of the ND-014 audit, `standards/iec60909/models.py`, `correction_factors.py`,
`current_calculation.py` and `scenarios.py` were zero-byte placeholders. ND-014.1 has since
implemented their domain contracts; they do not yet contain normative calculation policies or
current-calculation equations. Most existing calculation policy and orchestration still sits in the
numerical infrastructure module until the staged migration is completed.

### 3.3 Missing equipment/data contracts

- There is no implemented `InductionMotor` entity in `equipment/motors/`.
- Existing `InductionGeneratorParameters` represents an initial equivalent and a decay-time-constant metadata value; it does not, by itself, establish every parameter required for all IEC breaking and steady-state procedures.
- The converter model stores capability limits and control classification. Its fixed-phasor solver is explicitly not a dynamic converter-control model and must not be relabelled as an IEC converter contribution without the required IEC data and rule set.
- The existing source-voltage contribution calculation reconstructs nodal prefault voltage by source. It is not yet a calculation of each source's partial short-circuit current after the fault boundary equations have been applied.
- The current `IEC60909StudyResult` records selected factors and corrected networks, but it does not yet provide a complete clause/factor/input provenance record for every source and every output quantity.

## 4. Architectural decision proposed for ND-014

### 4.1 Separation of responsibilities

`ShortCircuitSolver` remains the generic sequence-domain solver. IEC-specific modelling and calculation rules move into `standards/iec60909/` as pure, testable policies and value objects. Sparse matrix construction and linear-system solution remain in `infrastructure/numerical/`.

The target dependency direction is:

`application use case -> standards.iec60909 policy -> infrastructure numerical ports/adapters -> NumPy/SciPy/NetworkX`

The IEC standard package must not import PySide6, FastAPI, SQLAlchemy or presentation code. It should not contain duplicate sparse-matrix implementations.

### 4.2 Proposed module responsibilities

| Module | Responsibility |
|---|---|
| `standards/iec60909/models.py` | Typed source classifications, current-case data, current contribution records, correction-factor records and immutable calculation-trace models |
| `standards/iec60909/scenarios.py` | Validate maximum/minimum case inputs, topology assumptions, equipment states and required source data; produce an explicit normalized study scenario |
| `standards/iec60909/correction_factors.py` | Pure standard-specific correction policies for network feeders, two-/three-winding transformers, machines and other supported equipment; each factor returns value, inputs and clause provenance |
| `standards/iec60909/current_calculation.py` | Current-quantity strategies for initial, peak, breaking, steady-state and thermal calculations, separated by applicable source/topology/fault class |
| `infrastructure/numerical/iec60909.py` | Compatibility facade/orchestrator: assemble corrected sequence networks, call numerical solvers, delegate to IEC policies, aggregate diagnostics and return results |
| `infrastructure/numerical/source_contributions.py` | Extend only the numerical capability needed to calculate per-source fault contributions in linear voltage-source networks; retain the existing converter fixed-phasor solver as a separate method |

The proposed module names match the existing placeholder files. Public interfaces must be designed before implementation, and the legacy `IEC60909Calculator` call should remain compatible where practical.

### 4.3 Source contribution taxonomy

The implementation must distinguish at least:

1. **Voltage-source contributions:** network feeders and supported rotating-machine equivalents, each with its own sequence data, correction policy and operating case.
2. **Current-source contributions:** converter or power-station-unit contributions represented using the applicable declared current-source data and IEC procedure.
3. **Passive network elements:** lines, cables, transformers, reactors, loads and grounding paths, which shape the sequence networks but are not active source contributions.

The initial current aggregation must preserve complex phasor / sequence relationships. Summing magnitudes indiscriminately is not an acceptable substitute for the required IEC composition procedure.

### 4.4 Topology-aware calculation strategies

Peak-current calculation must select an explicit strategy for the supported case: single-fed three-phase, multiple-fed three-phase or unbalanced fault. A radial-only factor must never be silently applied to a meshed or multiple-fed case.

Breaking-current and steady-state strategies must be selected according to source family and fault class. The existing equality simplification is retained only for the exact source/model class for which it is justified.

Thermal-equivalent current must own the relevant `m` and `n` factor calculation and the Joule integral. Its data dependencies and applicability conditions must be explicit; it must not be inferred from the existing radial three-phase simplification for other classes.

## 5. Proposed staged implementation

### ND-014.1 — IEC domain contracts and traceability

- Define source-family and source-mode classifications for IEC studies.
- Define immutable per-source contribution and factor-provenance value objects.
- Define a normalized maximum/minimum scenario.
- Define result completeness/availability states so unsupported quantities cannot be mistaken for zero.
- Preserve the existing result API through compatibility properties or a controlled migration.

**Acceptance:** unit tests for validation, immutability, missing-data behavior, identifiers, units and source-kind consistency; no changes to electrical results.

### ND-014.2 — Multiple voltage sources and rotating machines

- Support more than one network feeder where the selected IEC method permits it.
- Integrate supported synchronous-machine contributions using dedicated machine data/correction policies.
- Add asynchronous machine data needed for the applicable initial calculation procedures.
- Compute per-source fault contributions under the fault boundary equations, not merely prefault bus-voltage contributions.

**Acceptance:** analytic source-superposition tests, single-source regression equality, multi-source cases and explicit rejection of incomplete machine inputs.

### ND-014.3 — Current-source equipment and three-winding transformer correction

- Add an IEC-specific current-source model for the relevant converter/power-station-unit classes.
- Keep fixed sequence-current commands as a distinct academic/engineering input mode; do not silently use them as an IEC model.
- Add a dedicated induction-motor entity and its IEC input data if the motor calculations are within the accepted ND-014 scope.
- Implement three-winding transformer correction only with the complete required rated/test data and sequence connection model.

**Acceptance:** source-type-specific tests, data completeness diagnostics and no inferred zero-sequence paths.

### ND-014.4 — Peak, breaking, DC and steady-state currents

- Implement the separate applicable peak-current strategies for single-fed, multiple-fed and unbalanced cases.
- Implement source-aware symmetrical breaking-current strategies.
- Implement DC component and unbalanced asymmetrical breaking-current treatment where required by the accepted scope.
- Implement steady-state current strategies for supported synchronous/asynchronous source classes.

**Acceptance:** each strategy has clause-mapped unit tests and source-specific analytical cases; unsupported combinations return explicit unavailable status/diagnostics.

### ND-014.5 — Thermal equivalent current and Joule integral

- Implement the applicable thermal-equivalent-current procedure and factor calculations.
- Record duration, frequency, source class, current waveform assumptions and selected factors.

**Acceptance:** independent calculations of `m`, `n`, `Ith` and Joule integral for the supported classes; boundary/sensitivity tests.

### ND-014.6 — Integration and regression closure

- Integrate the standards policy into the existing calculator facade.
- Run all 404 ND-013 regression tests unchanged, then the new ND-014 suite.
- Run Ruff check, Ruff format and compileall in the developer's Python 3.13 environment.
- Keep ND-016 independent benchmarking as a later formal verification gate; ND-014 unit tests alone do not establish engineering accuracy.

## 6. Required invariants

1. No source contribution may be silently omitted or treated as zero when its model is missing or unspecified.
2. A source's electrical sequence connection and grounding configuration must be reflected in the required sequence networks.
3. Maximum and minimum cases must be constructed explicitly; maximum/minimum are not merely a scalar applied to an otherwise identical source inventory.
4. Network topology and source multiplicity must determine the selected peak-current procedure.
5. Current-source and voltage-source contributions remain distinguishable in stored results and traceability.
6. Each reported output quantity must declare whether it was calculated, unavailable, not applicable or rejected due to missing data.
7. Every correction factor must preserve its numerical value, inputs, unit/base, originating equipment and IEC clause reference.
8. The generic academic solver must remain independent of IEC-specific rules.
9. The existing sequence-network data and calculations must remain immutable during a study; correction procedures create calculation snapshots.
10. A result must identify the exact standard edition and the model assumptions used.

## 7. Verification matrix

| Test group | Required evidence |
|---|---|
| Baseline | All 404 ND-013 tests pass unchanged |
| Per-unit | Equivalent results after base conversion |
| Superposition | Complex contribution reconstruction within a declared numerical tolerance |
| Multiple feeders | Several independent network-feeder sources; no source silently omitted |
| Synchronous machines | Subtransient/transient/synchronous input cases where applicable |
| Asynchronous machines | Initial and time-dependent quantities only when the required data are supplied |
| Converters | IEC current-source contribution distinct from fixed-phasor solver mode |
| Transformers | Two-/three-winding correction, vector group and zero-sequence paths |
| Fault types | Three-phase, line-to-line, line-to-earth and line-to-line-to-earth where the system grounding makes them applicable |
| Topology | Radial, meshed and multiple-fed peak-current strategy selection |
| Thermal | `m`, `n`, `Ith` and Joule integral |
| Traceability | Every applied factor can be reconstructed from recorded inputs and clause metadata |
| Regression | Ruff check, Ruff format, compileall and full Pytest |

## 8. Normative evidence boundary

The official IEC webstore identifies IEC 60909-0:2026 as Edition 3.0, published 2026-07-23, covering low-/high-voltage three-phase AC systems at 50 Hz and 60 Hz. The public contents identify the distinct equipment and current-calculation topic areas mapped above.

This design note uses the public scope, contents and terminology to structure the software. It does not reproduce the standard and does not claim that a formula has been normatively verified. Exact coefficients, applicability rules, exceptions and tables must be checked against the licensed final IEC 60909-0:2026 document and applicable companion material before implementation.

## 9. Exit criteria for ND-014

ND-014 is complete only when:

- each supported source class has a validated IEC model and contribution method;
- each supported fault/topology combination selects the correct calculation strategy;
- maximum and minimum cases are built from explicit study assumptions and equipment states;
- `I''k`, `ip`, `Ib`, `Ik`, `Ith` and Joule integral are produced only where applicable;
- every source contribution and correction factor is traceable;
- unsupported combinations fail safely with actionable diagnostics;
- the ND-013 regression remains green and new analytic tests pass;
- all remaining engineering limitations are documented for ND-016 benchmarking.

A passing test suite is necessary but not sufficient for a declaration of IEC conformity.

## 10. ND-014.1 — Executable domain contracts

The first implementation stage now provides executable, immutable contracts in
`src/power_fault_analyzer/standards/iec60909/`:

- `models.py`: source family/mode, source descriptors and contributions, correction-factor
  evidence, quantity availability and calculation trace records.
- `scenarios.py`: normalized scenario with explicit network identity, fault, base, maximum/minimum
  case, topology class, source inventory, active equipment and assumptions.
- `correction_factors.py`: correction-factor policy protocol, immutable factor set and reference
  validation against the scenario inventory.
- `current_calculation.py`: strategy protocol, validated calculation request and result/method
  consistency checks.

The contracts reject duplicate source/factor identities, sources outside the declared scenario,
sequence currents not declared by the source descriptor, non-finite phasors, invalid units and
ambiguous unavailable quantities. `UNAVAILABLE` and `NOT_APPLICABLE` quantities carry no numeric
value; a calculated zero remains distinguishable from either state.

Example construction (no normative calculation is performed by this example):

```python
from uuid import uuid4

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.iec60909 import IEC60909CurrentCase
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.fault_specification import FaultSpecification
from power_fault_analyzer.domain.value_objects.iec60909_study import IEC60909StudySpecification
from power_fault_analyzer.network.sequence_networks.models import SystemBaseSet
from power_fault_analyzer.standards.iec60909 import (
    IEC60909CurrentCalculationRequest,
    IEC60909CorrectionFactorSet,
    IEC60909SourceContribution,
    IEC60909SourceDescriptor,
    IEC60909SourceFamily,
    IEC60909SourceMode,
    IEC60909StudyScenario,
    IEC60909TopologyClass,
)

bus_id = uuid4()
source_id = uuid4()
scenario_id = uuid4()
source = IEC60909SourceDescriptor(
    source_id=source_id,
    name="GRID-1",
    family=IEC60909SourceFamily.NETWORK_FEEDER,
    mode=IEC60909SourceMode.VOLTAGE_SOURCE,
    active_sequences=frozenset(SequenceType),
    model_reference="external-grid-input:GRID-1",
)
scenario = IEC60909StudyScenario(
    scenario_id=scenario_id,
    network_id=uuid4(),
    fault=FaultSpecification(FaultType.THREE_PHASE, bus_id),
    system_base=SystemBaseSet(100.0, {bus_id: 13.8}),
    study=IEC60909StudySpecification(
        current_case=IEC60909CurrentCase.MAXIMUM,
        fault_duration_s=1.0,
        frequency_hz=50.0,
    ),
    topology_class=IEC60909TopologyClass.RADIAL,
    sources=(source,),
)
contribution = IEC60909SourceContribution(
    source_id=source_id,
    source_name="GRID-1",
    source_family=source.family,
    source_mode=source.mode,
    sequence_currents_ka={SequenceType.POSITIVE: 10.0 + 0.0j},
)
request = IEC60909CurrentCalculationRequest(
    scenario=scenario,
    source_contributions=(contribution,),
    correction_factors=IEC60909CorrectionFactorSet(scenario_id),
)
```

ND-014.1 does not yet calculate `I''k`, `ip`, `Ib`, `Ik` or `Ith`. It establishes and tests the typed
contracts that later clause-mapped strategies will consume. The existing numerical calculator
and its outputs remain unchanged in this stage.


## 11. Post-increment implementation status (2026-11-22)

The original baseline statements above are historical. After ND-014.1 through ND-014.4A, the current implementation has also added a restricted network-feeder subset for unbalanced `Ib` (Clause 9.3) and `Ik` (Clause 11.3), plus a separately identified engineering R/X waveform estimate. The exact current scope, unsupported combinations, and distinction between supplementary output and normative IEC result are maintained in [`docs/standards/ND014_COMPLETION_MATRIX.md`](../standards/ND014_COMPLETION_MATRIX.md).

The current regression baseline after the completion patch is 480 passing tests. A full IEC 60909-0:2026 conformity claim is not supported: source-specific synchronous/asynchronous/converter procedures, multi-fed and unbalanced peak methods, full Clause 10, generalized Clause 14, three-winding correction integration, line-interior IEC methods, and independent benchmark validation remain open.
