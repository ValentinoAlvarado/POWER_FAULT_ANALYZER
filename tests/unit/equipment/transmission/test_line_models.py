from uuid import uuid4

import pytest

from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.construction import (
    ConductorMaterial,
    InsulationMaterial,
    ScreenBonding,
)
from power_fault_analyzer.domain.enums.line_model_kind import LineModelKind
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.interfaces.branch_model_contracts import (
    SequenceBranchModelProvider,
)
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.impedance import Admittance, Impedance
from power_fault_analyzer.domain.value_objects.sequence_parameters import (
    AdmittancePerLength,
    ImpedancePerLength,
    SequenceAdmittancePerLengthSet,
    SequenceImpedancePerLengthSet,
    SequenceImpedanceSet,
)
from power_fault_analyzer.domain.value_objects.voltage import Voltage
from power_fault_analyzer.equipment.transmission.line import Line
from power_fault_analyzer.equipment.transmission.line_parameters import LineParameters
from power_fault_analyzer.equipment.transmission.overhead_line import OverheadLine
from power_fault_analyzer.equipment.transmission.series_reactance import SeriesReactance
from power_fault_analyzer.equipment.transmission.underground_cable import UndergroundCable


def make_terminals(voltage_kv: float = 13.8) -> tuple[Terminal, Terminal]:
    equipment_id = uuid4()
    voltage = Voltage.from_kv(voltage_kv)
    return (
        Terminal(equipment_id, "FROM", voltage),
        Terminal(equipment_id, "TO", voltage),
    )


def make_parameters() -> LineParameters:
    return LineParameters(
        series_impedance_per_km=SequenceImpedancePerLengthSet(
            positive=ImpedancePerLength(0.1, 0.4),
            negative=ImpedancePerLength(0.12, 0.42),
            zero=ImpedancePerLength(0.3, 1.2),
        ),
        shunt_admittance_per_km=SequenceAdmittancePerLengthSet(
            positive=AdmittancePerLength(1e-6, 4e-6),
            negative=AdmittancePerLength(1.2e-6, 4.2e-6),
            zero=AdmittancePerLength(0.5e-6, 2e-6),
        ),
        reference_frequency=Frequency(60.0),
    )


def test_line_builds_nominal_pi_equivalent_and_scales_by_length() -> None:
    terminal_pair = make_terminals()
    line = Line(
        id=terminal_pair[0].equipment_id,
        name="LINE-01",
        terminals=terminal_pair,
        length_km=10.0,
        parameters=make_parameters(),
    )

    model = line.build_sequence_equivalent(SequenceType.POSITIVE)

    assert model.series_impedance == Impedance(1.0, 4.0)
    assert model.shunt_admittance_from.conductance_siemens == pytest.approx(5e-6)
    assert model.shunt_admittance_from.susceptance_siemens == pytest.approx(20e-6)
    assert model.shunt_admittance_to == model.shunt_admittance_from


def test_line_preserves_distinct_negative_and_zero_sequence_parameters() -> None:
    terminal_pair = make_terminals()
    line = Line(
        id=terminal_pair[0].equipment_id,
        name="LINE-SEQ",
        terminals=terminal_pair,
        length_km=5.0,
        parameters=make_parameters(),
    )

    positive = line.build_sequence_equivalent(SequenceType.POSITIVE)
    negative = line.build_sequence_equivalent(SequenceType.NEGATIVE)
    zero = line.build_sequence_equivalent(SequenceType.ZERO)

    assert positive.series_impedance == Impedance(0.5, 2.0)
    assert negative.series_impedance == Impedance(0.6, 2.1)
    assert zero.series_impedance == Impedance(1.5, 6.0)


def test_series_only_line_does_not_include_shunt_admittance() -> None:
    terminal_pair = make_terminals()
    line = Line(
        id=terminal_pair[0].equipment_id,
        name="SHORT-LINE",
        terminals=terminal_pair,
        length_km=2.0,
        parameters=make_parameters(),
        model_kind=LineModelKind.SERIES_ONLY,
    )

    model = line.build_sequence_equivalent(SequenceType.POSITIVE)
    assert model.shunt_admittance_from == Admittance.zero()
    assert model.shunt_admittance_to == Admittance.zero()
    assert model.series_impedance == Impedance(0.2, 0.8)


def test_line_requires_positive_finite_length() -> None:
    terminal_pair = make_terminals()
    for invalid in (0.0, -1.0, float("inf"), float("nan")):
        with pytest.raises((TypeError, ValueError)):
            Line(
                id=terminal_pair[0].equipment_id,
                name="INVALID-LINE",
                terminals=terminal_pair,
                length_km=invalid,
                parameters=make_parameters(),
            )


def test_line_rejects_boolean_length() -> None:
    terminal_pair = make_terminals()
    with pytest.raises(TypeError):
        Line(
            id=terminal_pair[0].equipment_id,
            name="INVALID-LINE",
            terminals=terminal_pair,
            length_km=True,
            parameters=make_parameters(),
        )


def test_overhead_line_exposes_construction_metadata() -> None:
    terminal_pair = make_terminals()
    line = OverheadLine(
        id=terminal_pair[0].equipment_id,
        name="OHL-01",
        terminals=terminal_pair,
        length_km=12.0,
        parameters=make_parameters(),
        conductor_material=ConductorMaterial.ACSR,
        bundle_subconductors=2,
    )
    assert line.conductor_material is ConductorMaterial.ACSR
    assert line.bundle_subconductors == 2
    assert line.length_km == 12.0


def test_overhead_line_rejects_invalid_bundle_count() -> None:
    terminal_pair = make_terminals()
    with pytest.raises(ValueError):
        OverheadLine(
            id=terminal_pair[0].equipment_id,
            name="OHL-INVALID",
            terminals=terminal_pair,
            length_km=12.0,
            parameters=make_parameters(),
            bundle_subconductors=0,
        )


def test_underground_cable_exposes_construction_metadata() -> None:
    terminal_pair = make_terminals()
    cable = UndergroundCable(
        id=terminal_pair[0].equipment_id,
        name="CABLE-01",
        terminals=terminal_pair,
        length_km=1.5,
        parameters=make_parameters(),
        conductor_material=ConductorMaterial.COPPER,
        conductor_cross_section_mm2=240.0,
        insulation_material=InsulationMaterial.XLPE,
        screen_bonding=ScreenBonding.CROSS_BONDED,
    )
    assert cable.conductor_cross_section_mm2 == 240.0
    assert cable.insulation_material is InsulationMaterial.XLPE
    assert cable.screen_bonding is ScreenBonding.CROSS_BONDED


def test_underground_cable_rejects_invalid_cross_section() -> None:
    terminal_pair = make_terminals()
    with pytest.raises(ValueError):
        UndergroundCable(
            id=terminal_pair[0].equipment_id,
            name="CABLE-INVALID",
            terminals=terminal_pair,
            length_km=1.5,
            parameters=make_parameters(),
            conductor_material=ConductorMaterial.COPPER,
            conductor_cross_section_mm2=0.0,
            insulation_material=InsulationMaterial.XLPE,
            screen_bonding=ScreenBonding.UNKNOWN,
        )


def test_series_reactance_uses_lumped_sequence_impedance() -> None:
    terminal_pair = make_terminals()
    equipment = SeriesReactance(
        id=terminal_pair[0].equipment_id,
        name="SERIES-REACTOR-01",
        terminals=terminal_pair,
        sequence_impedances=SequenceImpedanceSet(
            positive=Impedance(0.01, 0.2),
            negative=Impedance(0.01, 0.21),
            zero=Impedance(0.02, 0.5),
        ),
    )
    model = equipment.build_sequence_equivalent(SequenceType.ZERO)
    assert model.series_impedance == Impedance(0.02, 0.5)
    assert model.shunt_admittance_from == Admittance.zero()


def test_line_satisfies_sequence_branch_model_protocol() -> None:
    terminal_pair = make_terminals()
    line = Line(
        id=terminal_pair[0].equipment_id,
        name="LINE-PROTOCOL",
        terminals=terminal_pair,
        length_km=1.0,
        parameters=make_parameters(),
    )
    assert isinstance(line, SequenceBranchModelProvider)


def test_network_accepts_concrete_overhead_line_and_connects_terminals() -> None:
    terminal_pair = make_terminals()
    line = OverheadLine(
        id=terminal_pair[0].equipment_id,
        name="OHL-NETWORK",
        terminals=terminal_pair,
        length_km=8.0,
        parameters=make_parameters(),
    )
    network = Network("Branch Integration")
    bus_from = Bus("BUS-FROM", Voltage.from_kv(13.8))
    bus_to = Bus("BUS-TO", Voltage.from_kv(13.8))
    network.add_bus(bus_from)
    network.add_bus(bus_to)
    network.add_equipment(line)
    network.connect(line.terminal_from.id, bus_from.id)
    network.connect(line.terminal_to.id, bus_to.id)

    assert len(network.connections) == 2
    assert network.get_equipment(line.id) is line
