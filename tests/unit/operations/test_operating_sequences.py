from __future__ import annotations

import json
from uuid import uuid4

import pytest

from power_fault_analyzer.operations import (
    BusRecord,
    EquipmentRecord,
    JsonOperationJournal,
    NetworkSnapshot,
    OperatingScenario,
    OperationPermit,
    RestorationPlanner,
    SwitchingSequence,
    SwitchingSequenceError,
    SwitchingSequenceService,
    SwitchingSequenceStatus,
    SwitchingStep,
    SwitchPosition,
    TerminalConnection,
)


def make_snapshot(
    *, parallel_sources: bool = False, grounding_switch: bool = False
) -> tuple[NetworkSnapshot, dict[str, object]]:
    bus_a, bus_b, bus_c = uuid4(), uuid4(), uuid4()
    source_id, line_id, breaker_id = uuid4(), uuid4(), uuid4()
    source_t, line_t1, line_t2, breaker_t1, breaker_t2 = (uuid4() for _ in range(5))
    buses = (
        BusRecord(bus_a, "BUS-A"),
        BusRecord(bus_b, "BUS-B"),
        BusRecord(bus_c, "BUS-C"),
    )
    equipment = [
        EquipmentRecord(source_id, "GRID", (source_t,), is_source=True, family="source"),
        EquipmentRecord(line_id, "LINE-A-B", (line_t1, line_t2), family="transmission"),
        EquipmentRecord(
            breaker_id,
            "CB-B-C",
            (breaker_t1, breaker_t2),
            is_switch=True,
            default_switch_position=SwitchPosition.OPEN,
            family="circuit_breaker",
        ),
    ]
    connections = [
        TerminalConnection(source_t, bus_a),
        TerminalConnection(line_t1, bus_a),
        TerminalConnection(line_t2, bus_b),
        TerminalConnection(breaker_t1, bus_b),
        TerminalConnection(breaker_t2, bus_c),
    ]
    if parallel_sources:
        source_c, source_c_t = uuid4(), uuid4()
        equipment.append(
            EquipmentRecord(source_c, "GRID-C", (source_c_t,), is_source=True, family="source")
        )
        connections.append(TerminalConnection(source_c_t, bus_c))
    ground_id = None
    if grounding_switch:
        ground_id, ground_t = uuid4(), uuid4()
        equipment.append(
            EquipmentRecord(
                ground_id,
                "ES-C",
                (ground_t,),
                is_switch=True,
                default_switch_position=SwitchPosition.OPEN,
                is_grounding_switch=True,
                family="earthing_switch",
            )
        )
        connections.append(TerminalConnection(ground_t, bus_c))
    snapshot = NetworkSnapshot(
        network_id=uuid4(),
        network_name="Test network",
        buses=buses,
        equipment=tuple(equipment),
        connections=tuple(connections),
    )
    return snapshot, {
        "bus_a": bus_a,
        "bus_b": bus_b,
        "bus_c": bus_c,
        "source_id": source_id,
        "line_id": line_id,
        "breaker_id": breaker_id,
        "ground_id": ground_id,
    }


def test_sequence_opens_breaker_without_mutating_network_snapshot() -> None:
    snapshot, ids = make_snapshot()
    before = snapshot.connections
    sequence = SwitchingSequence(
        name="Open CB-B-C",
        steps=(
            SwitchingStep(
                equipment_id=ids["breaker_id"],
                expected_position=SwitchPosition.OPEN,
                target_position=SwitchPosition.CLOSED,
            ),
            SwitchingStep(
                equipment_id=ids["breaker_id"],
                expected_position=SwitchPosition.CLOSED,
                target_position=SwitchPosition.OPEN,
            ),
        ),
    )
    result = SwitchingSequenceService().simulate(snapshot, sequence)
    assert result.status is SwitchingSequenceStatus.COMPLETED
    assert result.completed_steps == 2
    assert result.final_topology.deenergized_bus_ids == frozenset({ids["bus_c"]})
    assert snapshot.connections == before


def test_sequence_detects_stale_expected_position() -> None:
    snapshot, ids = make_snapshot()
    sequence = SwitchingSequence(
        name="Stale operation",
        steps=(
            SwitchingStep(
                equipment_id=ids["breaker_id"],
                expected_position=SwitchPosition.CLOSED,
                target_position=SwitchPosition.OPEN,
            ),
        ),
    )
    result = SwitchingSequenceService().simulate(snapshot, sequence)
    assert result.status is SwitchingSequenceStatus.BLOCKED
    assert result.blocked_step is not None
    assert result.blocked_step.findings[0].code == "EXPECTED_SWITCH_STATE_MISMATCH"


def test_parallel_live_island_close_is_blocked_without_synchronism_reference() -> None:
    snapshot, ids = make_snapshot(parallel_sources=True)
    sequence = SwitchingSequence(
        name="Parallel two live islands",
        steps=(
            SwitchingStep(
                equipment_id=ids["breaker_id"],
                expected_position=SwitchPosition.OPEN,
                target_position=SwitchPosition.CLOSED,
            ),
        ),
    )
    result = SwitchingSequenceService().simulate(snapshot, sequence)
    assert result.status is SwitchingSequenceStatus.BLOCKED
    assert result.blocked_step is not None
    assert (
        result.blocked_step.findings[0].code
        == "PARALLEL_ENERGIZED_ISLANDS_REQUIRE_SYNCHRONISM_EVIDENCE"
    )
    assert result.final_topology.energized_bus_ids == result.initial_topology.energized_bus_ids


def test_parallel_live_island_close_accepts_traceable_synchronism_reference() -> None:
    snapshot, ids = make_snapshot(parallel_sources=True)
    sequence = SwitchingSequence(
        name="Parallel with verified synchronism",
        steps=(
            SwitchingStep(
                equipment_id=ids["breaker_id"],
                expected_position=SwitchPosition.OPEN,
                target_position=SwitchPosition.CLOSED,
            ),
        ),
        permit=OperationPermit(
            operator_id="operator-01",
            authorization_reference="SWITCH-ORDER-2026-001",
            synchronism_check_reference="SYNC-TEST-7781",
        ),
    )
    result = SwitchingSequenceService().simulate(snapshot, sequence)
    assert result.status is SwitchingSequenceStatus.COMPLETED
    assert len(result.final_topology.islands) == 1


def test_ground_switch_close_is_blocked_on_source_reachable_bus() -> None:
    snapshot, ids = make_snapshot(grounding_switch=True)
    scenario = OperatingScenario(
        name="Bus C energized",
        switch_positions={ids["breaker_id"]: SwitchPosition.CLOSED},
    )
    sequence = SwitchingSequence(
        name="Close earth switch",
        initial_scenario=scenario,
        permit=OperationPermit(voltage_absence_test_reference="VOLT-ABS-TEST-01"),
        steps=(
            SwitchingStep(
                equipment_id=ids["ground_id"],
                expected_position=SwitchPosition.OPEN,
                target_position=SwitchPosition.CLOSED,
            ),
        ),
    )
    result = SwitchingSequenceService().simulate(snapshot, sequence)
    assert result.status is SwitchingSequenceStatus.BLOCKED
    assert result.blocked_step.findings[0].code == "GROUND_SWITCH_CLOSE_ON_ENERGIZED_BUS"


def test_ground_switch_close_requires_voltage_absence_reference_even_if_deenergized() -> None:
    snapshot, ids = make_snapshot(grounding_switch=True)
    sequence = SwitchingSequence(
        name="Close earth switch without evidence",
        steps=(
            SwitchingStep(
                equipment_id=ids["ground_id"],
                expected_position=SwitchPosition.OPEN,
                target_position=SwitchPosition.CLOSED,
            ),
        ),
    )
    result = SwitchingSequenceService().simulate(snapshot, sequence)
    assert result.status is SwitchingSequenceStatus.BLOCKED
    assert result.blocked_step.findings[0].code == "GROUND_SWITCH_REQUIRES_VOLTAGE_ABSENCE_EVIDENCE"


def test_ground_switch_closure_on_graph_deenergized_bus_requires_traceable_evidence() -> None:
    snapshot, ids = make_snapshot(grounding_switch=True)
    sequence = SwitchingSequence(
        name="Earth isolated bus C",
        steps=(
            SwitchingStep(
                equipment_id=ids["ground_id"],
                expected_position=SwitchPosition.OPEN,
                target_position=SwitchPosition.CLOSED,
            ),
        ),
        permit=OperationPermit(voltage_absence_test_reference="VOLT-ABS-TEST-02"),
    )
    result = SwitchingSequenceService().simulate(snapshot, sequence)
    assert result.status is SwitchingSequenceStatus.COMPLETED
    assert ids["bus_c"] in result.final_topology.grounded_bus_ids


def test_close_onto_grounded_bus_is_blocked() -> None:
    snapshot, ids = make_snapshot(grounding_switch=True)
    # First close the earth switch on isolated BUS-C in the scenario; then
    # attempt to close the main breaker from energized BUS-B to grounded BUS-C.
    scenario = OperatingScenario(
        name="BUS-C grounded",
        switch_positions={ids["ground_id"]: SwitchPosition.CLOSED},
    )
    sequence = SwitchingSequence(
        name="Do not energize grounded bus",
        initial_scenario=scenario,
        steps=(
            SwitchingStep(
                equipment_id=ids["breaker_id"],
                expected_position=SwitchPosition.OPEN,
                target_position=SwitchPosition.CLOSED,
            ),
        ),
    )
    result = SwitchingSequenceService().simulate(snapshot, sequence)
    assert result.status is SwitchingSequenceStatus.BLOCKED
    assert result.blocked_step.findings[0].code == "CLOSE_ON_GROUNDED_BUS"


def test_out_of_service_switch_cannot_be_operated() -> None:
    snapshot, ids = make_snapshot()
    scenario = OperatingScenario(
        name="Out of service breaker",
        equipment_in_service={ids["breaker_id"]: False},
    )
    sequence = SwitchingSequence(
        name="Operate OOS switch",
        initial_scenario=scenario,
        steps=(
            SwitchingStep(
                equipment_id=ids["breaker_id"],
                expected_position=SwitchPosition.OPEN,
                target_position=SwitchPosition.CLOSED,
            ),
        ),
    )
    result = SwitchingSequenceService().simulate(snapshot, sequence)
    assert result.status is SwitchingSequenceStatus.BLOCKED
    assert result.blocked_step.findings[0].code == "SWITCH_OUT_OF_SERVICE"


def test_unknown_or_non_switch_equipment_is_rejected() -> None:
    snapshot, ids = make_snapshot()
    unknown = SwitchingSequence(
        name="Unknown",
        steps=(SwitchingStep(uuid4(), SwitchPosition.OPEN, SwitchPosition.CLOSED),),
    )
    with pytest.raises(SwitchingSequenceError, match="unknown equipment"):
        SwitchingSequenceService().simulate(snapshot, unknown)
    non_switch = SwitchingSequence(
        name="Line is not a switch",
        steps=(
            SwitchingStep(
                ids["line_id"], SwitchPosition.OPEN, SwitchPosition.CLOSED
            ),
        ),
    )
    with pytest.raises(SwitchingSequenceError, match="not a switching device"):
        SwitchingSequenceService().simulate(snapshot, non_switch)


def test_empty_sequence_is_valid_no_op() -> None:
    snapshot, _ = make_snapshot()
    result = SwitchingSequenceService().simulate(
        snapshot, SwitchingSequence(name="No-op", steps=())
    )
    assert result.status is SwitchingSequenceStatus.COMPLETED
    assert result.completed_steps == 0
    assert result.initial_topology.energized_bus_ids == result.final_topology.energized_bus_ids


def test_sequence_result_is_json_serializable() -> None:
    snapshot, ids = make_snapshot()
    sequence = SwitchingSequence(
        name="JSON result",
        steps=(SwitchingStep(ids["breaker_id"], SwitchPosition.OPEN, SwitchPosition.CLOSED),),
    )
    result = SwitchingSequenceService().simulate(snapshot, sequence)
    encoded = json.dumps(result.to_dict(), allow_nan=False)
    decoded = json.loads(encoded)
    assert decoded["status"] == "completed"
    assert decoded["permit"]["operator_id"] is None


def test_restoration_planner_proposes_closure_to_restore_bus_c() -> None:
    snapshot, ids = make_snapshot()
    scenario = OperatingScenario(
        name="Outage",
        switch_positions={ids["breaker_id"]: SwitchPosition.OPEN},
    )
    plan = RestorationPlanner().propose(snapshot, scenario, target_bus_ids=(ids["bus_c"],))
    assert plan.complete_for_target
    assert plan.restored_bus_ids == (ids["bus_c"],)
    assert len(plan.sequence.steps) == 1
    assert plan.sequence.steps[0].equipment_id == ids["breaker_id"]
    assert plan.sequence.steps[0].target_position is SwitchPosition.CLOSED


def test_restoration_planner_returns_incomplete_proposal_when_no_switch_is_available() -> None:
    snapshot, ids = make_snapshot()
    scenario = OperatingScenario(
        name="Outage without an operable tie",
        switch_positions={ids["breaker_id"]: SwitchPosition.OPEN},
        equipment_in_service={ids["breaker_id"]: False},
    )
    plan = RestorationPlanner().propose(snapshot, scenario, target_bus_ids=(ids["bus_c"],))
    assert not plan.complete_for_target
    assert plan.remaining_deenergized_bus_ids == (ids["bus_c"],)
    assert plan.sequence.steps == ()


def test_restoration_planner_rejects_targets_outside_network() -> None:
    snapshot, _ = make_snapshot()
    with pytest.raises(ValueError, match="unknown buses"):
        RestorationPlanner().propose(snapshot, OperatingScenario("Base"), target_bus_ids=(uuid4(),))


def test_restoration_plan_is_json_serializable() -> None:
    snapshot, ids = make_snapshot()
    scenario = OperatingScenario(
        name="Outage",
        switch_positions={ids["breaker_id"]: SwitchPosition.OPEN},
    )
    plan = RestorationPlanner().propose(snapshot, scenario, target_bus_ids=(ids["bus_c"],))
    data = json.loads(json.dumps(plan.to_dict(), allow_nan=False))
    assert data["simulation_only"] is True


def test_operation_journal_appends_and_reads_records_atomically(tmp_path) -> None:
    snapshot, ids = make_snapshot()
    sequence = SwitchingSequence(
        name="Journal sample",
        steps=(SwitchingStep(ids["breaker_id"], SwitchPosition.OPEN, SwitchPosition.CLOSED),),
    )
    result = SwitchingSequenceService().simulate(snapshot, sequence)
    journal = JsonOperationJournal(tmp_path / "events" / "operations.json")
    journal.append(result)
    journal.append(result)
    records = journal.read_records()
    assert len(records) == 2
    assert journal.export_dict()["record_count"] == 2


def test_operation_journal_rejects_invalid_schema(tmp_path) -> None:
    path = tmp_path / "broken.json"
    path.write_text('{"schema_version": 999, "records": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported operations journal schema"):
        JsonOperationJournal(path).read_records()
