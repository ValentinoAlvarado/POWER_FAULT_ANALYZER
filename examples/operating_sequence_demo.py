"""Demonstrate an operational restoration proposal on a real PFA scenario.

Run from the repository root after installing PFA-OPERATIONS-001 and 002:
    python .\\examples\\operating_sequence_demo.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.canonical_model_scenarios import build_double_bus_substation
from power_fault_analyzer.operations import (
    JsonOperationJournal,
    OperatingScenario,
    RestorationPlanner,
    SwitchingSequenceService,
)


def main() -> int:
    workspace = build_double_bus_substation()
    network = workspace.network
    coupler = next(item for item in network.equipment if item.name == "BC-01")
    initial_connections = network.connections
    initial_position = coupler.position

    outage = OperatingScenario(
        name="Double-bus tie open / restoration study",
        description="Study the open bus-coupler contingency without changing the physical Network.",
    )
    planner = RestorationPlanner()
    proposal = planner.propose(network, outage)

    print("RESTORATION PROPOSAL")
    print(json.dumps(proposal.to_dict(), indent=2, ensure_ascii=False))

    sequence_result = SwitchingSequenceService().simulate(network, proposal.sequence)
    print("\nSEQUENCE SIMULATION")
    print(json.dumps(sequence_result.to_dict(), indent=2, ensure_ascii=False))

    journal = JsonOperationJournal(ROOT / "outputs" / "operations" / "operation_journal.json")
    record = journal.append(sequence_result)
    print(f"\nJOURNAL RECORD: {record.record_id}")
    print(f"PHYSICAL CONNECTIONS PRESERVED: {network.connections == initial_connections}")
    print(f"PHYSICAL COUPLER POSITION PRESERVED: {coupler.position is initial_position}")
    print(f"PROPOSAL TARGETS RESTORED: {proposal.complete_for_target}")
    return 0 if (
        sequence_result.status.value == "completed"
        and network.connections == initial_connections
        and coupler.position is initial_position
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
