# PFA-OPERATIONS-003 — AC Restoration Assessment Gate

## Purpose

`RestorationAssessmentService` evaluates a `RestorationPlan` using results supplied by an external AC load-flow engine. It does **not** calculate AC power flow and does not validate the external solver's implementation, numerical conditioning, input provenance or model quality.

The assessment has three outcomes:

- `feasible`: all required cases converged, all required measurements were supplied, and every supplied voltage/loading/generator quantity was within the configured limits;
- `infeasible`: at least one measured quantity violated a configured limit;
- `indeterminate`: required cases or data were missing, a case did not converge, or a case identity/fingerprint did not match.

A known violation takes precedence over missing measurements, so a partially incomplete result can still be `infeasible`.

## Input contract

`ACLoadFlowCaseResult` represents one external case. Use `case_id="base"` for the base case and stable identifiers such as `N-1:LINE-01` for contingencies. Each case carries:

- the exact PFA network UUID;
- the SHA-256 scenario fingerprint;
- convergence status and timezone-aware solve timestamp;
- bus voltages in p.u.;
- branch loading as a percentage of the rating used by the external study;
- generator output and declared minimum/maximum active-power limits in MW.

The fingerprint covers the canonical network's slot-backed state (including equipment parameters and terminals), physical connections, and effective scenario overrides. It deliberately excludes scenario UUID and labels, because a replayed immutable sequence may receive a new scenario UUID without changing electrical state.

Create the fingerprint only after replaying the restoration plan and use it to tag every external case supplied for that plan. Do not reuse a result after changing the physical model, switch overrides, service status, source availability or solver input.

## Example API

```python
from power_fault_analyzer.operations import (
    ACLoadFlowCaseResult,
    RestorationAssessmentService,
    SwitchingSequenceService,
    scenario_fingerprint,
)

# plan is returned by RestorationPlanner.propose(...)
replay = SwitchingSequenceService().simulate(network, plan.sequence)
if replay.status.value != "completed":
    raise RuntimeError("The restoration sequence is blocked")

fingerprint = scenario_fingerprint(network, replay.final_scenario)
expected_buses = plan.projected_topology.energized_bus_ids

# Replace these maps with measurements from the connected AC load-flow engine.
base_case = ACLoadFlowCaseResult(
    case_id="base",
    network_id=network.id,
    scenario_fingerprint=fingerprint,
    converged=True,
    bus_voltages_pu={bus_id: 1.0 for bus_id in expected_buses},
    branch_loading_pct={},
    generator_output_mw={},
    generator_limits_mw={},
)

assessment = RestorationAssessmentService().assess(
    network,
    plan,
    base_case,
    required_branch_ids=(),       # Supply all required monitored branches.
    required_generator_ids=(),    # Supply all required dispatchable generators.
    required_contingency_case_ids=(),  # Supply declared N-1 cases in contingency_cases.
)
print(assessment.to_dict())
```

## Default thresholds

Defaults are 0.95–1.05 p.u. for voltage and 100% for branch loading. They are configurable screening defaults, **not universal planning criteria**. They must be set to the applicable grid code, operating procedure, equipment rating basis and study assumptions. Generator output is checked against the min/max values provided by the external case; no generic generator limits are invented by this package.

## Scope exclusions

The gate does not establish cold-load pickup, transient/dynamic stability, frequency response, voltage stability margins, short-circuit duty, protection coordination, arc-flash exposure, synchronism, grounding safety, field clearances or switching authorization. An N-1 assessment is only as complete as the explicitly declared contingency case identifiers and results. `feasible` means feasible against the supplied measurements and configured checks only.
