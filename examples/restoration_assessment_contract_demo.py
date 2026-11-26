"""Exercise the PFA-OPERATIONS-003 input/output contract with synthetic data.

This is a software contract demonstration, not a numerical power-flow study.
Replace the constructed measurements with results from a validated external
AC load-flow solver before making any engineering decision.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for import_root in (ROOT, ROOT / "src"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from examples.canonical_model_scenarios import build_double_bus_substation
from power_fault_analyzer.operations import (
    ACLoadFlowCaseResult,
    OperatingScenario,
    RestorationAssessmentService,
    RestorationPlanner,
    SwitchingSequenceService,
    SwitchPosition,
    scenario_fingerprint,
)


def main() -> int:
    workspace = build_double_bus_substation()
    network = workspace.network
    coupler = network.get_equipment(next(
        item.id for item in network.equipment if item.name == "BC-01"
    ))
    scenario = OperatingScenario(
        name="Bus-coupler restoration contract demo",
        switch_positions={coupler.id: SwitchPosition.OPEN},
    )
    plan = RestorationPlanner().propose(network, scenario)
    replay = SwitchingSequenceService().simulate(network, plan.sequence)
    if replay.status.value != "completed":
        raise RuntimeError("Synthetic restoration plan did not complete.")

    fingerprint = scenario_fingerprint(network, replay.final_scenario)
    voltages = {bus_id: 1.0 for bus_id in plan.projected_topology.energized_bus_ids}
    base = ACLoadFlowCaseResult(
        case_id="base", network_id=network.id, scenario_fingerprint=fingerprint,
        converged=True, bus_voltages_pu=voltages,
    )
    n1 = ACLoadFlowCaseResult(
        case_id="N-1:ILLUSTRATIVE", network_id=network.id,
        scenario_fingerprint=fingerprint, converged=True,
        bus_voltages_pu=voltages,
    )
    assessment = RestorationAssessmentService().assess(
        network,
        plan,
        base,
        contingency_cases=(n1,),
        required_contingency_case_ids=("N-1:ILLUSTRATIVE",),
    )
    print(json.dumps(assessment.to_dict(), indent=2, ensure_ascii=False))
    print("\nSYNTHETIC CONTRACT DATA ONLY — NOT AN AC LOAD-FLOW VALIDATION")
    return 0 if assessment.status.value == "feasible" else 1


if __name__ == "__main__":
    raise SystemExit(main())
