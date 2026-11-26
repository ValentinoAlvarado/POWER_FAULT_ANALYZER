"""Qt asynchronous controller for the isolated PFA script worker."""
from __future__ import annotations
import json
import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal
from power_fault_analyzer.infrastructure.persistence.json_network_document_repository import JSONNetworkDocumentRepository


class ScriptWorkerController(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    running_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProgram(sys.executable)
        self.process.setArguments(["-m", "power_fault_analyzer.scripting.worker"])
        environment = QProcessEnvironment.systemEnvironment()
        source_root = str(Path(__file__).resolve().parents[2])
        existing = environment.value("PYTHONPATH")
        environment.insert("PYTHONPATH", source_root + (os.pathsep + existing if existing else ""))
        self.process.setProcessEnvironment(environment)
        self.process.started.connect(self._write_request)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self._request = b""

    def start(self, source: str) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            raise RuntimeError("A PFA automation worker is already running.")
        if not source.strip():
            raise ValueError("Script is empty.")
        self._request = json.dumps({"source": source}).encode("utf-8")
        self.running_changed.emit(True)
        self.process.start()

    def cancel(self) -> None:
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return
        self.process.terminate()
        QTimer.singleShot(1200, self._kill_if_running)

    def _kill_if_running(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def _write_request(self) -> None:
        self.process.write(self._request)
        self.process.closeWriteChannel()

    def _process_error(self, error) -> None:
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.running_changed.emit(False)
            self.failed.emit(self.process.errorString())

    def _finished(self, exit_code: int, exit_status) -> None:
        self.running_changed.emit(False)
        raw = bytes(self.process.readAllStandardOutput())
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.failed.emit("Worker protocol error: invalid JSON response.")
            return
        if exit_code != 0 or not result.get("ok"):
            self.failed.emit(f"{result.get('error_type','WorkerError')}: {result.get('error','Unknown error')}")
            return
        with tempfile.TemporaryDirectory(prefix="pfa-qt-worker-") as directory:
            path = Path(directory) / "workspace.json"
            path.write_text(json.dumps(result["document"], allow_nan=False), encoding="utf-8")
            workspace = JSONNetworkDocumentRepository().load(path)
        self.succeeded.emit({"workspace": workspace, "project_name": result["project_name"],
                             "captured_output": result.get("captured_output", "")})
