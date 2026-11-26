"""Materialize PFA-ES-001 boundary placeholders as calculation-ready equipment.

The use cases preserve the original interface/equipment/terminal UUID so existing
symbol mappings remain valid. They build a fresh Network aggregate first and only
return a replacement workspace after the complete topology passes aggregate checks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from numbers import Real
from uuid import UUID, uuid4

from power_fault_analyzer.application.use_cases.network_workspace import NetworkWorkspace
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.equipment_interface import (
    EquipmentInterfaceKind,
    ParameterEvidenceStatus,
)
from power_fault_analyzer.domain.enums.grounding_mode import GroundingMode
from power_fault_analyzer.domain.enums.line_model_kind import LineModelKind
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.source_sequence_status import SourceSequenceStatus
from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
from power_fault_analyzer.domain.enums.winding_designation import WindingDesignation
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
    ImpedancePerLength,
    SequenceAdmittancePerLengthSet,
    SequenceImpedancePerLengthSet,
)
from power_fault_analyzer.domain.value_objects.source_models import (
    SourceEquivalentSet,
    SourceSequenceEquivalent,
)
from power_fault_analyzer.domain.value_objects.transformer_winding import TransformerWinding
from power_fault_analyzer.domain.value_objects.vector_group import VectorGroup
from power_fault_analyzer.domain.value_objects.voltage import Voltage
from power_fault_analyzer.equipment.interfaces.unresolved_equipment import (
    EngineeringParameter,
    UnresolvedEquipmentInterface,
)
from power_fault_analyzer.equipment.sources.equivalent_source import EquivalentSource
from power_fault_analyzer.equipment.transformers.two_winding_transformer import (
    TwoWindingTransformer,
)
from power_fault_analyzer.equipment.transmission.line import Line
from power_fault_analyzer.equipment.transmission.line_parameters import LineParameters


class BoundaryResolutionError(ValueError):
    """Raised when a boundary cannot be converted without inventing engineering data."""


@dataclass(frozen=True, slots=True)
class ResolveLineBoundaryInput:
    interface_id: UUID
    remote_bus_name: str
    line_name: str
    length_km: float
    frequency_hz: float
    positive_r_ohm_per_km: float
    positive_x_ohm_per_km: float
    negative_r_ohm_per_km: float
    negative_x_ohm_per_km: float
    zero_r_ohm_per_km: float
    zero_x_ohm_per_km: float
    source_name: str
    source_base_mva: float
    source_prefault_voltage_pu: complex
    source_positive_r_pu: float
    source_positive_x_pu: float
    source_negative_r_pu: float
    source_negative_x_pu: float
    source_zero_r_pu: float
    source_zero_x_pu: float
    evidence_reference: str


@dataclass(frozen=True, slots=True)
class ResolveTransformerBoundaryInput:
    interface_id: UUID
    low_bus_name: str
    transformer_name: str
    rated_power_mva: float
    impedance_base_mva: float
    low_rated_voltage_kv: float
    frequency_hz: float
    hv_connection: WindingConnection
    lv_connection: WindingConnection
    vector_group_clock: int
    positive_r_pu: float
    positive_x_pu: float
    negative_r_pu: float
    negative_x_pu: float
    zero_r_pu: float
    zero_x_pu: float
    hv_grounding: NeutralGrounding | None
    lv_grounding: NeutralGrounding | None
    evidence_reference: str


@dataclass(frozen=True, slots=True)
class BoundaryResolutionResult:
    workspace: NetworkWorkspace
    equipment: Line | TwoWindingTransformer
    remote_bus: Bus
    external_source: EquivalentSource | None = None


def _finite(
    value: Real,
    name: str,
    *,
    positive: bool = False,
    non_negative: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number, not bool.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    if positive and result <= 0.0:
        raise ValueError(f"{name} must be greater than zero.")
    if non_negative and result < 0.0:
        raise ValueError(f"{name} cannot be negative.")
    return result


def _evidence(
    reference: str,
    values: tuple[tuple[str, str, float | str], ...],
) -> tuple[EngineeringParameter, ...]:
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError(
            "An evidence reference is mandatory (nameplate, datasheet, study, "
            "or user-confirmed source)."
        )
    source = reference.strip()
    return tuple(
        EngineeringParameter(
            name=name,
            unit=unit,
            value=value,
            status=ParameterEvidenceStatus.USER_CONFIRMED,
            source_reference=source,
        )
        for name, unit, value in values
    )


def _clone_without_interface(
    network: Network,
    interface: UnresolvedEquipmentInterface,
) -> Network:
    """Clone topology, excluding one interface; no source workspace is mutated."""
    clone = Network(network.name, id=network.id)
    for bus in network.buses:
        clone.add_bus(bus)
    for equipment in network.equipment:
        if equipment.id != interface.id:
            clone.add_equipment(equipment)
    removed_terminal_ids = {item.id for item in interface.terminals}
    for connection in network.connections:
        if connection.terminal_id not in removed_terminal_ids:
            clone.connect(connection.terminal_id, connection.bus_id)
    return clone


def _interface_and_local_bus(
    workspace: NetworkWorkspace,
    identifier: UUID,
    expected_kind: EquipmentInterfaceKind,
) -> tuple[UnresolvedEquipmentInterface, Bus]:
    if not isinstance(workspace, NetworkWorkspace):
        raise TypeError("workspace must be NetworkWorkspace.")
    if not isinstance(identifier, UUID):
        raise TypeError("interface_id must be a UUID.")
    interface = workspace.network.get_equipment(identifier)
    if not isinstance(interface, UnresolvedEquipmentInterface):
        raise BoundaryResolutionError("Selected equipment is not an unresolved boundary interface.")
    if interface.interface_kind is not expected_kind:
        raise BoundaryResolutionError(
            f"Expected {expected_kind.value} boundary, received {interface.interface_kind.value}."
        )
    if len(interface.terminals) != 1:
        raise BoundaryResolutionError(
            "A boundary interface must expose exactly one local terminal."
        )
    try:
        local_bus_id = workspace.network.get_connection(interface.terminals[0].id).bus_id
    except KeyError as exc:
        raise BoundaryResolutionError(
            "The boundary terminal is not connected to a physical bus."
        ) from exc
    return interface, workspace.network.get_bus(local_bus_id)


def _replacement_workspace(
    old: NetworkWorkspace,
    new_network: Network,
    *,
    remote_bus: Bus,
    local_bus_id: UUID,
    vertical_offset: float = 0.0,
) -> NetworkWorkspace:
    positions = dict(old.diagram_positions)
    x, y = positions.get(local_bus_id, (300.0, 300.0))
    positions[remote_bus.id] = (x + 360.0, y + vertical_offset)
    symbols = {
        key: replace(
            placement,
            label=(
                placement.label.replace("datos de línea pendientes", "línea parametrizada").replace(
                    "datos de placa pendientes", "transformador parametrizado"
                )
                if placement.label
                else None
            ),
        )
        for key, placement in old.diagram_symbols.items()
    }
    return NetworkWorkspace(
        network=new_network,
        diagram_positions=positions,
        diagram_rotations=old.diagram_rotations,
        grid_spacing=old.grid_spacing,
        snap_enabled=old.snap_enabled,
        study_history=old.study_history,
        diagram_symbols=symbols,
    )


class ResolveLineBoundary:
    """Replace a line boundary with a series-only line and a remote Thevenin source.

    Shunt capacitance is not inferred: the resulting line model explicitly declares
    a series-only equivalent. The remote source requires explicit impedances for all
    three sequences on its own declared MVA/kV base.
    """

    def execute(
        self,
        workspace: NetworkWorkspace,
        specification: ResolveLineBoundaryInput,
    ) -> BoundaryResolutionResult:
        if not isinstance(specification, ResolveLineBoundaryInput):
            raise TypeError("specification must be ResolveLineBoundaryInput.")
        interface, local_bus = _interface_and_local_bus(
            workspace,
            specification.interface_id,
            EquipmentInterfaceKind.TRANSMISSION_LINE,
        )
        length = _finite(specification.length_km, "length_km", positive=True)
        frequency_hz = _finite(specification.frequency_hz, "frequency_hz", positive=True)
        source_base_mva = _finite(
            specification.source_base_mva,
            "source_base_mva",
            positive=True,
        )
        remote_name = specification.remote_bus_name.strip()
        line_name = specification.line_name.strip()
        source_name = specification.source_name.strip()
        if not remote_name or not line_name or not source_name:
            raise ValueError("Remote bus, line and source identifiers cannot be empty.")

        prefault = complex(specification.source_prefault_voltage_pu)
        if (
            not math.isfinite(prefault.real)
            or not math.isfinite(prefault.imag)
            or abs(prefault) <= 0.0
        ):
            raise ValueError("Source prefault voltage must be finite and non-zero.")

        line_sequence_values = {
            "positive": (
                _finite(
                    specification.positive_r_ohm_per_km,
                    "positive_r_ohm_per_km",
                    non_negative=True,
                ),
                _finite(specification.positive_x_ohm_per_km, "positive_x_ohm_per_km"),
            ),
            "negative": (
                _finite(
                    specification.negative_r_ohm_per_km,
                    "negative_r_ohm_per_km",
                    non_negative=True,
                ),
                _finite(specification.negative_x_ohm_per_km, "negative_x_ohm_per_km"),
            ),
            "zero": (
                _finite(
                    specification.zero_r_ohm_per_km,
                    "zero_r_ohm_per_km",
                    non_negative=True,
                ),
                _finite(specification.zero_x_ohm_per_km, "zero_x_ohm_per_km"),
            ),
        }
        source_sequence_values = {
            "positive": (
                _finite(
                    specification.source_positive_r_pu,
                    "source_positive_r_pu",
                    non_negative=True,
                ),
                _finite(
                    specification.source_positive_x_pu,
                    "source_positive_x_pu",
                    non_negative=True,
                ),
            ),
            "negative": (
                _finite(
                    specification.source_negative_r_pu,
                    "source_negative_r_pu",
                    non_negative=True,
                ),
                _finite(
                    specification.source_negative_x_pu,
                    "source_negative_x_pu",
                    non_negative=True,
                ),
            ),
            "zero": (
                _finite(
                    specification.source_zero_r_pu,
                    "source_zero_r_pu",
                    non_negative=True,
                ),
                _finite(
                    specification.source_zero_x_pu,
                    "source_zero_x_pu",
                    non_negative=True,
                ),
            ),
        }
        for sequence, (resistance, reactance) in line_sequence_values.items():
            if resistance == 0.0 and reactance == 0.0:
                raise ValueError(f"The {sequence}-sequence line impedance cannot be zero.")
        for sequence, (resistance, reactance) in source_sequence_values.items():
            if resistance == 0.0 and reactance == 0.0:
                raise ValueError(f"The {sequence}-sequence Thevenin impedance cannot be zero.")

        line_evidence_values: tuple[tuple[str, str, float | str], ...] = (
            ("remote_nominal_voltage_kv", "kV line-line", local_bus.nominal_voltage.value_kv),
            ("length_km", "km", length),
            ("frequency_hz", "Hz", frequency_hz),
            ("r1_per_km", "ohm/km", line_sequence_values["positive"][0]),
            ("x1_per_km", "ohm/km", line_sequence_values["positive"][1]),
            ("r2_per_km", "ohm/km", line_sequence_values["negative"][0]),
            ("x2_per_km", "ohm/km", line_sequence_values["negative"][1]),
            ("r0_per_km", "ohm/km", line_sequence_values["zero"][0]),
            ("x0_per_km", "ohm/km", line_sequence_values["zero"][1]),
            ("model_kind", "model", LineModelKind.SERIES_ONLY.value),
        )
        source_evidence_values: tuple[tuple[str, str, float | str], ...] = (
            ("source_base_mva", "MVA", source_base_mva),
            (
                "source_base_voltage_kv",
                "kV line-line",
                local_bus.nominal_voltage.value_kv,
            ),
            ("source_prefault_voltage_pu", "pu", f"{prefault.real:g}{prefault.imag:+g}j"),
            ("source_r1_pu", "pu", source_sequence_values["positive"][0]),
            ("source_x1_pu", "pu", source_sequence_values["positive"][1]),
            ("source_r2_pu", "pu", source_sequence_values["negative"][0]),
            ("source_x2_pu", "pu", source_sequence_values["negative"][1]),
            ("source_r0_pu", "pu", source_sequence_values["zero"][0]),
            ("source_x0_pu", "pu", source_sequence_values["zero"][1]),
        )
        line_evidence = _evidence(specification.evidence_reference, line_evidence_values)
        source_evidence = _evidence(specification.evidence_reference, source_evidence_values)

        remote_bus = Bus(remote_name, local_bus.nominal_voltage)
        old_terminal = interface.terminals[0]
        local_terminal = Terminal(
            equipment_id=interface.id,
            designation="FROM",
            rated_voltage=local_bus.nominal_voltage,
            id=old_terminal.id,
        )
        remote_terminal = Terminal(interface.id, "TO", remote_bus.nominal_voltage)
        parameters = LineParameters(
            series_impedance_per_km=SequenceImpedancePerLengthSet(
                ImpedancePerLength(*line_sequence_values["positive"]),
                ImpedancePerLength(*line_sequence_values["negative"]),
                ImpedancePerLength(*line_sequence_values["zero"]),
            ),
            shunt_admittance_per_km=SequenceAdmittancePerLengthSet.all_zero(),
            reference_frequency=Frequency(frequency_hz),
        )
        line = Line(
            id=interface.id,
            name=line_name,
            terminals=(local_terminal, remote_terminal),
            length_km=length,
            parameters=parameters,
            model_kind=LineModelKind.SERIES_ONLY,
            data_evidence=line_evidence,
        )

        source_id = uuid4()
        source_terminal = Terminal(source_id, "HV", remote_bus.nominal_voltage)
        source_base = ElectricalImpedanceBase(
            source_base_mva,
            remote_bus.nominal_voltage.value_kv,
        )
        source_equivalent = SourceEquivalentSet(
            base=source_base,
            positive=SourceSequenceEquivalent(
                SequenceType.POSITIVE,
                SourceSequenceStatus.AVAILABLE,
                PerUnitImpedance(*source_sequence_values["positive"]),
                prefault,
            ),
            negative=SourceSequenceEquivalent(
                SequenceType.NEGATIVE,
                SourceSequenceStatus.AVAILABLE,
                PerUnitImpedance(*source_sequence_values["negative"]),
            ),
            zero=SourceSequenceEquivalent(
                SequenceType.ZERO,
                SourceSequenceStatus.AVAILABLE,
                PerUnitImpedance(*source_sequence_values["zero"]),
            ),
        )
        source = EquivalentSource(
            id=source_id,
            name=source_name,
            terminal=source_terminal,
            frequency=Frequency(frequency_hz),
            equivalent=source_equivalent,
            data_evidence=source_evidence,
        )

        new_network = _clone_without_interface(workspace.network, interface)
        new_network.add_bus(remote_bus)
        new_network.add_equipment(line)
        new_network.connect(local_terminal.id, local_bus.id)
        new_network.connect(remote_terminal.id, remote_bus.id)
        new_network.add_equipment(source)
        new_network.connect(source_terminal.id, remote_bus.id)
        updated = _replacement_workspace(
            workspace,
            new_network,
            remote_bus=remote_bus,
            local_bus_id=local_bus.id,
        )
        return BoundaryResolutionResult(updated, line, remote_bus, source)


class ResolveTransformerBoundary:
    """Replace a transformer boundary with an explicit two-winding model and LV bus."""

    def execute(
        self,
        workspace: NetworkWorkspace,
        specification: ResolveTransformerBoundaryInput,
    ) -> BoundaryResolutionResult:
        if not isinstance(specification, ResolveTransformerBoundaryInput):
            raise TypeError("specification must be ResolveTransformerBoundaryInput.")
        interface, local_bus = _interface_and_local_bus(
            workspace,
            specification.interface_id,
            EquipmentInterfaceKind.POWER_TRANSFORMER,
        )
        rated_power = _finite(specification.rated_power_mva, "rated_power_mva", positive=True)
        impedance_base_mva = _finite(
            specification.impedance_base_mva,
            "impedance_base_mva",
            positive=True,
        )
        lv_voltage = _finite(
            specification.low_rated_voltage_kv,
            "low_rated_voltage_kv",
            positive=True,
        )
        frequency_hz = _finite(specification.frequency_hz, "frequency_hz", positive=True)
        low_bus_name = specification.low_bus_name.strip()
        transformer_name = specification.transformer_name.strip()
        if not low_bus_name or not transformer_name:
            raise ValueError("Low-voltage bus and transformer identifiers cannot be empty.")
        if not isinstance(specification.hv_connection, WindingConnection) or not isinstance(
            specification.lv_connection, WindingConnection
        ):
            raise TypeError("Transformer winding connections must be WindingConnection values.")
        if (
            isinstance(specification.vector_group_clock, bool)
            or not isinstance(specification.vector_group_clock, int)
            or not 0 <= specification.vector_group_clock <= 11
        ):
            raise ValueError("Vector-group clock number must be an integer from 0 to 11.")

        impedances = {
            "positive": (
                _finite(specification.positive_r_pu, "positive_r_pu", non_negative=True),
                _finite(specification.positive_x_pu, "positive_x_pu", non_negative=True),
            ),
            "negative": (
                _finite(specification.negative_r_pu, "negative_r_pu", non_negative=True),
                _finite(specification.negative_x_pu, "negative_x_pu", non_negative=True),
            ),
            "zero": (
                _finite(specification.zero_r_pu, "zero_r_pu", non_negative=True),
                _finite(specification.zero_x_pu, "zero_x_pu", non_negative=True),
            ),
        }
        if any(
            resistance == 0.0 and reactance == 0.0 for resistance, reactance in impedances.values()
        ):
            raise ValueError("Each transformer sequence leakage impedance must be non-zero.")

        for connection, grounding, side in (
            (specification.hv_connection, specification.hv_grounding, "HV"),
            (specification.lv_connection, specification.lv_grounding, "LV"),
        ):
            if connection is WindingConnection.DELTA and grounding is not None:
                raise ValueError(f"{side} delta winding cannot declare neutral grounding.")
            if connection is not WindingConnection.DELTA and not isinstance(
                grounding, NeutralGrounding
            ):
                raise ValueError(
                    f"{side} star/zigzag winding requires explicit neutral grounding data."
                )

        hv_voltage = local_bus.nominal_voltage.value_kv
        evidence_values: list[tuple[str, str, float | str]] = [
            ("rated_power_mva", "MVA", rated_power),
            ("impedance_base_mva", "MVA", impedance_base_mva),
            ("hv_rated_voltage_kv", "kV line-line", hv_voltage),
            ("lv_rated_voltage_kv", "kV line-line", lv_voltage),
            ("frequency_hz", "Hz", frequency_hz),
            ("hv_connection", "connection", specification.hv_connection.value),
            ("lv_connection", "connection", specification.lv_connection.value),
            ("vector_group_clock", "hour", float(specification.vector_group_clock)),
        ]
        for sequence, suffix in (("positive", "1"), ("negative", "2"), ("zero", "0")):
            resistance, reactance = impedances[sequence]
            evidence_values.extend(
                (
                    (f"r{suffix}_pu", "pu", resistance),
                    (f"x{suffix}_pu", "pu", reactance),
                )
            )
        for side, grounding in (
            ("hv", specification.hv_grounding),
            ("lv", specification.lv_grounding),
        ):
            if grounding is None:
                evidence_values.append((f"{side}_grounding", "mode", "delta"))
            else:
                evidence_values.extend(
                    (
                        (f"{side}_grounding_mode", "mode", grounding.mode.value),
                        (f"{side}_neutral_r_ohm", "ohm", grounding.resistance_ohm),
                        (f"{side}_neutral_x_ohm", "ohm", grounding.reactance_ohm),
                    )
                )
        evidence = _evidence(specification.evidence_reference, tuple(evidence_values))

        remote_bus = Bus(low_bus_name, Voltage.from_kv(lv_voltage))
        old_terminal = interface.terminals[0]
        hv_terminal = Terminal(
            equipment_id=interface.id,
            designation=WindingDesignation.HIGH_VOLTAGE.value,
            rated_voltage=local_bus.nominal_voltage,
            id=old_terminal.id,
        )
        lv_terminal = Terminal(
            interface.id,
            WindingDesignation.LOW_VOLTAGE.value,
            remote_bus.nominal_voltage,
        )

        def neutral_available(
            connection: WindingConnection,
            grounding: NeutralGrounding | None,
        ) -> bool:
            return (
                connection is not WindingConnection.DELTA
                and grounding is not None
                and grounding.mode is not GroundingMode.UNGROUNDED
            )

        hv_winding = TransformerWinding(
            designation=WindingDesignation.HIGH_VOLTAGE,
            rated_voltage_kv=hv_voltage,
            rated_power_mva=rated_power,
            connection=specification.hv_connection,
            neutral_grounding=specification.hv_grounding,
            neutral_terminal_available=neutral_available(
                specification.hv_connection,
                specification.hv_grounding,
            ),
        )
        lv_winding = TransformerWinding(
            designation=WindingDesignation.LOW_VOLTAGE,
            rated_voltage_kv=lv_voltage,
            rated_power_mva=rated_power,
            connection=specification.lv_connection,
            neutral_grounding=specification.lv_grounding,
            neutral_terminal_available=neutral_available(
                specification.lv_connection,
                specification.lv_grounding,
            ),
        )
        transformer = TwoWindingTransformer(
            id=interface.id,
            name=transformer_name,
            terminals=(hv_terminal, lv_terminal),
            windings=(hv_winding, lv_winding),
            frequency=Frequency(frequency_hz),
            vector_group=VectorGroup(
                specification.hv_connection,
                specification.lv_connection,
                specification.vector_group_clock,
            ),
            sequence_impedances=SequencePerUnitImpedance(
                base=ElectricalImpedanceBase(impedance_base_mva, hv_voltage),
                positive=PerUnitImpedance(*impedances["positive"]),
                negative=PerUnitImpedance(*impedances["negative"]),
                zero=PerUnitImpedance(*impedances["zero"]),
            ),
            data_evidence=evidence,
        )

        new_network = _clone_without_interface(workspace.network, interface)
        new_network.add_bus(remote_bus)
        new_network.add_equipment(transformer)
        new_network.connect(hv_terminal.id, local_bus.id)
        new_network.connect(lv_terminal.id, remote_bus.id)
        updated = _replacement_workspace(
            workspace,
            new_network,
            remote_bus=remote_bus,
            local_bus_id=local_bus.id,
            vertical_offset=220.0,
        )
        return BoundaryResolutionResult(updated, transformer, remote_bus, None)
