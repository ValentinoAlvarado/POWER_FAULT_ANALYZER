"""PySide6 main window for the first executable PFA project workspace."""

from __future__ import annotations

import cmath
import math
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from power_fault_analyzer.bootstrap.desktop_container import DesktopApplicationServices
from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.projects.models import Project, TheveninStudySettings
from power_fault_analyzer.interfaces.desktop.view_models import (
    phase_result_rows,
    sequence_result_rows,
)


class MainWindow(QMainWindow):
    """Desktop workspace wired to application use cases and existing PFA adapters."""

    def __init__(self, services: DesktopApplicationServices) -> None:
        super().__init__()
        self._services = services
        self._project: Project | None = None
        self._project_path: Path | None = None
        self._last_execution = None
        self._dirty = False
        self.setWindowTitle("POWER_FAULT_ANALYZER — Engineering Workspace")
        self.resize(1280, 820)
        self._build_actions()
        self._build_layout()
        self._set_project(self._services.project_workspace.create("REF-3PH-001B Project"), None)
        self.statusBar().showMessage("Ready — Thevenin bus-fault study workspace")

    def _build_actions(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self.new_action = QAction("New Project", self)
        self.new_action.setShortcut("Ctrl+N")
        self.new_action.triggered.connect(self._new_project)
        file_menu.addAction(self.new_action)

        self.open_action = QAction("Open Project…", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.triggered.connect(self._open_project)
        file_menu.addAction(self.open_action)

        self.save_action = QAction("Save Project", self)
        self.save_action.setShortcut("Ctrl+S")
        self.save_action.triggered.connect(self._save_project)
        file_menu.addAction(self.save_action)

        self.save_as_action = QAction("Save Project As…", self)
        self.save_as_action.setShortcut("Ctrl+Shift+S")
        self.save_as_action.triggered.connect(self._save_project_as)
        file_menu.addAction(self.save_as_action)
        file_menu.addSeparator()

        self.close_project_action = QAction("Close Project", self)
        self.close_project_action.triggered.connect(self._close_project)
        file_menu.addAction(self.close_project_action)
        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Alt+F4")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        study_menu = self.menuBar().addMenu("&Study")
        self.run_action = QAction("Run Fault Study", self)
        self.run_action.setShortcut("F5")
        self.run_action.triggered.connect(self._run_study)
        study_menu.addAction(self.run_action)

        self.export_action = QAction("Export Report…", self)
        self.export_action.setShortcut("Ctrl+E")
        self.export_action.setEnabled(False)
        self.export_action.triggered.connect(self._export_report)
        study_menu.addAction(self.export_action)

        toolbar = self.addToolBar("Workspace")
        toolbar.setMovable(False)
        toolbar.addAction(self.new_action)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)
        toolbar.addSeparator()
        toolbar.addAction(self.run_action)
        toolbar.addAction(self.export_action)

    def _build_layout(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        self.project_heading = QLabel("REF-3PH-001B Project")
        self.project_heading.setObjectName("projectHeading")
        self.project_heading.setStyleSheet("font-size: 20px; font-weight: 650;")
        root.addWidget(self.project_heading)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_project_tab()
        self._build_results_tab()
        self._build_history_tab()
        self.setCentralWidget(central)
        self.setStyleSheet(
            "QMainWindow { background: #f5f7fa; }"
            "QTabWidget::pane { background: white; border: 1px solid #d7dde5; }"
            "QLineEdit, QDoubleSpinBox, QComboBox, QTextEdit { padding: 5px; }"
            "QPushButton { padding: 7px 14px; }"
            "QTableWidget { gridline-color: #e2e7ed; }"
        )

    def _build_project_tab(self) -> None:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(10)

        self.project_name = QLineEdit()
        self.project_description = QTextEdit()
        self.project_description.setFixedHeight(62)
        self.study_name = QLineEdit()
        self.bus_name = QLineEdit()
        form.addRow("Project name", self.project_name)
        form.addRow("Description", self.project_description)
        form.addRow("Study name", self.study_name)
        form.addRow("Faulted bus label", self.bus_name)

        self.fields: dict[str, QDoubleSpinBox] = {}
        definitions = (
            ("base_power_mva", "System base power (MVA)", 100.0, 0.000001, 1_000_000.0),
            ("base_voltage_ll_kv", "Bus base voltage L-L (kV)", 13.8, 0.000001, 1_000_000.0),
            ("e1_real", "Prefault E1 real (p.u.)", 1.02, -1_000_000.0, 1_000_000.0),
            ("e1_imag", "Prefault E1 imaginary (p.u.)", 0.025, -1_000_000.0, 1_000_000.0),
            ("z1_real", "Z1 resistance (p.u.)", 0.08, 0.0, 1_000_000.0),
            ("z1_imag", "Z1 reactance (p.u.)", 0.24, -1_000_000.0, 1_000_000.0),
            ("z2_real", "Z2 resistance (p.u.)", 0.11, 0.0, 1_000_000.0),
            ("z2_imag", "Z2 reactance (p.u.)", 0.31, -1_000_000.0, 1_000_000.0),
            ("z0_real", "Z0 resistance (p.u.)", 0.18, 0.0, 1_000_000.0),
            ("z0_imag", "Z0 reactance (p.u.)", 0.52, -1_000_000.0, 1_000_000.0),
            ("zf_real", "Fault resistance Rf (p.u.)", 0.025, 0.0, 1_000_000.0),
            ("zf_imag", "Fault reactance Xf (p.u.)", 0.07, -1_000_000.0, 1_000_000.0),
        )
        for key, label, default, minimum, maximum in definitions:
            widget = QDoubleSpinBox()
            widget.setRange(minimum, maximum)
            widget.setDecimals(9)
            widget.setSingleStep(0.01)
            widget.setValue(default)
            widget.valueChanged.connect(self._mark_dirty)
            self.fields[key] = widget
            form.addRow(label, widget)

        self.fault_type = QComboBox()
        self._fault_labels = {
            FaultType.THREE_PHASE: "Three-phase balanced",
            FaultType.SINGLE_LINE_TO_GROUND: "Single line-to-ground (A-G)",
            FaultType.LINE_TO_LINE: "Line-to-line (B-C)",
            FaultType.DOUBLE_LINE_TO_GROUND: "Double line-to-ground (B-C-G)",
        }
        for fault_type, label in self._fault_labels.items():
            self.fault_type.addItem(label, fault_type.value)
        form.addRow("Fault classification", self.fault_type)
        scroll.setWidget(form_widget)
        page_layout.addWidget(scroll, 1)

        note = QLabel(
            "Model scope: one bus represented by explicit sequence Thevenin equivalents. "
            "This is not yet a multi-bus Network Editor."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #5f6b7a; padding: 6px;")
        page_layout.addWidget(note)
        self.tabs.addTab(page, "Project & Study")

        for widget in (self.project_name, self.study_name, self.bus_name, self.project_description):
            widget.textChanged.connect(self._mark_dirty)
        self.fault_type.currentIndexChanged.connect(self._mark_dirty)

    def _build_results_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.result_summary = QLabel("No study executed in this session.")
        self.result_summary.setWordWrap(True)
        self.result_summary.setStyleSheet("font-weight: 600; padding: 5px;")
        layout.addWidget(self.result_summary)

        layout.addWidget(QLabel("Phase quantities — A, B, C"))
        self.phase_table = QTableWidget(0, 9)
        self.phase_table.setHorizontalHeaderLabels(
            [
                "Phase",
                "|I| p.u.",
                "∠I °",
                "|I| kA",
                "|V| p.u.",
                "∠V °",
                "|V| kV L-N",
                "I real p.u.",
                "I imag p.u.",
            ]
        )
        self.phase_table.horizontalHeader().setStretchLastSection(True)
        self.phase_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.phase_table, 2)

        layout.addWidget(QLabel("Symmetrical-component quantities"))
        self.sequence_table = QTableWidget(0, 7)
        self.sequence_table.setHorizontalHeaderLabels(
            ["Sequence", "|I| p.u.", "∠I °", "|V| p.u.", "∠V °", "|Zth| p.u.", "∠Zth °"]
        )
        self.sequence_table.horizontalHeader().setStretchLastSection(True)
        self.sequence_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.sequence_table, 1)

        self.trace_text = QTextEdit()
        self.trace_text.setReadOnly(True)
        self.trace_text.setMaximumHeight(125)
        layout.addWidget(self.trace_text)
        self.tabs.addTab(page, "Results")

    def _build_history_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.history_table = QTableWidget(0, 6)
        self.history_table.setHorizontalHeaderLabels(
            ["Study", "Executed (UTC)", "Fault type", "Base MVA", "Base kV", "|IA| p.u."]
        )
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.cellDoubleClicked.connect(self._show_history_details)
        layout.addWidget(self.history_table)
        self.tabs.addTab(page, "Study History")

    def _settings_from_form(self) -> TheveninStudySettings:
        def number(key: str) -> float:
            return self.fields[key].value()

        return TheveninStudySettings(
            bus_name=self.bus_name.text().strip(),
            study_name=self.study_name.text().strip(),
            base_power_mva=number("base_power_mva"),
            base_voltage_ll_kv=number("base_voltage_ll_kv"),
            prefault_positive_voltage_pu=complex(number("e1_real"), number("e1_imag")),
            positive_sequence_impedance_pu=complex(number("z1_real"), number("z1_imag")),
            negative_sequence_impedance_pu=complex(number("z2_real"), number("z2_imag")),
            zero_sequence_impedance_pu=complex(number("z0_real"), number("z0_imag")),
            fault_type=FaultType(self.fault_type.currentData()),
            fault_impedance_pu=complex(number("zf_real"), number("zf_imag")),
        )

    def _set_project(self, project: Project, path: Path | None) -> None:
        self._project = project
        self._project_path = path
        settings = project.study_settings
        self.project_name.setText(project.name)
        self.project_description.setPlainText(project.description)
        self.study_name.setText(settings.study_name)
        self.bus_name.setText(settings.bus_name)
        values = {
            "base_power_mva": settings.base_power_mva,
            "base_voltage_ll_kv": settings.base_voltage_ll_kv,
            "e1_real": settings.prefault_positive_voltage_pu.real,
            "e1_imag": settings.prefault_positive_voltage_pu.imag,
            "z1_real": settings.positive_sequence_impedance_pu.real,
            "z1_imag": settings.positive_sequence_impedance_pu.imag,
            "z2_real": settings.negative_sequence_impedance_pu.real,
            "z2_imag": settings.negative_sequence_impedance_pu.imag,
            "z0_real": settings.zero_sequence_impedance_pu.real,
            "z0_imag": settings.zero_sequence_impedance_pu.imag,
            "zf_real": settings.fault_impedance_pu.real,
            "zf_imag": settings.fault_impedance_pu.imag,
        }
        for key, value in values.items():
            self.fields[key].setValue(value)
        index = self.fault_type.findData(settings.fault_type.value)
        self.fault_type.setCurrentIndex(max(index, 0))
        self._dirty = False
        self._last_execution = None
        self._clear_results()
        self._refresh_history()
        self._update_title()

    def _capture_project(self) -> Project:
        if self._project is None:
            raise RuntimeError("No project is open.")
        settings = self._settings_from_form()
        name = self.project_name.text().strip()
        if not name:
            raise ValueError("Project name cannot be empty.")
        return replace(
            self._project,
            name=name,
            description=self.project_description.toPlainText().strip(),
        ).with_settings(settings)

    def _new_project(self) -> None:
        if not self._confirm_discard_changes():
            return
        project = self._services.project_workspace.create("Untitled Project")
        self._set_project(project, None)
        self._dirty = True
        self._update_title()
        self.statusBar().showMessage("New project created", 5000)

    def _open_project(self) -> None:
        if not self._confirm_discard_changes():
            return
        selected, _ = QFileDialog.getOpenFileName(
            self, "Open PFA Project", str(Path.home()), "PFA Project (*.pfa)"
        )
        if not selected:
            return
        try:
            project = self._services.project_workspace.open(selected)
            self._set_project(project, Path(selected))
            self.statusBar().showMessage(f"Opened {selected}", 5000)
        except (OSError, TypeError, ValueError) as exc:
            QMessageBox.critical(self, "Open project failed", str(exc))

    def _save_project(self) -> bool:
        if self._project_path is None:
            return self._save_project_as()
        try:
            project = self._capture_project()
            saved_path = self._services.project_workspace.save(project, self._project_path)
            self._project = project
            self._project_path = saved_path
            self._dirty = False
            self._update_title()
            self.statusBar().showMessage(f"Project saved: {saved_path}", 5000)
            return True
        except (OSError, TypeError, ValueError) as exc:
            QMessageBox.critical(self, "Save project failed", str(exc))
            return False

    def _save_project_as(self) -> bool:
        selected, _ = QFileDialog.getSaveFileName(
            self, "Save PFA Project", str(Path.home() / "New Project.pfa"), "PFA Project (*.pfa)"
        )
        if not selected:
            return False
        try:
            project = self._capture_project()
            saved_path = self._services.project_workspace.save(project, selected)
            self._project = project
            self._project_path = saved_path
            self._dirty = False
            self._update_title()
            self.statusBar().showMessage(f"Project saved: {saved_path}", 5000)
            return True
        except (OSError, TypeError, ValueError) as exc:
            QMessageBox.critical(self, "Save project failed", str(exc))
            return False

    def _close_project(self) -> None:
        if not self._confirm_discard_changes():
            return
        self._project = None
        self._project_path = None
        self._last_execution = None
        self._dirty = False
        self._clear_results()
        self.history_table.setRowCount(0)
        self.project_heading.setText("No project open")
        self._update_title()
        self.run_action.setEnabled(False)
        self.save_action.setEnabled(False)
        self.save_as_action.setEnabled(False)
        self.tabs.setEnabled(False)
        self.statusBar().showMessage("Project closed", 5000)

    def _confirm_discard_changes(self) -> bool:
        if not self._dirty:
            return True
        choice = QMessageBox.question(
            self,
            "Unsaved changes",
            "The project has unsaved changes. Save before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return False
        if choice == QMessageBox.StandardButton.Save:
            return self._save_project()
        return True

    def _run_study(self) -> None:
        try:
            project = self._capture_project()
            execution = self._services.run_fault_study.execute(project)
            self._project = execution.project
            self._last_execution = execution
            if self._project_path is not None:
                self._project_path = self._services.project_workspace.save(
                    self._project, self._project_path
                )
            self._dirty = self._project_path is None
            self._display_execution(execution)
            self.export_action.setEnabled(True)
            self._refresh_history()
            self.tabs.setCurrentIndex(1)
            self._update_title()
            self.statusBar().showMessage("Fault study completed using ShortCircuitSolver", 7000)
        except (ArithmeticError, OSError, RuntimeError, TypeError, ValueError) as exc:
            QMessageBox.critical(self, "Fault study failed", str(exc))

    def _display_execution(self, execution) -> None:
        result = execution.result
        self.phase_table.setRowCount(0)
        for row in phase_result_rows(result):
            row_index = self.phase_table.rowCount()
            self.phase_table.insertRow(row_index)
            for column, value in enumerate(row):
                self.phase_table.setItem(row_index, column, _table_item(value))

        self.sequence_table.setRowCount(0)
        for row in sequence_result_rows(result):
            row_index = self.sequence_table.rowCount()
            self.sequence_table.insertRow(row_index)
            for column, value in enumerate(row):
                self.sequence_table.setItem(row_index, column, _table_item(value))

        self.result_summary.setText(
            f"{execution.project.name} | {result.fault_type.value} | "
            f"Bus {execution.project.study_settings.bus_name} | "
            f"Base {result.base_power_mva:g} MVA / {result.base_voltage_kv:g} kV | "
            f"Maximum phase current {result.maximum_phase_current_ka:.6f} kA"
        )
        settings = execution.project.study_settings
        self.trace_text.setPlainText(
            "Calculation provenance\n"
            "Solver: ShortCircuitSolver (production numerical kernel)\n"
            f"E1 = {settings.prefault_positive_voltage_pu!r} p.u.\n"
            f"Z1 = {settings.positive_sequence_impedance_pu!r} p.u.; "
            f"Z2 = {settings.negative_sequence_impedance_pu!r} p.u.; "
            f"Z0 = {settings.zero_sequence_impedance_pu!r} p.u.\n"
            f"Zf = {settings.fault_impedance_pu!r} p.u.\n"
            "Study path: general symmetrical-components bus fault; "
            "IEC 60909 corrections not applied."
        )

    def _export_report(self) -> None:
        if self._last_execution is None:
            QMessageBox.information(
                self,
                "No results",
                "Run a fault study before exporting a report.",
            )
            return
        directory = QFileDialog.getExistingDirectory(
            self,
            "Export engineering report",
            str(Path.home()),
        )
        if not directory:
            return
        try:
            files = self._services.export_report.execute(
                self._last_execution.report,
                directory,
                include_pdf=True,
                include_excel=True,
            )
            exported = [str(files.json_path), *(str(path) for path in files.csv_paths.values())]
            if files.pdf_path is not None:
                exported.append(str(files.pdf_path))
            if files.excel_path is not None:
                exported.append(str(files.excel_path))
            QMessageBox.information(
                self,
                "Report exported",
                "The engineering report was exported:\n\n" + "\n".join(exported),
            )
            self.statusBar().showMessage("Engineering report exported", 5000)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            QMessageBox.critical(self, "Report export failed", str(exc))

    def _refresh_history(self) -> None:
        history = self._project.study_history if self._project is not None else ()
        self.history_table.setRowCount(0)
        for run in history:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)
            phase_a_current = abs(complex(*run.phase_currents_pu[0]))
            values = (
                run.study_name,
                run.executed_at.isoformat(),
                run.fault_type.value,
                f"{run.base_power_mva:.6g}",
                f"{run.base_voltage_kv:.6g}",
                f"{phase_a_current:.9f}",
            )
            for column, value in enumerate(values):
                self.history_table.setItem(row, column, _table_item(value))

    def _show_history_details(self, row: int, _column: int) -> None:
        if self._project is None or row < 0 or row >= len(self._project.study_history):
            return
        run = self._project.study_history[row]
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Study results — {run.study_name}")
        dialog.resize(980, 430)
        layout = QVBoxLayout(dialog)
        settings = run.settings_snapshot
        layout.addWidget(
            QLabel(
                f"{run.executed_at.isoformat()} | {run.fault_type.value} | "
                f"{run.base_power_mva:g} MVA / {run.base_voltage_kv:g} kV | "
                f"Z1={settings.positive_sequence_impedance_pu!r} p.u. | "
                f"Zf={settings.fault_impedance_pu!r} p.u."
            )
        )
        table = QTableWidget(3, 7)
        table.setHorizontalHeaderLabels(
            ["Phase", "|I| p.u.", "∠I °", "|I| kA", "|V| p.u.", "∠V °", "|V| kV L-N"]
        )
        for index, phase in enumerate(("A", "B", "C")):
            current_pu = complex(*run.phase_currents_pu[index])
            current_ka = complex(*run.phase_currents_ka[index])
            voltage_pu = complex(*run.phase_voltages_pu[index])
            voltage_kv = complex(*run.phase_voltages_kv[index])
            values = (
                phase,
                f"{abs(current_pu):.9f}",
                f"{math.degrees(cmath.phase(current_pu)):.6f}",
                f"{abs(current_ka):.9f}",
                f"{abs(voltage_pu):.9f}",
                f"{math.degrees(cmath.phase(voltage_pu)):.6f}",
                f"{abs(voltage_kv):.9f}",
            )
            for column, value in enumerate(values):
                table.setItem(index, column, _table_item(value))
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)
        ground_current = complex(*run.ground_current_pu)
        layout.addWidget(
            QLabel(
                f"Ground current: {ground_current.real:+.9f} "
                f"{ground_current.imag:+.9f}j p.u. "
                f"(|I0-ground|={abs(ground_current):.9f} p.u.)"
            )
        )
        layout.addWidget(QLabel("Sequence current snapshots (p.u.)"))
        for sequence, phasor in run.sequence_currents_pu:
            value = complex(*phasor)
            layout.addWidget(
                QLabel(
                    f"I{sequence}: {value.real:+.9f} {value.imag:+.9f}j p.u. "
                    f"(|I|={abs(value):.9f}, "
                    f"angle={math.degrees(cmath.phase(value)):.6f}°)"
                )
            )
        for sequence, phasor in run.sequence_voltages_pu:
            value = complex(*phasor)
            layout.addWidget(
                QLabel(
                    f"V{sequence}: {value.real:+.9f} {value.imag:+.9f}j p.u. "
                    f"(|V|={abs(value):.9f}, "
                    f"angle={math.degrees(cmath.phase(value)):.6f}°)"
                )
            )
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def _clear_results(self) -> None:
        self.result_summary.setText("No study executed in this session.")
        self.phase_table.setRowCount(0)
        self.sequence_table.setRowCount(0)
        self.trace_text.clear()
        self.export_action.setEnabled(False)

    def _mark_dirty(self, *_args) -> None:
        self._dirty = True
        if self._last_execution is not None:
            self._last_execution = None
            self.export_action.setEnabled(False)
            self.result_summary.setText(
                "Study inputs changed. The displayed result is no longer current; "
                "run the study again before exporting."
            )
        self._update_title()

    def _update_title(self) -> None:
        if self._project is None:
            self.setWindowTitle("POWER_FAULT_ANALYZER — No project")
            self.project_heading.setText("No project open")
            return
        marker = " *" if self._dirty else ""
        self.project_heading.setText(self._project.name + marker)
        path_hint = f" — {self._project_path}" if self._project_path else " — Unsaved project"
        self.setWindowTitle(f"{self._project.name}{marker}{path_hint} — POWER_FAULT_ANALYZER")
        self.run_action.setEnabled(True)
        self.save_action.setEnabled(True)
        self.save_as_action.setEnabled(True)
        self.tabs.setEnabled(True)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._confirm_discard_changes():
            event.accept()
        else:
            event.ignore()


def _table_item(value: object) -> QTableWidgetItem:
    item = QTableWidgetItem(str(value))
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item
