"""Asynchronous authoring surface backed by the canonical NetworkWorkspace API."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from power_fault_analyzer.scripting.qt_worker import ScriptWorkerController

STARTER_SCRIPT = '''project = ScriptProject("Untitled electrical project")
bus = project.add_bus("BUS-01", voltage_kv=13.8, x=420, y=260)

# Add equipment only after its nameplate and sequence data have been verified.
# The worker returns a NetworkWorkspace from the canonical PFA domain model.
project.assert_valid()
workspace = project.render()
'''


class CodeAutomationStudio(QWidget):
    """Builds the same NetworkWorkspace used by the graphical Workbench."""

    workspace_built = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = "build"
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel("PYTHON AUTOMATION")
        title.setObjectName("SectionEyebrow")
        header.addWidget(title)
        header.addStretch(1)
        self.validate_button = QPushButton("Validate script")
        self.run_button = QPushButton("Build diagram")
        self.cancel_button = QPushButton("Cancel")
        self.run_button.setObjectName("DiagramFitButton")
        self.cancel_button.setEnabled(False)
        header.addWidget(self.validate_button)
        header.addWidget(self.run_button)
        header.addWidget(self.cancel_button)
        root.addLayout(header)

        warning = QLabel(
            "Runs in a separate worker process to keep the Workbench responsive. "
            "The worker applies a restricted authoring API but is not a hardened OS sandbox. "
            "Run trusted local scripts only."
        )
        warning.setWordWrap(True)
        warning.setObjectName("AutomationWarning")
        root.addWidget(warning)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("PythonAutomationEditor")
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setTabStopDistance(4 * self.editor.fontMetrics().horizontalAdvance(" "))
        self.editor.setPlaceholderText("Write a POWER_FAULT_ANALYZER project-authoring script…")
        self.editor.setPlainText(STARTER_SCRIPT)
        self.output = QTextBrowser()
        self.output.setObjectName("AutomationOutput")
        self.output.setOpenExternalLinks(False)
        splitter.addWidget(self.editor)
        splitter.addWidget(self.output)
        splitter.setSizes([620, 180])
        root.addWidget(splitter, 1)

        self.worker = ScriptWorkerController(self)
        self.worker.succeeded.connect(self._worker_succeeded)
        self.worker.failed.connect(self._worker_failed)
        self.worker.running_changed.connect(self._running_changed)
        self.validate_button.clicked.connect(self.validate_script)
        self.run_button.clicked.connect(self.run_script)
        self.cancel_button.clicked.connect(self.worker.cancel)

    def _start(self, mode: str) -> None:
        self._mode = mode
        try:
            self.output.setPlainText("Starting isolated worker process…")
            self.worker.start(self.editor.toPlainText())
        except (RuntimeError, ValueError) as exc:
            self.output.setPlainText(f"WORKER START ERROR\n{type(exc).__name__}: {exc}")

    def validate_script(self) -> None:
        self._start("validate")

    def run_script(self) -> None:
        self._start("build")

    def _running_changed(self, running: bool) -> None:
        self.validate_button.setEnabled(not running)
        self.run_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.editor.setReadOnly(running)

    def _worker_succeeded(self, result: object) -> None:
        workspace = result["workspace"]
        network = workspace.network
        summary = (
            f"VALIDATION PASSED\nProject: {result['project_name']}\n"
            f"Buses: {len(network.buses)}\nEquipment: {len(network.equipment)}\n"
            f"Explicit connections: {len(network.connections)}\n"
            "Structural validation only; no electrical study was executed."
        )
        self.output.setPlainText(summary)
        if self._mode == "build":
            self.workspace_built.emit(workspace)
            self.output.append("The canonical workspace was sent to the Network Design renderer.")

    def _worker_failed(self, message: str) -> None:
        self.output.setPlainText(f"SCRIPT WORKER ERROR\n{message}")
