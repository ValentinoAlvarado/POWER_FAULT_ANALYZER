"""Offscreen smoke test for the real Qt workbench and REF-3PH-001B network path."""

from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from power_fault_analyzer.application.use_cases.network_workspace import NetworkStudyRecord
from power_fault_analyzer.bootstrap.workbench_container import build_workbench_services
from power_fault_analyzer.interfaces.desktop.workbench.workbench_window import WorkbenchWindow


def main() -> int:
    application = QApplication.instance() or QApplication([])
    services = build_workbench_services()
    window = WorkbenchWindow(services)
    window._load_reference_template()
    application.processEvents()

    if window.project.name != "REF-3PH-001B":
        raise AssertionError("Reference template did not create the expected project.")
    if window.project.study_settings.base_power_mva != 100.0:
        raise AssertionError("Reference project did not preserve the 100 MVA base.")
    if window.project.study_settings.positive_sequence_impedance_pu != 0.08 + 0.24j:
        raise AssertionError("Reference project did not preserve Z1.")
    if len(window.workspace.network.buses) != 1:
        raise AssertionError("Reference network must contain exactly one physical bus.")
    if len(window.workspace.network.equipment) != 1:
        raise AssertionError("Reference network must contain one explicit Thevenin source.")
    if len(window.workspace.network.connections) != 1:
        raise AssertionError("The Thevenin source terminal must be connected to its bus.")

    bus = window.workspace.network.buses[0]
    execution = services.run_network_fault_study.execute(
        window.workspace.network,
        fault_bus_id=bus.id,
        fault_type=window.project.study_settings.fault_type,
        fault_impedance_pu=window.project.study_settings.fault_impedance_pu,
        base_power_mva=window.project.study_settings.base_power_mva,
        project_name=window.project.name,
    )
    current_pu = abs(execution.result.phase_currents_pu[0])
    voltage_pu = abs(execution.result.phase_voltages_pu[0])
    current_ka = abs(execution.result.phase_currents_ka[0])

    if not math.isclose(current_pu, 3.117347105392, rel_tol=1e-10, abs_tol=1e-10):
        raise AssertionError(f"Unexpected REF-3PH-001B current: {current_pu:.12f} p.u.")
    if not math.isclose(voltage_pu, 0.231713481890, rel_tol=1e-10, abs_tol=1e-10):
        raise AssertionError(f"Unexpected REF-3PH-001B voltage: {voltage_pu:.12f} p.u.")
    if not math.isclose(current_ka, 13.042037611997, rel_tol=1e-9, abs_tol=1e-9):
        raise AssertionError(f"Unexpected REF-3PH-001B current: {current_ka:.12f} kA.")

    window.results.display(execution.result, project_name=window.project.name, bus_name=bus.name)
    if window.results.phase_table.rowCount() != 3:
        raise AssertionError("Results workspace did not render all three phase rows.")
    if window.results.sequence_table.rowCount() != 3:
        raise AssertionError("Results workspace did not render all three sequence rows.")

    record = NetworkStudyRecord.create(
        project_name=window.project.name,
        study_name=execution.report.metadata.study_name,
        network_id=window.workspace.network.id,
        fault_bus_id=bus.id,
        fault_bus_name=bus.name,
        result=execution.result,
    )
    window.workspace.record_study(record)
    window._refresh_explorer()

    with tempfile.TemporaryDirectory(prefix="pfa-workbench-smoke-") as directory:
        sidecar = Path(directory) / "REF-3PH-001B.pfa.network.json"
        services.network_document_repository.save(window.workspace, sidecar)
        restored = services.network_document_repository.load(sidecar)
        if len(restored.study_history) != 1:
            raise AssertionError("Network study history did not survive persistence round-trip.")
        if restored.study_history[0].result.phase_currents_pu != execution.result.phase_currents_pu:
            raise AssertionError("Persisted phase currents differ from the executed solver result.")

    window.show()
    application.processEvents()
    if not window.isVisible():
        raise AssertionError("Qt workbench window could not be shown.")
    window.close()
    application.processEvents()
    print(
        "APP-REBOOT-001 Qt smoke test PASS | "
        f"I={current_pu:.12f} p.u. | V={voltage_pu:.12f} p.u. | "
        f"I={current_ka:.12f} kA | phases=3 | sequences=3 | history=persisted"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
