"""Append-only JSON journal for simulated switching-sequence results.

This is an engineering trace, not an authoritative SOE recorder. The file
format is versioned and writes atomically. It assumes a single writer process;
production deployments requiring concurrent writes should use a transactional
repository adapter.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from .sequences import SwitchingSequenceResult

JOURNAL_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class OperationJournalRecord:
    record_id: UUID
    recorded_at_utc: str
    result: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": str(self.record_id),
            "recorded_at_utc": self.recorded_at_utc,
            "result": self.result,
        }


class JsonOperationJournal:
    """Store immutable simulation records in an atomic JSON document."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read_records(self) -> tuple[OperationJournalRecord, ...]:
        if not self.path.exists():
            return ()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != JOURNAL_SCHEMA_VERSION:
            raise ValueError("Unsupported operations journal schema.")
        entries = payload.get("records")
        if not isinstance(entries, list):
            raise TypeError("Operations journal records must be a JSON array.")
        records: list[OperationJournalRecord] = []
        for item in entries:
            if not isinstance(item, dict) or not isinstance(item.get("result"), dict):
                raise TypeError("Malformed operations journal record.")
            records.append(
                OperationJournalRecord(
                    record_id=UUID(str(item["record_id"])),
                    recorded_at_utc=str(item["recorded_at_utc"]),
                    result=item["result"],
                )
            )
        return tuple(records)

    def append(self, result: SwitchingSequenceResult) -> OperationJournalRecord:
        if not result.simulation_only:
            raise ValueError("Only simulation-only sequence results are accepted by this journal.")
        existing = self.read_records()
        record = OperationJournalRecord(
            record_id=uuid4(),
            recorded_at_utc=datetime.now(UTC).isoformat(),
            result=result.to_dict(),
        )
        self._write((*existing, record))
        return record

    def _write(self, records: tuple[OperationJournalRecord, ...]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": JOURNAL_SCHEMA_VERSION,
            "record_count": len(records),
            "records": [item.to_dict() for item in records],
        }
        serialized = json.dumps(
            payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
        )
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_name = stream.name
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, self.path)
        finally:
            if temporary_name and os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def export_dict(self) -> dict[str, Any]:
        records = self.read_records()
        return {
            "schema_version": JOURNAL_SCHEMA_VERSION,
            "record_count": len(records),
            "records": [item.to_dict() for item in records],
        }
