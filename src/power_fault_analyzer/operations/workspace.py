"""Application-facing helpers for operating scenarios stored in NetworkWorkspace."""
from __future__ import annotations

from .adapter import network_to_snapshot
from .models import OperatingScenario, OperatingTopologyResult
from .service import OperatingTopologyService


def scenario_from_physical_network(
    network, name: str, *, description: str = ""
) -> OperatingScenario:
    """Capture the current physical switch/availability state as an immutable scenario."""
    snapshot = network_to_snapshot(network)
    return OperatingScenario(
        name=name,
        description=description,
        switch_positions={
            item.equipment_id: item.default_switch_position
            for item in snapshot.equipment
            if item.is_switch and item.default_switch_position is not None
        },
        equipment_in_service={
            item.equipment_id: item.default_in_service for item in snapshot.equipment
        },
        source_enabled={item.equipment_id: True for item in snapshot.equipment if item.is_source},
    )


def analyze_workspace(
    workspace,
    *,
    scenario_id=None,
    service: OperatingTopologyService | None = None,
) -> OperatingTopologyResult:
    """Analyze the active or explicitly selected workspace scenario, read-only."""
    from power_fault_analyzer.application.use_cases.network_workspace import NetworkWorkspace

    if not isinstance(workspace, NetworkWorkspace):
        raise TypeError("workspace must be a NetworkWorkspace.")
    selected_id = workspace.active_operating_scenario_id if scenario_id is None else scenario_id
    if selected_id is None:
        raise ValueError("No active operating scenario is selected.")
    try:
        scenario = workspace.operating_scenarios[selected_id]
    except KeyError as exc:
        raise KeyError(f"Unknown operating scenario '{selected_id}'.") from exc
    snapshot = network_to_snapshot(workspace.network)
    return (service or OperatingTopologyService()).analyze_snapshot(snapshot, scenario)


__all__ = ["analyze_workspace", "scenario_from_physical_network"]
