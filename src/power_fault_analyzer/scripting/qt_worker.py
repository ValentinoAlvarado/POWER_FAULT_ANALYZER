"""Qt asynchronous controller for the isolated PFA script worker."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from power_fault_analyzer.infrastructure.persistence.json_network_document_repository import (
    JSONNetworkDocumentRepository,
)


class ScriptWorkerController(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    running_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self._request = b""
        self._temporary_directory: tempfile.TemporaryDirectory | None = None
        self._response_path: Path | None = None

    def start(self, source: str) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            raise RuntimeError("A PFA automation worker is already running.")
        if not source.strip():
            raise ValueError("Script is empty.")

        self._temporary_directory = tempfile.TemporaryDirectory(prefix="pfa-qt-worker-")
        directory = Path(self._temporary_directory.name)
        request_path = directory / "request.json"
        self._response_path = directory / "response.json"
        request_path.write_text(
            json.dumps({"source": source}, ensure_ascii=False),
            encoding="utf-8",
        )

        if getattr(sys, "frozen", False):
            # In a PyInstaller build sys.executable is this GUI executable, not
            # a Python interpreter. app.main dispatches this flag before Qt.
            self.process.setProgram(sys.executable)
            self.process.setArguments([
                "--pfa-script-worker",
                str(request_path),
                str(self._response_path),
            ])
        else:
            self.process.setProgram(sys.executable)
            self.process.setArguments([
                "-m",
                "power_fault_analyzer.scripting.worker",
                "--pfa-script-worker",
                str(request_path),
                str(self._response_path),
            ])

        self.running_changed.emit(True)
        self.process.start()

    def cancel(self) -> None:
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return
        self.process.terminate()
        QTimer.singleShot(1200, self._kill_if_running)

    def _release_temporary_directory(self) -> None:
        temporary, self._temporary_directory = self._temporary_directory, None
        self._response_path = None
        if temporary is not None:
            temporary.cleanup()

    def _kill_if_running(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def _process_error(self, error) -> None:
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.running_changed.emit(False)
            self.failed.emit(self.process.errorString())
            self._release_temporary_directory()

    def _finished(self, exit_code: int, exit_status) -> None:
        self.running_changed.emit(False)
        response_path = self._response_path
        stderr = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
        try:
            if response_path is None or not response_path.is_file():
                detail = stderr.strip() or f"Worker exited with code {exit_code} without a response file."
                self.failed.emit(f"Worker protocol error: {detail}")
                return
            result = json.loads(response_path.read_text(encoding="utf-8"))
            if exit_code != 0 or not result.get("ok"):
                self.failed.emit(
                    f"{result.get('error_type', 'WorkerError')}: "
                    f"{result.get('error', 'Unknown error')}"
                )
                return
            with tempfile.TemporaryDirectory(prefix="pfa-qt-workspace-") as directory:
                path = Path(directory) / "workspace.json"
                path.write_text(json.dumps(result["document"], allow_nan=False), encoding="utf-8")
                workspace = JSONNetworkDocumentRepository().load(path)
            self.succeeded.emit({
                "workspace": workspace,
                "project_name": result["project_name"],
                "captured_output": result.get("captured_output", ""),
            })
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            self.failed.emit(f"Worker response error: {type(exc).__name__}: {exc}")
        finally:
            self._release_temporary_directory()
