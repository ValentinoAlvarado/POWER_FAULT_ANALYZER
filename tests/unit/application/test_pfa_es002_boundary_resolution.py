from __future__ import annotations

import json
from dataclasses import replace

import pytest

from power_fault_analyzer.application.use_cases.export_study_report import ExportStudyReport
from power_fault_analyzer.application.use_cases.resolve_substation_boundary import (
    BoundaryResolutionError,
    ResolveLineBoundary,
    ResolveLineBoundaryInput,
    ResolveTransformerBoundary,
    ResolveTransformerBoundaryInput,
)
from power_fault_analyzer.application.use_cases.run_network_short_circuit_study import (
    RunNetworkShortCircuitStudy,
)
from power_fault_analyzer.application.use_cases.substation_engineering import (
    BuildPFAES001Substation,
)
from power_fault_analyzer.domain.enums.equipment_interface import (
    EquipmentInterfaceKind,
    ParameterEvidenceStatus,
)
from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
from power_fault_analyzer.domain.value_objects.neutral_grounding import NeutralGrounding
from power_fault_analyzer.equipment.interfaces.unresolved_equipment import (
    UnresolvedEquipmentInterface,
)
from power_fault_analyzer.equipment.sources.equivalent_source import EquivalentSource
from power_fault_analyzer.equipment.transformers.two_winding_transformer import (
    TwoWindingTransformer,
)
from power_fault_analyzer.equipment.transmission.line import Line
from power_fault_analyzer.infrastructure.adapters.engineering_report_exporter_adapter import (
    EngineeringReportExporterAdapter,
)
from power_fault_analyzer.infrastructure.adapters.sequence_network_set_factory_adapter import (
    SequenceNetworkSetFactoryAdapter,
)
from power_fault_analyzer.infrastructure.adapters.short_circuit_solver_adapter import (
    NumericalShortCircuitSolverAdapter,
)
from power_fault_analyzer.infrastructure.persistence.json_network_document_repository import (
    JSONNetworkDocumentRepository,
)
from power_fault_analyzer.network.sequence_networks.models import SystemBaseSet


def _build_substation():
    return BuildPFAES001Substation().execute().workspace


def _line_spec(workspace) -> ResolveLineBoundaryInput:
    interface = next(
        item
        for item in workspace.network.equipment
        if isinstance(item, UnresolvedEquipmentInterface)
        and item.interface_kind is EquipmentInterfaceKind.TRANSMISSION_LINE
    )
    return ResolveLineBoundaryInput(
        interface_id=interface.id,
        remote_bus_name="GRID-REMOTE-220",
        line_name="L-220-01",
        length_km=18.5,
        frequency_hz=60.0,
        positive_r_ohm_per_km=0.028,
        positive_x_ohm_per_km=0.31,
        negative_r_ohm_per_km=0.031,
        negative_x_ohm_per_km=0.33,
        zero_r_ohm_per_km=0.22,
        zero_x_ohm_per_km=0.92,
        source_name="GRID-TH-REMOTE",
        source_base_mva=100.0,
        source_prefault_voltage_pu=1.0 + 0.0j,
        source_positive_r_pu=0.018,
        source_positive_x_pu=0.19,
        source_negative_r_pu=0.022,
        source_negative_x_pu=0.21,
        source_zero_r_pu=0.065,
        source_zero_x_pu=0.48,
        evidence_reference="TEST FIXTURE ONLY — not real substation data",
    )


def _transformer_spec(workspace) -> ResolveTransformerBoundaryInput:
    interface = next(
        item
        for item in workspace.network.equipment
        if isinstance(item, UnresolvedEquipmentInterface)
        and item.interface_kind is EquipmentInterfaceKind.POWER_TRANSFORMER
    )
    return ResolveTransformerBoundaryInput(
        interface_id=interface.id,
        low_bus_name="BUS-LV-01-60KV",
        transformer_name="TR-220-60-01",
        rated_power_mva=60.0,
        impedance_base_mva=60.0,
        low_rated_voltage_kv=60.0,
        frequency_hz=60.0,
        hv_connection=WindingConnection.STAR,
        lv_connection=WindingConnection.DELTA,
        vector_group_clock=11,
        positive_r_pu=0.006,
        positive_x_pu=0.105,
        negative_r_pu=0.006,
        negative_x_pu=0.105,
        zero_r_pu=0.018,
        zero_x_pu=0.085,
        hv_grounding=NeutralGrounding.solid(),
        lv_grounding=None,
        evidence_reference="TEST FIXTURE ONLY — not real substation data",
    )


def _resolve_complete_workspace():
    workspace = _build_substation()
    line = ResolveLineBoundary().execute(workspace, _line_spec(workspace))
    transformer_spec = _transformer_spec(line.workspace)
    transformer = ResolveTransformerBoundary().execute(line.workspace, transformer_spec)
    return transformer.workspace, line, transformer


def test_line_boundary_is_replaced_by_real_line_and_explicit_remote_source():
    workspace = _build_substation()
    specification = _line_spec(workspace)
    old_terminal_id = (
        next(
            item
            for item in workspace.network.equipment
            if isinstance(item, UnresolvedEquipmentInterface)
            and item.interface_kind is EquipmentInterfaceKind.TRANSMISSION_LINE
        )
        .terminals[0]
        .id
    )

    result = ResolveLineBoundary().execute(workspace, specification)

    assert isinstance(result.equipment, Line)
    assert isinstance(result.external_source, EquivalentSource)
    assert result.equipment.id == specification.interface_id
    assert result.equipment.terminals[0].id == old_terminal_id
    assert result.equipment.terminals[0].designation == "FROM"
    assert (
        result.remote_bus.nominal_voltage
        == workspace.network.get_bus(
            workspace.network.get_connection(old_terminal_id).bus_id
        ).nominal_voltage
    )
    assert result.workspace.network.get_equipment(specification.interface_id) is result.equipment
    assert result.workspace.network.get_connection(old_terminal_id).bus_id in {
        item.id for item in result.workspace.network.buses
    }
    assert not any(
        isinstance(item, UnresolvedEquipmentInterface) and item.id == specification.interface_id
        for item in result.workspace.network.equipment
    )
    assert all(
        item.status is ParameterEvidenceStatus.USER_CONFIRMED
        for item in result.equipment.data_evidence
    )
    assert result.equipment.data_evidence[0].source_reference.startswith("TEST FIXTURE ONLY")
    assert len(result.equipment.terminals) == 2
    assert result.external_source is not None
    assert any(
        item.name == "source_base_voltage_kv" and item.value == 220.0
        for item in result.external_source.data_evidence
    )


def test_transformer_boundary_is_replaced_and_terminal_mapping_identity_is_preserved():
    workspace = _build_substation()
    old_interface = next(
        item
        for item in workspace.network.equipment
        if isinstance(item, UnresolvedEquipmentInterface)
        and item.interface_kind is EquipmentInterfaceKind.POWER_TRANSFORMER
    )
    old_terminal_id = old_interface.terminals[0].id
    mapped_instances = [
        placement
        for placement in workspace.diagram_symbols.values()
        if placement.equipment_id == old_interface.id
    ]

    result = ResolveTransformerBoundary().execute(workspace, _transformer_spec(workspace))

    assert isinstance(result.equipment, TwoWindingTransformer)
    assert result.equipment.id == old_interface.id
    assert result.equipment.terminals[0].id == old_terminal_id
    assert result.equipment.terminals[0].designation == "HV"
    assert result.equipment.vector_group_notation == "YNd11"
    assert result.remote_bus.nominal_voltage.value_kv == 60.0
    assert result.workspace.network.get_connection(old_terminal_id).bus_id == (
        workspace.network.get_connection(old_terminal_id).bus_id
    )
    assert all(
        placement.instance_id in result.workspace.diagram_symbols for placement in mapped_instances
    )
    assert len(result.equipment.data_evidence) >= 15
    assert all(
        item.status is ParameterEvidenceStatus.USER_CONFIRMED
        for item in result.equipment.data_evidence
    )
    assert any(item.name == "x1_pu" for item in result.equipment.data_evidence)


def test_boundary_resolution_is_atomic_when_input_is_invalid():
    workspace = _build_substation()
    before_bus_ids = {item.id for item in workspace.network.buses}
    before_equipment_ids = {item.id for item in workspace.network.equipment}
    specification = _line_spec(workspace)
    invalid = replace(
        specification,
        source_positive_r_pu=0.0,
        source_positive_x_pu=0.0,
    )

    with pytest.raises(ValueError):
        ResolveLineBoundary().execute(workspace, invalid)

    assert {item.id for item in workspace.network.buses} == before_bus_ids
    assert {item.id for item in workspace.network.equipment} == before_equipment_ids


def test_transformer_boundary_rejects_non_integer_vector_clock_without_mutation():
    workspace = _build_substation()
    before = {item.id for item in workspace.network.equipment}
    specification = replace(_transformer_spec(workspace), vector_group_clock=11.5)

    with pytest.raises(ValueError, match="integer from 0 to 11"):
        ResolveTransformerBoundary().execute(workspace, specification)

    assert {item.id for item in workspace.network.equipment} == before


def test_complete_resolved_substation_runs_supported_fault_types_and_exports_report(tmp_path):
    workspace, _, _ = _resolve_complete_workspace()
    network = workspace.network
    sequence_networks = SequenceNetworkSetFactoryAdapter().build_all(
        network, SystemBaseSet.from_network(network, 100.0)
    )
    alias_id = next(
        bus_id
        for bus_id, node_id in sequence_networks.positive.bus_node_map.items()
        if bus_id != node_id
    )
    bus = network.get_bus(alias_id)

    runner = RunNetworkShortCircuitStudy(
        NumericalShortCircuitSolverAdapter(), SequenceNetworkSetFactoryAdapter()
    )
    executions = {}
    for fault_type in FaultType:
        execution = runner.execute(
            network,
            fault_bus_id=bus.id,
            fault_type=fault_type,
            fault_impedance_pu=0.0j,
            base_power_mva=100.0,
            project_name="PFA-ES-002 TEST FIXTURE",
        )
        assert execution.result.maximum_phase_current_ka > 0.0
        assert execution.result.bus_id == bus.id
        assert execution.report.metadata.study_name.startswith("Short-circuit at")
        executions[fault_type] = execution

    assert set(executions[FaultType.SINGLE_LINE_TO_GROUND].result.sequence_currents_pu) == {
        SequenceType.POSITIVE,
        SequenceType.NEGATIVE,
        SequenceType.ZERO,
    }
    assumptions = executions[FaultType.SINGLE_LINE_TO_GROUND].report.assumptions
    assert any("TEST FIXTURE ONLY" in item and "USER_CONFIRMED" in item for item in assumptions)
    assert any("System three-phase base power: 100 MVA" in item for item in assumptions)
    line = next(item for item in network.equipment if isinstance(item, Line))
    transformer = next(
        item for item in network.equipment if isinstance(item, TwoWindingTransformer)
    )
    line_branch = next(item for item in sequence_networks.positive.branches if item.id == line.id)
    transformer_branch = next(
        item for item in sequence_networks.positive.branches if item.id == transformer.id
    )
    # Zbase = 220^2 / 100 = 484 ohm; transformer impedance is converted
    # from its 60 MVA test base to the 100 MVA system base.
    assert line_branch.series_impedance_pu == pytest.approx(complex(0.028, 0.31) * 18.5 / 484.0)
    assert transformer_branch.series_impedance_pu == pytest.approx(
        complex(0.006, 0.105) * (100.0 / 60.0)
    )
    assert any(item.name == "L-220-01" for item in network.equipment)
    assert any(item.name == "TR-220-60-01" for item in network.equipment)
    assert not any(isinstance(item, UnresolvedEquipmentInterface) for item in network.equipment)

    exported = ExportStudyReport(EngineeringReportExporterAdapter()).execute(
        executions[FaultType.SINGLE_LINE_TO_GROUND].report,
        tmp_path,
        include_pdf=True,
        include_excel=True,
    )
    assert exported.json_path.is_file()
    assert exported.pdf_path.is_file()
    assert exported.excel_path.is_file()
    assert exported.csv_paths


def test_schema_13_roundtrip_preserves_line_transformer_and_source_evidence(tmp_path):
    workspace, _, _ = _resolve_complete_workspace()
    path = JSONNetworkDocumentRepository().save(workspace, tmp_path / "pfa-es002.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.5"

    loaded = JSONNetworkDocumentRepository().load(path)
    equipment_by_id = {item.id: item for item in loaded.network.equipment}
    for original in workspace.network.equipment:
        restored = equipment_by_id[original.id]
        if isinstance(original, (Line, TwoWindingTransformer, EquivalentSource)):
            assert restored.data_evidence == original.data_evidence
            assert restored.data_evidence
            assert all(
                item.status is ParameterEvidenceStatus.USER_CONFIRMED
                for item in restored.data_evidence
            )


def test_cannot_resolve_wrong_interface_kind():
    workspace = _build_substation()
    line = next(
        item
        for item in workspace.network.equipment
        if isinstance(item, UnresolvedEquipmentInterface)
        and item.interface_kind is EquipmentInterfaceKind.TRANSMISSION_LINE
    )
    specification = _transformer_spec(workspace)
    wrong = ResolveTransformerBoundaryInput(
        **{
            field: getattr(specification, field)
            for field in specification.__dataclass_fields__
            if field != "interface_id"
        },
        interface_id=line.id,
    )
    with pytest.raises(BoundaryResolutionError):
        ResolveTransformerBoundary().execute(workspace, wrong)
