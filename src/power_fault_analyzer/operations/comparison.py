"""Scenario-to-scenario operational impact comparison."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from .models import OperatingTopologyResult


@dataclass(frozen=True, slots=True)
class OperatingScenarioComparison:
    baseline_scenario: str
    comparison_scenario: str
    newly_deenergized_bus_ids: tuple[UUID, ...]
    newly_energized_bus_ids: tuple[UUID, ...]
    opened_switch_ids: tuple[UUID, ...]
    closed_switch_ids: tuple[UUID, ...]
    island_count_delta: int
    newly_grounded_bus_ids: tuple[UUID, ...] = ()
    newly_ungrounded_bus_ids: tuple[UUID, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "baseline_scenario": self.baseline_scenario,
            "comparison_scenario": self.comparison_scenario,
            "newly_deenergized_bus_ids": [str(item) for item in self.newly_deenergized_bus_ids],
            "newly_energized_bus_ids": [str(item) for item in self.newly_energized_bus_ids],
            "opened_switch_ids": [str(item) for item in self.opened_switch_ids],
            "closed_switch_ids": [str(item) for item in self.closed_switch_ids],
            "island_count_delta": self.island_count_delta,
            "newly_grounded_bus_ids": [str(item) for item in self.newly_grounded_bus_ids],
            "newly_ungrounded_bus_ids": [str(item) for item in self.newly_ungrounded_bus_ids],
        }


def compare_scenarios(
    baseline: OperatingTopologyResult,
    comparison: OperatingTopologyResult,
) -> OperatingScenarioComparison:
    if baseline.network_id != comparison.network_id:
        raise ValueError("Cannot compare operating scenarios from different physical networks.")
    baseline_equipment = {item.equipment_id: item for item in baseline.equipment}
    comparison_equipment = {item.equipment_id: item for item in comparison.equipment}
    if baseline_equipment.keys() != comparison_equipment.keys():
        raise ValueError("Scenario results do not contain the same equipment identities.")
    baseline_open = baseline.open_switch_ids
    comparison_open = comparison.open_switch_ids
    return OperatingScenarioComparison(
        baseline_scenario=baseline.scenario_name,
        comparison_scenario=comparison.scenario_name,
        newly_deenergized_bus_ids=tuple(sorted(
            baseline.energized_bus_ids - comparison.energized_bus_ids, key=str
        )),
        newly_energized_bus_ids=tuple(sorted(
            comparison.energized_bus_ids - baseline.energized_bus_ids, key=str
        )),
        opened_switch_ids=tuple(sorted(comparison_open - baseline_open, key=str)),
        closed_switch_ids=tuple(sorted(baseline_open - comparison_open, key=str)),
        island_count_delta=len(comparison.islands) - len(baseline.islands),
        newly_grounded_bus_ids=tuple(sorted(comparison.grounded_bus_ids - baseline.grounded_bus_ids, key=str)),
        newly_ungrounded_bus_ids=tuple(sorted(baseline.grounded_bus_ids - comparison.grounded_bus_ids, key=str)),
    )
