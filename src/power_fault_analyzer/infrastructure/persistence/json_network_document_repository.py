"""Atomic JSON persistence for physical network entities and separate drawing layout."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from power_fault_analyzer.application.ports.network_document_repository import (
    NetworkDocumentRepositoryPort,
)
from power_fault_analyzer.application.use_cases.network_workspace import (
    DiagramLabelPlacement,
    DiagramSymbolPlacement,
    NetworkStudyRecord,
    NetworkWorkspace,
)
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.bus_kind import BusKind
from power_fault_analyzer.domain.enums.equipment_interface import (
    EquipmentInterfaceKind,
    ParameterEvidenceStatus,
)
from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.grounding_mode import GroundingMode
from power_fault_analyzer.domain.enums.line_model_kind import LineModelKind
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.source_sequence_status import SourceSequenceStatus
from power_fault_analyzer.domain.enums.switching_device import SwitchingDeviceKind, SwitchPosition
from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
from power_fault_analyzer.domain.enums.winding_designation import WindingDesignation
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.neutral_grounding import NeutralGrounding
from power_fault_analyzer.domain.value_objects.per_unit_impedance import (
    PerUnitImpedance,
    SequencePerUnitImpedance,
)
from power_fault_analyzer.domain.value_objects.sequence_parameters import (
    AdmittancePerLength,
    ImpedancePerLength,
    SequenceAdmittancePerLengthSet,
    SequenceImpedancePerLengthSet,
)
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult
from power_fault_analyzer.domain.value_objects.source_models import (
    SourceEquivalentSet,
    SourceSequenceEquivalent,
    SynchronousMachineSequenceImpedances,
)
from power_fault_analyzer.domain.value_objects.tap_changer import TapChanger
from power_fault_analyzer.domain.value_objects.transformer_winding import TransformerWinding
from power_fault_analyzer.domain.value_objects.vector_group import VectorGroup
from power_fault_analyzer.domain.value_objects.voltage import Voltage
from power_fault_analyzer.equipment.interfaces.unresolved_branch import (
    UnresolvedTwoTerminalEquipment,
)
from power_fault_analyzer.equipment.interfaces.unresolved_equipment import (
    EngineeringParameter,
    UnresolvedEquipmentInterface,
)
from power_fault_analyzer.equipment.interfaces.unresolved_single_terminal import (
    UnresolvedSingleTerminalEquipment,
)
from power_fault_analyzer.equipment.sources.equivalent_source import EquivalentSource
from power_fault_analyzer.equipment.sources.synchronous_generator import SynchronousGenerator
from power_fault_analyzer.equipment.switching.switching_device import SwitchingDevice
from power_fault_analyzer.equipment.transformers.two_winding_transformer import (
    TwoWindingTransformer,
)
from power_fault_analyzer.equipment.transmission.line import Line
from power_fault_analyzer.equipment.transmission.line_parameters import LineParameters
from power_fault_analyzer.operations.models import OperatingScenario


class NetworkDocumentError(ValueError):
    """Raised for unsupported or corrupt persisted network documents."""


class JSONNetworkDocumentRepository(NetworkDocumentRepositoryPort):
    SCHEMA_VERSION = "1.6"
    SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0", "1.1", "1.2", "1.3", "1.4", "1.5", SCHEMA_VERSION})

    def load(self, path: str | Path) -> NetworkWorkspace:
        source = Path(path)
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise NetworkDocumentError(f"Cannot read network document '{source}': {exc}") from exc
        schema_version = payload.get("schema_version") if isinstance(payload, dict) else None
        if schema_version not in self.SUPPORTED_SCHEMA_VERSIONS:
            supported = ", ".join(sorted(self.SUPPORTED_SCHEMA_VERSIONS))
            raise NetworkDocumentError(
                f"Unsupported network document schema: {schema_version!r}; supported versions: {supported}."
            )
        try:
            model = payload["network"]
            network = Network(model["name"], id=UUID(model["id"]))
            for item in model.get("buses", []):
                network.add_bus(
                    Bus(
                        id=UUID(item["id"]),
                        name=item["name"],
                        nominal_voltage=Voltage.from_kv(float(item["nominal_voltage_kv"])),
                        kind=BusKind(item.get("kind", BusKind.BUSBAR.value)),
                    )
                )
            for item in model.get("equipment", []):
                network.add_equipment(_equipment_from_dict(item))
            for item in model.get("connections", []):
                network.connect(UUID(item["terminal_id"]), UUID(item["bus_id"]))
            diagram_payload = payload.get("diagram", {})
            positions = {
                UUID(key): (float(value[0]), float(value[1]))
                for key, value in diagram_payload.get("positions", {}).items()
            }
            symbols = {}
            for item in diagram_payload.get("symbols", []):
                placement = DiagramSymbolPlacement(
                    instance_id=UUID(item["instance_id"]),
                    asset_id=item["asset_id"],
                    x=float(item["x"]),
                    y=float(item["y"]),
                    rotation_deg=float(item.get("rotation_deg", 0.0)),
                    equipment_id=UUID(item["equipment_id"]) if item.get("equipment_id") else None,
                    terminal_mappings=tuple(
                        (mapping["source_terminal_id"], UUID(mapping["equipment_terminal_id"]))
                        for mapping in item.get("terminal_mappings", [])
                    ),
                    label=item.get("label"),
                )
                symbols[placement.instance_id] = placement
            labels = {}
            for item in diagram_payload.get("labels", []):
                label = DiagramLabelPlacement(
                    label_id=UUID(item["label_id"]),
                    owner_id=UUID(item["owner_id"]) if item.get("owner_id") else None,
                    text=item["text"],
                    x=float(item["x"]),
                    y=float(item["y"]),
                    anchor=item.get("anchor", "middle"),
                    font_family=item.get("font_family", "Segoe UI"),
                    size_pt=float(item.get("size_pt", 7.5)),
                    weight=item.get("weight", "normal"),
                    color=item.get("color", "#172033"),
                    rotation_deg=float(item.get("rotation_deg", 0.0)),
                    visible=bool(item.get("visible", True)),
                    layer=item.get("layer", "annotations"),
                    priority=int(item.get("priority", 50)),
                    unit=item.get("unit"),
                    number_format=item.get("number_format"),
                )
                labels[label.label_id] = label
            return NetworkWorkspace(
                network=network,
                diagram_positions=positions,
                diagram_rotations={
                    UUID(key): float(value)
                    for key, value in diagram_payload.get("rotations", {}).items()
                },
                diagram_symbols=symbols,
                diagram_labels=labels,
                grid_spacing=float(payload.get("diagram", {}).get("grid_spacing", 20.0)),
                snap_enabled=bool(payload.get("diagram", {}).get("snap_enabled", True)),
                study_history=tuple(
                    _study_from_dict(item) for item in payload.get("study_history", [])
                ),
                operating_scenarios={
                    scenario.scenario_id: scenario
                    for scenario in (
                        OperatingScenario.from_dict(item)
                        for item in payload.get("operations", {}).get("scenarios", [])
                    )
                },
                active_operating_scenario_id=(
                    UUID(payload["operations"]["active_scenario_id"])
                    if payload.get("operations", {}).get("active_scenario_id") else None
                ),
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise NetworkDocumentError(f"Invalid network document '{source}': {exc}") from exc

    def save(self, workspace: NetworkWorkspace, path: str | Path) -> Path:
        if not isinstance(workspace, NetworkWorkspace):
            raise TypeError("workspace must be a NetworkWorkspace.")
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        network = workspace.network
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "network": {
                "id": str(network.id),
                "name": network.name,
                "buses": [
                    {
                        "id": str(bus.id),
                        "name": bus.name,
                        "nominal_voltage_kv": bus.nominal_voltage.value_kv,
                        "kind": bus.kind.value,
                    }
                    for bus in network.buses
                ],
                "equipment": [_equipment_to_dict(item) for item in network.equipment],
                "connections": [
                    {"terminal_id": str(item.terminal_id), "bus_id": str(item.bus_id)}
                    for item in network.connections
                ],
            },
            "study_history": [_study_to_dict(item) for item in workspace.study_history],
            "operations": {
                "scenarios": [
                    item.to_dict()
                    for item in sorted(
                        workspace.operating_scenarios.values(), key=lambda value: str(value.scenario_id)
                    )
                ],
                "active_scenario_id": (
                    str(workspace.active_operating_scenario_id)
                    if workspace.active_operating_scenario_id else None
                ),
            },
            "diagram": {
                "positions": {
                    str(identifier): [float(position[0]), float(position[1])]
                    for identifier, position in workspace.diagram_positions.items()
                },
                "rotations": {
                    str(identifier): float(rotation)
                    for identifier, rotation in workspace.diagram_rotations.items()
                },
                "symbols": [
                    {
                        "instance_id": str(item.instance_id),
                        "asset_id": item.asset_id,
                        "x": item.x,
                        "y": item.y,
                        "rotation_deg": item.rotation_deg,
                        "equipment_id": str(item.equipment_id) if item.equipment_id else None,
                        "terminal_mappings": [
                            {
                                "source_terminal_id": source_terminal_id,
                                "equipment_terminal_id": str(equipment_terminal_id),
                            }
                            for source_terminal_id, equipment_terminal_id in item.terminal_mappings
                        ],
                        "label": item.label,
                    }
                    for item in workspace.diagram_symbols.values()
                ],
                "labels": [
                    {
                        "label_id": str(item.label_id),
                        "owner_id": str(item.owner_id) if item.owner_id else None,
                        "text": item.text,
                        "x": item.x,
                        "y": item.y,
                        "anchor": item.anchor,
                        "font_family": item.font_family,
                        "size_pt": item.size_pt,
                        "weight": item.weight,
                        "color": item.color,
                        "rotation_deg": item.rotation_deg,
                        "visible": item.visible,
                        "layer": item.layer,
                        "priority": item.priority,
                        "unit": item.unit,
                        "number_format": item.number_format,
                    }
                    for item in workspace.diagram_labels.values()
                ],
                "grid_spacing": workspace.grid_spacing,
                "snap_enabled": workspace.snap_enabled,
            },
        }
        serialized = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="\n",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = stream.name
                stream.write(serialized)
            os.replace(temporary, target)
        except OSError:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
            raise
        return target


def _terminal_to_dict(terminal: Terminal) -> dict[str, Any]:
    return {
        "id": str(terminal.id),
        "equipment_id": str(terminal.equipment_id),
        "designation": terminal.designation,
        "rated_voltage_kv": terminal.rated_voltage.value_kv,
    }


def _terminal_from_dict(payload: dict[str, Any]) -> Terminal:
    return Terminal(
        id=UUID(payload["id"]),
        equipment_id=UUID(payload["equipment_id"]),
        designation=payload["designation"],
        rated_voltage=Voltage.from_kv(float(payload["rated_voltage_kv"])),
    )


def _complex_to_list(value: complex) -> list[float]:
    item = complex(value)
    return [item.real, item.imag]


def _impedance_to_dict(value: PerUnitImpedance) -> dict[str, float]:
    return {"r": value.resistance_pu, "x": value.reactance_pu}


def _impedance_from_dict(payload: dict[str, Any]) -> PerUnitImpedance:
    return PerUnitImpedance(float(payload["r"]), float(payload["x"]))


def _sequence_per_length_to_dict(value: SequenceImpedancePerLengthSet) -> dict[str, Any]:
    return {
        name: {
            "r_ohm_per_km": getattr(value, name).resistance_ohm_per_km,
            "x_ohm_per_km": getattr(value, name).reactance_ohm_per_km,
        }
        for name in ("positive", "negative", "zero")
    }


def _sequence_per_length_from_dict(payload: dict[str, Any]) -> SequenceImpedancePerLengthSet:
    def build(name: str) -> ImpedancePerLength:
        item = payload[name]
        return ImpedancePerLength(float(item["r_ohm_per_km"]), float(item["x_ohm_per_km"]))

    return SequenceImpedancePerLengthSet(build("positive"), build("negative"), build("zero"))


def _shunt_per_length_to_dict(value: SequenceAdmittancePerLengthSet) -> dict[str, Any]:
    return {
        name: {
            "g_s_per_km": getattr(value, name).conductance_siemens_per_km,
            "b_s_per_km": getattr(value, name).susceptance_siemens_per_km,
        }
        for name in ("positive", "negative", "zero")
    }


def _shunt_per_length_from_dict(payload: dict[str, Any]) -> SequenceAdmittancePerLengthSet:
    def build(name: str) -> AdmittancePerLength:
        item = payload[name]
        return AdmittancePerLength(float(item["g_s_per_km"]), float(item["b_s_per_km"]))

    return SequenceAdmittancePerLengthSet(build("positive"), build("negative"), build("zero"))


def _source_sequence_to_dict(item: SourceSequenceEquivalent) -> dict[str, Any]:
    return {
        "sequence": item.sequence.value,
        "status": item.status.value,
        "impedance": _impedance_to_dict(item.impedance) if item.impedance is not None else None,
        "internal_voltage_pu": _complex_to_list(item.internal_voltage_pu)
        if item.internal_voltage_pu is not None
        else None,
    }


def _source_sequence_from_dict(payload: dict[str, Any]) -> SourceSequenceEquivalent:
    status = SourceSequenceStatus(payload["status"])
    impedance = _impedance_from_dict(payload["impedance"]) if payload["impedance"] else None
    voltage = complex(*payload["internal_voltage_pu"]) if payload["internal_voltage_pu"] else None
    return SourceSequenceEquivalent(SequenceType(payload["sequence"]), status, impedance, voltage)


def _winding_to_dict(winding: TransformerWinding) -> dict[str, Any]:
    grounding = winding.neutral_grounding
    tap = winding.tap_changer
    return {
        "designation": winding.designation.value,
        "rated_voltage_kv": winding.rated_voltage_kv,
        "rated_power_mva": winding.rated_power_mva,
        "connection": winding.connection.value,
        "neutral_grounding": (
            {
                "mode": grounding.mode.value,
                "resistance_ohm": grounding.resistance_ohm,
                "reactance_ohm": grounding.reactance_ohm,
            }
            if grounding is not None
            else None
        ),
        "neutral_terminal_available": winding.neutral_terminal_available,
        "tap_changer": (
            {
                "minimum_position": tap.minimum_position,
                "maximum_position": tap.maximum_position,
                "neutral_position": tap.neutral_position,
                "current_position": tap.current_position,
                "step_percent": tap.step_percent,
            }
            if tap is not None
            else None
        ),
    }


def _winding_from_dict(payload: dict[str, Any]) -> TransformerWinding:
    grounding_payload = payload.get("neutral_grounding")
    grounding = (
        NeutralGrounding(
            GroundingMode(grounding_payload["mode"]),
            float(grounding_payload["resistance_ohm"]),
            float(grounding_payload["reactance_ohm"]),
        )
        if grounding_payload is not None
        else None
    )
    tap_payload = payload.get("tap_changer")
    tap = TapChanger(**tap_payload) if tap_payload is not None else None
    return TransformerWinding(
        designation=WindingDesignation(payload["designation"]),
        rated_voltage_kv=float(payload["rated_voltage_kv"]),
        rated_power_mva=float(payload["rated_power_mva"]),
        connection=WindingConnection(payload["connection"]),
        neutral_grounding=grounding,
        neutral_terminal_available=bool(payload["neutral_terminal_available"]),
        tap_changer=tap,
    )


def _evidence_to_dict(values: tuple[EngineeringParameter, ...]) -> list[dict[str, Any]]:
    return [
        {
            "name": item.name,
            "unit": item.unit,
            "value": item.value,
            "status": item.status.value,
            "source_reference": item.source_reference,
        }
        for item in values
    ]


def _evidence_from_dict(payload: list[dict[str, Any]] | None) -> tuple[EngineeringParameter, ...]:
    return tuple(
        EngineeringParameter(
            name=item["name"],
            unit=item["unit"],
            value=item.get("value"),
            status=ParameterEvidenceStatus(item["status"]),
            source_reference=item.get("source_reference"),
        )
        for item in (payload or [])
    )


def _equipment_to_dict(equipment) -> dict[str, Any]:
    base = {
        "id": str(equipment.id),
        "name": equipment.name,
        "terminals": [_terminal_to_dict(item) for item in equipment.terminals],
    }
    if isinstance(equipment, SwitchingDevice):
        return {
            **base,
            "kind": "switching_device",
            "device_kind": equipment.device_kind.value,
            "position": equipment.position.value,
        }
    if isinstance(equipment, UnresolvedSingleTerminalEquipment):
        return {
            **base,
            "kind": "unresolved_single_terminal_equipment",
            "equipment_kind": equipment.equipment_kind,
            "family": equipment.family.value,
            "parameters": _evidence_to_dict(equipment.parameters),
        }
    if isinstance(equipment, UnresolvedTwoTerminalEquipment):
        return {
            **base,
            "kind": "unresolved_two_terminal_equipment",
            "equipment_kind": equipment.equipment_kind,
            "family": equipment.family.value,
            "parameters": _evidence_to_dict(equipment.parameters),
        }
    if isinstance(equipment, UnresolvedEquipmentInterface):
        return {
            **base,
            "kind": "unresolved_equipment_interface",
            "interface_kind": equipment.interface_kind.value,
            "parameters": _evidence_to_dict(equipment.parameters),
        }
    if isinstance(equipment, EquivalentSource):
        equivalent = equipment.equivalent
        return {
            **base,
            "kind": "equivalent_source",
            "frequency_hz": equipment.frequency.value_hz,
            "base": {"mva": equivalent.base.base_power_mva, "kv": equivalent.base.base_voltage_kv},
            "sequences": {
                "positive": _source_sequence_to_dict(equivalent.positive),
                "negative": _source_sequence_to_dict(equivalent.negative),
                "zero": _source_sequence_to_dict(equivalent.zero),
            },
            "data_evidence": _evidence_to_dict(equipment.data_evidence),
        }
    if isinstance(equipment, SynchronousGenerator):
        seq = equipment.sequence_impedances
        return {
            **base,
            "kind": "synchronous_generator",
            "frequency_hz": equipment.frequency.value_hz,
            "prefault_voltage_pu": _complex_to_list(equipment.prefault_voltage_pu),
            "stator_connection": equipment.stator_connection.value,
            "neutral_grounding": {
                "mode": equipment.neutral_grounding.mode.value,
                "resistance_ohm": equipment.neutral_grounding.resistance_ohm,
                "reactance_ohm": equipment.neutral_grounding.reactance_ohm,
            },
            "sequence_impedances": {
                "base": {"mva": seq.base.base_power_mva, "kv": seq.base.base_voltage_kv},
                "positive_subtransient": _impedance_to_dict(seq.positive_subtransient),
                "positive_transient": _impedance_to_dict(seq.positive_transient),
                "positive_synchronous": _impedance_to_dict(seq.positive_synchronous),
                "negative": _impedance_to_dict(seq.negative),
                "zero": _impedance_to_dict(seq.zero),
            },
        }
    if isinstance(equipment, TwoWindingTransformer):
        sequence = equipment.sequence_impedances
        return {
            **base,
            "kind": "two_winding_transformer",
            "frequency_hz": equipment.frequency.value_hz,
            "vector_group": {
                "reference_connection": equipment.vector_group.reference_connection.value,
                "secondary_connection": equipment.vector_group.secondary_connection.value,
                "clock_number": equipment.vector_group.clock_number,
            },
            "windings": [_winding_to_dict(item) for item in equipment.windings],
            "sequence_impedances": {
                "base": {
                    "mva": sequence.base.base_power_mva,
                    "kv": sequence.base.base_voltage_kv,
                },
                "positive": _impedance_to_dict(sequence.positive),
                "negative": _impedance_to_dict(sequence.negative),
                "zero": _impedance_to_dict(sequence.zero),
            },
            "data_evidence": _evidence_to_dict(equipment.data_evidence),
        }
    if isinstance(equipment, Line):
        return {
            **base,
            "kind": "line",
            "length_km": equipment.length_km,
            "model_kind": equipment.model_kind.value,
            "frequency_hz": equipment.parameters.reference_frequency.value_hz,
            "series_impedance_per_km": _sequence_per_length_to_dict(
                equipment.parameters.series_impedance_per_km
            ),
            "shunt_admittance_per_km": _shunt_per_length_to_dict(
                equipment.parameters.shunt_admittance_per_km
            ),
            "data_evidence": _evidence_to_dict(equipment.data_evidence),
        }
    raise NetworkDocumentError(
        f"Cannot persist unsupported equipment type '{type(equipment).__name__}'."
    )


def _equipment_from_dict(payload: dict[str, Any]):
    identifier = UUID(payload["id"])
    terminals = tuple(_terminal_from_dict(item) for item in payload["terminals"])
    kind = payload["kind"]
    if kind == "switching_device":
        if len(terminals) != 2:
            raise NetworkDocumentError(
                "Persisted switching_device must have exactly two terminals."
            )
        return SwitchingDevice(
            id=identifier,
            name=payload["name"],
            terminals=(terminals[0], terminals[1]),
            device_kind=SwitchingDeviceKind(payload["device_kind"]),
            position=SwitchPosition(payload["position"]),
        )
    if kind == "unresolved_single_terminal_equipment":
        from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
        if len(terminals) != 1:
            raise NetworkDocumentError("Unresolved single-terminal equipment must have one terminal.")
        return UnresolvedSingleTerminalEquipment(
            id=identifier, name=payload["name"], terminal=terminals[0],
            equipment_kind=payload["equipment_kind"],
            family=EquipmentFamily(payload["family"]),
            parameters=_evidence_from_dict(payload["parameters"]),
        )
    if kind == "unresolved_two_terminal_equipment":
        from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
        if len(terminals) != 2:
            raise NetworkDocumentError("Unresolved two-terminal equipment must have exactly two terminals.")
        return UnresolvedTwoTerminalEquipment(
            id=identifier, name=payload["name"], terminals=(terminals[0], terminals[1]),
            equipment_kind=payload["equipment_kind"],
            family=EquipmentFamily(payload["family"]),
            parameters=_evidence_from_dict(payload["parameters"]),
        )
    if kind == "unresolved_equipment_interface":
        if len(terminals) != 1:
            raise NetworkDocumentError(
                "Persisted unresolved_equipment_interface must have exactly one terminal."
            )
        parameters = _evidence_from_dict(payload["parameters"])
        return UnresolvedEquipmentInterface(
            id=identifier,
            name=payload["name"],
            terminal=terminals[0],
            interface_kind=EquipmentInterfaceKind(payload["interface_kind"]),
            parameters=parameters,
        )
    if kind == "equivalent_source":
        base = ElectricalImpedanceBase(payload["base"]["mva"], payload["base"]["kv"])
        seq = payload["sequences"]
        equivalent = SourceEquivalentSet(
            base,
            _source_sequence_from_dict(seq["positive"]),
            _source_sequence_from_dict(seq["negative"]),
            _source_sequence_from_dict(seq["zero"]),
        )
        return EquivalentSource(
            id=identifier,
            name=payload["name"],
            terminal=terminals[0],
            frequency=Frequency(payload["frequency_hz"]),
            equivalent=equivalent,
            data_evidence=_evidence_from_dict(payload.get("data_evidence")),
        )
    if kind == "synchronous_generator":
        seq = payload["sequence_impedances"]
        base = ElectricalImpedanceBase(seq["base"]["mva"], seq["base"]["kv"])
        grounding = payload["neutral_grounding"]
        neutral = NeutralGrounding(
            GroundingMode(grounding["mode"]),
            grounding["resistance_ohm"],
            grounding["reactance_ohm"],
        )
        impedances = SynchronousMachineSequenceImpedances(
            base=base,
            positive_subtransient=_impedance_from_dict(seq["positive_subtransient"]),
            positive_transient=_impedance_from_dict(seq["positive_transient"]),
            positive_synchronous=_impedance_from_dict(seq["positive_synchronous"]),
            negative=_impedance_from_dict(seq["negative"]),
            zero=_impedance_from_dict(seq["zero"]),
        )
        return SynchronousGenerator(
            id=identifier,
            name=payload["name"],
            terminal=terminals[0],
            frequency=Frequency(payload["frequency_hz"]),
            sequence_impedances=impedances,
            neutral_grounding=neutral,
            stator_connection=WindingConnection(payload["stator_connection"]),
            prefault_voltage_pu=complex(*payload["prefault_voltage_pu"]),
        )
    if kind == "two_winding_transformer":
        vector = payload["vector_group"]
        sequence = payload["sequence_impedances"]
        base = ElectricalImpedanceBase(
            float(sequence["base"]["mva"]), float(sequence["base"]["kv"])
        )
        impedances = SequencePerUnitImpedance(
            base=base,
            positive=_impedance_from_dict(sequence["positive"]),
            negative=_impedance_from_dict(sequence["negative"]),
            zero=_impedance_from_dict(sequence["zero"]),
        )
        return TwoWindingTransformer(
            id=identifier,
            name=payload["name"],
            terminals=(terminals[0], terminals[1]),
            windings=tuple(_winding_from_dict(item) for item in payload["windings"]),
            frequency=Frequency(payload["frequency_hz"]),
            vector_group=VectorGroup(
                WindingConnection(vector["reference_connection"]),
                WindingConnection(vector["secondary_connection"]),
                int(vector["clock_number"]),
            ),
            sequence_impedances=impedances,
            data_evidence=_evidence_from_dict(payload.get("data_evidence")),
        )
    if kind == "line":
        parameters = LineParameters(
            series_impedance_per_km=_sequence_per_length_from_dict(
                payload["series_impedance_per_km"]
            ),
            shunt_admittance_per_km=_shunt_per_length_from_dict(payload["shunt_admittance_per_km"]),
            reference_frequency=Frequency(payload["frequency_hz"]),
        )
        return Line(
            id=identifier,
            name=payload["name"],
            terminals=(terminals[0], terminals[1]),
            length_km=payload["length_km"],
            parameters=parameters,
            model_kind=LineModelKind(payload["model_kind"]),
            data_evidence=_evidence_from_dict(payload.get("data_evidence")),
        )
    raise NetworkDocumentError(f"Unsupported persisted equipment kind '{kind}'.")


def _complex_to_pair(value: complex) -> list[float]:
    number = complex(value)
    return [number.real, number.imag]


def _complex_from_pair(value: Any) -> complex:
    if not isinstance(value, list) or len(value) != 2:
        raise NetworkDocumentError("Complex result values must be encoded as [real, imaginary].")
    return complex(float(value[0]), float(value[1]))


def _sequence_mapping_to_dict(values) -> dict[str, list[float]]:
    return {sequence.value: _complex_to_pair(value) for sequence, value in values.items()}


def _sequence_mapping_from_dict(values: dict[str, Any]) -> dict[SequenceType, complex]:
    return {SequenceType(name): _complex_from_pair(pair) for name, pair in values.items()}


def _study_to_dict(record: NetworkStudyRecord) -> dict[str, Any]:
    result = record.result
    return {
        "run_id": str(record.run_id),
        "executed_at": record.executed_at.isoformat(),
        "project_name": record.project_name,
        "study_name": record.study_name,
        "network_id": str(record.network_id),
        "fault_bus_id": str(record.fault_bus_id),
        "fault_bus_name": record.fault_bus_name,
        "result": {
            "fault_type": result.fault_type.value,
            "bus_id": str(result.bus_id),
            "fault_impedance_pu": _complex_to_pair(result.fault_impedance_pu),
            "base_power_mva": result.base_power_mva,
            "base_voltage_kv": result.base_voltage_kv,
            "base_current_ka": result.base_current_ka,
            "prefault_sequence_voltages_pu": _sequence_mapping_to_dict(
                result.prefault_sequence_voltages_pu
            ),
            "driving_point_impedances_pu": _sequence_mapping_to_dict(
                result.driving_point_impedances_pu
            ),
            "sequence_currents_pu": _sequence_mapping_to_dict(result.sequence_currents_pu),
            "sequence_fault_voltages_pu": _sequence_mapping_to_dict(
                result.sequence_fault_voltages_pu
            ),
            "phase_currents_pu": [_complex_to_pair(item) for item in result.phase_currents_pu],
            "phase_voltages_pu": [_complex_to_pair(item) for item in result.phase_voltages_pu],
            "phase_currents_ka": [_complex_to_pair(item) for item in result.phase_currents_ka],
            "phase_voltages_kv": [_complex_to_pair(item) for item in result.phase_voltages_kv],
            "ground_current_pu": _complex_to_pair(result.ground_current_pu),
            "ground_current_ka": _complex_to_pair(result.ground_current_ka),
            "diagnostics": [
                {
                    "code": item.code,
                    "message": item.message,
                    "severity": item.severity.value,
                    "entity_id": str(item.entity_id) if item.entity_id else None,
                }
                for item in result.diagnostics
            ],
        },
    }


def _study_from_dict(payload: dict[str, Any]) -> NetworkStudyRecord:
    item = payload["result"]
    diagnostics = tuple(
        DomainDiagnostic(
            code=value["code"],
            message=value["message"],
            severity=DiagnosticSeverity(value["severity"]),
            entity_id=UUID(value["entity_id"]) if value.get("entity_id") else None,
        )
        for value in item.get("diagnostics", [])
    )
    result = ShortCircuitResult(
        fault_type=FaultType(item["fault_type"]),
        bus_id=UUID(item["bus_id"]),
        fault_impedance_pu=_complex_from_pair(item["fault_impedance_pu"]),
        base_power_mva=float(item["base_power_mva"]),
        base_voltage_kv=float(item["base_voltage_kv"]),
        base_current_ka=float(item["base_current_ka"]),
        prefault_sequence_voltages_pu=_sequence_mapping_from_dict(
            item["prefault_sequence_voltages_pu"]
        ),
        driving_point_impedances_pu=_sequence_mapping_from_dict(
            item["driving_point_impedances_pu"]
        ),
        sequence_currents_pu=_sequence_mapping_from_dict(item["sequence_currents_pu"]),
        sequence_fault_voltages_pu=_sequence_mapping_from_dict(item["sequence_fault_voltages_pu"]),
        phase_currents_pu=tuple(_complex_from_pair(value) for value in item["phase_currents_pu"]),
        phase_voltages_pu=tuple(_complex_from_pair(value) for value in item["phase_voltages_pu"]),
        phase_currents_ka=tuple(_complex_from_pair(value) for value in item["phase_currents_ka"]),
        phase_voltages_kv=tuple(_complex_from_pair(value) for value in item["phase_voltages_kv"]),
        ground_current_pu=_complex_from_pair(item["ground_current_pu"]),
        ground_current_ka=_complex_from_pair(item["ground_current_ka"]),
        diagnostics=diagnostics,
    )
    return NetworkStudyRecord(
        run_id=UUID(payload["run_id"]),
        executed_at=datetime.fromisoformat(payload["executed_at"]),
        project_name=payload["project_name"],
        study_name=payload["study_name"],
        network_id=UUID(payload["network_id"]),
        fault_bus_id=UUID(payload["fault_bus_id"]),
        fault_bus_name=payload["fault_bus_name"],
        result=result,
    )
