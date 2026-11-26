"""Exercise PFA-ES-002 boundary resolution, fault studies and report exports.

All electrical numbers below are deliberately synthetic test fixtures. They are
not representative substation data and must never be used for an actual study.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from power_fault_analyzer.application.use_cases.export_study_report import ExportStudyReport
from power_fault_analyzer.application.use_cases.resolve_substation_boundary import (
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
from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
from power_fault_analyzer.domain.value_objects.neutral_grounding import NeutralGrounding
from power_fault_analyzer.equipment.interfaces.unresolved_equipment import (
    UnresolvedEquipmentInterface,
)
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

_FIXTURE_REFERENCE = "PFA-ES-002 SMOKE FIXTURE ONLY — NOT REAL ELECTRICAL DATA"


def _resolve_boundaries(workspace):
    line_interface = next(
        item
        for item in workspace.network.equipment
        if isinstance(item, UnresolvedEquipmentInterface)
        and item.interface_kind is EquipmentInterfaceKind.TRANSMISSION_LINE
    )
    line = ResolveLineBoundary().execute(
        workspace,
        ResolveLineBoundaryInput(
            interface_id=line_interface.id,
            remote_bus_name="SMOKE-REMOTE-220",
            line_name="SMOKE-LINE-220",
            length_km=10.0,
            frequency_hz=60.0,
            positive_r_ohm_per_km=0.025,
            positive_x_ohm_per_km=0.30,
            negative_r_ohm_per_km=0.025,
            negative_x_ohm_per_km=0.30,
            zero_r_ohm_per_km=0.18,
            zero_x_ohm_per_km=0.85,
            source_name="SMOKE-REMOTE-THEVENIN",
            source_base_mva=100.0,
            source_prefault_voltage_pu=1.0 + 0.0j,
            source_positive_r_pu=0.015,
            source_positive_x_pu=0.18,
            source_negative_r_pu=0.015,
            source_negative_x_pu=0.18,
            source_zero_r_pu=0.05,
            source_zero_x_pu=0.42,
            evidence_reference=_FIXTURE_REFERENCE,
        ),
    )

    transformer_interface = next(
        item
        for item in line.workspace.network.equipment
        if isinstance(item, UnresolvedEquipmentInterface)
        and item.interface_kind is EquipmentInterfaceKind.POWER_TRANSFORMER
    )
    transformer = ResolveTransformerBoundary().execute(
        line.workspace,
        ResolveTransformerBoundaryInput(
            interface_id=transformer_interface.id,
            low_bus_name="SMOKE-BUS-60",
            transformer_name="SMOKE-TRANSFORMER-220-60",
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
            evidence_reference=_FIXTURE_REFERENCE,
        ),
    )
    return transformer.workspace


def main() -> int:
    workspace = BuildPFAES001Substation().execute().workspace
    workspace = _resolve_boundaries(workspace)
    network = workspace.network

    unresolved = [
        item for item in network.equipment if isinstance(item, UnresolvedEquipmentInterface)
    ]
    if unresolved:
        raise AssertionError(f"Unresolved boundary equipment remains: {len(unresolved)}")

    evidence = [
        parameter
        for equipment in network.equipment
        for parameter in getattr(equipment, "data_evidence", ())
    ]
    if not evidence or any(
        item.status is not ParameterEvidenceStatus.USER_CONFIRMED for item in evidence
    ):
        raise AssertionError("Resolved boundary provenance was not retained as USER_CONFIRMED.")
    if any(item.source_reference != _FIXTURE_REFERENCE for item in evidence):
        raise AssertionError("Unexpected evidence reference in fixture model.")

    factory = SequenceNetworkSetFactoryAdapter()
    bases = SystemBaseSet.from_network(network, 100.0)
    networks = factory.build_all(network, bases)
    physical_bus_id = next(
        bus_id for bus_id, node_id in networks.positive.bus_node_map.items() if bus_id != node_id
    )
    runner = RunNetworkShortCircuitStudy(
        NumericalShortCircuitSolverAdapter(),
        factory,
    )
    executions = {}
    for fault_type in FaultType:
        execution = runner.execute(
            network,
            fault_bus_id=physical_bus_id,
            fault_type=fault_type,
            fault_impedance_pu=0.0j,
            base_power_mva=100.0,
            project_name="PFA-ES-002 TEST FIXTURE ONLY",
        )
        if execution.result.bus_id != physical_bus_id:
            raise AssertionError("Physical fault-bus identity was not preserved.")
        if execution.result.maximum_phase_current_ka <= 0.0:
            raise AssertionError(f"Non-positive fault current for {fault_type.value}.")
        if not any(
            "USER_CONFIRMED" in assumption and _FIXTURE_REFERENCE in assumption
            for assumption in execution.report.assumptions
        ):
            raise AssertionError("Study report omitted boundary parameter provenance.")
        executions[fault_type] = execution

    with tempfile.TemporaryDirectory(prefix="pfa_es002_") as folder:
        root = Path(folder)
        document_path = JSONNetworkDocumentRepository().save(
            workspace,
            root / "resolved_substation.json",
        )
        restored = JSONNetworkDocumentRepository().load(document_path)
        restored_equipment = {item.id: item for item in restored.network.equipment}
        if not all(
            restored_equipment[item.id].data_evidence == item.data_evidence
            for item in network.equipment
            if getattr(item, "data_evidence", ())
        ):
            raise AssertionError("JSON persistence lost equipment evidence.")

        exported = ExportStudyReport(EngineeringReportExporterAdapter()).execute(
            executions[FaultType.SINGLE_LINE_TO_GROUND].report,
            root / "reports",
            include_pdf=True,
            include_excel=True,
        )
        required = (exported.json_path, exported.pdf_path, exported.excel_path)
        if any(path is None or not path.is_file() for path in required):
            raise AssertionError("A required study report export was not created.")
        if not exported.csv_paths or any(
            not path.is_file() for path in exported.csv_paths.values()
        ):
            raise AssertionError("CSV result export was not created.")

    print("PFA-ES-002 END-TO-END SMOKE: PASS")
    print("Boundary resolution -> explicit sequence models -> 4 bus-fault types")
    print("-> provenance-bearing report -> JSON persistence -> PDF/XLSX/CSV/JSON export")
    print("Electrical values: TEST FIXTURE ONLY — NOT VALID FOR REAL SUBSTATION STUDIES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
