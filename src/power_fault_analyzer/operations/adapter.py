"""Structural adapter from the canonical PFA Network aggregate to operations.

The adapter intentionally reads the aggregate; it never calls connect(),
 disconnect(), or mutates equipment.  It supports explicit source identities
when projects use custom source classes unknown to the default classifier.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol
from uuid import UUID

from .models import (
    BusRecord,
    EquipmentRecord,
    NetworkSnapshot,
    SwitchPosition,
    TerminalConnection,
)


class _TerminalLike(Protocol):
    id: UUID


class _BusLike(Protocol):
    id: UUID
    name: str


class _ConnectionLike(Protocol):
    terminal_id: UUID
    bus_id: UUID


class _EquipmentLike(Protocol):
    id: UUID
    name: str
    terminals: tuple[_TerminalLike, ...]


class _NetworkLike(Protocol):
    id: UUID
    name: str
    buses: tuple[_BusLike, ...]
    equipment: tuple[_EquipmentLike, ...]
    connections: tuple[_ConnectionLike, ...]


def _enum_value(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw).strip().casefold()


def _default_source_classifier(equipment: object) -> bool:
    kind = _enum_value(getattr(equipment, "equipment_kind", ""))
    family = _enum_value(getattr(equipment, "family", ""))
    class_name = type(equipment).__name__.casefold()
    declared = {kind, family}
    source_tokens = {"source", "generator", "synchronous_generator", "external_grid", "equivalent_source"}
    if declared & source_tokens:
        return True
    return any(token in class_name for token in ("equivalentsource", "synchronousgenerator", "externalgrid"))


def _switch_position(equipment: object) -> SwitchPosition:
    raw = getattr(equipment, "position", None)
    value = _enum_value(raw)
    if value in {"open", "opened", "disconnect", "disconnected"}:
        return SwitchPosition.OPEN
    if value in {"closed", "close", "connected"}:
        return SwitchPosition.CLOSED
    raise ValueError(
        f"Switch {getattr(equipment, 'name', type(equipment).__name__)!r} "
        f"has unsupported position value {raw!r}. Expected OPEN or CLOSED."
    )


def network_to_snapshot(
    network: _NetworkLike,
    *,
    source_equipment_ids: Iterable[UUID] | None = None,
    source_classifier: Callable[[object], bool] = _default_source_classifier,
) -> NetworkSnapshot:
    """Project a PFA Network into the stable input contract for operations.

    A switch is recognized structurally by the pair of attributes ``device_kind``
    and ``position`` used by PFA's SwitchingDevice.  Source detection can be
    made exact by supplying ``source_equipment_ids``.
    """
    explicit_sources = None if source_equipment_ids is None else frozenset(source_equipment_ids)
    buses = tuple(BusRecord(bus_id=item.id, name=item.name) for item in network.buses)
    equipment_records: list[EquipmentRecord] = []
    known_equipment_ids: set[UUID] = set()
    for equipment in network.equipment:
        is_switch = hasattr(equipment, "device_kind") and hasattr(equipment, "position")
        source = equipment.id in explicit_sources if explicit_sources is not None else source_classifier(equipment)
        terminal_ids = tuple(item.id for item in equipment.terminals)
        default_in_service = getattr(equipment, "in_service", True)
        if not isinstance(default_in_service, bool):
            raise TypeError(f"Equipment {equipment.name!r} exposes non-boolean in_service.")
        family_value = getattr(equipment, "device_kind", None)
        if family_value is None:
            family_value = getattr(equipment, "family", type(equipment).__name__)
        family = _enum_value(family_value)
        family_value = getattr(equipment, "device_kind", None)
        if family_value is None:
            family_value = getattr(equipment, "family", type(equipment).__name__)
        family = _enum_value(family_value)
        equipment_records.append(
            EquipmentRecord(
                equipment_id=equipment.id,
                name=equipment.name,
                terminal_ids=terminal_ids,
                is_switch=is_switch,
                default_switch_position=_switch_position(equipment) if is_switch else None,
                is_source=source,
                is_grounding_switch=(
                    is_switch
                    and _enum_value(getattr(equipment, "device_kind", ""))
                    in {"earthing_switch", "grounding_switch", "earth_switch", "ground_switch"}
                ),
                default_in_service=default_in_service,
                family=family,
            )
        )
        known_equipment_ids.add(equipment.id)

    if explicit_sources is not None:
        unknown_sources = explicit_sources - known_equipment_ids
        if unknown_sources:
            raise ValueError(f"Explicit source IDs are not present in the network: {sorted(map(str, unknown_sources))}")
        equipment_records = [
            EquipmentRecord(
                equipment_id=item.equipment_id,
                name=item.name,
                terminal_ids=item.terminal_ids,
                is_switch=item.is_switch,
                default_switch_position=item.default_switch_position,
                is_source=item.equipment_id in explicit_sources,
                is_grounding_switch=item.is_grounding_switch,
                default_in_service=item.default_in_service,
                family=item.family,
            )
            for item in equipment_records
        ]

    connections = tuple(
        TerminalConnection(terminal_id=item.terminal_id, bus_id=item.bus_id)
        for item in network.connections
    )
    return NetworkSnapshot(
        network_id=network.id,
        network_name=network.name,
        buses=buses,
        equipment=tuple(equipment_records),
        connections=connections,
    )
