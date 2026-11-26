from __future__ import annotations

import pytest

from power_fault_analyzer.domain.enums.bus_kind import BusKind
from power_fault_analyzer.domain.value_objects.diagnostic import DiagnosticSeverity
from power_fault_analyzer.equipment.sources.equivalent_source import EquivalentSource
from power_fault_analyzer.scripting import ScriptProject


def test_script_project_builds_real_bus_and_explicit_equivalent_source() -> None:
    project = ScriptProject("Substation 60 kV")
    bus = project.add_bus("BUS-101", 60.0, x=500, y=300)
    source = project.add_equivalent_source(
        "GRID-EQUIVALENT",
        bus,
        base_mva=100.0,
        z1_pu=0.08 + 0.24j,
        z2_pu=0.11 + 0.31j,
        z0_pu=0.18 + 0.52j,
    )

    assert isinstance(source, EquivalentSource)
    assert project.network.buses == (bus,)
    assert project.network.equipment == (source,)
    assert project.network.connections[0].terminal_id == source.terminal.id
    assert project.network.connections[0].bus_id == bus.id
    assert project.workspace.diagram_positions[bus.id] == (500.0, 300.0)
    assert project.workspace.diagram_positions[source.id] == (330.0, 180.0)
    assert project.validate() == ()
    assert project.validate(for_calculation=True) == ()
    assert project.render() is project.workspace


def test_script_project_requires_explicit_sequence_impedances() -> None:
    project = ScriptProject("Incomplete network")
    bus = project.add_bus("BUS-1", 13.8, kind=BusKind.BUSBAR)
    with pytest.raises(TypeError):
        project.add_equivalent_source("GRID", bus, base_mva=100.0)  # type: ignore[call-arg]


def test_script_project_rejects_calculation_with_unconnected_equipment() -> None:
    project = ScriptProject("Empty network")
    project.add_bus("BUS-1", 13.8)
    diagnostics = project.validate(for_calculation=True)
    assert any(item.severity is DiagnosticSeverity.ERROR for item in diagnostics)
    with pytest.raises(ValueError, match="Network validation failed"):
        project.assert_valid(for_calculation=True)
