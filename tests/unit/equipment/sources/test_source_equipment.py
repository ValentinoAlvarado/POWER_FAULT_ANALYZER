from uuid import uuid4

import pytest

from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.converter_control_mode import (
    ConverterControlMode,
    ConverterCurrentPriority,
)
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.source_operating_regime import SourceOperatingRegime
from power_fault_analyzer.domain.enums.source_sequence_status import SourceSequenceStatus
from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
from power_fault_analyzer.domain.exceptions.source_exceptions import (
    UnsupportedSourceOperatingRegimeError,
)
from power_fault_analyzer.domain.interfaces.source_model_contracts import (
    FaultCurrentCapabilityProvider,
    SourceModelProvider,
)
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.impedance import Impedance
from power_fault_analyzer.domain.value_objects.neutral_grounding import NeutralGrounding
from power_fault_analyzer.domain.value_objects.source_models import (
    ConverterFaultCurrentCapability,
    ExternalGridShortCircuitData,
    InductionGeneratorParameters,
    SourceEquivalentSet,
    SourceSequenceEquivalent,
    SynchronousMachineSequenceImpedances,
)
from power_fault_analyzer.domain.value_objects.transformer_impedance import (
    PerUnitImpedance,
    SequencePerUnitImpedance,
)
from power_fault_analyzer.domain.value_objects.voltage import Voltage
from power_fault_analyzer.equipment.sources import (
    ConverterBasedGenerator,
    EquivalentSource,
    ExternalGrid,
    InductionGenerator,
    SynchronousGenerator,
)


def _terminal(voltage_kv: float = 13.8) -> Terminal:
    equipment_id = uuid4()
    return Terminal(
        equipment_id=equipment_id,
        designation="P",
        rated_voltage=Voltage.from_kv(voltage_kv),
    )


def _machine_impedances() -> SynchronousMachineSequenceImpedances:
    return SynchronousMachineSequenceImpedances(
        base=ElectricalImpedanceBase(100.0, 13.8),
        positive_subtransient=PerUnitImpedance(0.01, 0.20),
        positive_transient=PerUnitImpedance(0.02, 0.30),
        positive_synchronous=PerUnitImpedance(0.03, 1.50),
        negative=PerUnitImpedance(0.01, 0.18),
        zero=PerUnitImpedance(0.02, 0.10),
    )


def _induction_parameters() -> InductionGeneratorParameters:
    base = ElectricalImpedanceBase(20.0, 13.8)
    return InductionGeneratorParameters(
        rated_power_mva=20.0,
        sequence_impedances=SequencePerUnitImpedance(
            base=base,
            positive=PerUnitImpedance(0.02, 0.22),
            negative=PerUnitImpedance(0.03, 0.25),
            zero=PerUnitImpedance(0.04, 0.12),
        ),
        decay_time_constant_s=0.08,
        prefault_voltage_pu=0.97 - 0.02j,
    )


def test_external_grid_builds_positive_sequence_equivalent_on_system_base() -> None:
    terminal = _terminal()
    grid = ExternalGrid(
        id=terminal.equipment_id,
        name="UTILITY-GRID",
        terminal=terminal,
        frequency=Frequency(60),
        short_circuit_data=ExternalGridShortCircuitData(100.0, 0.1),
    )
    base = ElectricalImpedanceBase(100.0, 13.8)
    model = grid.build_source_equivalent(base, SourceOperatingRegime.SUBTRANSIENT)
    assert model.positive.status is SourceSequenceStatus.AVAILABLE
    assert abs(model.positive.impedance.value_pu) == pytest.approx(1.0)
    assert model.positive.internal_voltage_pu == 1 + 0j
    assert model.negative.status is SourceSequenceStatus.UNSPECIFIED
    assert model.zero.status is SourceSequenceStatus.UNSPECIFIED


def test_external_grid_uses_explicit_negative_and_zero_sequence_impedances() -> None:
    terminal = _terminal()
    grid = ExternalGrid(
        id=terminal.equipment_id,
        name="GRID-WITH-SEQUENCE-DATA",
        terminal=terminal,
        frequency=Frequency(50),
        short_circuit_data=ExternalGridShortCircuitData(
            100,
            0.1,
            negative_sequence_impedance_ohm=Impedance(0.02, 0.25),
            zero_sequence_impedance_ohm=Impedance(0.04, 0.35),
        ),
    )
    model = grid.build_source_equivalent(
        ElectricalImpedanceBase(100, 13.8), SourceOperatingRegime.TRANSIENT
    )
    assert model.negative.status is SourceSequenceStatus.AVAILABLE
    assert model.zero.status is SourceSequenceStatus.AVAILABLE
    assert model.negative.impedance.value_pu == pytest.approx(complex(0.02, 0.25) / 1.9044)
    assert model.zero.impedance.value_pu == pytest.approx(complex(0.04, 0.35) / 1.9044)


def test_external_grid_is_registered_and_connected_to_network() -> None:
    terminal = _terminal()
    grid = ExternalGrid(
        id=terminal.equipment_id,
        name="GRID",
        terminal=terminal,
        frequency=Frequency(60),
        short_circuit_data=ExternalGridShortCircuitData(500, 0.05),
    )
    network = Network("SOURCE CONNECTION")
    bus = Bus("BUS-1", Voltage.from_kv(13.8))
    network.add_bus(bus)
    network.add_equipment(grid)
    connection = network.connect(terminal.id, bus.id)
    assert connection.bus_id == bus.id
    assert grid.family is EquipmentFamily.SOURCE


def test_synchronous_generator_selects_positive_sequence_regime() -> None:
    terminal = _terminal()
    generator = SynchronousGenerator(
        id=terminal.equipment_id,
        name="GEN-1",
        terminal=terminal,
        frequency=Frequency(60),
        sequence_impedances=_machine_impedances(),
        neutral_grounding=NeutralGrounding.solid(),
    )
    base = ElectricalImpedanceBase(50, 13.8)
    subtransient = generator.build_source_equivalent(base, SourceOperatingRegime.SUBTRANSIENT)
    transient = generator.build_source_equivalent(base, SourceOperatingRegime.TRANSIENT)
    synchronous = generator.build_source_equivalent(base, SourceOperatingRegime.SYNCHRONOUS)
    assert subtransient.positive.impedance.value_pu == pytest.approx(0.005 + 0.1j)
    assert transient.positive.impedance.value_pu == pytest.approx(0.01 + 0.15j)
    assert synchronous.positive.impedance.value_pu == pytest.approx(0.015 + 0.75j)


def test_synchronous_generator_adds_three_times_neutral_impedance_to_zero_sequence() -> None:
    terminal = _terminal()
    generator = SynchronousGenerator(
        id=terminal.equipment_id,
        name="GEN-GROUNDED",
        terminal=terminal,
        frequency=Frequency(60),
        sequence_impedances=_machine_impedances(),
        neutral_grounding=NeutralGrounding.through_impedance(0.1, 0.05),
    )
    base = ElectricalImpedanceBase(100, 13.8)
    model = generator.build_source_equivalent(base, SourceOperatingRegime.SUBTRANSIENT)
    machine_z0_ohm = complex(0.02, 0.10) * base.base_impedance_ohm
    expected = (machine_z0_ohm + complex(0.3, 0.15)) / base.base_impedance_ohm
    assert model.zero.status is SourceSequenceStatus.AVAILABLE
    assert model.zero.impedance.value_pu == pytest.approx(expected)


def test_synchronous_generator_blocks_zero_sequence_for_ungrounded_neutral() -> None:
    terminal = _terminal()
    generator = SynchronousGenerator(
        id=terminal.equipment_id,
        name="GEN-UNGROUNDED",
        terminal=terminal,
        frequency=Frequency(60),
        sequence_impedances=_machine_impedances(),
        neutral_grounding=NeutralGrounding.ungrounded(),
    )
    model = generator.build_source_equivalent(
        ElectricalImpedanceBase(100, 13.8), SourceOperatingRegime.SUBTRANSIENT
    )
    assert model.zero.status is SourceSequenceStatus.BLOCKED


def test_synchronous_generator_blocks_zero_sequence_for_delta_stator() -> None:
    terminal = _terminal()
    generator = SynchronousGenerator(
        id=terminal.equipment_id,
        name="GEN-DELTA",
        terminal=terminal,
        frequency=Frequency(60),
        sequence_impedances=_machine_impedances(),
        neutral_grounding=NeutralGrounding.ungrounded(),
        stator_connection=WindingConnection.DELTA,
    )
    model = generator.build_source_equivalent(
        ElectricalImpedanceBase(100, 13.8), SourceOperatingRegime.SUBTRANSIENT
    )
    assert model.zero.status is SourceSequenceStatus.BLOCKED


def test_synchronous_generator_rejects_grounded_delta_stator() -> None:
    terminal = _terminal()
    with pytest.raises(ValueError, match="delta stator"):
        SynchronousGenerator(
            id=terminal.equipment_id,
            name="INVALID-GEN",
            terminal=terminal,
            frequency=Frequency(60),
            sequence_impedances=_machine_impedances(),
            neutral_grounding=NeutralGrounding.solid(),
            stator_connection=WindingConnection.DELTA,
        )


def test_synchronous_generator_requires_machine_base_voltage_to_match_terminal() -> None:
    terminal = _terminal(13.8)
    bad_data = SynchronousMachineSequenceImpedances(
        base=ElectricalImpedanceBase(100, 11.0),
        positive_subtransient=PerUnitImpedance(0.01, 0.2),
        positive_transient=PerUnitImpedance(0.02, 0.3),
        positive_synchronous=PerUnitImpedance(0.03, 1.5),
        negative=PerUnitImpedance(0.01, 0.18),
        zero=PerUnitImpedance(0.02, 0.1),
    )
    with pytest.raises(ValueError, match="base voltage must match"):
        SynchronousGenerator(
            id=terminal.equipment_id,
            name="BAD-BASE",
            terminal=terminal,
            frequency=Frequency(60),
            sequence_impedances=bad_data,
            neutral_grounding=NeutralGrounding.solid(),
        )


def test_induction_generator_exposes_only_initial_regime() -> None:
    terminal = _terminal()
    generator = InductionGenerator(
        id=terminal.equipment_id,
        name="IND-GEN",
        terminal=terminal,
        frequency=Frequency(60),
        parameters=_induction_parameters(),
        neutral_grounding=NeutralGrounding.solid(),
    )
    base = ElectricalImpedanceBase(100, 13.8)
    model = generator.build_source_equivalent(base, SourceOperatingRegime.SUBTRANSIENT)
    assert model.positive.internal_voltage_pu == pytest.approx(0.97 - 0.02j)
    assert model.positive.impedance.value_pu == pytest.approx(0.1 + 1.1j)


@pytest.mark.parametrize(
    "regime", [SourceOperatingRegime.TRANSIENT, SourceOperatingRegime.SYNCHRONOUS]
)
def test_induction_generator_rejects_unsupported_regimes(regime) -> None:
    terminal = _terminal()
    generator = InductionGenerator(
        id=terminal.equipment_id,
        name="IND-GEN",
        terminal=terminal,
        frequency=Frequency(60),
        parameters=_induction_parameters(),
        neutral_grounding=NeutralGrounding.solid(),
    )
    with pytest.raises(UnsupportedSourceOperatingRegimeError):
        generator.build_source_equivalent(ElectricalImpedanceBase(100, 13.8), regime)


def test_induction_generator_zero_sequence_includes_neutral_grounding() -> None:
    terminal = _terminal()
    generator = InductionGenerator(
        id=terminal.equipment_id,
        name="IND-GEN-GROUNDED",
        terminal=terminal,
        frequency=Frequency(60),
        parameters=_induction_parameters(),
        neutral_grounding=NeutralGrounding.solid(),
    )
    base = ElectricalImpedanceBase(100, 13.8)
    model = generator.build_source_equivalent(base, SourceOperatingRegime.SUBTRANSIENT)
    assert model.zero.impedance.value_pu == pytest.approx(0.2 + 0.6j)


def test_induction_generator_zero_sequence_blocked_when_ungrounded() -> None:
    terminal = _terminal()
    generator = InductionGenerator(
        id=terminal.equipment_id,
        name="IND-GEN-UNGROUNDED",
        terminal=terminal,
        frequency=Frequency(60),
        parameters=_induction_parameters(),
        neutral_grounding=NeutralGrounding.ungrounded(),
    )
    model = generator.build_source_equivalent(
        ElectricalImpedanceBase(100, 13.8), SourceOperatingRegime.SUBTRANSIENT
    )
    assert model.zero.status is SourceSequenceStatus.BLOCKED


def test_explicit_equivalent_source_converts_to_requested_base() -> None:
    terminal = _terminal()
    original_base = ElectricalImpedanceBase(100, 13.8)
    equivalent = SourceEquivalentSet(
        base=original_base,
        positive=SourceSequenceEquivalent(
            SequenceType.POSITIVE,
            SourceSequenceStatus.AVAILABLE,
            PerUnitImpedance(0.01, 0.2),
            0.99 + 0.01j,
        ),
        negative=SourceSequenceEquivalent(
            SequenceType.NEGATIVE,
            SourceSequenceStatus.AVAILABLE,
            PerUnitImpedance(0.02, 0.18),
        ),
        zero=SourceSequenceEquivalent.unspecified(SequenceType.ZERO),
    )
    source = EquivalentSource(
        id=terminal.equipment_id,
        name="EQUIVALENT-SOURCE",
        terminal=terminal,
        frequency=Frequency(60),
        equivalent=equivalent,
    )
    result = source.build_source_equivalent(
        ElectricalImpedanceBase(50, 13.8), SourceOperatingRegime.TRANSIENT
    )
    assert result.positive.impedance.value_pu == pytest.approx(0.005 + 0.1j)
    assert result.zero.status is SourceSequenceStatus.UNSPECIFIED
    assert result.positive.internal_voltage_pu == pytest.approx(0.99 + 0.01j)


def test_converter_based_generator_exposes_current_capability_not_thevenin_model() -> None:
    terminal = _terminal()
    converter = ConverterBasedGenerator(
        id=terminal.equipment_id,
        name="PV-INVERTER",
        terminal=terminal,
        frequency=Frequency(60),
        control_mode=ConverterControlMode.GRID_FOLLOWING,
        current_priority=ConverterCurrentPriority.REACTIVE,
        fault_current_capability=ConverterFaultCurrentCapability(
            base=ElectricalImpedanceBase(10.0, 13.8),
            overall_current_limit_pu=1.2,
            positive_sequence_limit_pu=1.2,
            negative_sequence_limit_pu=0.2,
            zero_sequence_limit_pu=0.0,
        ),
    )
    assert isinstance(converter, FaultCurrentCapabilityProvider)
    assert not isinstance(converter, SourceModelProvider)
    assert converter.family is EquipmentFamily.CONVERTER
    assert converter.fault_current_capability.zero_sequence_limit_pu == 0.0


def test_all_thevenin_sources_satisfy_source_model_protocol() -> None:
    terminal_1 = _terminal()
    grid = ExternalGrid(
        id=terminal_1.equipment_id,
        name="GRID",
        terminal=terminal_1,
        frequency=Frequency(60),
        short_circuit_data=ExternalGridShortCircuitData(100, 0.1),
    )
    terminal_2 = _terminal()
    generator = SynchronousGenerator(
        id=terminal_2.equipment_id,
        name="SG",
        terminal=terminal_2,
        frequency=Frequency(60),
        sequence_impedances=_machine_impedances(),
        neutral_grounding=NeutralGrounding.solid(),
    )
    assert isinstance(grid, SourceModelProvider)
    assert isinstance(generator, SourceModelProvider)


def test_source_models_can_be_registered_in_network() -> None:
    terminal = _terminal()
    generator = SynchronousGenerator(
        id=terminal.equipment_id,
        name="GEN",
        terminal=terminal,
        frequency=Frequency(60),
        sequence_impedances=_machine_impedances(),
        neutral_grounding=NeutralGrounding.solid(),
    )
    network = Network("GENERATOR NETWORK")
    bus = Bus("BUS-GEN", Voltage.from_kv(13.8))
    network.add_bus(bus)
    network.add_equipment(generator)
    network.connect(terminal.id, bus.id)
    assert network.get_equipment(generator.id) is generator


def test_source_base_must_be_validated_before_model_build() -> None:
    terminal = _terminal()
    grid = ExternalGrid(
        id=terminal.equipment_id,
        name="GRID",
        terminal=terminal,
        frequency=Frequency(60),
        short_circuit_data=ExternalGridShortCircuitData(100, 0.1),
    )
    with pytest.raises(TypeError, match="ElectricalImpedanceBase"):
        grid.build_source_equivalent(object(), SourceOperatingRegime.SUBTRANSIENT)


def test_external_grid_scales_prefault_voltage_to_requested_voltage_base() -> None:
    terminal = _terminal(13.8)
    grid = ExternalGrid(
        id=terminal.equipment_id,
        name="GRID-VBASE",
        terminal=terminal,
        frequency=Frequency(60),
        short_circuit_data=ExternalGridShortCircuitData(100, 0.1, prefault_voltage_pu=1.02),
    )
    model = grid.build_source_equivalent(
        ElectricalImpedanceBase(100, 6.9), SourceOperatingRegime.SUBTRANSIENT
    )
    assert model.positive.internal_voltage_pu == pytest.approx(2.04 + 0j)


def test_converter_based_generator_rejects_current_base_voltage_mismatch() -> None:
    terminal = _terminal(13.8)
    with pytest.raises(ValueError, match="current base voltage"):
        ConverterBasedGenerator(
            id=terminal.equipment_id,
            name="BAD-CONVERTER-BASE",
            terminal=terminal,
            frequency=Frequency(60),
            control_mode=ConverterControlMode.GRID_FOLLOWING,
            current_priority=ConverterCurrentPriority.REACTIVE,
            fault_current_capability=ConverterFaultCurrentCapability(
                base=ElectricalImpedanceBase(10.0, 0.4),
                overall_current_limit_pu=1.2,
                positive_sequence_limit_pu=1.2,
            ),
        )
