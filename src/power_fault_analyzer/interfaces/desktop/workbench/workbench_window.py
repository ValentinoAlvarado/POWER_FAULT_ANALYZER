"""Dockable engineering workbench for physical network modelling and fault studies."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import traceback
from copy import deepcopy
from dataclasses import fields, replace
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from PySide6.QtCore import (
    QObject,
    QRectF,
    QRunnable,
    QSettings,
    QSize,
    QStandardPaths,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QKeySequence,
    QPainter,
    QPalette,
    QUndoCommand,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QSplitterHandle,
    QStyle,
    QTabWidget,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from power_fault_analyzer.application.commands import (
    MoveDiagramElements,
    NetworkWorkspaceCommands,
    RemoveBus,
    RemoveDiagramLabel,
    RemoveDiagramPosition,
    RemoveDiagramRotation,
    RemoveDiagramSymbol,
    RemoveEquipment,
    RotateBusbar,
    SetActiveOperatingScenario,
    SetOperatingScenarioSwitchPosition,
    UpdateBus,
    UpsertDiagramLabel,
    UpsertDiagramSymbol,
    UpsertOperatingScenario,
)
from power_fault_analyzer.application.use_cases.network_workspace import (
    DiagramLabelPlacement,
    DiagramSymbolPlacement,
    NetworkStudyRecord,
    NetworkWorkspace,
)
from power_fault_analyzer.diagram.layout import Point, snap_point
from power_fault_analyzer.diagram.model_document_export import (
    export_engineering_pdf,
    export_engineering_svg,
)
from power_fault_analyzer.diagram.model_projection import project_network_to_diagram
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.enums.bus_kind import BusKind
from power_fault_analyzer.domain.enums.equipment_interface import EquipmentInterfaceKind
from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.switching_device import SwitchPosition
from power_fault_analyzer.domain.exceptions.network_exceptions import NetworkDomainError
from power_fault_analyzer.domain.projects.models import Project
from power_fault_analyzer.domain.services.network_validation_service import (
    DefaultNetworkValidationService,
)
from power_fault_analyzer.domain.value_objects.diagnostic import DiagnosticSeverity
from power_fault_analyzer.equipment.interfaces.unresolved_equipment import (
    UnresolvedEquipmentInterface,
)
from power_fault_analyzer.equipment.motors.induction_motor import InductionMotor
from power_fault_analyzer.equipment.sources.equivalent_source import EquivalentSource
from power_fault_analyzer.equipment.sources.synchronous_generator import SynchronousGenerator
from power_fault_analyzer.equipment.switching.switching_device import SwitchingDevice
from power_fault_analyzer.equipment.transformers.two_winding_transformer import (
    TwoWindingTransformer,
)
from power_fault_analyzer.equipment.transmission.line import Line
from power_fault_analyzer.interfaces.desktop.icon_theme import engineering_icon
from power_fault_analyzer.interfaces.desktop.release_updates import (
    ReleaseUpdate,
    discover_latest_release,
    download_update_bundle,
    load_installation_build_info,
)
from power_fault_analyzer.interfaces.desktop.workbench.code_automation_studio import (
    CodeAutomationStudio,
)
from power_fault_analyzer.interfaces.desktop.workbench.dialogs import (
    BusDialog,
    EquivalentSourceDialog,
    FaultStudyDialog,
    GeneratorDialog,
    LineDialog,
    ResolveLineBoundaryDialog,
    ResolveTransformerBoundaryDialog,
)
from power_fault_analyzer.interfaces.desktop.workbench.network_canvas import NetworkCanvasView
from power_fault_analyzer.interfaces.desktop.workbench.qet_symbol_browser import QETSymbolBrowser
from power_fault_analyzer.interfaces.desktop.workbench.results_workspace import ResultsWorkspace
from power_fault_analyzer.operations import analyze_workspace, scenario_from_physical_network
from power_fault_analyzer.operations.models import SwitchPosition as OperatingSwitchPosition


class _WorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)


class _StudyWorker(QRunnable):
    """Run a callable away from the GUI thread."""

    def __init__(self, callable_):
        super().__init__()
        self._callable = callable_
        self.signals = _WorkerSignals()

    def run(self) -> None:
        try:
            self.signals.succeeded.emit(self._callable())
        except Exception:  # noqa: BLE001 - isolate failures at the worker/GUI boundary.
            self.signals.failed.emit(traceback.format_exc())


class _UpdateDownloadSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(int)


class _UpdateDownloadWorker(QRunnable):
    """Download and verify a published portable update without blocking Qt."""

    def __init__(self, release: ReleaseUpdate) -> None:
        super().__init__()
        self.release = release
        self.signals = _UpdateDownloadSignals()

    def run(self) -> None:
        try:
            bundle = download_update_bundle(
                self.release,
                progress=self.signals.progress.emit,
            )
            self.signals.completed.emit(bundle)
        except Exception as exc:  # noqa: BLE001 - isolate failures at the worker/GUI boundary.
            self.signals.failed.emit(str(exc))


class _MoveDiagramItemCommand(QUndoCommand):
    def __init__(
        self, window, identifier: str, old_x: float, old_y: float, new_x: float, new_y: float
    ):
        super().__init__("Move diagram element")
        self._window = window
        self._identifier = identifier
        self._old = (old_x, old_y)
        self._new = (new_x, new_y)

    def undo(self) -> None:
        self._window._apply_diagram_position(self._identifier, *self._old)

    def redo(self) -> None:
        self._window._apply_diagram_position(self._identifier, *self._new)


class _MoveDiagramItemsCommand(QUndoCommand):
    """Move a selection as one undoable canvas operation."""

    def __init__(self, window, moves: dict[str, tuple[float, float, float, float]]) -> None:
        super().__init__(f"Nudge {len(moves)} diagram element(s)")
        self._window = window
        self._moves = dict(moves)

    def undo(self) -> None:
        for identifier, (old_x, old_y, _new_x, _new_y) in self._moves.items():
            self._window._apply_diagram_position(identifier, old_x, old_y)

    def redo(self) -> None:
        for identifier, (_old_x, _old_y, new_x, new_y) in self._moves.items():
            self._window._apply_diagram_position(identifier, new_x, new_y)


class _RestoreWorkspaceSnapshot:
    """Workspace command that restores a prior snapshot in place."""

    name = "Restore workspace snapshot"

    def __init__(self, snapshot: NetworkWorkspace) -> None:
        self._snapshot = deepcopy(snapshot)

    def execute(self, workspace: NetworkWorkspace) -> None:
        snapshot = deepcopy(self._snapshot)
        current_network = workspace.network
        for attribute in Network.__slots__:
            setattr(current_network, attribute, deepcopy(getattr(snapshot.network, attribute)))
        for descriptor in fields(NetworkWorkspace):
            if descriptor.name == "network":
                continue
            setattr(workspace, descriptor.name, deepcopy(getattr(snapshot, descriptor.name)))


class _OperatingWorkspaceSnapshotCommand(QUndoCommand):
    """Undoable scenario edit; physical Network is never touched by the edit itself."""

    def __init__(self, window, before: NetworkWorkspace, after: NetworkWorkspace, text: str) -> None:
        super().__init__(text)
        self._window = window
        self._before = deepcopy(before)
        self._after = deepcopy(after)

    def undo(self) -> None:
        self._window._apply_operating_workspace_snapshot(self._before, f"Undid {self.text()}.")

    def redo(self) -> None:
        self._window._apply_operating_workspace_snapshot(self._after, f"Applied {self.text()}.")


class _DeleteWorkspaceSelectionCommand(QUndoCommand):
    """Undoable, atomic deletion of selected domain and drawing objects."""

    def __init__(self, window, commands: tuple[object, ...]) -> None:
        super().__init__(f"Delete {len(commands)} selected object(s)")
        self._window = window
        self._commands = commands
        self._before = deepcopy(window.workspace)

    def redo(self) -> None:
        self._window.commands.execute_many(self._commands)
        self._window._model_changed(f"Deleted {len(self._commands)} selected object(s).")

    def undo(self) -> None:
        self._window.commands.execute(_RestoreWorkspaceSnapshot(self._before))
        self._window._model_changed("Restored deleted selection.")


class _AddDiagramSymbolCommand(QUndoCommand):
    def __init__(self, window, placement: DiagramSymbolPlacement, definition) -> None:
        super().__init__("Insert source drawing symbol")
        self._window = window
        self._placement = placement
        self._definition = definition

    def undo(self) -> None:
        self._window._remove_diagram_symbol(self._placement.instance_id)

    def redo(self) -> None:
        self._window._add_diagram_symbol(self._placement, self._definition)


class _RotateDiagramSymbolCommand(QUndoCommand):
    def __init__(self, window, identifier: UUID, old: float, new: float) -> None:
        super().__init__("Rotate drawing symbol")
        self._window = window
        self._identifier = identifier
        self._old = old
        self._new = new

    def undo(self) -> None:
        self._window._apply_diagram_symbol_rotation(self._identifier, self._old)

    def redo(self) -> None:
        self._window._apply_diagram_symbol_rotation(self._identifier, self._new)


class _RotateBusCommand(QUndoCommand):
    def __init__(self, window, identifier: UUID, old: float, new: float) -> None:
        super().__init__("Rotate busbar")
        self._window = window
        self._identifier = identifier
        self._old = old
        self._new = new

    def undo(self) -> None:
        self._window._apply_bus_rotation(self._identifier, self._old)

    def redo(self) -> None:
        self._window._apply_bus_rotation(self._identifier, self._new)


class _RemoveDiagramSymbolCommand(QUndoCommand):
    def __init__(self, window, placement: DiagramSymbolPlacement, definition) -> None:
        super().__init__("Remove drawing symbol")
        self._window = window
        self._placement = placement
        self._definition = definition

    def undo(self) -> None:
        self._window._add_diagram_symbol(self._placement, self._definition)

    def redo(self) -> None:
        self._window._remove_diagram_symbol(self._placement.instance_id)


class _EngineeringSplitterHandle(QSplitterHandle):
    """High-contrast splitter handle with a visible grip affordance."""

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#64748B"))
        if self.orientation() == Qt.Orientation.Horizontal:
            center_x = self.width() / 2.0
            for offset in (-6.0, 0.0, 6.0):
                painter.drawRoundedRect(
                    QRectF(center_x - 2.0, self.height() / 2.0 + offset - 1.0, 4.0, 2.0),
                    1.0,
                    1.0,
                )
        else:
            center_y = self.height() / 2.0
            for offset in (-6.0, 0.0, 6.0):
                painter.drawRoundedRect(
                    QRectF(self.width() / 2.0 + offset - 1.0, center_y - 2.0, 2.0, 4.0),
                    1.0,
                    1.0,
                )
        painter.end()


class _SwitchPositionCommand(QUndoCommand):
    def __init__(
        self, window, equipment_id: UUID, old_position: SwitchPosition, new_position: SwitchPosition
    ):
        super().__init__("Change switch position")
        self._window = window
        self._equipment_id = equipment_id
        self._old_position = old_position
        self._new_position = new_position

    def undo(self) -> None:
        self._window._apply_switch_position(self._equipment_id, self._old_position)

    def redo(self) -> None:
        self._window._apply_switch_position(self._equipment_id, self._new_position)


class _InspectorEditCommand(QUndoCommand):
    """Undoable property edit committed through the shared workspace command bus."""

    def __init__(self, window, kind: str, identifier: str, before: dict, after: dict) -> None:
        super().__init__("Edit engineering element properties")
        self._window = window
        self._kind = kind
        self._identifier = identifier
        self._before = dict(before)
        self._after = dict(after)

    def undo(self) -> None:
        self._window._apply_inspector_state(self._kind, self._identifier, self._before)

    def redo(self) -> None:
        self._window._apply_inspector_state(self._kind, self._identifier, self._after)


class _EngineeringSplitter(QSplitter):
    """Splitter with obvious handles, intended for the resizable workbench."""

    def createHandle(self) -> QSplitterHandle:
        return _EngineeringSplitterHandle(self.orientation(), self)


class WorkbenchWindow(QMainWindow):
    """Main window composed from real network use cases and the production solver."""

    def __init__(self, services, parent=None) -> None:
        super().__init__(parent)
        self.services = services
        self.project: Project = services.project_workspace.create("Untitled Project")
        self.workspace = NetworkWorkspace(Network("Network 1"))
        self.commands = NetworkWorkspaceCommands(self.workspace, source="workbench")
        self.project_path: Path | None = None
        self._dirty = False
        self._active_execution = None
        self._session_runs: list[tuple[str, str, str]] = []
        self._thread_pool = QThreadPool.globalInstance()
        self._undo_stack = QUndoStack(self)
        self._dark_theme = False
        self._selected_equipment_id: UUID | None = None
        self._property_editor_target: tuple[str, str] | None = None
        self._property_editor_state: dict | None = None
        self._ui_settings = QSettings("POWER_FAULT_ANALYZER", "EngineeringWorkbench")
        self._dark_theme = (
            self._ui_settings.value("appearance/theme", "light", type=str) == "dark"
        )
        self._updates_on_startup = self._ui_settings.value(
            "updates/check_on_startup", True, type=bool
        )
        self._update_check_worker = None
        self._update_download_worker = None
        self._update_progress: QProgressDialog | None = None
        self._update_handoff_process: subprocess.Popen | None = None
        self._update_handoff_timer: QTimer | None = None
        self._update_handoff_status_path: Path | None = None
        self._update_handoff_log_path: Path | None = None
        self._update_handoff_bundle_directory: Path | None = None
        self._update_handoff_started_at = 0.0
        self._update_shutdown_approved = False
        self._build_actions()
        self._build_docks()
        self._build_central_workspace()
        self._build_canvas_shortcuts()
        self._build_toolbars()
        self._connect_canvas()
        self._bind_workspace_commands()
        self._refresh_all()
        self.resize(1600, 1000)
        self.setMinimumSize(1050, 700)
        QTimer.singleShot(0, self._restore_workspace_layout)
        self._apply_theme(persist=False)
        self.setWindowTitle("POWER_FAULT_ANALYZER — Engineering Workbench")
        self.statusBar().showMessage("Ready · Physical network model · 60 Hz")
        self._log("Workbench initialized. Add equipment or load REF-3PH-001B template.")
        if self._updates_on_startup and getattr(sys, "frozen", False):
            QTimer.singleShot(4000, lambda: self._check_for_updates(automatic=True))

    # ------------------------------------------------------------------ actions
    def _awesome_icon(self, name: str, fallback: QStyle.StandardPixmap):
        return engineering_icon(self.style(), name, fallback)

    def _action(self, text: str, slot, shortcut: str | None = None) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        return action

    def _build_actions(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        self.new_action = self._action("New", self._new_project, "Ctrl+N")
        self.new_action.setToolTip("Create a new project")
        self.new_action.setIcon(self._awesome_icon("fa5s.file", QStyle.StandardPixmap.SP_FileIcon))
        self.open_action = self._action("Open", self._open_project, "Ctrl+O")
        self.open_action.setToolTip("Open an existing PFA project")
        self.open_action.setIcon(
            self._awesome_icon("fa5s.folder-open", QStyle.StandardPixmap.SP_DialogOpenButton)
        )
        self.save_action = self._action("Save", self._save_project, "Ctrl+S")
        self.save_action.setToolTip("Save the project and network document")
        self.save_action.setIcon(
            self._awesome_icon("fa5s.save", QStyle.StandardPixmap.SP_DialogSaveButton)
        )
        self.save_as_action = self._action("Save As…", self._save_project_as, "Ctrl+Shift+S")
        self.exit_action = self._action("Exit", self.close, "Alt+F4")
        for action in (self.new_action, self.open_action, self.save_action, self.save_as_action):
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        self.edit_menu = bar.addMenu("&Edit")

        diagram_menu = bar.addMenu("&Diagram")
        self.rotate_clockwise_action = self._action(
            "Rotate CW",
            lambda: self._rotate_selected_symbol(90.0),
            "Ctrl+R",
        )
        self.rotate_counterclockwise_action = self._action(
            "Rotate CCW",
            lambda: self._rotate_selected_symbol(-90.0),
            "Ctrl+Shift+R",
        )
        self.rotate_clockwise_action.setIcon(
            self._awesome_icon("fa5s.redo-alt", QStyle.StandardPixmap.SP_ArrowForward)
        )
        self.rotate_counterclockwise_action.setIcon(
            self._awesome_icon("fa5s.undo-alt", QStyle.StandardPixmap.SP_ArrowBack)
        )
        self.rotate_clockwise_action.setText("Rotate ↻")
        self.rotate_counterclockwise_action.setText("Rotate ↺")
        self.rotate_clockwise_action.setToolTip(
            "Rotate the selected busbar or source drawing symbol 90 degrees clockwise"
        )
        self.rotate_counterclockwise_action.setToolTip(
            "Rotate the selected busbar or source drawing symbol 90 degrees counterclockwise"
        )
        self.remove_selected_action = self._action(
            "Remove Selected Element", self._remove_selected, "Delete"
        )
        self.rotate_clockwise_action.setText("Rotate 90° Clockwise")
        self.rotate_counterclockwise_action.setText("Rotate 90° Counterclockwise")
        diagram_menu.addAction(self.rotate_clockwise_action)
        diagram_menu.addAction(self.rotate_counterclockwise_action)
        diagram_menu.addSeparator()
        diagram_menu.addAction(self.remove_selected_action)

        project_menu = bar.addMenu("&Project")
        project_menu.addAction(
            self._action("Load REF-3PH-001B Template", self._load_reference_template)
        )
        project_menu.addAction(self._action("Validate Network", self._validate_network))

        model_menu = bar.addMenu("&Model")
        model_menu.addAction(self._action("Add AC Bus…", self._add_bus))
        model_menu.addAction(self._action("Add Thevenin Source…", self._add_equivalent_source))
        model_menu.addAction(self._action("Add Synchronous Generator…", self._add_generator))
        model_menu.addAction(self._action("Add Transmission Line…", self._add_line))
        model_menu.addAction(
            self._action("Connect Selected Buses with Line…", self._add_line_from_selection)
        )
        model_menu.addSeparator()
        model_menu.addAction(
            self._action("Resolve PFA-ES-001 Boundary Equipment…", self._resolve_boundary_equipment)
        )

        network_menu = bar.addMenu("&Network")
        self.fit_diagram_action = self._action("Fit Diagram", self._fit_diagram, "Ctrl+0")
        self.grid_action = self._action("Show Grid", self._toggle_grid)
        self.snap_action = self._action("Snap to Grid", self._toggle_snap)
        network_menu.addAction(self.fit_diagram_action)
        network_menu.addAction(self.grid_action)
        network_menu.addAction(self.snap_action)

        operations_menu = bar.addMenu("&Operations")
        self.capture_operating_scenario_action = self._action(
            "Capture Physical State as Scenario…", self._capture_operating_scenario
        )
        self.activate_operating_scenario_action = self._action(
            "Activate Saved Scenario…", self._activate_operating_scenario
        )
        self.deactivate_operating_scenario_action = self._action(
            "Deactivate Operating Overlay", self._deactivate_operating_scenario
        )
        self.set_scenario_switch_action = self._action(
            "Set Selected Switch State in Scenario…", self._set_selected_scenario_switch_position
        )
        self.analyze_operating_scenario_action = self._action(
            "Analyze Active Scenario", self._analyze_active_operating_scenario
        )
        for action in (
            self.capture_operating_scenario_action,
            self.activate_operating_scenario_action,
            self.deactivate_operating_scenario_action,
            self.set_scenario_switch_action,
            self.analyze_operating_scenario_action,
        ):
            operations_menu.addAction(action)

        analysis_menu = bar.addMenu("&Analysis")
        self.run_action = self._action("Run Study", self._run_fault_study, "F5")
        self.run_action.setToolTip("Run the configured short-circuit study")
        self.run_action.setIcon(self._awesome_icon("fa5s.play", QStyle.StandardPixmap.SP_MediaPlay))
        analysis_menu.addAction(self.run_action)

        self.view_menu = bar.addMenu("&View")
        self.theme_action = self._action("Dark mode", self._toggle_theme)
        self.theme_action.setCheckable(True)
        self.theme_action.setChecked(self._dark_theme)
        self.theme_action.setToolTip(
            "Toggle the workbench shell theme. The engineering drawing sheet remains light."
        )
        self.theme_action.setIcon(
            self._awesome_icon("fa5s.moon", QStyle.StandardPixmap.SP_DialogHelpButton)
        )
        self.view_menu.addAction(self.theme_action)
        self.show_source_candidates_action = QAction("Show QET drawing-only candidates", self)
        self.show_source_candidates_action.setCheckable(True)
        self.show_source_candidates_action.setChecked(False)
        self.show_source_candidates_action.toggled.connect(self._set_source_candidate_visibility)
        self.view_menu.addAction(self.show_source_candidates_action)

        tools_menu = bar.addMenu("&Tools")
        tools_menu.addAction(self._action("Validate Network", self._validate_network))

        reports_menu = bar.addMenu("&Reports")
        self.export_action = self._action("Export", self._export_report, "Ctrl+E")
        self.export_action.setToolTip("Export the active study report")
        self.export_action.setIcon(
            self._awesome_icon("fa5s.file-export", QStyle.StandardPixmap.SP_DialogSaveButton)
        )
        self.export_action.setEnabled(False)
        self.export_diagram_action = self._action(
            "Export One-Line Diagram as SVG…", self._export_diagram_svg, "Ctrl+Shift+E"
        )
        reports_menu.addAction(self.export_action)
        reports_menu.addAction(self.export_diagram_action)

        help_menu = bar.addMenu("&Help")
        self.keyboard_shortcuts_action = self._action(
            "Keyboard Shortcuts…", self._show_keyboard_shortcuts, "F1"
        )
        help_menu.addAction(self.keyboard_shortcuts_action)
        help_menu.addSeparator()
        self.check_updates_action = self._action(
            "Check for Updates…", lambda: self._check_for_updates(automatic=False)
        )
        help_menu.addAction(self.check_updates_action)
        self.check_updates_on_startup_action = QAction("Check for Updates at Startup", self)
        self.check_updates_on_startup_action.setCheckable(True)
        self.check_updates_on_startup_action.setChecked(self._updates_on_startup)
        self.check_updates_on_startup_action.toggled.connect(self._set_update_check_preference)
        help_menu.addAction(self.check_updates_on_startup_action)
        help_menu.addSeparator()
        help_menu.addAction(self._action("About POWER_FAULT_ANALYZER", self._about))

    def _add_canvas_shortcut(
        self, text: str, shortcuts: tuple[str, ...], slot, tooltip: str = ""
    ) -> QAction:
        action = QAction(text, self.canvas)
        action.setShortcuts([QKeySequence(value) for value in shortcuts])
        action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        action.setAutoRepeat(False)
        if tooltip:
            action.setToolTip(tooltip)
        action.triggered.connect(slot)
        self.canvas.addAction(action)
        self._canvas_shortcut_actions.append(action)
        self.canvas_shortcuts[text] = action
        return action

    def _build_canvas_shortcuts(self) -> None:
        """Bind editor-only shortcuts to the canvas, not to text-entry widgets."""
        self._canvas_shortcut_actions: list[QAction] = []
        self.canvas_shortcuts: dict[str, QAction] = {}

        self.undo_action = self._undo_stack.createUndoAction(self.canvas, "Undo")
        self.undo_action.setShortcuts([QKeySequence("Ctrl+Z")])
        self.undo_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.canvas.addAction(self.undo_action)
        self.edit_menu.addAction(self.undo_action)

        self.redo_action = self._undo_stack.createRedoAction(self.canvas, "Redo")
        self.redo_action.setShortcuts(
            [QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")]
        )
        self.redo_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.canvas.addAction(self.redo_action)
        self.edit_menu.addAction(self.redo_action)
        self.edit_menu.addSeparator()

        self.select_all_action = self._add_canvas_shortcut(
            "Select All Diagram Elements", ("Ctrl+A",), self.canvas.select_all_elements,
            "Select all visible buses, equipment and drawing symbols in the diagram.",
        )
        self.edit_menu.addAction(self.select_all_action)

        self.clear_selection_action = self._add_canvas_shortcut(
            "Clear Selection", ("Escape",), self.canvas.clear_selection,
            "Clear the current diagram selection.",
        )
        self.edit_menu.addAction(self.clear_selection_action)
        self.remove_selected_action.setText("Delete Selection")
        self.edit_menu.addAction(self.remove_selected_action)

        # Existing commands are attached to the canvas so Delete/rotation do not
        # hijack editing shortcuts in the inspector, search fields or code editor.
        for action, sequences in (
            (self.remove_selected_action, ("Delete", "Backspace")),
            (self.rotate_clockwise_action, ("Ctrl+R",)),
            (self.rotate_counterclockwise_action, ("Ctrl+Shift+R",)),
            (self.fit_diagram_action, ("Ctrl+0", "Home")),
            (self.grid_action, ("G",)),
            (self.snap_action, ("Ctrl+G",)),
        ):
            # These actions were originally created by _action(..., parent=self),
            # before the canvas existed. Adding an action to a widget does NOT
            # change QAction.parent(). With WidgetWithChildrenShortcut, Qt scopes
            # activation to the action's parent widget, not the widget that merely
            # references it. Reparent explicitly or shortcuts leak to the whole
            # main window and behave inconsistently with canvas-created actions.
            action.setParent(self.canvas)
            action.setShortcuts([QKeySequence(value) for value in sequences])
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.setAutoRepeat(False)
            self.canvas.addAction(action)

        self.zoom_in_action = self._add_canvas_shortcut(
            "Zoom In", ("Ctrl++", "Ctrl+="), lambda: self._zoom_diagram(1.2),
            "Zoom in on the diagram.",
        )
        self.zoom_out_action = self._add_canvas_shortcut(
            "Zoom Out", ("Ctrl+-",), lambda: self._zoom_diagram(1.0 / 1.2),
            "Zoom out of the diagram.",
        )
        self.property_focus_action = self._add_canvas_shortcut(
            "Edit Selected Properties", ("F2",), self._focus_property_editor,
            "Focus the selected element's Properties inspector.",
        )
        self._add_canvas_shortcut(
            "Nudge Left", ("Left",), lambda: self._nudge_selected(-1, 0),
            "Move selected element(s) one grid step left, or one scene unit without snap.",
        )
        self._add_canvas_shortcut(
            "Nudge Right", ("Right",), lambda: self._nudge_selected(1, 0),
            "Move selected element(s) one grid step right, or one scene unit without snap.",
        )
        self._add_canvas_shortcut(
            "Nudge Up", ("Up",), lambda: self._nudge_selected(0, -1),
            "Move selected element(s) one grid step up, or one scene unit without snap.",
        )
        self._add_canvas_shortcut(
            "Nudge Down", ("Down",), lambda: self._nudge_selected(0, 1),
            "Move selected element(s) one grid step down, or one scene unit without snap.",
        )
        self._add_canvas_shortcut(
            "Nudge Left (Large)", ("Shift+Left",), lambda: self._nudge_selected(-1, 0, large=True)
        )
        self._add_canvas_shortcut(
            "Nudge Right (Large)", ("Shift+Right",), lambda: self._nudge_selected(1, 0, large=True)
        )
        self._add_canvas_shortcut(
            "Nudge Up (Large)", ("Shift+Up",), lambda: self._nudge_selected(0, -1, large=True)
        )
        self._add_canvas_shortcut(
            "Nudge Down (Large)", ("Shift+Down",), lambda: self._nudge_selected(0, 1, large=True)
        )

    def _build_toolbars(self) -> None:
        """Build one compact command bar instead of four competing toolbars."""
        toolbar = QToolBar("Engineering Commands", self)
        toolbar.setObjectName("EngineeringCommandBar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(17, 17))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.setContentsMargins(5, 1, 5, 1)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        self.command_toolbar = toolbar

        def add_command(
            text: str,
            tooltip: str,
            slot,
            icon: str,
            fallback: QStyle.StandardPixmap,
        ) -> QAction:
            action = self._action(text, slot)
            action.setToolTip(tooltip)
            action.setIcon(self._awesome_icon(icon, fallback))
            toolbar.addAction(action)
            return action

        def add_existing(action: QAction, icon: str, fallback: QStyle.StandardPixmap) -> None:
            action.setIcon(self._awesome_icon(icon, fallback))
            toolbar.addAction(action)

        self.quick_toolbar = toolbar
        add_existing(self.new_action, "fa5s.file", QStyle.StandardPixmap.SP_FileIcon)
        add_existing(
            self.open_action, "fa5s.folder-open", QStyle.StandardPixmap.SP_DialogOpenButton
        )
        add_existing(self.save_action, "fa5s.save", QStyle.StandardPixmap.SP_DialogSaveButton)
        toolbar.addSeparator()
        self.model_toolbar = toolbar
        add_command(
            "Bus",
            "Add an AC busbar",
            self._add_bus,
            "fa5s.grip-lines",
            QStyle.StandardPixmap.SP_DesktopIcon,
        )
        add_command(
            "Source",
            "Add a Thevenin equivalent source",
            self._add_equivalent_source,
            "fa5s.bolt",
            QStyle.StandardPixmap.SP_DriveHDIcon,
        )
        add_command(
            "Generator",
            "Add a synchronous generator",
            self._add_generator,
            "fa5s.industry",
            QStyle.StandardPixmap.SP_ComputerIcon,
        )
        add_command(
            "Line",
            "Add a transmission line",
            self._add_line,
            "fa5s.project-diagram",
            QStyle.StandardPixmap.SP_ArrowRight,
        )
        toolbar.addSeparator()
        self.diagram_toolbar = toolbar
        rotate_cw_toolbar = add_command(
            "Rotate ↻",
            "Rotate selected busbar or source drawing symbol 90° clockwise",
            lambda: self._rotate_selected_symbol(90.0),
            "fa5s.redo-alt",
            QStyle.StandardPixmap.SP_ArrowForward,
        )
        rotate_ccw_toolbar = add_command(
            "Rotate ↺",
            "Rotate selected busbar or source drawing symbol 90° counterclockwise",
            lambda: self._rotate_selected_symbol(-90.0),
            "fa5s.undo-alt",
            QStyle.StandardPixmap.SP_ArrowBack,
        )
        self.rotate_cw_toolbar_action = rotate_cw_toolbar
        self.rotate_ccw_toolbar_action = rotate_ccw_toolbar
        toolbar.addSeparator()
        self.analysis_toolbar = toolbar
        add_existing(self.run_action, "fa5s.play", QStyle.StandardPixmap.SP_MediaPlay)
        self.export_diagram_action.setText("Export SVG")
        self.export_diagram_action.setIcon(
            self._awesome_icon("fa5s.file-image", QStyle.StandardPixmap.SP_DialogSaveButton)
        )
        toolbar.addAction(self.export_diagram_action)
        toolbar.addSeparator()
        toolbar.addAction(self.theme_action)

    # ------------------------------------------------------------- main layout
    def _panel(self, title: str, content: QWidget, *, show_heading: bool = True) -> QFrame:
        panel = QFrame()
        panel_key = "".join(character if character.isalnum() else "_" for character in title)
        panel.setObjectName(f"WorkbenchPanel_{panel_key.strip('_')}")
        panel.setProperty("workbenchPanel", True)
        content.setProperty("workbenchPanelContent", True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 7, 8, 8)
        layout.setSpacing(6)
        if show_heading:
            heading = QLabel(title.upper())
            heading.setObjectName("WorkbenchPanelHeading")
            layout.addWidget(heading, 0)
        layout.addWidget(content, 1)
        panel.setMinimumWidth(0)
        panel.setMinimumHeight(0)
        return panel

    def _build_docks(self) -> None:
        explorer_content = QWidget()
        explorer_layout = QVBoxLayout(explorer_content)
        explorer_layout.setContentsMargins(8, 7, 8, 7)
        explorer_layout.setSpacing(6)
        explorer_heading = QLabel("PROJECT STRUCTURE")
        explorer_heading.setObjectName("SectionEyebrow")
        explorer_layout.addWidget(explorer_heading)
        self.explorer_search = QLineEdit()
        self.explorer_search.setObjectName("ProjectTreeSearch")
        self.explorer_search.setPlaceholderText("Filter networks and equipment…")
        self.explorer_search.textChanged.connect(self._filter_explorer)
        explorer_layout.addWidget(self.explorer_search)
        self.explorer = QTreeWidget()
        self.explorer.setHeaderHidden(True)
        self.explorer.setHeaderLabels(["Project Explorer"])
        self.explorer.setIndentation(16)
        self.explorer.setAnimated(True)
        self.explorer.setUniformRowHeights(True)
        self.explorer.itemSelectionChanged.connect(self._on_explorer_selection)
        explorer_layout.addWidget(self.explorer, 1)
        self.explorer_panel = self._panel("Project Explorer", explorer_content, show_heading=False)

        palette = QWidget()
        palette_layout = QVBoxLayout(palette)
        palette_layout.setContentsMargins(8, 7, 8, 7)
        palette_layout.setSpacing(7)
        palette_intro = QLabel("CORE NETWORK EQUIPMENT")
        palette_intro.setObjectName("SectionEyebrow")
        palette_layout.addWidget(palette_intro)
        equipment_grid = QGridLayout()
        equipment_grid.setSpacing(8)
        for index, (label, title, slot, icon_name, fallback_icon) in enumerate(
            (
                (
                    "BUS",
                    "AC busbar",
                    self._add_bus,
                    "fa5s.grip-lines",
                    QStyle.StandardPixmap.SP_DesktopIcon,
                ),
                (
                    "SRC",
                    "Thevenin source",
                    self._add_equivalent_source,
                    "fa5s.bolt",
                    QStyle.StandardPixmap.SP_DriveHDIcon,
                ),
                (
                    "GEN",
                    "Synchronous generator",
                    self._add_generator,
                    "fa5s.industry",
                    QStyle.StandardPixmap.SP_ComputerIcon,
                ),
                (
                    "LINE",
                    "Transmission line",
                    self._add_line,
                    "fa5s.project-diagram",
                    QStyle.StandardPixmap.SP_ArrowRight,
                ),
            )
        ):
            button = QPushButton(f"{label}\n{title}")
            button.setObjectName("EquipmentTile")
            button.setMinimumHeight(58)
            button.setIcon(self._awesome_icon(icon_name, fallback_icon))
            button.setIconSize(QSize(24, 24))
            button.setToolTip(f"Insert {title}")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(slot)
            equipment_grid.addWidget(button, index // 2, index % 2)
        palette_layout.addLayout(equipment_grid)
        template_heading = QLabel("REFERENCE NETWORKS")
        template_heading.setObjectName("SectionEyebrow")
        palette_layout.addWidget(template_heading)
        template_button = QPushButton("Load REF-3PH-001B Template")
        template_button.setObjectName("SecondaryAction")
        template_button.setIcon(
            self._awesome_icon(
                "fa5s.project-diagram", QStyle.StandardPixmap.SP_FileDialogContentsView
            )
        )
        template_button.setMinimumHeight(34)
        template_button.clicked.connect(self._load_reference_template)
        palette_layout.addWidget(template_button)
        substation_button = QPushButton("Build PFA-ES-001 · 220 kV Double Bus")
        self.pfa_es001_button = substation_button
        substation_button.setObjectName("SecondaryAction")
        substation_button.setIcon(
            self._awesome_icon("fa5s.subway", QStyle.StandardPixmap.SP_ComputerIcon)
        )
        substation_button.setMinimumHeight(36)
        substation_button.setToolTip(
            "Builds a double-bus substation with explicit switch topology and unresolved "
            "line/transformer data boundaries. No synthetic electrical parameters are added."
        )
        substation_button.clicked.connect(self._load_pfa_es001_substation)
        palette_layout.addWidget(substation_button)
        palette_layout.addStretch(1)
        self.palette_panel = self._panel("Equipment", palette, show_heading=False)

        self.properties = QTreeWidget()
        self.properties.setHeaderLabels(["Property", "Value"])
        self.properties.setColumnWidth(0, 155)
        properties_content = QWidget()
        properties_layout = QVBoxLayout(properties_content)
        properties_layout.setContentsMargins(8, 7, 8, 7)
        properties_layout.setSpacing(7)
        properties_heading = QLabel("SELECTION PROPERTIES")
        properties_heading.setObjectName("SectionEyebrow")
        properties_layout.addWidget(properties_heading)
        empty_container = QWidget()
        empty_container.setObjectName("InspectorEmptyContainer")
        empty_layout = QVBoxLayout(empty_container)
        empty_layout.setContentsMargins(0, 4, 0, 0)
        empty_layout.setSpacing(10)

        # The inspector remains useful before an object is selected. It reports
        # live model scope instead of leaving a large, empty property pane.
        self.inspector_overview_card = QFrame()
        self.inspector_overview_card.setObjectName("InspectorOverviewCard")
        overview_layout = QVBoxLayout(self.inspector_overview_card)
        overview_layout.setContentsMargins(12, 12, 12, 12)
        overview_layout.setSpacing(5)
        overview_eyebrow = QLabel("ACTIVE NETWORK")
        overview_eyebrow.setObjectName("InspectorOverviewEyebrow")
        self.inspector_network_name = QLabel("Network 1")
        self.inspector_network_name.setObjectName("InspectorOverviewTitle")
        self.inspector_network_meta = QLabel("System base — · Reference voltage —")
        self.inspector_network_meta.setObjectName("InspectorOverviewMeta")
        overview_layout.addWidget(overview_eyebrow)
        overview_layout.addWidget(self.inspector_network_name)
        overview_layout.addWidget(self.inspector_network_meta)

        metric_grid = QGridLayout()
        metric_grid.setContentsMargins(0, 6, 0, 0)
        metric_grid.setHorizontalSpacing(8)
        metric_grid.setVerticalSpacing(0)

        def add_overview_metric(column: int, caption: str) -> QLabel:
            metric = QFrame()
            metric.setObjectName("InspectorMetricCard")
            metric_layout = QVBoxLayout(metric)
            metric_layout.setContentsMargins(9, 8, 9, 8)
            metric_layout.setSpacing(2)
            caption_label = QLabel(caption.upper())
            caption_label.setObjectName("InspectorMetricCaption")
            value_label = QLabel("0")
            value_label.setObjectName("InspectorMetricValue")
            metric_layout.addWidget(caption_label)
            metric_layout.addWidget(value_label)
            metric_grid.addWidget(metric, 0, column)
            return value_label

        self.inspector_bus_count = add_overview_metric(0, "Buses")
        self.inspector_equipment_count = add_overview_metric(1, "Equipment")
        self.inspector_study_count = add_overview_metric(2, "Studies")
        overview_layout.addLayout(metric_grid)
        empty_layout.addWidget(self.inspector_overview_card)

        self.properties_empty_state = QFrame()
        self.properties_empty_state.setObjectName("InspectorEmptyState")
        empty_card_layout = QVBoxLayout(self.properties_empty_state)
        empty_card_layout.setContentsMargins(12, 12, 12, 12)
        empty_card_layout.setSpacing(5)
        empty_eyebrow = QLabel("OBJECT INSPECTOR")
        empty_eyebrow.setObjectName("InspectorEmptyEyebrow")
        empty_title = QLabel("No element selected")
        empty_title.setObjectName("InspectorEmptyTitle")
        empty_description = QLabel(
            "Select a bus, branch, transformer, source or switching device in the "
            "diagram or project tree to inspect its electrical parameters and connections."
        )
        empty_description.setObjectName("InspectorEmptyDescription")
        empty_description.setWordWrap(True)
        empty_card_layout.addWidget(empty_eyebrow)
        empty_card_layout.addWidget(empty_title)
        empty_card_layout.addWidget(empty_description)
        empty_layout.addWidget(self.properties_empty_state)
        empty_layout.addStretch(1)
        self.properties_empty_container = empty_container
        properties_layout.addWidget(self.properties_empty_container, 0)

        # The property table must be parented into the inspector layout. Without
        # this, QWidget.show() opens an orphan top-level widget instead of showing
        # the selected object's parameters inside the right-hand Properties pane.
        self.properties.setAlternatingRowColors(True)
        self.properties.setRootIsDecorated(False)
        self.properties.setUniformRowHeights(True)
        properties_layout.addWidget(self.properties, 1)
        self.properties.hide()

        self.property_editor_widget = QWidget()
        self.property_editor_widget.setObjectName("TransactionalPropertyEditor")
        editor_form = QFormLayout(self.property_editor_widget)
        editor_form.setContentsMargins(0, 6, 0, 0)
        editor_form.setHorizontalSpacing(10)
        editor_form.setVerticalSpacing(6)
        self.property_name_caption = QLabel("Display label")
        self.property_name_edit = QLineEdit()
        self.property_name_edit.setObjectName("PropertyNameEdit")
        self.property_name_edit.setClearButtonEnabled(True)
        editor_form.addRow(self.property_name_caption, self.property_name_edit)

        self.property_voltage_caption = QLabel("Nominal voltage (kV)")
        self.property_voltage_edit = QDoubleSpinBox()
        self.property_voltage_edit.setObjectName("PropertyVoltageEdit")
        self.property_voltage_edit.setRange(0.001, 100000.0)
        self.property_voltage_edit.setDecimals(4)
        self.property_voltage_edit.setSuffix(" kV")
        editor_form.addRow(self.property_voltage_caption, self.property_voltage_edit)

        self.property_x_edit = QDoubleSpinBox()
        self.property_x_edit.setObjectName("PropertyPositionXEdit")
        self.property_x_edit.setRange(-1_000_000.0, 1_000_000.0)
        self.property_x_edit.setDecimals(2)
        self.property_x_edit.setSingleStep(10.0)
        editor_form.addRow("Position X", self.property_x_edit)

        self.property_y_edit = QDoubleSpinBox()
        self.property_y_edit.setObjectName("PropertyPositionYEdit")
        self.property_y_edit.setRange(-1_000_000.0, 1_000_000.0)
        self.property_y_edit.setDecimals(2)
        self.property_y_edit.setSingleStep(10.0)
        editor_form.addRow("Position Y", self.property_y_edit)

        self.property_rotation_caption = QLabel("Diagram rotation")
        self.property_rotation_edit = QDoubleSpinBox()
        self.property_rotation_edit.setObjectName("PropertyRotationEdit")
        self.property_rotation_edit.setRange(0.0, 359.9)
        self.property_rotation_edit.setDecimals(1)
        self.property_rotation_edit.setSingleStep(90.0)
        self.property_rotation_edit.setSuffix("°")
        editor_form.addRow(self.property_rotation_caption, self.property_rotation_edit)

        self.apply_property_changes_button = QPushButton("Apply selection changes")
        self.apply_property_changes_button.setObjectName("ApplyPropertyChanges")
        self.apply_property_changes_button.setToolTip(
            "Commit this edit as one atomic workspace command; Ctrl+Z restores the previous values."
        )
        self.apply_property_changes_button.clicked.connect(self._apply_property_editor_changes)
        editor_form.addRow(self.apply_property_changes_button)
        self.property_editor_widget.hide()
        properties_layout.addWidget(self.property_editor_widget, 0)

        self.switch_state_button = QPushButton("Change selected switch position…")
        self.switch_state_button.setObjectName("SecondaryAction")
        self.switch_state_button.setIcon(
            self._awesome_icon("fa5s.toggle-on", QStyle.StandardPixmap.SP_DialogApplyButton)
        )
        self.switch_state_button.clicked.connect(self._toggle_selected_switch_position)
        self.switch_state_button.hide()
        properties_layout.addWidget(self.switch_state_button)
        self.properties_panel = self._panel("Properties", properties_content, show_heading=False)

        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            resource_root = Path(sys._MEIPASS)
        else:
            resource_root = Path(__file__).resolve().parents[5]
        self.symbol_browser = QETSymbolBrowser(resource_root)
        self.symbol_browser.symbol_selected.connect(self._on_qet_symbol_selected)
        self.symbol_browser.insert_requested.connect(self._insert_qet_symbol)
        self.symbol_browser_panel = self._panel(
            "Source Library", self.symbol_browser, show_heading=False
        )

        self.inspector_tabs = QTabWidget()
        self.inspector_tabs.setObjectName("EngineeringInspectorTabs")
        self.inspector_tabs.setDocumentMode(True)
        self.inspector_tabs.setMovable(False)
        self.inspector_tabs.setUsesScrollButtons(True)
        self.inspector_tabs.addTab(
            self.palette_panel,
            self._awesome_icon("fa5s.toolbox", QStyle.StandardPixmap.SP_DirIcon),
            "Equipment",
        )
        self.inspector_tabs.addTab(
            self.properties_panel,
            self._awesome_icon("fa5s.sliders-h", QStyle.StandardPixmap.SP_FileDialogDetailedView),
            "Properties",
        )
        self.inspector_tabs.addTab(
            self.symbol_browser_panel,
            self._awesome_icon("fa5s.shapes", QStyle.StandardPixmap.SP_FileDialogContentsView),
            "Source Library",
        )
        self.inspector_tabs.setMinimumWidth(275)

        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(5000)
        self.console_dock = self._dock(
            "Calculation Console", self.console, Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self.console_dock.hide()
        self._progress = QProgressBar(self)
        self._progress.setRange(0, 0)
        self._progress.setTextVisible(False)
        self._progress.setMaximumWidth(150)
        self._progress.hide()
        self.statusBar().addPermanentWidget(self._progress)

        self._panel_actions = {}
        explorer_action = QAction("Project Explorer", self)
        explorer_action.setCheckable(True)
        explorer_action.setChecked(True)
        explorer_action.toggled.connect(self.explorer_panel.setVisible)
        self._panel_actions[self.explorer_panel] = explorer_action
        self.view_menu.addAction(explorer_action)
        self.view_menu.addSeparator()
        for title, panel in (
            ("Equipment", self.palette_panel),
            ("Properties", self.properties_panel),
            ("Source Library", self.symbol_browser_panel),
        ):
            self.view_menu.addAction(
                self._action(
                    title,
                    lambda _checked=False, target=panel: self.inspector_tabs.setCurrentWidget(
                        target
                    ),
                )
            )
        self.view_menu.addAction(
            self._action(
                "Code & Automation Studio",
                lambda: self.workspace_tabs.setCurrentWidget(self.code_studio),
            )
        )
        self.view_menu.addAction(self.console_dock.toggleViewAction())
        self.view_menu.addSeparator()
        self.view_menu.addAction(
            self._action("Reset Workspace Layout", self._reset_workspace_layout)
        )

    def _dock(self, title: str, widget: QWidget, area: Qt.DockWidgetArea) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(title.replace(" ", "") + "Dock")
        dock.setWidget(widget)
        dock.setAllowedAreas(area)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.addDockWidget(area, dock)
        return dock

    def _build_central_workspace(self) -> None:
        self.workspace_tabs = QTabWidget()
        self.workspace_tabs.setObjectName("MainWorkspaceTabs")
        self.canvas = NetworkCanvasView()
        if self.symbol_browser.catalog is not None:
            self.canvas.set_symbol_definitions(
                {
                    item.provenance.asset_id: item
                    for item in self.symbol_browser.catalog.symbols
                    if item.provenance.asset_id is not None
                }
            )

        # Keep the diagram itself as the dominant document surface. Its context
        # controls live in a shallow document bar rather than in floating panels.
        design_page = QWidget()
        design_page.setObjectName("NetworkDesignPage")
        design_layout = QVBoxLayout(design_page)
        design_layout.setContentsMargins(0, 0, 0, 0)
        design_layout.setSpacing(0)
        self.diagram_header = QFrame()
        self.diagram_header.setObjectName("DiagramDocumentBar")
        header_layout = QHBoxLayout(self.diagram_header)
        header_layout.setContentsMargins(12, 4, 10, 4)
        header_layout.setSpacing(7)
        document_identity = QVBoxLayout()
        document_identity.setSpacing(1)
        self.diagram_eyebrow = QLabel("NETWORK MODEL  /  SINGLE-LINE DIAGRAM")
        self.diagram_eyebrow.setObjectName("DiagramEyebrow")
        self.diagram_title = QLabel("Network 1")
        self.diagram_title.setObjectName("DiagramTitle")
        document_identity.addWidget(self.diagram_eyebrow)
        document_identity.addWidget(self.diagram_title)
        header_layout.addLayout(document_identity, 1)

        self.diagram_summary = QLabel()
        self.diagram_summary.setObjectName("DiagramSummary")
        self.diagram_summary.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        header_layout.addWidget(self.diagram_summary)

        self.grid_toggle = QToolButton()
        self.grid_toggle.setText("Grid")
        self.grid_toggle.setObjectName("DiagramToggle")
        self.grid_toggle.setIcon(
            self._awesome_icon("fa5s.border-all", QStyle.StandardPixmap.SP_FileDialogDetailedView)
        )
        self.grid_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.grid_toggle.setCheckable(True)
        self.grid_toggle.setChecked(True)
        self.grid_toggle.setToolTip("Show or hide the drawing grid")
        self.grid_toggle.toggled.connect(self._set_grid_visible)
        header_layout.addWidget(self.grid_toggle)

        self.snap_toggle = QToolButton()
        self.snap_toggle.setText("Snap")
        self.snap_toggle.setObjectName("DiagramToggle")
        self.snap_toggle.setIcon(
            self._awesome_icon("fa5s.magnet", QStyle.StandardPixmap.SP_DialogApplyButton)
        )
        self.snap_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.snap_toggle.setCheckable(True)
        self.snap_toggle.setChecked(True)
        self.snap_toggle.setToolTip("Snap diagram objects to the drawing grid")
        self.snap_toggle.toggled.connect(self._set_snap_enabled)
        header_layout.addWidget(self.snap_toggle)

        zoom_out_button = QToolButton()
        zoom_out_button.setObjectName("DiagramZoomButton")
        zoom_out_button.setText("−")
        zoom_out_button.setToolTip("Zoom out (Ctrl+- or mouse wheel)")
        zoom_out_button.clicked.connect(lambda: self._zoom_diagram(1 / 1.2))
        header_layout.addWidget(zoom_out_button)

        zoom_in_button = QToolButton()
        zoom_in_button.setObjectName("DiagramZoomButton")
        zoom_in_button.setText("+")
        zoom_in_button.setToolTip("Zoom in (Ctrl++ or mouse wheel)")
        zoom_in_button.clicked.connect(lambda: self._zoom_diagram(1.2))
        header_layout.addWidget(zoom_in_button)

        fit_button = QPushButton("Fit All")
        fit_button.setObjectName("DiagramFitButton")
        fit_button.setIcon(
            self._awesome_icon("fa5s.expand", QStyle.StandardPixmap.SP_TitleBarMaxButton)
        )
        fit_button.setToolTip("Fit the complete active network diagram into the viewport")
        fit_button.clicked.connect(self._fit_diagram)
        header_layout.addWidget(fit_button)

        design_layout.addWidget(self.diagram_header)
        design_layout.addWidget(self.canvas, 1)

        self.results = ResultsWorkspace()
        self.code_studio = CodeAutomationStudio()
        self.code_studio.workspace_built.connect(self._apply_script_workspace)
        self.workspace_tabs.addTab(
            design_page,
            self._awesome_icon(
                "fa5s.project-diagram", QStyle.StandardPixmap.SP_FileDialogContentsView
            ),
            "Network Design",
        )
        self.workspace_tabs.addTab(
            self.results,
            self._awesome_icon("fa5s.chart-line", QStyle.StandardPixmap.SP_FileDialogDetailedView),
            "Results Workspace",
        )
        self.workspace_tabs.addTab(
            self.code_studio,
            self._awesome_icon("fa5s.code", QStyle.StandardPixmap.SP_FileDialogDetailedView),
            "Code & Automation",
        )
        self.workspace_tabs.setMinimumWidth(460)

        self.main_splitter = _EngineeringSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setObjectName("MainWorkspaceSplitter")
        self.main_splitter.setHandleWidth(9)
        self.main_splitter.setChildrenCollapsible(True)
        self.main_splitter.addWidget(self.explorer_panel)
        self.main_splitter.addWidget(self.workspace_tabs)
        self.main_splitter.addWidget(self.inspector_tabs)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        self.explorer_panel.setMinimumWidth(190)
        self.inspector_tabs.setMinimumWidth(275)
        self.main_splitter.setCollapsible(0, True)
        self.main_splitter.setCollapsible(1, False)
        self.main_splitter.setCollapsible(2, True)
        self.main_splitter.setOpaqueResize(True)
        for index in range(1, self.main_splitter.count()):
            handle = self.main_splitter.handle(index)
            handle.setCursor(Qt.CursorShape.SplitHCursor)
            handle.setToolTip("Drag to resize or collapse the workspace sidebar")
        self.main_splitter.setSizes([205, 1_000, 300])
        self.setCentralWidget(self.main_splitter)

    def _restore_workspace_layout(self) -> None:
        geometry = self._ui_settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        main_state = self._ui_settings.value("window/main_state")
        if main_state is not None:
            self.restoreState(main_state)
        main_splitter_state = self._ui_settings.value("layout/main_splitter")
        if main_splitter_state is not None:
            self.main_splitter.restoreState(main_splitter_state)
        else:
            self.main_splitter.setSizes([205, 1_000, 300])
        inspector_index = self._ui_settings.value("layout/inspector_tab", 0, type=int)
        if 0 <= inspector_index < self.inspector_tabs.count():
            self.inspector_tabs.setCurrentIndex(inspector_index)
        for panel, action in self._panel_actions.items():
            key = f"layout/panel_visible/{panel.objectName()}"
            visible = self._ui_settings.value(key, True, type=bool)
            panel.setVisible(visible)
            action.setChecked(visible)
        candidate_visibility_version = self._ui_settings.value(
            "view/qet_candidate_visibility_version", 0, type=int
        )
        if candidate_visibility_version < 1:
            # Earlier builds exposed every imported drawing-only reference by default.
            # Migrate once so old profiles open on a clean engineering SLD.
            self._ui_settings.setValue("view/qet_source_candidates_visible", False)
            self._ui_settings.setValue("view/qet_candidate_visibility_version", 1)
        candidates_visible = self._ui_settings.value(
            "view/qet_source_candidates_visible", False, type=bool
        )
        self.show_source_candidates_action.setChecked(candidates_visible)

    def _save_workspace_layout(self) -> None:
        self._ui_settings.setValue("window/geometry", self.saveGeometry())
        self._ui_settings.setValue("window/main_state", self.saveState())
        self._ui_settings.setValue("layout/main_splitter", self.main_splitter.saveState())
        self._ui_settings.setValue("layout/inspector_tab", self.inspector_tabs.currentIndex())
        for panel in self._panel_actions:
            self._ui_settings.setValue(
                f"layout/panel_visible/{panel.objectName()}", not panel.isHidden()
            )
        self._ui_settings.setValue(
            "view/qet_source_candidates_visible",
            self.show_source_candidates_action.isChecked(),
        )
        self._ui_settings.sync()

    def _reset_workspace_layout(self) -> None:
        self.resize(1600, 1000)
        for panel, action in self._panel_actions.items():
            panel.show()
            action.setChecked(True)
        self.main_splitter.setSizes([205, 1_000, 300])
        self.inspector_tabs.setCurrentWidget(self.palette_panel)
        self.show_source_candidates_action.setChecked(False)
        self.canvas.set_source_candidate_visibility(False)
        self.statusBar().showMessage(
            "Workspace reset. Drag the visible splitter grips to resize columns and panels.",
            6500,
        )
        self._save_workspace_layout()

    def _set_source_candidate_visibility(self, visible: bool) -> None:
        self.canvas.set_source_candidate_visibility(visible)
        state = "visible" if visible else "hidden"
        self.statusBar().showMessage(
            f"QET drawing-only reference candidates are now {state}; they are never electrical equipment.",
            6000,
        )

    def _on_qet_symbol_selected(self, asset_id: str) -> None:
        self.inspector_tabs.setCurrentWidget(self.symbol_browser_panel)
        self.statusBar().showMessage(
            f"Source drawing symbol selected: {asset_id}. Inserted symbols remain drawing-only "
            "until an explicit electrical equipment mapping is implemented.",
            9000,
        )

    def _apply_script_workspace(self, workspace: NetworkWorkspace) -> None:
        """Replace the active network workspace with a script-built model."""
        if not isinstance(workspace, NetworkWorkspace):
            QMessageBox.warning(
                self, "Code & Automation", "Script did not return a valid workspace."
            )
            return
        if not self._confirm_discard():
            self._log(
                "Code & Automation result was not applied; the active project was preserved."
            )
            return
        self.project = self.services.project_workspace.create(workspace.network.name)
        self.project_path = None
        self.workspace = workspace
        self._bind_workspace_commands()
        self._active_execution = None
        self.export_action.setEnabled(False)
        self.results.clear()
        self.canvas.set_workspace(self.workspace)
        self._refresh_explorer()
        self._clear_properties()
        self._update_title()
        self._update_diagram_header()
        self._update_status_bases()
        self._dirty = True
        self.workspace_tabs.setCurrentIndex(0)
        self._log("Network workspace replaced from Code & Automation Studio.")
        QTimer.singleShot(100, self._fit_diagram)
        self.statusBar().showMessage(
            "Script-built network rendered · structural validation passed", 7000
        )

    def _bind_workspace_commands(self) -> None:
        """Rebind the shared transaction boundary after workspace replacement."""
        self.commands = NetworkWorkspaceCommands(self.workspace, source="workbench")
        if hasattr(self, "canvas"):
            self.canvas.set_command_service(self.commands)

    def _connect_canvas(self) -> None:
        self.canvas.element_selected.connect(self._inspect_element)
        self.canvas.layout_changed.connect(self._mark_dirty)
        self.canvas.position_committed.connect(self._record_move)
        self.canvas.rotate_symbol_requested.connect(self._rotate_diagram_symbol_by_identifier)
        self.canvas.remove_symbol_requested.connect(self._remove_selected)
        self.canvas.create_bus_requested.connect(self._add_bus)
        self.canvas.load_template_requested.connect(self._load_reference_template)

    def _insert_qet_symbol(self, asset_id: str, rotation_deg: float = 0.0) -> None:
        try:
            definition = self.symbol_browser.definition_for_asset(asset_id)
        except KeyError as exc:
            QMessageBox.warning(self, "Insert Source Symbol", str(exc))
            return
        center = self.canvas.mapToScene(self.canvas.viewport().rect().center())
        # A source symbol is positioned by its declared hotspot, not by a guessed
        # top-left corner. This keeps the electrical reference point under the cursor.
        anchor_x = center.x()
        anchor_y = center.y()
        if self.workspace.snap_enabled:
            grid = self.workspace.grid_spacing
            snapped = snap_point(Point(anchor_x, anchor_y), grid)
            anchor_x, anchor_y = snapped.x, snapped.y
        x = anchor_x - definition.hotspot.x
        y = anchor_y - definition.hotspot.y
        placement = DiagramSymbolPlacement.create(asset_id, x, y, rotation_deg)
        # Explicit insertion must reveal the drawing-only layer before the new
        # graphics item is created; QGraphicsScene cannot select hidden items.
        # Keep the menu action and canvas layer state synchronized.
        if not self.show_source_candidates_action.isChecked():
            self.show_source_candidates_action.setChecked(True)
        self._undo_stack.push(_AddDiagramSymbolCommand(self, placement, definition))
        self.canvas.setFocus()
        self.statusBar().showMessage(
            "Placed as a source drawing candidate only. It is not an approved one-line symbol "
            "or an electrical network component.",
            9000,
        )

    def _add_diagram_symbol(self, placement: DiagramSymbolPlacement, definition) -> None:
        self.commands.upsert_symbol(placement)
        self.canvas.insert_diagram_symbol(placement, definition)
        self._refresh_explorer()
        self._mark_dirty()
        self._log(
            f"Inserted drawing symbol {placement.asset_id} · rotation {placement.rotation_deg:g}°. "
            "No electrical topology was inferred."
        )

    def _remove_diagram_symbol(self, instance_id: UUID) -> None:
        self.commands.remove_symbol(instance_id)
        self.canvas.remove_diagram_symbol(instance_id)
        self._refresh_explorer()
        self._clear_properties()
        self._mark_dirty()

    def _apply_diagram_symbol_rotation(self, instance_id: UUID, rotation_deg: float) -> None:
        current = self.workspace.diagram_symbols[instance_id]
        placement = self.commands.move_symbol(
            instance_id, current.x, current.y, rotation_deg=rotation_deg
        )
        self.canvas.set_diagram_symbol_rotation(instance_id, placement.rotation_deg)
        self._inspect_element("diagram_symbol", str(instance_id))
        self._mark_dirty()

    def _rotate_selected_symbol(self, delta_deg: float) -> None:
        selected_bus = self.canvas.selected_bus_symbol()
        if selected_bus is not None:
            identifier, current = selected_bus
            self._undo_stack.push(
                _RotateBusCommand(self, identifier, current, (current + float(delta_deg)) % 360.0)
            )
            return
        selected = self.canvas.selected_diagram_symbol()
        if selected is None:
            self.statusBar().showMessage(
                "Select a busbar or a placed source drawing symbol to rotate.", 5000
            )
            return
        identifier, _current = selected
        self._rotate_diagram_symbol_by_identifier(str(identifier), delta_deg)

    def _apply_bus_rotation(self, identifier: UUID, rotation_deg: float) -> None:
        normalized = self.commands.rotate_bus(identifier, rotation_deg)
        self.canvas.set_bus_rotation(identifier, normalized)
        self._inspect_element("bus", str(identifier))
        self._mark_dirty()

    def _rotate_diagram_symbol_by_identifier(self, identifier: str, delta_deg: float) -> None:
        try:
            placement_id = UUID(identifier)
            placement = self.workspace.diagram_symbols[placement_id]
        except (ValueError, KeyError) as exc:
            self._log(f"Cannot rotate drawing symbol {identifier}: {exc}")
            return
        target = (placement.rotation_deg + float(delta_deg)) % 360.0
        if abs(target - placement.rotation_deg) < 1e-9:
            return
        self._undo_stack.push(
            _RotateDiagramSymbolCommand(self, placement_id, placement.rotation_deg, target)
        )

    # --------------------------------------------------------------- projects
    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Unsaved project",
            "Save changes before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self._save_project()
        return True

    def _new_project(self) -> None:
        if not self._confirm_discard():
            return
        name = "Untitled Project"
        self.project = self.services.project_workspace.create(name)
        self.workspace = NetworkWorkspace(Network("Network 1"))
        self._bind_workspace_commands()
        self.project_path = None
        self._undo_stack.clear()
        self._session_runs.clear()
        self._active_execution = None
        self.results.clear()
        self.export_action.setEnabled(False)
        self._dirty = False
        self._refresh_all()
        self._log("Created a new empty project.")

    def _load_reference_template(self) -> None:
        if not self._confirm_discard():
            return
        template = self.services.build_reference_template.execute("REF-3PH-001")
        self.project = self.services.project_workspace.create(
            "REF-3PH-001B",
            "Physical one-bus Thevenin benchmark network",
            template.study_settings,
        )
        self.workspace = template.workspace
        self._bind_workspace_commands()
        self.project_path = None
        self._undo_stack.clear()
        self._session_runs.clear()
        self._active_execution = None
        self.results.clear()
        self.export_action.setEnabled(False)
        self._dirty = True
        self._refresh_all()
        QTimer.singleShot(100, self._fit_diagram)
        self._log(
            "Loaded REF-3PH-001B physical network template: one AC bus and one explicit "
            "Thevenin equivalent source."
        )

    def _load_pfa_es001_substation(self) -> None:
        """Create the PFA-ES-001 model through the application use case."""
        if not self._confirm_discard():
            return
        try:
            built = self.services.build_pfa_es001_substation.execute()
            self.project = self.services.project_workspace.create(
                "PFA-ES-001",
                "220 kV double-bus substation · one line bay · one transformer bay",
            )
            self.workspace = built.workspace
            self._bind_workspace_commands()
        except (ValueError, TypeError, NetworkDomainError) as exc:
            QMessageBox.critical(self, "Build PFA-ES-001", str(exc))
            return
        self.project_path = None
        self._undo_stack.clear()
        self._session_runs.clear()
        self._active_execution = None
        self.results.clear()
        self.export_action.setEnabled(False)
        self._dirty = True
        self._refresh_all()
        QTimer.singleShot(100, self._fit_diagram)
        report = built.validation
        self._log(
            "Built PFA-ES-001: 220 kV double bus, two bays, eight explicit switchgear devices, "
            "one line boundary and one transformer boundary."
        )
        self._log(
            f"Substation validation: structural topology "
            f"{'VALID' if report.structurally_valid else 'INVALID'}; "
            f"study readiness {'READY' if report.study_ready else 'BLOCKED'} (unresolved external data)."
        )
        for interface in report.interfaces:
            self._log(
                f"{interface.equipment_name}: busbar={', '.join(interface.connected_busbar_names) or 'NONE'}; "
                f"unresolved={len(interface.unresolved_parameters)} parameters."
            )
        self.statusBar().showMessage(
            "PFA-ES-001 loaded · topology validated · studies blocked until equipment data is verified",
            12000,
        )

    @staticmethod
    def _network_sidecar(project_path: Path) -> Path:
        return project_path.with_suffix(project_path.suffix + ".network.json")

    @staticmethod
    def _default_projects_directory() -> Path:
        """Return a per-user project directory outside the application installation."""
        documents = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )
        base = Path(documents) if documents else Path.home() / "Documents"
        directory = base / "POWER_FAULT_ANALYZER" / "Projects"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _open_project(self) -> None:
        if not self._confirm_discard():
            return
        initial_directory = (
            self.project_path.parent
            if self.project_path is not None
            else self._default_projects_directory()
        )
        selected, _ = QFileDialog.getOpenFileName(
            self, "Open PFA Project", str(initial_directory), "PFA Project (*.pfa)"
        )
        if not selected:
            return
        path = Path(selected)
        try:
            project = self.services.project_workspace.open(path)
            network_path = self._network_sidecar(path)
            if network_path.is_file():
                workspace = self.services.network_document_repository.load(network_path)
            else:
                workspace = NetworkWorkspace(Network(f"{project.name} Network"))
                self._log("No network sidecar found; opened project with an empty network.")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            QMessageBox.critical(self, "Open Project", str(exc))
            return
        self.project = project
        self.workspace = workspace
        self._bind_workspace_commands()
        self.project_path = path
        self._undo_stack.clear()
        self._active_execution = None
        self.results.clear()
        self.export_action.setEnabled(False)
        self._session_runs = [
            (record.study_name, record.result.fault_type.value, record.fault_bus_name)
            for record in self.workspace.study_history
        ]
        self._dirty = False
        self._refresh_all()
        QTimer.singleShot(100, self._fit_diagram)
        self._log(f"Opened project: {path}")

    def _save_project(self) -> bool:
        if self.project_path is None:
            return self._save_project_as()
        try:
            saved = self.services.project_workspace.save(self.project, self.project_path)
            sidecar = self.services.network_document_repository.save(
                self.workspace, self._network_sidecar(saved)
            )
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.critical(self, "Save Project", str(exc))
            return False
        self.project_path = saved
        self._dirty = False
        self._update_title()
        self.statusBar().showMessage(f"Project and network saved: {saved.name}", 6000)
        self._log(f"Saved project document: {saved}")
        self._log(f"Saved physical network and diagram layout: {sidecar}")
        return True

    def _save_project_as(self) -> bool:
        initial_path = (
            self.project_path
            if self.project_path is not None
            else self._default_projects_directory() / f"{self.project.name}.pfa"
        )
        selected, _ = QFileDialog.getSaveFileName(
            self, "Save PFA Project", str(initial_path), "PFA Project (*.pfa)"
        )
        if not selected:
            return False
        self.project_path = Path(selected)
        if self.project_path.suffix.lower() != ".pfa":
            self.project_path = self.project_path.with_suffix(".pfa")
        return self._save_project()

    def closeEvent(self, event) -> None:
        if self._update_shutdown_approved:
            # The update path already saved the project before downloading.
            # Do not show a second discard prompt after the updater accepted handoff.
            self._save_workspace_layout()
            self.canvas.prepare_for_shutdown()
            event.accept()
            return
        if self._confirm_discard():
            self._save_workspace_layout()
            self.canvas.prepare_for_shutdown()
            event.accept()
        else:
            event.ignore()

    # ------------------------------------------------------------- model editing
    def _add_bus(self) -> None:
        dialog = BusDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            name, voltage = dialog.values()
            index = len(self.workspace.network.buses)
            bus = self.commands.add_bus(
                name, voltage,
                180.0 + (index % 4) * 180.0,
                100.0 + (index // 4) * 150.0,
            )
            self._model_changed(f"Added AC bus {bus.name} at {voltage:g} kV.")
        except (NetworkDomainError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Add AC Bus", str(exc))

    def _add_equivalent_source(self) -> None:
        if not self.workspace.network.buses:
            QMessageBox.information(self, "Add Source", "Create an AC bus first.")
            return
        dialog = EquivalentSourceDialog(self.workspace.network.buses, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            name, bus_id, base_mva, e1, z1, z2, z0, frequency = dialog.specification()
            bus_pos = self.workspace.diagram_positions.get(bus_id, (100.0, 100.0))
            source_count = sum(
                1
                for item in self.workspace.network.equipment
                if isinstance(item, (EquivalentSource, SynchronousGenerator))
                and self.workspace.network.get_connection(item.terminals[0].id).bus_id == bus_id
            )
            source = self.commands.add_equivalent_source(
                name=name,
                bus_id=bus_id,
                base_power_mva=base_mva,
                positive_sequence_pu=z1,
                negative_sequence_pu=z2,
                zero_sequence_pu=z0,
                prefault_voltage_pu=e1,
                frequency_hz=frequency,
                position=(
                    bus_pos[0] - 150.0,
                    bus_pos[1] - 90.0 - source_count * 105.0,
                ),
            )
            self._model_changed(f"Added explicit Thevenin equivalent source {source.name}.")
        except (NetworkDomainError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Add Thevenin Source", str(exc))

    def _add_generator(self) -> None:
        if not self.workspace.network.buses:
            QMessageBox.information(self, "Add Generator", "Create an AC bus first.")
            return
        dialog = GeneratorDialog(self.workspace.network.buses, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            specification = dialog.specification()
            bus_pos = self.workspace.diagram_positions.get(specification.bus_id, (100.0, 100.0))
            source_count = sum(
                1
                for item in self.workspace.network.equipment
                if isinstance(item, (EquivalentSource, SynchronousGenerator))
                and self.workspace.network.get_connection(item.terminals[0].id).bus_id
                == specification.bus_id
            )
            generator = self.commands.add_generator(
                specification,
                position=(
                    bus_pos[0] - 150.0,
                    bus_pos[1] - 90.0 - source_count * 105.0,
                ),
            )
            self._model_changed(
                f"Added synchronous generator {generator.name} with explicit sequence data."
            )
        except (NetworkDomainError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Add Synchronous Generator", str(exc))

    def _add_line_from_selection(self, _checked: bool = False) -> None:
        selected = self.canvas.selected_bus_ids
        if len(selected) != 2:
            QMessageBox.information(
                self,
                "Connect Buses",
                "Select exactly two bus symbols in the Network Design canvas, then retry.",
            )
            return
        self._add_line(from_bus_id=selected[0], to_bus_id=selected[1])

    def _add_line(
        self,
        _checked: bool = False,
        *,
        from_bus_id: UUID | None = None,
        to_bus_id: UUID | None = None,
    ) -> None:
        buses = self.workspace.network.buses
        if len(buses) < 2:
            QMessageBox.information(self, "Add Line", "At least two AC buses are required.")
            return
        dialog = LineDialog(buses, self, from_bus_id=from_bus_id, to_bus_id=to_bus_id)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            line = self.commands.add_line(dialog.specification())
            self._model_changed(
                f"Added {line.model_kind.value} line {line.name}; sequence series impedances are explicit."
            )
        except (NetworkDomainError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Add Transmission Line", str(exc))

    def _resolve_boundary_equipment(self) -> None:
        interfaces = [
            item
            for item in self.workspace.network.equipment
            if isinstance(item, UnresolvedEquipmentInterface)
        ]
        if not interfaces:
            QMessageBox.information(
                self,
                "Resolve Boundary Equipment",
                "There are no unresolved equipment boundaries.",
            )
            return
        labels = [
            f"{item.name} · {item.interface_kind.value} · {str(item.id)[:8]}" for item in interfaces
        ]
        selected, accepted = QInputDialog.getItem(
            self,
            "Resolve Boundary Equipment",
            "Select the boundary to materialize:",
            labels,
            0,
            False,
        )
        if not accepted:
            return
        interface = interfaces[labels.index(selected)]

        if interface.interface_kind is EquipmentInterfaceKind.TRANSMISSION_LINE:
            dialog = ResolveLineBoundaryDialog(interface, self)
            while dialog.exec() == dialog.DialogCode.Accepted:
                try:
                    specification = dialog.specification()
                    resolution = self.services.resolve_line_boundary.execute(
                        self.workspace, specification
                    )
                except (NetworkDomainError, ValueError, TypeError) as exc:
                    QMessageBox.warning(self, "Resolve Line Boundary", str(exc))
                    continue
                self.workspace = resolution.workspace
                self._bind_workspace_commands()
                self._model_changed(
                    f"Resolved {resolution.equipment.name}: explicit series-only line + remote "
                    f"Thevenin source {resolution.external_source.name}; source reference recorded."
                )
                break
            else:
                return
        elif interface.interface_kind is EquipmentInterfaceKind.POWER_TRANSFORMER:
            dialog = ResolveTransformerBoundaryDialog(interface, self)
            while dialog.exec() == dialog.DialogCode.Accepted:
                try:
                    specification = dialog.specification()
                    resolution = self.services.resolve_transformer_boundary.execute(
                        self.workspace, specification
                    )
                except (NetworkDomainError, ValueError, TypeError) as exc:
                    QMessageBox.warning(self, "Resolve Transformer Boundary", str(exc))
                    continue
                self.workspace = resolution.workspace
                self._bind_workspace_commands()
                self._model_changed(
                    f"Resolved {resolution.equipment.name}: two-winding transformer "
                    f"{resolution.equipment.vector_group_notation}; "
                    f"LV bus {resolution.remote_bus.name}."
                )
                break
            else:
                return
        else:
            QMessageBox.warning(
                self,
                "Resolve Boundary Equipment",
                f"Unsupported boundary type: {interface.interface_kind.value}",
            )
            return

        self._log(
            "Parameter provenance recorded as USER_CONFIRMED. The entered source reference "
            "has not been independently verified by PFA."
        )
        self.statusBar().showMessage(
            "Boundary equipment materialized · run Validate Network before a study", 9000
        )

    def _remove_selected(self) -> None:
        """Delete the canvas selection as one atomic, undoable workspace command."""
        selected_refs = self.canvas.selected_element_refs()
        if selected_refs:
            commands = []
            # Remove custom labels and drawing-only symbols before their owners.
            for kind, identifier in selected_refs:
                object_id = UUID(identifier)
                if kind == "label" and object_id in self.workspace.diagram_labels:
                    commands.append(RemoveDiagramLabel(object_id))
                elif kind == "diagram_symbol" and object_id in self.workspace.diagram_symbols:
                    commands.append(RemoveDiagramSymbol(object_id))
            # Equipment must be removed before buses so connected terminal references
            # are released within the same atomic command batch.
            for kind, identifier in selected_refs:
                if kind in {"equipment", "generator", "line"}:
                    commands.append(RemoveEquipment(UUID(identifier)))
            for kind, identifier in selected_refs:
                if kind == "bus":
                    commands.append(RemoveBus(UUID(identifier)))
            if not commands:
                self.statusBar().showMessage(
                    "The selected generated label has no editable override, or the item is not removable.",
                    5000,
                )
                return
            # Validate the complete deletion against an isolated workspace before
            # placing it on QUndoStack. Failed deletion never partially mutates PFA.
            try:
                trial_workspace = deepcopy(self.workspace)
                NetworkWorkspaceCommands(trial_workspace, source="shortcut-preflight").execute_many(
                    tuple(commands)
                )
                self._undo_stack.push(_DeleteWorkspaceSelectionCommand(self, tuple(commands)))
            except (NetworkDomainError, ValueError, TypeError, KeyError, RuntimeError) as exc:
                QMessageBox.warning(self, "Delete Selection", str(exc))
            return

        # Preserve Explorer deletion when the Project Explorer owns the selection.
        selected = self.explorer.selectedItems()
        if not selected:
            return
        data = selected[0].data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, tuple) or len(data) != 2:
            return
        kind, identifier = data
        try:
            if kind == "bus":
                self.commands.remove_bus(UUID(identifier))
            elif kind in {
                "equivalent_source", "synchronous_generator", "line",
                "two_winding_transformer", "unresolved_equipment_interface", "other",
            }:
                self.commands.remove_equipment(UUID(identifier))
            else:
                return
            self._model_changed(f"Removed selected {kind}.")
        except (NetworkDomainError, ValueError, TypeError, KeyError) as exc:
            QMessageBox.warning(self, "Remove Element", str(exc))

    def _commit_operating_workspace_commands(self, commands: tuple[object, ...], label: str) -> None:
        """Preflight scenario commands, then put one complete snapshot on Qt undo/redo."""
        before = deepcopy(self.workspace)
        preview = deepcopy(self.workspace)
        NetworkWorkspaceCommands(preview, source="workbench-operations-preflight").execute_many(commands)
        after = deepcopy(preview)
        self._undo_stack.push(_OperatingWorkspaceSnapshotCommand(self, before, after, label))

    def _apply_operating_workspace_snapshot(self, snapshot: NetworkWorkspace, message: str) -> None:
        self.commands.execute(_RestoreWorkspaceSnapshot(snapshot))
        self._operating_state_changed(message)

    def _operating_state_changed(self, message: str) -> None:
        """Refresh only the scenario projection; physical-network studies remain valid."""
        self._dirty = True
        self.canvas.set_workspace(self.workspace)
        self._update_title()
        self._update_diagram_header()
        self._log(message)
        self.statusBar().showMessage(message, 7000)

    def _capture_operating_scenario(self) -> None:
        name, accepted = QInputDialog.getText(
            self, "Capture Operating Scenario", "Scenario name:", text="Normal operation"
        )
        if not accepted:
            return
        if not name.strip():
            QMessageBox.warning(self, "Operating Scenario", "Scenario name cannot be empty.")
            return
        try:
            scenario = scenario_from_physical_network(
                self.workspace.network, name.strip(),
                description="Captured from physical equipment positions; simulation overlay only.",
            )
            self._commit_operating_workspace_commands(
                (UpsertOperatingScenario(scenario), SetActiveOperatingScenario(scenario.scenario_id)),
                "Capture and activate operating scenario",
            )
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Operating Scenario", str(exc))

    def _activate_operating_scenario(self) -> None:
        scenarios = sorted(
            self.workspace.operating_scenarios.values(), key=lambda item: item.name.casefold()
        )
        if not scenarios:
            QMessageBox.information(self, "Operating Scenario", "No saved operating scenarios exist.")
            return
        labels = {
            f"{item.name} [{str(item.scenario_id)[:8]}]": item.scenario_id for item in scenarios
        }
        selected, accepted = QInputDialog.getItem(
            self, "Activate Operating Scenario", "Scenario:", list(labels), 0, False
        )
        if not accepted:
            return
        try:
            self._commit_operating_workspace_commands(
                (SetActiveOperatingScenario(labels[selected]),), "Activate operating scenario"
            )
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Operating Scenario", str(exc))

    def _deactivate_operating_scenario(self) -> None:
        if self.workspace.active_operating_scenario_id is None:
            return
        try:
            self._commit_operating_workspace_commands(
                (SetActiveOperatingScenario(None),), "Deactivate operating overlay"
            )
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Operating Scenario", str(exc))

    def _set_selected_scenario_switch_position(self) -> None:
        scenario = self.workspace.active_operating_scenario
        if scenario is None:
            QMessageBox.information(
                self, "Operating Scenario", "Activate an operating scenario first."
            )
            return
        selected = self.canvas.selected_element_refs()
        equipment_ids = [
            UUID(identifier) for kind, identifier in selected
            if kind in {"equipment", "line"}
        ]
        if len(equipment_ids) != 1:
            QMessageBox.information(
                self, "Operating Scenario", "Select exactly one switching device on the diagram."
            )
            return
        try:
            equipment = self.workspace.network.get_equipment(equipment_ids[0])
            if not isinstance(equipment, SwitchingDevice):
                raise TypeError("The selected equipment is not a switching device.")
            current = scenario.switch_positions.get(
                equipment.id,
                OperatingSwitchPosition(equipment.position.value),
            )
            options = ["Open", "Closed"]
            default_index = 0 if current is OperatingSwitchPosition.OPEN else 1
            selected_position, accepted = QInputDialog.getItem(
                self, "Simulated Switch Position", equipment.name, options, default_index, False
            )
            if not accepted:
                return
            target = (
                OperatingSwitchPosition.OPEN
                if selected_position == "Open" else OperatingSwitchPosition.CLOSED
            )
            self._commit_operating_workspace_commands(
                (SetOperatingScenarioSwitchPosition(scenario.scenario_id, equipment.id, target),),
                "Change simulated switch position",
            )
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Operating Scenario", str(exc))

    def _analyze_active_operating_scenario(self) -> None:
        try:
            result = analyze_workspace(self.workspace)
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Operating Scenario Analysis", str(exc))
            return
        summary = (
            f"Scenario: {result.scenario_name}\n"
            f"Buses: {len(result.buses)}\n"
            f"Energized: {len(result.energized_bus_ids)}\n"
            f"De-energized: {len(result.deenergized_bus_ids)}\n"
            f"Islands: {len(result.islands)}\n"
            f"Diagnostics: {len(result.diagnostics)}\n\n"
            "This is a topology/connectivity assessment, not an AC load-flow or safety clearance."
        )
        QMessageBox.information(self, "Operating Scenario Analysis", summary)

    def _model_changed(self, message: str) -> None:
        self._dirty = True
        self._active_execution = None
        self.export_action.setEnabled(False)
        self.results.clear()
        self.canvas.set_workspace(self.workspace)
        self._refresh_explorer()
        self._update_title()
        self._log(message)
        self.statusBar().showMessage("Network model changed · previous results invalidated", 7000)

    # ------------------------------------------------------------------ analysis
    def _run_fault_study(self) -> None:
        buses = self.workspace.network.buses
        if not buses:
            QMessageBox.information(self, "Short-Circuit Study", "The network has no AC buses.")
            return
        defaults = self.project.study_settings
        bus_default = next((item for item in buses if item.name == defaults.bus_name), buses[0])
        dialog = FaultStudyDialog(
            buses,
            default_base_mva=defaults.base_power_mva,
            default_fault_type=defaults.fault_type,
            default_fault_impedance=defaults.fault_impedance_pu,
            default_bus_id=bus_default.id,
            parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            bus_id, fault_type, fault_impedance, base_mva = dialog.values()
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Short-Circuit Study", str(exc))
            return
        bus = self.workspace.network.get_bus(bus_id)
        self.run_action.setEnabled(False)
        self._progress.show()
        self._set_editing_enabled(False)
        self._log(
            f"Starting {fault_type.value} fault study at bus {bus.name}; "
            f"Zf={fault_impedance.real:g}+j{fault_impedance.imag:g} p.u."
        )
        network = self.workspace.network
        project_name = self.project.name
        worker = _StudyWorker(
            lambda: self.services.run_network_fault_study.execute(
                network,
                fault_bus_id=bus_id,
                fault_type=fault_type,
                fault_impedance_pu=fault_impedance,
                base_power_mva=base_mva,
                project_name=project_name,
            )
        )
        worker.signals.succeeded.connect(
            lambda execution: self._study_succeeded(execution, fault_type, bus.name)
        )
        worker.signals.failed.connect(self._study_failed)
        self._active_worker = worker
        self._thread_pool.start(worker)

    def _set_editing_enabled(self, enabled: bool) -> None:
        for widget in (
            self.explorer,
            self.palette_panel,
            self.properties,
            self.symbol_browser,
            self.canvas,
            self.quick_toolbar,
            self.model_toolbar,
            self.diagram_toolbar,
            self.analysis_toolbar,
        ):
            widget.setEnabled(enabled)
        self.menuBar().setEnabled(enabled)

    def _study_succeeded(self, execution, fault_type: FaultType, bus_name: str) -> None:
        self._active_worker = None
        self._progress.hide()
        self._active_execution = execution
        self.results.display(execution.result, project_name=self.project.name, bus_name=bus_name)
        self.workspace_tabs.setCurrentWidget(self.results)
        self.run_action.setEnabled(True)
        self._set_editing_enabled(True)
        self.export_action.setEnabled(True)
        record = NetworkStudyRecord.create(
            project_name=self.project.name,
            study_name=execution.report.metadata.study_name,
            network_id=self.workspace.network.id,
            fault_bus_id=execution.result.bus_id,
            fault_bus_name=bus_name,
            result=execution.result,
        )
        self.workspace.record_study(record)
        self._session_runs = [
            (item.study_name, item.result.fault_type.value, item.fault_bus_name)
            for item in self.workspace.study_history
        ]
        self._dirty = True
        self._update_title()
        self._refresh_explorer()
        maximum = max(abs(value) for value in execution.result.phase_currents_ka)
        self._log(f"PASS · ShortCircuitSolver completed; maximum phase current={maximum:.9f} kA.")
        self._log(
            "Sequence networks built: "
            f"positive={len(execution.networks.positive.nodes)} nodes / "
            f"{len(execution.networks.positive.branches)} branches; "
            f"negative={len(execution.networks.negative.nodes)} nodes / "
            f"{len(execution.networks.negative.branches)} branches; "
            f"zero={len(execution.networks.zero.nodes)} nodes / "
            f"{len(execution.networks.zero.branches)} branches."
        )
        self.statusBar().showMessage("Short-circuit study completed · Results available", 7000)

    def _study_failed(self, details: str) -> None:
        self._active_worker = None
        self._progress.hide()
        self.run_action.setEnabled(True)
        self._set_editing_enabled(True)
        self._log("ERROR · Short-circuit study failed.")
        self._log(details)
        QMessageBox.critical(self, "Short-Circuit Study Failed", details.splitlines()[-1])

    def _validate_network(self) -> None:
        diagnostics = DefaultNetworkValidationService().validate_for_calculation(
            self.workspace.network
        )
        errors = [item for item in diagnostics if item.severity is DiagnosticSeverity.ERROR]
        warnings = [item for item in diagnostics if item.severity is DiagnosticSeverity.WARNING]
        self._log(f"Network validation: {len(errors)} error(s), {len(warnings)} warning(s).")
        for item in diagnostics:
            self._log(f"{item.severity.value.upper()} · {item.code}: {item.message}")
        if errors:
            QMessageBox.warning(
                self,
                "Network Validation",
                f"{len(errors)} blocking error(s). See Calculation Console.",
            )
        else:
            QMessageBox.information(
                self, "Network Validation", "No blocking topology diagnostics were returned."
            )

    def _export_diagram_svg(self) -> None:
        if self.workspace is None or not self.workspace.network.buses:
            QMessageBox.information(self, "Export One-Line Diagram", "The electrical model is empty.")
            return
        selected, selected_filter = QFileDialog.getSaveFileName(
            self, "Export Engineering Diagram", f"{self.project.name}.svg",
            "SVG vector document (*.svg);;PDF vector document (*.pdf)",
        )
        if not selected:
            return
        path = Path(selected)
        extension = ".pdf" if "PDF" in selected_filter else ".svg"
        if path.suffix.lower() not in {".svg", ".pdf"}:
            path = path.with_suffix(extension)
        try:
            document = project_network_to_diagram(self.workspace)
            options = {"width_mm": 180.0, "height_mm": 120.0,
                       "author": "", "revision": "PFA-SYNC-001"}
            if path.suffix.lower() == ".pdf":
                export_engineering_pdf(document, path, **options)
            else:
                export_engineering_svg(document, path, **options)
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            QMessageBox.critical(self, "Engineering Diagram Export", str(exc))
            return
        self._log(
            f"Canonical model diagram exported as {path.suffix.upper()} "
            f"(buses={len(document.buses)}, equipment={len(document.symbols)}, "
            f"terminal connections={len(document.connection_pairs)}): {path}"
        )
        self.statusBar().showMessage(f"Canonical engineering diagram exported: {path.name}", 7000)

    def _export_report(self) -> None:
        if self._active_execution is None:
            return
        directory = QFileDialog.getExistingDirectory(self, "Export Engineering Report", "")
        if not directory:
            return
        try:
            exported = self.services.export_report.execute(
                self._active_execution.report,
                directory,
                include_pdf=True,
                include_excel=True,
            )
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.critical(self, "Report Export", str(exc))
            return
        self._log(f"Report JSON: {exported.json_path}")
        self._log(f"Report PDF: {exported.pdf_path}")
        self._log(f"Report Excel: {exported.excel_path}")
        for name, path in exported.csv_paths.items():
            self._log(f"Report CSV ({name}): {path}")
        QMessageBox.information(self, "Report Export", f"Reports exported to:\n{directory}")

    # ------------------------------------------------------------------- canvas
    def _record_move(
        self, identifier: str, old_x: float, old_y: float, new_x: float, new_y: float
    ) -> None:
        if abs(old_x - new_x) + abs(old_y - new_y) < 0.1:
            return
        self._undo_stack.push(_MoveDiagramItemCommand(self, identifier, old_x, old_y, new_x, new_y))

    def _apply_diagram_position(self, identifier: str, x: float, y: float) -> None:
        object_id = UUID(identifier)
        # A canonical equipment ID must move the electrical equipment itself.
        # A drawing placement is addressed by its own instance UUID; do not let a
        # linked QET reference shadow the actual equipment during keyboard nudging.
        placement = self.workspace.diagram_symbols.get(object_id)
        if placement is None and object_id not in {
            *(bus.id for bus in self.workspace.network.buses),
            *(equipment.id for equipment in self.workspace.network.equipment),
        }:
            placement = next(
                (item for item in self.workspace.diagram_symbols.values()
                 if item.equipment_id == object_id), None
            )
        if placement is not None:
            self.commands.move_symbol(placement.instance_id, x, y)
            if placement.instance_id == object_id:
                self._inspect_element("diagram_symbol", identifier)
        else:
            self.commands.move_elements({object_id: (x, y)})
        self.canvas.apply_position(identifier, x, y)
        self._dirty = True
        self._update_title()

    def _nudge_selected(self, dx: int, dy: int, *, large: bool = False) -> None:
        selected = self.canvas.selected_movable_positions()
        if not selected:
            return
        if self.workspace.snap_enabled:
            step = float(self.workspace.grid_spacing) * (5.0 if large else 1.0)
        else:
            step = 10.0 if large else 1.0
        delta_x, delta_y = float(dx) * step, float(dy) * step
        moves: dict[str, tuple[float, float, float, float]] = {}
        for identifier, old_x, old_y in selected:
            new_x, new_y = old_x + delta_x, old_y + delta_y
            if self.workspace.snap_enabled:
                spacing = float(self.workspace.grid_spacing)
                snapped = snap_point(Point(new_x, new_y), spacing)
                new_x, new_y = snapped.x, snapped.y
            if abs(new_x - old_x) + abs(new_y - old_y) > 1e-9:
                moves[identifier] = (old_x, old_y, new_x, new_y)
        if moves:
            self._undo_stack.push(_MoveDiagramItemsCommand(self, moves))
            self.statusBar().showMessage(
                f"Moved {len(moves)} selected element(s) · undo available", 2500
            )

    def _zoom_diagram(self, factor: float) -> None:
        current = abs(float(self.canvas.transform().m11()))
        target = max(0.08, min(8.0, current * float(factor)))
        if current <= 1e-9 or abs(target - current) <= 1e-9:
            return
        scale = target / current
        self.canvas.scale(scale, scale)

    def _focus_property_editor(self) -> None:
        if not self._property_editor_target and self._selected_equipment_id is None:
            self.statusBar().showMessage("Select a bus or equipment item first.", 3000)
            return
        self.inspector_tabs.show()
        self.properties_panel.show()
        self.inspector_tabs.setCurrentWidget(self.properties_panel)
        self.property_name_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.property_name_edit.selectAll()

    def _show_keyboard_shortcuts(self) -> None:
        message = """FILE
Ctrl+N  New project
Ctrl+O  Open project
Ctrl+S  Save project
Ctrl+Shift+S  Save project as

EDIT (when the diagram canvas is focused)
Ctrl+Z  Undo
Ctrl+Y or Ctrl+Shift+Z  Redo
Ctrl+A  Select all diagram elements
Delete / Backspace  Delete selection (undoable)
Escape  Clear selection

DIAGRAM (when the diagram canvas is focused)
Arrow keys  Nudge selection by one grid step
Shift+Arrow  Nudge selection by five grid steps
Ctrl+R / Ctrl+Shift+R  Rotate clockwise / counterclockwise
Ctrl++ / Ctrl+-  Zoom in / out
Home or Ctrl+0  Fit diagram
G  Show/hide grid
Ctrl+G  Toggle snap to grid
F2  Focus selected element properties

ANALYSIS AND EXPORT
F5  Run study
Ctrl+E  Export active study report
Ctrl+Shift+E  Export diagram as SVG
F1  Show this shortcut reference

Canvas editing shortcuts are scoped to the diagram so text fields and the Code & Automation editor retain their native keyboard behavior."""
        QMessageBox.information(self, "POWER_FAULT_ANALYZER — Keyboard Shortcuts", message)

    def _fit_diagram(self) -> None:
        """Fit the complete electrical drawing with proportional, bounded margins."""
        bounds = self.canvas.scene().itemsBoundingRect()
        if bounds.isEmpty():
            self.statusBar().showMessage(
                "The diagram is empty; add a busbar or open a reference case.", 4500
            )
            return
        # A fixed 100-unit margin made small networks appear unnecessarily tiny.
        # Scale the margin to the actual diagram extent, with a minimum clearance.
        margin_x = max(24.0, bounds.width() * 0.12)
        margin_y = max(24.0, bounds.height() * 0.12)
        target = bounds.adjusted(-margin_x, -margin_y, margin_x, margin_y)
        self.canvas.fitInView(target, Qt.AspectRatioMode.KeepAspectRatio)
        self.canvas.viewport().update()
        self.statusBar().showMessage("Diagram fitted to all visible network elements.", 2200)

    def _set_grid_visible(self, visible: bool) -> None:
        self.canvas.set_grid_visible(visible)
        self.grid_toggle.setChecked(bool(visible))

    def _toggle_grid(self) -> None:
        self._set_grid_visible(not self.canvas.grid_visible)

    def _set_snap_enabled(self, enabled: bool) -> None:
        self.commands.set_grid(self.workspace.grid_spacing, bool(enabled))
        self.canvas.set_snap_enabled(enabled)
        self.snap_toggle.setChecked(bool(enabled))
        self._mark_dirty()

    def _toggle_snap(self) -> None:
        self._set_snap_enabled(not self.workspace.snap_enabled)

    def _update_inspector_overview(self) -> None:
        """Refresh the live model-scope summary shown when nothing is selected."""
        if not hasattr(self, "inspector_network_name"):
            return
        network = self.workspace.network
        settings = self.project.study_settings
        self.inspector_network_name.setText(network.name)
        self.inspector_network_meta.setText(
            f"System base {settings.base_power_mva:g} MVA  ·  "
            f"Reference voltage {settings.base_voltage_ll_kv:g} kV"
        )
        self.inspector_bus_count.setText(str(len(network.buses)))
        self.inspector_equipment_count.setText(str(len(network.equipment)))
        self.inspector_study_count.setText(str(len(self.workspace.study_history)))

    def _update_diagram_header(self) -> None:
        network = self.workspace.network
        self.diagram_title.setText(network.name)
        self._update_inspector_overview()
        bus_count = len(network.buses)
        equipment_count = len(network.equipment)
        symbol_count = len(self.workspace.diagram_symbols)
        settings = self.project.study_settings
        self.diagram_summary.setText(
            f"{bus_count} BUSES   ·   {equipment_count} EQUIPMENT   ·   "
            f"{symbol_count} DRAWING REFERENCES   ·   {settings.base_power_mva:g} MVA BASE"
        )
        self.grid_toggle.blockSignals(True)
        self.grid_toggle.setChecked(self.canvas.grid_visible)
        self.grid_toggle.blockSignals(False)
        self.snap_toggle.blockSignals(True)
        self.snap_toggle.setChecked(self.workspace.snap_enabled)
        self.snap_toggle.blockSignals(False)

    def _filter_explorer(self, text: str) -> None:
        needle = text.casefold().strip()

        def visit(item: QTreeWidgetItem) -> bool:
            direct_match = not needle or needle in item.text(0).casefold()
            child_match = False
            for index in range(item.childCount()):
                child_match = visit(item.child(index)) or child_match
            visible = direct_match or child_match
            item.setHidden(not visible)
            if needle and child_match:
                item.setExpanded(True)
            return visible

        for index in range(self.explorer.topLevelItemCount()):
            visit(self.explorer.topLevelItem(index))

    # -------------------------------------------------------------- navigation
    def _refresh_all(self) -> None:
        self.canvas.set_workspace(self.workspace)
        self._refresh_explorer()
        self._clear_properties()
        self._update_title()
        self._update_status_bases()
        self._update_diagram_header()
        self._filter_explorer(self.explorer_search.text())

    def _refresh_explorer(self) -> None:
        self.explorer.clear()
        root = QTreeWidgetItem([self.project.name])
        root.setIcon(0, self._awesome_icon("fa5s.folder", QStyle.StandardPixmap.SP_DirIcon))
        root.setData(0, Qt.ItemDataRole.UserRole, ("project", str(self.project.project_id)))
        self.explorer.addTopLevelItem(root)
        bus_count = len(self.workspace.network.buses)
        bus_word = "bus" if bus_count == 1 else "buses"
        network_node = QTreeWidgetItem(
            [f"{self.workspace.network.name} · {bus_count} {bus_word}"]
        )
        network_node.setIcon(
            0, self._awesome_icon("fa5s.project-diagram", QStyle.StandardPixmap.SP_DirIcon)
        )
        root.addChild(network_node)
        groups = {
            "Buses": [("bus", item) for item in self.workspace.network.buses],
            "Branches": [
                ("line", item)
                for item in self.workspace.network.equipment
                if isinstance(item, Line)
            ],
            "Transformers": [
                ("two_winding_transformer", item)
                for item in self.workspace.network.equipment
                if isinstance(item, TwoWindingTransformer)
            ],
            "Generators and Sources": [
                (
                    "synchronous_generator"
                    if isinstance(item, SynchronousGenerator)
                    else "equivalent_source",
                    item,
                )
                for item in self.workspace.network.equipment
                if isinstance(item, (SynchronousGenerator, EquivalentSource))
            ],
            "Switchgear": [
                ("switching_device", item)
                for item in self.workspace.network.equipment
                if isinstance(item, SwitchingDevice)
            ],
            "Unresolved Equipment Interfaces": [
                ("unresolved_equipment_interface", item)
                for item in self.workspace.network.equipment
                if isinstance(item, UnresolvedEquipmentInterface)
            ],
            "Other Equipment": [
                ("other", item)
                for item in self.workspace.network.equipment
                if not isinstance(
                    item,
                    (
                        Line,
                        TwoWindingTransformer,
                        SynchronousGenerator,
                        EquivalentSource,
                        SwitchingDevice,
                        UnresolvedEquipmentInterface,
                    ),
                )
            ],
        }
        group_icons = {
            "Buses": "fa5s.grip-lines",
            "Branches": "fa5s.project-diagram",
            "Transformers": "fa5s.exchange-alt",
            "Generators and Sources": "fa5s.bolt",
            "Switchgear": "fa5s.toggle-on",
            "Unresolved Equipment Interfaces": "fa5s.exclamation-triangle",
            "Other Equipment": "fa5s.cubes",
        }
        leaf_icons = {
            "bus": "fa5s.grip-lines",
            "line": "fa5s.project-diagram",
            "two_winding_transformer": "fa5s.exchange-alt",
            "synchronous_generator": "fa5s.industry",
            "equivalent_source": "fa5s.bolt",
            "switching_device": "fa5s.toggle-on",
            "unresolved_equipment_interface": "fa5s.exclamation-triangle",
            "other": "fa5s.cube",
        }
        for title, elements in groups.items():
            # Do not advertise empty model classes as if they were usable project
            # objects. Supported categories appear as soon as they contain data.
            if not elements:
                continue
            group = QTreeWidgetItem([f"{title} ({len(elements)})"])
            group.setIcon(
                0, self._awesome_icon(group_icons[title], QStyle.StandardPixmap.SP_DirIcon)
            )
            network_node.addChild(group)
            for kind, element in elements:
                leaf = QTreeWidgetItem([element.name])
                leaf.setIcon(
                    0, self._awesome_icon(leaf_icons[kind], QStyle.StandardPixmap.SP_FileIcon)
                )
                leaf.setData(0, Qt.ItemDataRole.UserRole, (kind, str(element.id)))
                group.addChild(leaf)
        mapped_symbols = [
            item for item in self.workspace.diagram_symbols.values() if item.equipment_id
        ]
        drawing_only_symbols = [
            item for item in self.workspace.diagram_symbols.values() if not item.equipment_id
        ]
        for title, placements in (
            ("Mapped Source-Symbol Candidates", mapped_symbols),
            ("Drawing-Only Source Symbols", drawing_only_symbols),
        ):
            if not placements:
                continue
            symbol_group = QTreeWidgetItem([f"{title} ({len(placements)})"])
            symbol_group.setIcon(
                0, self._awesome_icon("fa5s.shapes", QStyle.StandardPixmap.SP_DirIcon)
            )
            root.addChild(symbol_group)
            for placement in placements:
                try:
                    definition = self.symbol_browser.definition_for_asset(placement.asset_id)
                    symbol_name = definition.name_for("es")
                except KeyError:
                    symbol_name = f"Missing source asset: {placement.asset_id}"
                label = f"{placement.label} · {symbol_name}" if placement.label else symbol_name
                leaf = QTreeWidgetItem([label])
                leaf.setIcon(
                    0, self._awesome_icon("fa5s.draw-polygon", QStyle.StandardPixmap.SP_FileIcon)
                )
                leaf.setData(
                    0, Qt.ItemDataRole.UserRole, ("diagram_symbol", str(placement.instance_id))
                )
                symbol_group.addChild(leaf)

        study_records = self.workspace.study_history
        if study_records:
            studies = QTreeWidgetItem([f"Studies & Results ({len(study_records)})"])
            studies.setIcon(
                0, self._awesome_icon("fa5s.chart-line", QStyle.StandardPixmap.SP_DirIcon)
            )
            root.addChild(studies)
            for index, record in enumerate(study_records, start=1):
                leaf = QTreeWidgetItem(
                    [
                        (
                            f"{index:02d} · {record.study_name} · "
                            f"{record.result.fault_type.value} @ {record.fault_bus_name}"
                        )
                    ]
                )
                leaf.setData(0, Qt.ItemDataRole.UserRole, ("study", str(record.run_id)))
                studies.addChild(leaf)
        self.explorer.addTopLevelItem(root)
        self.explorer.expandToDepth(2)
        if hasattr(self, "explorer_search"):
            self._filter_explorer(self.explorer_search.text())
        if hasattr(self, "diagram_summary"):
            self._update_diagram_header()

    def _on_explorer_selection(self) -> None:
        items = self.explorer.selectedItems()
        if not items:
            return
        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, tuple) and len(data) == 2 and data[0] == "study":
            record = next(
                (item for item in self.workspace.study_history if str(item.run_id) == data[1]),
                None,
            )
            if record is not None:
                self.results.display(
                    record.result,
                    project_name=record.project_name,
                    bus_name=record.fault_bus_name,
                )
                self.workspace_tabs.setCurrentWidget(self.results)
                self._active_execution = None
                self.export_action.setEnabled(False)
                self.statusBar().showMessage(
                    "Historical result snapshot loaded · report re-export requires the original report object",
                    7000,
                )
            return
        if (
            isinstance(data, tuple)
            and len(data) == 2
            and data[0]
            in {
                "bus",
                "line",
                "two_winding_transformer",
                "equivalent_source",
                "synchronous_generator",
                "switching_device",
                "unresolved_equipment_interface",
                "other",
                "diagram_symbol",
            }
        ):
            self.canvas.select_element(UUID(data[1]))
            self._inspect_element(*data)

    def _inspect_element(self, kind: str, identifier: str) -> None:
        if not kind or not identifier:
            self._selected_equipment_id = None
            if hasattr(self, "switch_state_button"):
                self.switch_state_button.hide()
            self._clear_properties()
            return
        self._selected_equipment_id = None
        if hasattr(self, "switch_state_button"):
            self.switch_state_button.hide()
        # Selection from the diagram must reveal the editable inspector even if a
        # previous workspace-layout restore left its tab page hidden.
        self.inspector_tabs.show()
        self.properties_panel.show()
        self.inspector_tabs.setCurrentWidget(self.properties_panel)
        try:
            object_id = UUID(identifier)
            if kind == "diagram_symbol":
                placement = self.workspace.diagram_symbols[object_id]
                definition = self.symbol_browser.definition_for_asset(placement.asset_id)
                if placement.equipment_id is not None:
                    mapped_equipment = self.workspace.network.get_equipment(placement.equipment_id)
                    if isinstance(mapped_equipment, SwitchingDevice):
                        self._selected_equipment_id = mapped_equipment.id
                        target = (
                            SwitchPosition.OPEN
                            if mapped_equipment.is_closed
                            else SwitchPosition.CLOSED
                        )
                        self.switch_state_button.setText(
                            f"Set selected switch {target.value.upper()}…"
                        )
                        self.switch_state_button.show()
                rows = (
                    (
                        "Element type",
                        "Mapped source-symbol candidate"
                        if placement.equipment_id
                        else "Source drawing candidate",
                    ),
                    ("Symbol", definition.name_for("es")),
                    ("Source asset ID", placement.asset_id),
                    ("Rotation", f"{placement.rotation_deg:g}°"),
                    ("Position X", f"{placement.x:g}"),
                    ("Position Y", f"{placement.y:g}"),
                    ("License", definition.provenance.license_identifier),
                    ("Source status", "Unverified QET drawing candidate"),
                    ("Normative status", definition.provenance.normative_status),
                    (
                        "SLD export",
                        "Candidate only; verify standard edition and redistribution rights",
                    ),
                    (
                        "Electrical mapping",
                        (
                            f"Equipment {placement.equipment_id}; "
                            f"{len(placement.terminal_mappings)} explicit terminal mappings"
                        )
                        if placement.equipment_id
                        else "Not mapped — drawing-only object; excluded from network topology.",
                    ),
                )
            elif kind == "label":
                document = project_network_to_diagram(self.workspace)
                label = next(
                    (item for item in document.labels if item.label_id == object_id), None
                )
                if label is None:
                    raise KeyError(f"Unknown diagram annotation: {object_id}")
                rows = (
                    ("Element type", "Independent diagram annotation"),
                    ("Text", label.text),
                    ("Anchor", label.anchor),
                    ("Position X", f"{label.position.x:g}"),
                    ("Position Y", f"{label.position.y:g}"),
                    ("Rotation", f"{label.rotation_deg:g}°"),
                    ("Layer", label.layer),
                    ("Owner ID", str(label.owner_id) if label.owner_id else "Document"),
                    ("Domain effect", "None — annotation only"),
                )
            elif kind == "bus":
                element = self.workspace.network.get_bus(object_id)
                rows = (
                    (
                        "Element type",
                        "Busbar" if element.kind is BusKind.BUSBAR else "Connection node",
                    ),
                    ("Identifier", element.name),
                    ("Nominal voltage L-L", f"{element.nominal_voltage.value_kv:g} kV"),
                    (
                        "Diagram orientation",
                        f"{self.workspace.diagram_rotations.get(element.id, 0.0):g}°",
                    ),
                    ("Domain ID", str(element.id)),
                )
            else:
                element = self.workspace.network.get_equipment(object_id)
                rows = self._equipment_properties(kind, element)
                if isinstance(element, SwitchingDevice):
                    self._selected_equipment_id = element.id
                    if hasattr(self, "switch_state_button"):
                        target = SwitchPosition.OPEN if element.is_closed else SwitchPosition.CLOSED
                        self.switch_state_button.setText(
                            f"Set selected switch {target.value.upper()}…"
                        )
                        self.switch_state_button.show()
        except (KeyError, ValueError, TypeError) as exc:
            self._log(f"Properties inspector could not resolve selection: {exc}")
            return
        self.properties_empty_container.hide()
        self.properties.show()
        self.properties.clear()
        for name, value in rows:
            self.properties.addTopLevelItem(QTreeWidgetItem([name, value]))
        try:
            self._populate_property_editor(kind, identifier)
        except (KeyError, ValueError, TypeError) as exc:
            self.property_editor_widget.hide()
            self._log(f"Editable property inspector could not resolve selection: {exc}")

    def _projected_label(self, owner_id: UUID, *, text: str | None = None):
        document = project_network_to_diagram(self.workspace)
        candidates = [item for item in document.labels if item.owner_id == owner_id]
        if text is not None:
            exact = next((item for item in candidates if item.text == text), None)
            if exact is not None:
                return exact
        return next((item for item in candidates if item.label_id is not None), None)

    def _projected_position(self, kind: str, object_id: UUID) -> tuple[float, float]:
        stored = self.workspace.diagram_positions.get(object_id)
        if stored is not None:
            return float(stored[0]), float(stored[1])
        document = project_network_to_diagram(self.workspace)
        if kind == "bus":
            item = next(item for item in document.buses if item.bus_id == object_id)
            return item.center.x, item.center.y
        item = next(item for item in document.symbols if item.equipment_id == object_id)
        return item.center.x, item.center.y

    def _populate_property_editor(self, kind: str, identifier: str) -> None:
        object_id = UUID(identifier)
        document = project_network_to_diagram(self.workspace)
        state: dict
        name_caption = "Display label"
        voltage_visible = False
        rotation_visible = False

        if kind == "bus":
            bus = self.workspace.network.get_bus(object_id)
            x, y = self._projected_position(kind, object_id)
            state = {
                "name": bus.name,
                "voltage_kv": bus.nominal_voltage.value_kv,
                "x": x,
                "y": y,
                "rotation": self.workspace.diagram_rotations.get(object_id, 0.0),
                "position_explicit": object_id in self.workspace.diagram_positions,
                "rotation_explicit": object_id in self.workspace.diagram_rotations,
            }
            name_caption = "Bus name"
            voltage_visible = True
            rotation_visible = True
        elif kind == "diagram_symbol":
            placement = self.workspace.diagram_symbols[object_id]
            definition = self.symbol_browser.definition_for_asset(placement.asset_id)
            state = {
                "label": placement.label,
                "display_label": placement.label or definition.name_for("es"),
                "placement": placement,
                "x": placement.x,
                "y": placement.y,
                "rotation": placement.rotation_deg,
            }
            name_caption = "Drawing label"
            rotation_visible = True
        elif kind == "label":
            model = next(
                (item for item in document.labels if item.label_id == object_id), None
            )
            if model is None:
                raise KeyError(f"Unknown diagram annotation: {object_id}")
            override = self.workspace.diagram_labels.get(object_id)
            base_workspace = deepcopy(self.workspace)
            base_workspace.diagram_labels.pop(object_id, None)
            base_document = project_network_to_diagram(base_workspace)
            base_label = next(
                (item for item in base_document.labels if item.label_id == object_id),
                model,
            )
            state = {
                "label": model.text,
                "x": model.position.x,
                "y": model.position.y,
                "rotation": model.rotation_deg,
                "label_id": object_id,
                "label_override": override,
                "base_label": base_label,
            }
            name_caption = "Annotation text"
            rotation_visible = True
        elif kind in {"equipment", "line", "two_winding_transformer", "equivalent_source",
                      "synchronous_generator", "switching_device",
                      "unresolved_equipment_interface", "other"}:
            element = self.workspace.network.get_equipment(object_id)
            expected_label_id = uuid5(
                NAMESPACE_URL, f"urn:pfa:diagram-label:{object_id}:equipment-name"
            )
            projected_label = next(
                (item for item in document.labels if item.label_id == expected_label_id),
                None,
            )
            if projected_label is None or projected_label.label_id is None:
                raise KeyError(f"No editable canonical label is projected for {element.name}.")
            override = self.workspace.diagram_labels.get(projected_label.label_id)
            base_workspace = deepcopy(self.workspace)
            base_workspace.diagram_labels.pop(projected_label.label_id, None)
            base_document = project_network_to_diagram(base_workspace)
            base_label = next(
                (item for item in base_document.labels
                 if item.label_id == projected_label.label_id),
                None,
            )
            if base_label is None:
                raise KeyError(f"No generated base label is available for {element.name}.")
            x, y = self._projected_position(kind, object_id)
            state = {
                "display_label": override.text if override is not None else projected_label.text,
                "label_id": projected_label.label_id,
                "label_override": override,
                "base_label": base_label,
                "x": x,
                "y": y,
                "position_explicit": object_id in self.workspace.diagram_positions,
            }
            name_caption = "Equipment label"
        else:
            raise KeyError(f"Selection type '{kind}' is not editable in this increment.")

        self._property_editor_target = (kind, identifier)
        self._property_editor_state = dict(state)
        self.property_name_caption.setText(name_caption)
        text_value = state.get("name", state.get("display_label", state.get("label", "")))
        self.property_name_edit.setText(str(text_value))
        self.property_voltage_edit.setVisible(voltage_visible)
        self.property_voltage_caption.setVisible(voltage_visible)
        if voltage_visible:
            self.property_voltage_edit.setValue(float(state["voltage_kv"]))
        self.property_x_edit.setValue(float(state["x"]))
        self.property_y_edit.setValue(float(state["y"]))
        self.property_rotation_edit.setVisible(rotation_visible)
        self.property_rotation_caption.setVisible(rotation_visible)
        if rotation_visible:
            self.property_rotation_edit.setValue(float(state.get("rotation", 0.0)) % 360.0)
        self.property_editor_widget.show()

    @staticmethod
    def _placement_from_engineering_label(
        base_label, text: str, *, x: float, y: float, rotation_deg: float, existing=None
    ) -> DiagramLabelPlacement:
        if base_label.label_id is None:
            raise ValueError("The selected generated annotation has no stable label identity.")
        if existing is not None:
            return replace(
                existing, text=text, x=x, y=y, rotation_deg=rotation_deg
            )
        return DiagramLabelPlacement(
            label_id=base_label.label_id,
            owner_id=base_label.owner_id,
            text=text,
            x=x,
            y=y,
            anchor=base_label.anchor,
            font_family=base_label.font_family,
            size_pt=base_label.size_pt,
            weight=base_label.weight,
            color=base_label.color,
            rotation_deg=rotation_deg,
            visible=base_label.visible,
            layer=base_label.layer,
            priority=base_label.priority,
            unit=base_label.unit,
            number_format=base_label.number_format,
        )

    def _apply_property_editor_changes(self) -> None:
        if self._property_editor_target is None or self._property_editor_state is None:
            return
        kind, identifier = self._property_editor_target
        before = dict(self._property_editor_state)
        after = dict(before)
        name_value = self.property_name_edit.text().strip()
        if not name_value:
            QMessageBox.warning(self, "Property Editor", "The name or label cannot be empty.")
            return
        if kind == "bus":
            after["name"] = name_value
            after["voltage_kv"] = self.property_voltage_edit.value()
        elif kind == "equipment":
            after["display_label"] = name_value
        elif kind == "diagram_symbol":
            after["display_label"] = name_value
            after["label"] = (
                None
                if before["label"] is None and name_value == before["display_label"]
                else name_value
            )
        elif kind in {"line", "two_winding_transformer", "equivalent_source",
                      "synchronous_generator", "switching_device",
                      "unresolved_equipment_interface", "other"}:
            after["display_label"] = name_value
        else:
            after["label"] = name_value
        after["x"] = self.property_x_edit.value()
        after["y"] = self.property_y_edit.value()
        if "position_explicit" in before:
            moved = (abs(after["x"] - before["x"]) > 1e-9
                     or abs(after["y"] - before["y"]) > 1e-9)
            after["position_explicit"] = before["position_explicit"] or moved
        if "rotation" in after:
            after["rotation"] = self.property_rotation_edit.value() % 360.0
            if "rotation_explicit" in before:
                rotated = abs(after["rotation"] - before["rotation"]) > 1e-9
                after["rotation_explicit"] = before["rotation_explicit"] or rotated
        if kind == "diagram_symbol":
            after["placement"] = replace(
                before["placement"], x=after["x"], y=after["y"],
                rotation_deg=after["rotation"], label=after["label"],
            )

        if kind in {"equipment", "line", "two_winding_transformer", "equivalent_source",
                    "synchronous_generator", "switching_device",
                    "unresolved_equipment_interface", "other"}:
            base = before["base_label"]
            old_override = before.get("label_override")
            # The projected EngineeringLabel stores its coordinates in Point
            # `position`; persisted DiagramLabelPlacement overrides expose
            # scalar `x` and `y`.  Keep the two contracts explicit instead of
            # treating the objects as interchangeable.
            if old_override is not None:
                current_label_x = old_override.x
                current_label_y = old_override.y
                current_label_rotation = old_override.rotation_deg
            else:
                current_label_x = base.position.x
                current_label_y = base.position.y
                current_label_rotation = base.rotation_deg
            label_x = current_label_x + (after["x"] - before["x"])
            label_y = current_label_y + (after["y"] - before["y"])
            if (
                name_value == base.text
                and abs(label_x - base.position.x) <= 1e-9
                and abs(label_y - base.position.y) <= 1e-9
                and abs(current_label_rotation - base.rotation_deg) <= 1e-9
            ):
                after["label_override"] = None
            else:
                after["label_override"] = self._placement_from_engineering_label(
                    base, name_value, x=label_x, y=label_y,
                    rotation_deg=current_label_rotation, existing=old_override,
                )
        elif kind == "label":
            base = before["base_label"]
            if (
                name_value == base.text
                and abs(after["x"] - base.position.x) <= 1e-9
                and abs(after["y"] - base.position.y) <= 1e-9
                and abs(after["rotation"] - base.rotation_deg) <= 1e-9
            ):
                after["label_override"] = None
            else:
                after["label_override"] = self._placement_from_engineering_label(
                    base, name_value, x=after["x"], y=after["y"],
                    rotation_deg=after["rotation"], existing=before.get("label_override"),
                )

        if all(after.get(key) == before.get(key) for key in after):
            return
        try:
            # Validate against an isolated workspace before QUndoStack calls redo().
            # Qt undo commands must not leak domain exceptions from redo/undo callbacks.
            self._preflight_inspector_state(kind, identifier, after)
            self._undo_stack.push(
                _InspectorEditCommand(self, kind, identifier, before, after)
            )
        except (KeyError, ValueError, TypeError, RuntimeError, NetworkDomainError) as exc:
            QMessageBox.warning(self, "Property Editor", str(exc))

    def _preflight_inspector_state(self, kind: str, identifier: str, state: dict) -> None:
        """Validate an inspector edit on an isolated copy before it enters QUndoStack."""
        preview_workspace = deepcopy(self.workspace)
        preview_commands = NetworkWorkspaceCommands(
            preview_workspace, source="workbench-inspector-preflight"
        )
        preview_commands.execute_many(self._build_inspector_commands(kind, identifier, state))

    def _build_inspector_commands(self, kind: str, identifier: str, state: dict) -> list:
        """Build the same domain/presentation commands for preflight, commit and undo."""
        object_id = UUID(identifier)
        commands = []
        if kind == "bus":
            current = self.workspace.network.get_bus(object_id)
            if current.name != state["name"] or abs(
                current.nominal_voltage.value_kv - state["voltage_kv"]
            ) > 1e-9:
                commands.append(UpdateBus(object_id, state["name"], state["voltage_kv"]))
            current_position = self.workspace.diagram_positions.get(object_id)
            desired_position_explicit = state.get("position_explicit", True)
            if desired_position_explicit:
                if current_position is None or tuple(current_position) != (state["x"], state["y"]):
                    commands.append(MoveDiagramElements(((object_id, state["x"], state["y"]),)))
            elif current_position is not None:
                commands.append(RemoveDiagramPosition(object_id))
            current_rotation = self.workspace.diagram_rotations.get(object_id, 0.0)
            desired_rotation_explicit = state.get("rotation_explicit", True)
            if desired_rotation_explicit:
                if abs(current_rotation - state["rotation"]) > 1e-9:
                    commands.append(RotateBusbar(object_id, state["rotation"]))
            elif object_id in self.workspace.diagram_rotations:
                commands.append(RemoveDiagramRotation(object_id))
        elif kind in {"equipment", "line", "two_winding_transformer", "equivalent_source",
                      "synchronous_generator", "switching_device",
                      "unresolved_equipment_interface", "other"}:
            current_position = self.workspace.diagram_positions.get(object_id)
            desired_position_explicit = state.get("position_explicit", True)
            if desired_position_explicit:
                if current_position is None or tuple(current_position) != (state["x"], state["y"]):
                    commands.append(MoveDiagramElements(((object_id, state["x"], state["y"]),)))
            elif current_position is not None:
                commands.append(RemoveDiagramPosition(object_id))
            label_id = state["label_id"]
            current_override = self.workspace.diagram_labels.get(label_id)
            desired_override = state.get("label_override")
            if current_override != desired_override:
                if desired_override is None:
                    if current_override is not None:
                        commands.append(RemoveDiagramLabel(label_id))
                else:
                    commands.append(UpsertDiagramLabel(desired_override))
        elif kind == "diagram_symbol":
            commands.append(UpsertDiagramSymbol(state["placement"]))
        elif kind == "label":
            label_id = state["label_id"]
            current_override = self.workspace.diagram_labels.get(label_id)
            desired_override = state.get("label_override")
            if current_override != desired_override:
                if desired_override is None:
                    if current_override is not None:
                        commands.append(RemoveDiagramLabel(label_id))
                else:
                    commands.append(UpsertDiagramLabel(desired_override))
        return commands

    def _apply_inspector_state(self, kind: str, identifier: str, state: dict) -> None:
        object_id = UUID(identifier)
        commands = self._build_inspector_commands(kind, identifier, state)
        if commands:
            self.commands.execute_many(commands)
            self.canvas.set_workspace(self.workspace)
            self._refresh_explorer()
            self._update_diagram_header()
            self._mark_dirty()
            self.canvas.select_element(object_id)
            self._inspect_element(kind, identifier)

    def _toggle_selected_switch_position(self) -> None:
        if self._selected_equipment_id is None:
            return
        try:
            equipment = self.workspace.network.get_equipment(self._selected_equipment_id)
        except KeyError:
            return
        if not isinstance(equipment, SwitchingDevice):
            return
        target = SwitchPosition.OPEN if equipment.is_closed else SwitchPosition.CLOSED
        self._undo_stack.push(
            _SwitchPositionCommand(self, equipment.id, equipment.position, target)
        )

    def _apply_switch_position(self, equipment_id: UUID, position: SwitchPosition) -> None:
        equipment = self.commands.set_switch_position(equipment_id, position)
        for placement in tuple(self.workspace.diagram_symbols.values()):
            if placement.equipment_id != equipment_id:
                continue
            label = placement.label or equipment.name
            for suffix in (" (OPEN)", " (CLOSED)"):
                if label.endswith(suffix):
                    label = label[: -len(suffix)]
                    break
            self.commands.move_symbol(
                placement.instance_id, placement.x, placement.y,
                rotation_deg=placement.rotation_deg,
                label=f"{label} ({position.value.upper()})",
            )
        self._refresh_all()
        self._inspect_element("switching_device", str(equipment_id))
        self._mark_dirty()
        self.statusBar().showMessage(
            f"{equipment.name} set to {position.value.upper()} · topology reprojected",
            7000,
        )

    def _equipment_properties(self, kind: str, element) -> tuple[tuple[str, str], ...]:
        connections = {item.terminal_id: item.bus_id for item in self.workspace.network.connections}
        connected = [
            self.workspace.network.get_bus(connections[item.id]).name
            for item in element.terminals
            if item.id in connections
        ]
        base = [
            ("Element type", kind.replace("_", " ").title()),
            ("Identification", element.name),
            ("Connected buses", ", ".join(connected) or "Not connected"),
            ("Terminal count", str(len(element.terminals))),
            ("Domain ID", str(element.id)),
        ]
        if isinstance(element, EquivalentSource):
            model = element.equivalent
            base.extend(
                (
                    ("Base power", f"{model.base.base_power_mva:g} MVA"),
                    ("Base voltage", f"{model.base.base_voltage_kv:g} kV"),
                    ("Z1", _sequence_value(model.positive.impedance)),
                    ("Z2", _sequence_value(model.negative.impedance)),
                    ("Z0", _sequence_value(model.zero.impedance)),
                )
            )
        elif isinstance(element, SynchronousGenerator):
            model = element.sequence_impedances
            base.extend(
                (
                    ("Machine base", f"{model.base.base_power_mva:g} MVA"),
                    ("Z1 subtransient", _sequence_value(model.positive_subtransient)),
                    ("Z1 transient", _sequence_value(model.positive_transient)),
                    ("Z1 synchronous", _sequence_value(model.positive_synchronous)),
                    ("Z2", _sequence_value(model.negative)),
                    ("Z0", _sequence_value(model.zero)),
                    ("Stator connection", element.stator_connection.value),
                    ("Neutral grounding", element.neutral_grounding.mode.value),
                )
            )
        elif isinstance(element, Line):
            parameters = element.parameters.series_impedance_per_km
            base.extend(
                (
                    ("Model", element.model_kind.value),
                    ("Length", f"{element.length_km:g} km"),
                    ("Z1 per km", _complex_value(parameters.positive)),
                    ("Z2 per km", _complex_value(parameters.negative)),
                    ("Z0 per km", _complex_value(parameters.zero)),
                )
            )
        elif isinstance(element, TwoWindingTransformer):
            base.extend(
                (
                    ("Vector group", element.vector_group_notation),
                    ("Frequency", f"{element.frequency.value_hz:g} Hz"),
                    (
                        "HV winding",
                        f"{element.windings[0].rated_voltage_kv:g} kV / {element.windings[0].rated_power_mva:g} MVA",
                    ),
                    (
                        "LV winding",
                        f"{element.windings[1].rated_voltage_kv:g} kV / {element.windings[1].rated_power_mva:g} MVA",
                    ),
                    ("Z1", _complex_value(element.sequence_impedances.positive)),
                    ("Z2", _complex_value(element.sequence_impedances.negative)),
                    ("Z0", _complex_value(element.sequence_impedances.zero)),
                )
            )
        if isinstance(element, (Line, TwoWindingTransformer, EquivalentSource)):
            for parameter in element.data_evidence:
                source = f" · {parameter.source_reference}" if parameter.source_reference else ""
                base.append(
                    (
                        f"Evidence · {parameter.name} [{parameter.unit}]",
                        f"{parameter.status.value}: {parameter.value}{source}",
                    )
                )
        elif isinstance(element, SwitchingDevice):
            base.extend(
                (
                    ("Switchgear class", element.device_kind.value),
                    ("Position", element.position.value.upper()),
                    (
                        "Topology effect",
                        "Closed: merges terminal nodes"
                        if element.is_closed
                        else "Open: isolates terminal nodes",
                    ),
                    ("Numerical impedance", "Not stamped; ideal topological switching model"),
                )
            )
        elif isinstance(element, UnresolvedEquipmentInterface):
            base.extend(
                (
                    ("Interface kind", element.interface_kind.value),
                    (
                        "Calculation readiness",
                        "BLOCKED — unresolved boundary, not a numerical equipment model",
                    ),
                )
            )
            for parameter in element.parameters:
                value = "UNRESOLVED" if parameter.value is None else str(parameter.value)
                source = (
                    f" · source: {parameter.source_reference}" if parameter.source_reference else ""
                )
                base.append(
                    (
                        f"{parameter.name} [{parameter.unit}]",
                        f"{parameter.status.value}: {value}{source}",
                    )
                )
        elif isinstance(element, InductionMotor):
            base.append(("Model", "Induction motor; display only in this increment"))
        base.append(
            ("Editing", "Read-only inspector; model updates use dedicated application commands.")
        )
        return tuple(base)

    def _clear_properties(self) -> None:
        self._property_editor_target = None
        self._property_editor_state = None
        if hasattr(self, "property_editor_widget"):
            self.property_editor_widget.hide()
        self._selected_equipment_id = None
        if hasattr(self, "switch_state_button"):
            self.switch_state_button.hide()
        self.properties.clear()
        self.properties.hide()
        if hasattr(self, "properties_empty_container"):
            self.properties_empty_container.show()
        if hasattr(self, "inspector_overview_card"):
            self.inspector_overview_card.show()
        if hasattr(self, "properties_empty_state"):
            self.properties_empty_state.show()

    # ------------------------------------------------------------------- helpers
    def _mark_dirty(self, *_args) -> None:
        self._dirty = True
        self._update_title()

    def _update_title(self) -> None:
        marker = " *" if self._dirty else ""
        self.setWindowTitle(
            f"{self.project.name}{marker} — POWER_FAULT_ANALYZER Engineering Workbench"
        )

    def _update_status_bases(self) -> None:
        settings = self.project.study_settings
        self.statusBar().showMessage(
            f"System base {settings.base_power_mva:g} MVA · "
            f"Reference voltage {settings.base_voltage_ll_kv:g} kV · "
            f"Network buses {len(self.workspace.network.buses)}"
        )

    def _log(self, message: str) -> None:
        self.console.appendPlainText(message)
        severity_text = message.casefold()
        diagnostic_markers = ("error", "warning", "failed", "exception", "blocked")
        diagnostic_message = severity_text.startswith("invalid") or any(
            marker in severity_text for marker in diagnostic_markers
        )
        if hasattr(self, "console_dock") and diagnostic_message:
            self.console_dock.show()
            self.console_dock.raise_()

    def _apply_theme(self, *, persist: bool = True) -> None:
        """Apply the selected shell theme consistently to docked and floating panels."""
        theme = "dark" if self._dark_theme else "light"
        stylesheet = (
            _DARK_WORKBENCH_STYLESHEET if self._dark_theme else _LIGHT_WORKBENCH_STYLESHEET
        )
        application = QApplication.instance()
        if application is not None:
            palette = QPalette()
            if self._dark_theme:
                role_colors = {
                    QPalette.ColorRole.Window: "#111922",
                    QPalette.ColorRole.WindowText: "#E5EDF4",
                    QPalette.ColorRole.Base: "#111B26",
                    QPalette.ColorRole.AlternateBase: "#202E3C",
                    QPalette.ColorRole.ToolTipBase: "#202E3C",
                    QPalette.ColorRole.ToolTipText: "#E5EDF4",
                    QPalette.ColorRole.Text: "#E5EDF4",
                    QPalette.ColorRole.Button: "#202E3C",
                    QPalette.ColorRole.ButtonText: "#E5EDF4",
                    QPalette.ColorRole.Highlight: "#244B60",
                    QPalette.ColorRole.HighlightedText: "#F5FAFC",
                    QPalette.ColorRole.Link: "#29B6D1",
                }
            else:
                role_colors = {
                    QPalette.ColorRole.Window: "#F3F5F8",
                    QPalette.ColorRole.WindowText: "#1D2939",
                    QPalette.ColorRole.Base: "#FFFFFF",
                    QPalette.ColorRole.AlternateBase: "#F8FAFC",
                    QPalette.ColorRole.ToolTipBase: "#FFFFFF",
                    QPalette.ColorRole.ToolTipText: "#1D2939",
                    QPalette.ColorRole.Text: "#1D2939",
                    QPalette.ColorRole.Button: "#FFFFFF",
                    QPalette.ColorRole.ButtonText: "#344054",
                    QPalette.ColorRole.Highlight: "#DCEAF4",
                    QPalette.ColorRole.HighlightedText: "#173A57",
                    QPalette.ColorRole.Link: "#1D6A83",
                }
            for role, color in role_colors.items():
                palette.setColor(role, QColor(color))
            application.setPalette(palette)
            application.setStyleSheet(stylesheet)
        else:
            self.setStyleSheet(stylesheet)
        # Keep the SLD as a neutral engineering sheet in both shell themes.
        self.canvas.setBackgroundBrush(QColor("#F5F7F9"))
        self.canvas.viewport().update()
        if hasattr(self, "theme_action"):
            self.theme_action.setText("Dark mode")
            self.theme_action.setChecked(self._dark_theme)
            self.theme_action.setIcon(
                self._awesome_icon(
                    "fa5s.moon" if self._dark_theme else "fa5s.sun",
                    QStyle.StandardPixmap.SP_DialogHelpButton,
                )
            )
            self.theme_action.setToolTip(
                "Dark workbench shell is active; the drawing sheet remains light."
                if self._dark_theme
                else "Light workbench shell is active; the drawing sheet remains light."
            )
        if persist:
            self._ui_settings.setValue("appearance/theme", theme)
            self._ui_settings.sync()

    def _toggle_theme(self, checked: bool | None = None) -> None:
        self._dark_theme = not self._dark_theme if checked is None else bool(checked)
        self._apply_theme(persist=True)

    def _set_update_check_preference(self, enabled: bool) -> None:
        self._updates_on_startup = bool(enabled)
        self._ui_settings.setValue("updates/check_on_startup", self._updates_on_startup)
        self._ui_settings.sync()
        self.statusBar().showMessage(
            "Automatic update checks enabled." if enabled else "Automatic update checks disabled.",
            5000,
        )

    def _check_for_updates(self, *, automatic: bool = False) -> None:
        if self._update_check_worker is not None:
            return
        build_info = load_installation_build_info()
        if build_info is None:
            if not automatic:
                QMessageBox.information(
                    self,
                    "Software Updates",
                    "Update checks are available in the installed Windows x64 portable build. "
                    "A source checkout cannot replace itself.",
                )
            return

        self.check_updates_action.setEnabled(False)
        self.statusBar().showMessage("Checking for a newer published PFA release…")
        worker = _StudyWorker(
            lambda: discover_latest_release(build_info["version"])
        )
        worker.signals.succeeded.connect(
            lambda release: self._update_check_completed(
                release,
                automatic,
                build_info["version"],
            )
        )
        worker.signals.failed.connect(
            lambda detail: self._update_check_failed(detail, automatic)
        )
        self._update_check_worker = worker
        self._thread_pool.start(worker)

    def _update_check_completed(
        self,
        release: ReleaseUpdate | None,
        automatic: bool,
        installed_version: str,
    ) -> None:
        self._update_check_worker = None
        self.check_updates_action.setEnabled(True)
        if release is None:
            self.statusBar().showMessage("PFA is up to date with the latest published release.", 7000)
            if not automatic:
                QMessageBox.information(
                    self,
                    "Software Updates",
                    "No newer complete Windows x64 release is available. "
                    "Only published GitHub Releases are considered; workflow artifacts are not "
                    "treated as public product versions.",
                )
            return

        notes = release.body.strip()
        if len(notes) > 1400:
            notes = notes[:1400].rstrip() + "…"
        details = (
            f"A newer POWER_FAULT_ANALYZER version is available.\n\n"
            f"Installed: {installed_version}\n"
            f"Available: {release.tag_name}\n\n"
            f"{notes or 'No release notes were provided.'}\n\n"
            "The portable application will be updated in place. Your project files and "
            "preferences are stored separately. The previous application folder will be "
            "retained as a rollback backup."
        )
        answer = QMessageBox.question(
            self,
            "PFA Update Available",
            details,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._start_update_download(release)

    def _update_check_failed(self, detail: str, automatic: bool) -> None:
        self._update_check_worker = None
        self.check_updates_action.setEnabled(True)
        self.statusBar().showMessage("Could not check for PFA updates.", 7000)
        if not automatic:
            QMessageBox.warning(
                self,
                "Update Check Failed",
                f"GitHub could not be reached or returned invalid release metadata.\n\n{detail}",
            )

    def _start_update_download(self, release: ReleaseUpdate) -> None:
        if self._dirty and not self._save_project():
            QMessageBox.information(
                self,
                "PFA Update",
                "The update was cancelled because the current project could not be saved.",
            )
            return

        self._update_progress = QProgressDialog(
            f"Downloading POWER_FAULT_ANALYZER {release.tag_name}…", "", 0, 100, self
        )
        self._update_progress.setWindowTitle("PFA Update")
        self._update_progress.setCancelButton(None)
        self._update_progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._update_progress.setMinimumDuration(0)
        self._update_progress.setAutoClose(False)
        self._update_progress.setAutoReset(False)
        self._update_progress.setValue(0)
        self._update_progress.show()

        worker = _UpdateDownloadWorker(release)
        worker.signals.progress.connect(self._update_download_progress)
        worker.signals.completed.connect(self._update_download_completed)
        worker.signals.failed.connect(self._update_download_failed)
        self._update_download_worker = worker
        self._thread_pool.start(worker)

    def _update_download_progress(self, value: int) -> None:
        if self._update_progress is not None:
            self._update_progress.setValue(value)

    def _update_download_completed(self, bundle) -> None:
        self._update_download_worker = None
        if self._update_progress is not None:
            self._update_progress.close()
            self._update_progress = None
        self._launch_portable_update(bundle)

    def _update_download_failed(self, detail: str) -> None:
        self._update_download_worker = None
        if self._update_progress is not None:
            self._update_progress.close()
            self._update_progress = None
        QMessageBox.critical(
            self,
            "PFA Update Failed",
            f"The update package could not be downloaded or verified. "
            f"The installed application has not been changed.\n\n{detail}",
        )

    def _launch_portable_update(self, bundle) -> None:
        install_directory = Path(sys.executable).resolve().parent
        executable = install_directory / "POWER_FAULT_ANALYZER.exe"
        powershell = (
            Path(os.environ.get("SystemRoot", r"C:\Windows"))
            / "System32"
            / "WindowsPowerShell"
            / "v1.0"
            / "powershell.exe"
        )
        if not executable.is_file() or not powershell.is_file():
            shutil.rmtree(bundle.directory, ignore_errors=True)
            QMessageBox.critical(
                self,
                "PFA Update",
                "The portable installation or Windows PowerShell could not be located. "
                "The current version was not changed.",
            )
            return

        log_directory = (
            Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
            / "POWER_FAULT_ANALYZER"
            / "Logs"
            / "Updates"
        )
        try:
            log_directory.mkdir(parents=True, exist_ok=True)
            updater_log_path = log_directory / f"{bundle.directory.name}.log"
            status_path = log_directory / f"{bundle.directory.name}.status"
            status_path.unlink(missing_ok=True)
            updater_log = updater_log_path.open("w", encoding="utf-8")
        except OSError as exc:
            shutil.rmtree(bundle.directory, ignore_errors=True)
            QMessageBox.critical(
                self,
                "PFA Update",
                "PFA could not prepare persistent updater diagnostics. "
                "The current version was not changed.\n\n"
                f"{exc}",
            )
            return

        arguments = [
            str(powershell),
            "-NoLogo",
            "-NoProfile",
            "-WindowStyle",
            "Hidden",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(bundle.updater_script),
            "-ZipPath",
            str(bundle.archive),
            "-ChecksumPath",
            str(bundle.checksum_manifest),
            "-InstallDirectory",
            str(install_directory),
            "-WaitForProcessId",
            str(os.getpid()),
            "-StatusPath",
            str(status_path),
            "-Restart",
            "-CleanupDirectory",
            str(bundle.directory),
        ]
        startup_info = subprocess.STARTUPINFO()
        startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup_info.wShowWindow = subprocess.SW_HIDE
        creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            updater_process = subprocess.Popen(
                arguments,
                cwd=str(install_directory),
                stdin=subprocess.DEVNULL,
                stdout=updater_log,
                stderr=subprocess.STDOUT,
                close_fds=True,
                startupinfo=startup_info,
                creationflags=creation_flags,
            )
        except OSError as exc:
            updater_log.close()
            shutil.rmtree(bundle.directory, ignore_errors=True)
            QMessageBox.critical(
                self,
                "PFA Update",
                "Could not start the portable updater. The current version was not changed.\n\n"
                f"{exc}\n\nDiagnostics: {updater_log_path}",
            )
            return
        finally:
            if not updater_log.closed:
                updater_log.close()

        self._update_handoff_process = updater_process
        self._update_handoff_status_path = status_path
        self._update_handoff_log_path = updater_log_path
        self._update_handoff_bundle_directory = Path(bundle.directory)
        self._update_handoff_started_at = time.monotonic()
        self._update_handoff_timer = QTimer(self)
        self._update_handoff_timer.setInterval(200)
        self._update_handoff_timer.timeout.connect(self._poll_portable_update_handoff)
        self.statusBar().showMessage(
            "Preparing update. PFA will close only after the updater confirms it is ready…"
        )
        self._update_handoff_timer.start()

    def _poll_portable_update_handoff(self) -> None:
        status_path = self._update_handoff_status_path
        process = self._update_handoff_process
        if status_path is None or process is None:
            self._fail_portable_update_handoff("Updater handoff state was not initialized.")
            return

        state = ""
        detail = ""
        try:
            if status_path.is_file():
                lines = status_path.read_text(encoding="utf-8-sig").splitlines()
                if lines:
                    state = lines[0].strip().lower()
                    detail = "\n".join(lines[1:]).strip()
        except (OSError, UnicodeError):
            # The updater writes a tiny status file atomically from the user's
            # perspective; a concurrent read can briefly fail on Windows.
            pass

        if state == "ready":
            if self._update_handoff_timer is not None:
                self._update_handoff_timer.stop()
                self._update_handoff_timer.deleteLater()
                self._update_handoff_timer = None
            self._update_shutdown_approved = True
            self.statusBar().showMessage(
                "Updater is ready. Closing PFA so the verified replacement can be applied…"
            )
            QTimer.singleShot(0, self.close)
            return

        if state in {"failed", "rollback_failed", "rollback_restart_failed"}:
            self._fail_portable_update_handoff(
                detail or f"The updater stopped during its {state.replace('_', ' ')} stage."
            )
            return

        exit_code = process.poll()
        if exit_code is not None:
            self._fail_portable_update_handoff(
                detail
                or "The updater process exited before confirming that it was ready "
                f"(exit code {exit_code})."
            )
            return

        if time.monotonic() - self._update_handoff_started_at > 30.0:
            try:
                process.terminate()
            except OSError:
                pass
            self._fail_portable_update_handoff(
                "The updater did not complete its preflight handshake within 30 seconds. "
                "PFA has remained open and the installed version was not changed."
            )

    def _fail_portable_update_handoff(self, detail: str) -> None:
        if self._update_handoff_timer is not None:
            self._update_handoff_timer.stop()
            self._update_handoff_timer.deleteLater()
            self._update_handoff_timer = None

        bundle_directory = self._update_handoff_bundle_directory
        process = self._update_handoff_process
        if process is not None and process.poll() is not None and bundle_directory is not None:
            shutil.rmtree(bundle_directory, ignore_errors=True)

        log_path = self._update_handoff_log_path
        log_detail = ""
        if log_path is not None:
            try:
                if log_path.is_file():
                    log_detail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
            except OSError:
                pass

        self._update_handoff_process = None
        self._update_handoff_status_path = None
        self._update_handoff_log_path = None
        self._update_handoff_bundle_directory = None
        diagnostics = f"\n\nUpdater log: {log_path}" if log_path is not None else ""
        if log_detail:
            diagnostics += f"\n\nLast updater output:\n{log_detail}"
        QMessageBox.critical(
            self,
            "PFA Update Failed",
            "The updater did not confirm a safe handoff. PFA has stayed open and "
            "the installed version was not changed.\n\n"
            f"{detail}{diagnostics}",
        )
        self.statusBar().showMessage("Update cancelled. The current installation was not changed.", 8000)

    def _about(self) -> None:
        QMessageBox.information(
            self,
            "About POWER_FAULT_ANALYZER",
            "POWER_FAULT_ANALYZER Engineering Workbench\n"
            "APP-REBOOT-005 · Workbench visual re-composition\n\n"
            "Electrical calculations are executed by the existing numerical engine. "
            "The graphical diagram is presentation metadata; network topology is held by the domain aggregate.",
        )


_LIGHT_WORKBENCH_STYLESHEET = """
QMainWindow, QWidget { color: #1D2939; font-family: "Segoe UI"; font-size: 9pt; }
QMainWindow { background: #F3F5F8; }
QMenuBar { background: #FFFFFF; color: #344054; border-bottom: 1px solid #E4E7EC; padding: 1px 6px; min-height: 24px; }
QMenuBar::item { padding: 4px 8px; background: transparent; }
QMenuBar::item:selected { background: #EEF4F8; border-radius: 4px; }
QMenu { background: #FFFFFF; color: #1D2939; border: 1px solid #D0D5DD; padding: 5px; }
QMenu::item { padding: 7px 28px 7px 22px; }
QMenu::item:selected { background: #EAF2F8; color: #173A57; }
QToolBar#EngineeringCommandBar { background: #FFFFFF; border: 0; border-bottom: 1px solid #DCE3EA; spacing: 3px; padding: 2px 5px; min-height: 32px; }
QToolButton { color: #344054; border: 1px solid transparent; border-radius: 4px; padding: 4px 6px; min-height: 22px; }
QToolButton:hover { background: #F2F6FA; border-color: #D0DCE7; }
QToolBar::separator { background: #E4E7EC; width: 1px; margin: 4px 8px; }
QTreeWidget, QPlainTextEdit { background: #FFFFFF; color: #1D2939; border: 1px solid #E4E7EC; selection-background-color: #DCEAF4; selection-color: #173A57; alternate-background-color: #F8FAFC; }
QTreeWidget { outline: 0; border: 0; }
QTreeWidget::item { padding: 5px 4px; border: 0; }
QTreeWidget::item:hover { background: #F5F8FA; }
QTreeWidget::item:selected { background: #E6F0F6; color: #173A57; }
QTabWidget::pane { background: #FFFFFF; border: 1px solid #E1E6EC; top: -1px; }
QTabBar::tab { background: #F3F5F8; color: #667085; padding: 6px 11px; margin-right: 1px; border: 0; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { background: #FFFFFF; color: #173A57; border-bottom: 2px solid #1D6A83; font-weight: 600; }
QTabBar::tab:hover:!selected { background: #EAF0F5; color: #344054; }
QPushButton { background: #FFFFFF; color: #344054; border: 1px solid #D0D5DD; border-radius: 5px; padding: 8px 11px; }
QPushButton:hover { background: #F7FAFC; border-color: #9FB3C4; }
QPushButton:pressed { background: #EAF2F8; }
QPushButton#PrimaryAction { background: #173A57; color: #FFFFFF; border: 1px solid #173A57; font-weight: 600; }
QPushButton#PrimaryAction:hover { background: #24516F; border-color: #24516F; }
QPushButton#SecondaryAction { color: #173A57; border-color: #B7C9D6; }
QPushButton#EquipmentTile { background: #FFFFFF; border: 1px solid #DCE3E9; border-radius: 7px; color: #344054; font-weight: 600; padding: 12px; text-align: left; }
QPushButton#EquipmentTile:hover { background: #F3F8FB; border-color: #91AFC1; color: #173A57; }
QLineEdit, QDoubleSpinBox, QComboBox { background: #FFFFFF; color: #1D2939; border: 1px solid #D0D5DD; border-radius: 4px; padding: 5px 7px; min-height: 18px; selection-background-color: #DCEAF4; }
QLineEdit:focus, QDoubleSpinBox:focus, QComboBox:focus { border: 1px solid #4D829D; }
QHeaderView::section { background: #F5F7FA; color: #475467; padding: 8px; border: 0; border-bottom: 1px solid #E4E7EC; font-weight: 600; }
QStatusBar { background: #FFFFFF; color: #667085; border-top: 1px solid #E4E7EC; min-height: 19px; padding: 0 4px; }
QDockWidget { background: #FFFFFF; color: #344054; }
QDockWidget > QWidget { background: #FFFFFF; }
QWidget[workbenchPanelContent="true"] { background: #FFFFFF; }
QWidget#NetworkDesignPage { background: #F3F5F8; }
QTabWidget#MainWorkspaceTabs::pane { background: #F3F5F8; border: 0; }
QFrame[workbenchPanel="true"] { background: #FFFFFF; border: 1px solid #E4E7EC; }
QFrame#DiagramDocumentBar { background: #FFFFFF; border: 0; border-bottom: 1px solid #E4E7EC; }
QLabel#DiagramEyebrow { color: #667085; font-size: 7pt; font-weight: 700; letter-spacing: 1.15px; }
QLabel#DiagramTitle { color: #172B3A; font-size: 11pt; font-weight: 650; }
QLabel#DiagramSummary { color: #667085; font-size: 7.5pt; font-weight: 600; }
QToolButton#DiagramToggle { background: #F8FAFC; color: #475467; border: 1px solid #DCE3E9; border-radius: 5px; padding: 6px 11px; }
QToolButton#DiagramToggle:checked { background: #E7F1F5; color: #15546A; border-color: #9BBBC8; font-weight: 600; }
QPushButton#DiagramFitButton { padding: 6px 14px; background: #173A57; color: white; border-color: #173A57; font-weight: 600; }
QLineEdit#ProjectTreeSearch { background: #F8FAFC; }
QLabel#WorkbenchPanelHeading { color: #475467; font-size: 8pt; font-weight: 700; letter-spacing: 1px; padding: 3px 2px 7px 2px; }
QLabel#SectionEyebrow { color: #667085; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }
QLabel#CanvasWelcomeEyebrow { color: #1D6A83; font-size: 8pt; font-weight: 700; letter-spacing: 1.2px; }
QLabel#CanvasWelcomeTitle { color: #172B3A; font-size: 20pt; font-weight: 600; }
QLabel#CanvasWelcomeDescription { color: #667085; font-size: 10pt; }
QLabel#CanvasWelcomeHint { color: #98A2B3; font-size: 8pt; }
QFrame#CanvasWelcomeCard { background: #FFFFFF; border: 1px solid #DCE3E9; border-radius: 12px; }
QWidget#InspectorEmptyContainer { background: transparent; }
QFrame#InspectorOverviewCard { background: #FFFFFF; border: 1px solid #DCE3E9; border-radius: 7px; }
QLabel#InspectorOverviewEyebrow { color: #1D6A83; font-size: 7.5pt; font-weight: 700; letter-spacing: 0.8px; }
QLabel#InspectorOverviewTitle { color: #172B3A; font-size: 12pt; font-weight: 650; }
QLabel#InspectorOverviewMeta { color: #667085; font-size: 8pt; }
QFrame#InspectorMetricCard { background: #F8FAFC; border: 1px solid #E4E7EC; border-radius: 5px; }
QLabel#InspectorMetricCaption { color: #667085; font-size: 7pt; font-weight: 700; }
QLabel#InspectorMetricValue { color: #173A57; font-size: 15pt; font-weight: 700; }
QFrame#InspectorEmptyState { background: #F8FAFC; border: 1px dashed #D0D5DD; border-radius: 8px; }
QToolButton#DiagramZoomButton { background: #F8FAFC; color: #344054; border: 1px solid #DCE3E9; border-radius: 5px; padding: 4px 10px; min-width: 22px; font-size: 12pt; font-weight: 700; }
QToolButton#DiagramZoomButton:hover { background: #EAF2F8; border-color: #9FB3C4; }
QLabel#InspectorEmptyEyebrow { color: #1D6A83; font-size: 8pt; font-weight: 700; }
QLabel#InspectorEmptyTitle { color: #172B3A; font-size: 12pt; font-weight: 650; }
QLabel#InspectorEmptyDescription { color: #667085; font-size: 9pt; }
QFrame#SymbolPreviewFrame { background: #FFFFFF; border: 1px solid #E4E7EC; border-radius: 6px; }
QLabel#CandidateStatus { background: #FFF7E8; color: #946200; border: 1px solid #F3D49A; border-radius: 4px; padding: 4px 6px; font-size: 7pt; font-weight: 700; }
QLabel#QETProvenanceDetails { background: #F8FAFC; color: #475467; border: 1px solid #EAECF0; border-radius: 5px; padding: 8px; font-size: 8pt; }
QLabel#QETLibraryStatus { color: #98A2B3; font-size: 8pt; }
QToolButton#ProvenanceToggle { color: #475467; text-align: left; padding: 4px 2px; }
QSplitter::handle { background: #E5EAF0; }
QSplitter::handle:hover { background: #8AA5B7; }
QSplitter::handle:horizontal { width: 9px; margin: 0 1px; }
QSplitter::handle:vertical { height: 8px; margin: 1px 0; }
"""

_DARK_WORKBENCH_STYLESHEET = """
QMainWindow, QWidget { color: #E5EDF4; font-family: "Segoe UI"; font-size: 9pt; }
QMainWindow { background: #111922; }
QMenuBar { background: #192431; color: #E5EDF4; border-bottom: 1px solid #354556; padding: 1px 6px; min-height: 24px; }
QMenuBar::item { padding: 4px 8px; background: transparent; }
QMenuBar::item:selected { background: #304254; border-radius: 4px; }
QMenu { background: #202E3C; color: #E5EDF4; border: 1px solid #354556; padding: 4px; }
QMenu::item { padding: 6px 26px 6px 20px; }
QMenu::item:selected { background: #244B60; color: #F5FAFC; }
QToolBar#EngineeringCommandBar { background: #192431; border: 0; border-bottom: 1px solid #354556; spacing: 3px; padding: 2px 5px; min-height: 32px; }
QToolButton { background: transparent; color: #E5EDF4; border: 1px solid transparent; border-radius: 4px; padding: 4px 6px; min-height: 22px; }
QToolButton:hover { background: #304254; border-color: #4A5D70; }
QToolButton:pressed, QToolButton:checked { background: #244B60; border-color: #29B6D1; }
QToolBar::separator { background: #354556; width: 1px; margin: 4px 6px; }
QDockWidget { background: #192431; color: #E5EDF4; }
QDockWidget > QWidget { background: #192431; }
QDockWidget::title { background: #202E3C; color: #E5EDF4; padding: 6px 9px; border-bottom: 1px solid #354556; font-weight: 600; }
QWidget[workbenchPanelContent="true"] { background: #192431; }
QWidget#NetworkDesignPage { background: #111922; }
QTabWidget#MainWorkspaceTabs::pane { background: #111922; border: 0; }
QTreeWidget, QPlainTextEdit { background: #111B26; color: #E5EDF4; border: 1px solid #354556; selection-background-color: #244B60; selection-color: #F5FAFC; alternate-background-color: #202E3C; }
QTreeWidget { outline: 0; border: 0; }
QTreeWidget::item { padding: 5px 4px; border: 0; }
QTreeWidget::item:hover { background: #304254; }
QTreeWidget::item:selected { background: #244B60; color: #F5FAFC; }
QTabWidget::pane { background: #192431; border: 1px solid #354556; top: -1px; }
QTabBar::tab { background: #202E3C; color: #A5B4C3; padding: 6px 11px; margin-right: 1px; border: 0; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { background: #192431; color: #E5EDF4; border-bottom: 2px solid #29B6D1; font-weight: 600; }
QTabBar::tab:hover:!selected { background: #304254; color: #E5EDF4; }
QPushButton { background: #202E3C; color: #E5EDF4; border: 1px solid #4A5D70; border-radius: 4px; padding: 6px 9px; }
QPushButton:hover { background: #304254; border-color: #29B6D1; }
QPushButton:pressed { background: #244B60; }
QPushButton#PrimaryAction { background: #1D657C; color: #FFFFFF; border: 1px solid #1D657C; font-weight: 600; }
QPushButton#PrimaryAction:hover { background: #247F9A; border-color: #247F9A; }
QPushButton#SecondaryAction { color: #B9EAF2; border-color: #4A5D70; }
QPushButton#EquipmentTile { background: #202E3C; border: 1px solid #354556; border-radius: 6px; color: #E5EDF4; font-weight: 600; padding: 9px; text-align: left; }
QPushButton#EquipmentTile:hover { background: #304254; border-color: #29B6D1; color: #FFFFFF; }
QLineEdit, QDoubleSpinBox, QComboBox { background: #111B26; color: #E5EDF4; border: 1px solid #485B6F; border-radius: 4px; padding: 5px 7px; min-height: 18px; selection-background-color: #244B60; }
QLineEdit:focus, QDoubleSpinBox:focus, QComboBox:focus { border: 1px solid #29B6D1; }
QHeaderView::section { background: #202E3C; color: #A5B4C3; padding: 6px; border: 0; border-bottom: 1px solid #354556; font-weight: 600; }
QStatusBar { background: #192431; color: #A5B4C3; border-top: 1px solid #354556; min-height: 19px; padding: 0 4px; }
QFrame[workbenchPanel="true"] { background: #192431; border: 1px solid #354556; }
QFrame#DiagramDocumentBar { background: #192431; border: 0; border-bottom: 1px solid #354556; }
QLabel#DiagramEyebrow, QLabel#DiagramSummary { color: #A5B4C3; }
QLabel#DiagramTitle { color: #F5FAFC; font-size: 11pt; font-weight: 650; }
QToolButton#DiagramToggle { background: #202E3C; color: #E5EDF4; border: 1px solid #4A5D70; border-radius: 4px; padding: 4px 8px; }
QToolButton#DiagramToggle:checked { background: #244B60; color: #FFFFFF; border-color: #29B6D1; font-weight: 600; }
QPushButton#DiagramFitButton { padding: 5px 11px; background: #1D657C; color: white; border-color: #1D657C; font-weight: 600; }
QLineEdit#ProjectTreeSearch { background: #111B26; }
QLabel#WorkbenchPanelHeading { color: #A5B4C3; font-size: 8pt; font-weight: 700; letter-spacing: 1px; padding: 3px 2px 6px 2px; }
QLabel#SectionEyebrow { color: #A5B4C3; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }
QLabel#CanvasWelcomeEyebrow { color: #29B6D1; font-size: 8pt; font-weight: 700; letter-spacing: 1.2px; }
QLabel#CanvasWelcomeTitle { color: #F5FAFC; font-size: 20pt; font-weight: 600; }
QLabel#CanvasWelcomeDescription { color: #A5B4C3; font-size: 10pt; }
QLabel#CanvasWelcomeHint { color: #A5B4C3; font-size: 8pt; }
QFrame#CanvasWelcomeCard, QFrame#SymbolPreviewFrame { background: #202E3C; border: 1px solid #354556; border-radius: 8px; }
QWidget#InspectorEmptyContainer { background: transparent; }
QFrame#InspectorOverviewCard { background: #192431; border: 1px solid #354556; border-radius: 6px; }
QLabel#InspectorOverviewEyebrow { color: #29B6D1; font-size: 7.5pt; font-weight: 700; letter-spacing: 0.8px; }
QLabel#InspectorOverviewTitle { color: #F5FAFC; font-size: 12pt; font-weight: 650; }
QLabel#InspectorOverviewMeta { color: #A5B4C3; font-size: 8pt; }
QFrame#InspectorMetricCard { background: #202E3C; border: 1px solid #354556; border-radius: 5px; }
QLabel#InspectorMetricCaption { color: #A5B4C3; font-size: 7pt; font-weight: 700; }
QLabel#InspectorMetricValue { color: #F5FAFC; font-size: 15pt; font-weight: 700; }
QFrame#InspectorEmptyState { background: #202E3C; border: 1px dashed #4A5D70; border-radius: 8px; }
QToolButton#DiagramZoomButton { background: #202E3C; color: #E5EDF4; border: 1px solid #4A5D70; border-radius: 4px; padding: 3px 9px; min-width: 22px; font-size: 12pt; font-weight: 700; }
QToolButton#DiagramZoomButton:hover { background: #304254; border-color: #29B6D1; }
QLabel#InspectorEmptyEyebrow { color: #29B6D1; font-size: 8pt; font-weight: 700; }
QLabel#InspectorEmptyTitle { color: #F5FAFC; font-size: 12pt; font-weight: 650; }
QLabel#InspectorEmptyDescription { color: #A5B4C3; font-size: 9pt; }
QLabel#CandidateStatus { background: #3B3020; color: #F0C36D; border: 1px solid #7D6436; border-radius: 4px; padding: 4px 6px; font-size: 7pt; font-weight: 700; }
QLabel#QETProvenanceDetails { background: #111B26; color: #A5B4C3; border: 1px solid #354556; border-radius: 5px; padding: 8px; font-size: 8pt; }
QLabel#QETLibraryStatus { color: #A5B4C3; font-size: 8pt; }
QToolButton#ProvenanceToggle { color: #A5B4C3; text-align: left; padding: 4px 2px; }
QSplitter::handle { background: #354556; }
QSplitter::handle:hover { background: #29B6D1; }
QSplitter::handle:horizontal { width: 9px; margin: 0 1px; }
QSplitter::handle:vertical { height: 7px; margin: 1px 0; }
"""


def _sequence_value(value) -> str:
    if value is None:
        return "Not specified"
    impedance = complex(value.resistance_pu, value.reactance_pu)
    return _complex(impedance) + " p.u."


def _complex_value(value) -> str:
    return _complex(complex(value.resistance_ohm_per_km, value.reactance_ohm_per_km)) + " Ω/km"


def _complex(value: complex) -> str:
    return f"{value.real:.6g} {'+' if value.imag >= 0 else '−'} j{abs(value.imag):.6g}"
