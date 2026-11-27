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

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        timeout_ms: int = 30_000,
        termination_grace_ms: int = 1_200,
    ) -> None:
        super().__init__(parent)
        if timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive.")
        if termination_grace_ms <= 0:
            raise ValueError("termination_grace_ms must be positive.")

        self.process = QProcess(self)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self._timeout_ms = timeout_ms
        self._termination_grace_ms = termination_grace_ms
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)
        self._termination_timer = QTimer(self)
        self._termination_timer.setSingleShot(True)
        self._termination_timer.timeout.connect(self._kill_if_running)
        self._termination_message: str | None = None
        self._temporary_directory: tempfile.TemporaryDirectory | None = None
        self._response_path: Path | None = None

    def start(self, source: str) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            raise RuntimeError("A PFA automation worker is already running.")
        if not source.strip():
            raise ValueError("Script is empty.")

        self._stop_timers()
        self._termination_message = None
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
        self._timeout_timer.start(self._timeout_ms)

    def cancel(self) -> None:
        self._terminate("Script execution cancelled.")

    def _on_timeout(self) -> None:
        self._terminate(
            f"Script execution timed out after {self._timeout_ms / 1000:g} seconds."
        )

    def _terminate(self, message: str) -> None:
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return
        self._termination_message = message
        self._timeout_timer.stop()
        self.process.terminate()
        self._termination_timer.start(self._termination_grace_ms)

    def _stop_timers(self) -> None:
        self._timeout_timer.stop()
        self._termination_timer.stop()

    def _release_temporary_directory(self) -> None:
        temporary, self._temporary_directory = self._temporary_directory, None
        self._response_path = None
        if temporary is not None:
            temporary.cleanup()

    def _kill_if_running(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def _process_error(self, error) -> None:
        if (
            self.process.state() == QProcess.ProcessState.NotRunning
            and self._temporary_directory is not None
        ):
            self._stop_timers()
            message, self._termination_message = (
                self._termination_message or self.process.errorString(),
                None,
            )
            self.running_changed.emit(False)
            self.failed.emit(message)
            self._release_temporary_directory()

    def _finished(self, exit_code: int, exit_status) -> None:
        # FailedToStart may emit errorOccurred before any finished signal.
        if self._temporary_directory is None:
            return
        self._stop_timers()
        termination_message, self._termination_message = self._termination_message, None
        self.running_changed.emit(False)
        if termination_message is not None:
            self.failed.emit(termination_message)
            self._release_temporary_directory()
            return

        response_path = self._response_path
        stderr = bytes(self.process.readAllStandardError()).decode(
            "utf-8", errors="replace"
        )
        try:
            if exit_status != QProcess.ExitStatus.NormalExit:
                detail = stderr.strip() or "Worker process terminated abnormally."
                self.failed.emit(f"Worker process error: {detail}")
                return
            if response_path is None or not response_path.is_file():
                detail = stderr.strip() or (
                    f"Worker exited with code {exit_code} without a response file."
                )
                self.failed.emit(f"Worker protocol error: {detail}")
                return
            result = json.loads(response_path.read_text(encoding="utf-8"))
            if not isinstance(result, dict):
                raise TypeError("Worker response must be a JSON object.")
            if exit_code != 0 or result.get("ok") is not True:
                self.failed.emit(
                    f"{result.get('error_type', 'WorkerError')}: "
                    f"{result.get('error', 'Unknown error')}"
                )
                return
            with tempfile.TemporaryDirectory(prefix="pfa-qt-workspace-") as directory:
                path = Path(directory) / "workspace.json"
                path.write_text(
                    json.dumps(result["document"], allow_nan=False),
                    encoding="utf-8",
                )
                workspace = JSONNetworkDocumentRepository().load(path)
            self.succeeded.emit({
                "workspace": workspace,
                "project_name": result["project_name"],
                "captured_output": result.get("captured_output", ""),
            })
        except (
            OSError,
            UnicodeDecodeError,
            KeyError,
            TypeError,
            AttributeError,
            ValueError,
        ) as exc:
            self.failed.emit(f"Worker response error: {type(exc).__name__}: {exc}")
        finally:
            self._release_temporary_directory()
