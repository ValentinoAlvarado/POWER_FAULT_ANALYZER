"""Synchronous and asynchronous clients for the separate PFA script worker."""
from __future__ import annotations
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


class ScriptWorkerError(RuntimeError):
    pass


def _environment() -> dict[str, str]:
    env = os.environ.copy()
    package_root = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = package_root + os.pathsep + env.get("PYTHONPATH", "")
    return env


def run_script_worker(source: str, *, timeout_seconds: float = 30.0) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive.")
    process = subprocess.run(
        [sys.executable, "-m", "power_fault_analyzer.scripting.worker"],
        input=json.dumps({"source": source}), text=True, capture_output=True,
        timeout=timeout_seconds, env=_environment(), check=False,
    )
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise ScriptWorkerError(f"Worker returned invalid JSON: {process.stderr[:1000]}") from exc
    if process.returncode != 0 or not result.get("ok"):
        raise ScriptWorkerError(f"{result.get('error_type','WorkerError')}: {result.get('error','Unknown worker failure')}")
    return result


async def run_script_worker_async(source: str, *, timeout_seconds: float = 30.0) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive.")
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "power_fault_analyzer.scripting.worker",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, env=_environment(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(json.dumps({"source": source}).encode("utf-8")),
            timeout=timeout_seconds,
        )
    except (asyncio.TimeoutError, asyncio.CancelledError):
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
        raise
    try:
        result = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ScriptWorkerError(f"Worker returned invalid JSON: {stderr.decode('utf-8')[:1000]}") from exc
    if process.returncode != 0 or not result.get("ok"):
        raise ScriptWorkerError(f"{result.get('error_type','WorkerError')}: {result.get('error','Unknown worker failure')}")
    return result
