"""Analytical tests for the supported IEC 60909 network-feeder subset."""

from __future__ import annotations

import math
from dataclasses import replace
from uuid import uuid4

import pytest

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.iec60909 import (
    IEC60909CurrentCase,
    IEC60909LowVoltageTolerance,
)
from power_fault_analyzer.domain.enums.sequence_equipment_kind import SequenceEquipmentKind
from power_fault_analyzer.domain.enums.sequence_source_kind import SequenceSourceKind
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.fault_specification import FaultSpecification
from power_fault_analyzer.domain.value_objects.iec60909_study import (
    IEC60909StudySpecification,
)
from power_fault_analyzer.infrastructure.numerical.iec60909 import (
    IEC60909CalculationError,
    IEC60909Calculator,
)
from power_fault_analyzer.network.sequence_networks.models import (
    SequenceBranch,
    SequenceNetwork,
    SequenceNetworkSet,
    SequenceNode,
    SequenceShunt,
    SystemBaseSet,
)


@pytest.fixture
def feeder_study():
    bus_id = uuid4()
    network_id = uuid4()
    source_id = uuid4()
    impedances = {
        SequenceType.POSITIVE: 0.08 + 0.24j,
        SequenceType.NEGATIVE: 0.11 + 0.31j,
        SequenceType.ZERO: 0.18 + 0.52j,
    }
    models = {}
    for sequence in SequenceType:
        source = SequenceShunt(
            id=source_id,
            name=f"GRID-{sequence.value}",
            node_id=bus_id,
            admittance_pu=1.0 / impedances[sequence],
            source_voltage_pu=1.0 if sequence is SequenceType.POSITIVE else 0.0j,
            source_kind=SequenceSourceKind.NETWORK_FEEDER,
        )
        models[sequence] = SequenceNetwork(
            network_id=network_id,
            sequence=sequence,
            nodes=(SequenceNode(bus_id, "GRID-BUS"),),
            branches=(),
            shunts=(source,),
        )
    networks = SequenceNetworkSet(
        positive=models[SequenceType.POSITIVE],
        negative=models[SequenceType.NEGATIVE],
        zero=models[SequenceType.ZERO],
    )
    system_base = SystemBaseSet(100.0, {bus_id: 13.8})
    return bus_id, impedances, networks, system_base


def make_study(
    current_case=IEC60909CurrentCase.MAXIMUM,
    **kwargs,
):
    kwargs.setdefault("frequency_hz", 50.0)
    return IEC60909StudySpecification(
        current_case=current_case,
        fault_duration_s=1.0,
        **kwargs,
    )


@pytest.mark.parametrize("invalid_time", [0.0, -0.01, float("nan"), True])
def test_study_rejects_invalid_first_pole_contact_separation_time(invalid_time):
    with pytest.raises((TypeError, ValueError), match="first_pole_contact_separation_time_s"):
        make_study(first_pole_contact_separation_time_s=invalid_time)


def test_study_requires_explicit_system_frequency():
    with pytest.raises(TypeError, match="frequency_hz"):
        IEC60909StudySpecification(
            current_case=IEC60909CurrentCase.MAXIMUM,
            fault_duration_s=1.0,
        )


def test_voltage_factors_follow_selected_lv_tolerance_and_hv_values():
    lv6 = make_study(low_voltage_tolerance=IEC60909LowVoltageTolerance.PERCENT_6)
    lv10 = make_study(low_voltage_tolerance=IEC60909LowVoltageTolerance.PERCENT_10)
    minimum = make_study(
        IEC60909CurrentCase.MINIMUM,
        low_voltage_tolerance=IEC60909LowVoltageTolerance.PERCENT_6,
    )

    assert lv6.voltage_factor(0.4) == pytest.approx(1.05)
    assert lv10.voltage_factor(0.4) == pytest.approx(1.10)
    assert minimum.voltage_factor(0.4) == pytest.approx(0.95)
    assert minimum.voltage_factor(13.8) == pytest.approx(1.00)
    assert lv6.voltage_factor(13.8) == pytest.approx(1.10)


def test_maximum_voltage_factor_remains_cmax_for_minimum_transformer_correction():
    minimum = make_study(
        IEC60909CurrentCase.MINIMUM,
        low_voltage_tolerance=IEC60909LowVoltageTolerance.PERCENT_6,
    )

    assert minimum.voltage_factor(0.4) == pytest.approx(0.95)
    assert minimum.maximum_voltage_factor(0.4) == pytest.approx(1.05)


def test_voltage_factor_rejects_unsupported_voltage_and_excess_equipment_voltage():
    study = make_study(equipment_max_voltage_kv=15.0)
    with pytest.raises(ValueError, match="exceeds equipment_max_voltage_kv"):
        study.voltage_factor(13.8)
    with pytest.raises(ValueError, match="not defined"):
        study.voltage_factor(500.0)


def test_three_phase_maximum_case_calculates_initial_peak_and_thermal_currents(feeder_study):
    bus_id, impedances, networks, base = feeder_study
    study = make_study()
    fault = FaultSpecification(FaultType.THREE_PHASE, bus_id)

    result = IEC60909Calculator().calculate(networks, fault, base, study)

    expected_initial_pu = 1.10 / abs(impedances[SequenceType.POSITIVE])
    expected_initial_ka = expected_initial_pu * base.for_bus(bus_id).base_current_ka
    expected_kappa = 1.02 + 0.98 * math.exp(
        -3.0 * impedances[SequenceType.POSITIVE].real / impedances[SequenceType.POSITIVE].imag
    )
    logarithm = math.log(expected_kappa - 1.0)
    expected_m = math.expm1(4.0 * 50.0 * logarithm) / (2.0 * 50.0 * logarithm)

    assert result.standard_edition == "IEC 60909-0:2026"
    assert result.voltage_factor == pytest.approx(1.10)
    assert result.initial_symmetrical_current_ka == pytest.approx(expected_initial_ka)
    assert result.peak_current_factor == pytest.approx(expected_kappa)
    assert result.peak_current_ka == pytest.approx(
        expected_kappa * math.sqrt(2.0) * expected_initial_ka
    )
    assert result.breaking_current_ka == pytest.approx(expected_initial_ka)
    assert result.steady_state_current_ka == pytest.approx(expected_initial_ka)
    assert result.thermal_factor_dc == pytest.approx(expected_m)
    assert result.thermal_factor_ac == pytest.approx(1.0)
    assert result.thermal_equivalent_current_ka == pytest.approx(
        expected_initial_ka * math.sqrt(expected_m + 1.0)
    )
    assert result.joule_integral_ka2s == pytest.approx(
        expected_initial_ka**2 * (expected_m + 1.0) * study.fault_duration_s
    )
    assert result.current_method_references["I''k"].endswith(
        "/7.2/three-phase/initial-symmetrical-current"
    )
    assert result.current_method_references["ip"].endswith(
        "/8.1/single-fed-three-phase-radial-network-feeder"
    )
    assert result.current_method_references["Ib"].endswith("/9.1.5/network-feeder-contribution")
    assert result.current_method_references["Ik"].endswith("/11.2.5/network-feeder-contribution")
    assert "iDC" in result.unavailable_quantity_reasons
    assert "Ibasym" in result.unavailable_quantity_reasons


def test_minimum_case_uses_cmin_and_does_not_report_peak_or_thermal(feeder_study):
    bus_id, impedances, networks, base = feeder_study
    study = make_study(IEC60909CurrentCase.MINIMUM)
    result = IEC60909Calculator().calculate(
        networks,
        FaultSpecification(FaultType.THREE_PHASE, bus_id),
        base,
        study,
    )

    expected = base.for_bus(bus_id).base_current_ka / abs(impedances[SequenceType.POSITIVE])
    assert result.voltage_factor == pytest.approx(1.0)
    assert result.initial_symmetrical_current_ka == pytest.approx(expected)
    assert result.peak_current_ka is None
    assert result.thermal_equivalent_current_ka is None


def test_unbalanced_bolted_fault_uses_required_sequence_networks_only(feeder_study):
    bus_id, impedances, networks, base = feeder_study
    study = make_study()
    result = IEC60909Calculator().calculate(
        networks,
        FaultSpecification(FaultType.LINE_TO_LINE, bus_id),
        base,
        study,
    )
    expected_sequence_current = 1.10 / abs(
        impedances[SequenceType.POSITIVE] + impedances[SequenceType.NEGATIVE]
    )
    expected_phase_current = math.sqrt(3.0) * expected_sequence_current
    assert result.initial_symmetrical_current_ka == pytest.approx(
        expected_phase_current * base.for_bus(bus_id).base_current_ka
    )
    assert result.peak_current_ka is None
    assert result.thermal_equivalent_current_ka is None
    assert result.breaking_current_ka == pytest.approx(result.initial_symmetrical_current_ka)
    assert result.steady_state_current_ka == pytest.approx(result.initial_symmetrical_current_ka)
    assert result.current_method_references["Ib"].endswith(
        "/9.3/unbalanced-network-feeder-contributions"
    )
    assert result.current_method_references["Ik"].endswith(
        "/11.3/unbalanced-network-feeder-contributions"
    )
    assert "iDC" in result.unavailable_quantity_reasons
    assert "Ibasym" in result.unavailable_quantity_reasons


def test_single_fed_unbalanced_fault_calculates_breaking_and_steady_state_for_feeder(feeder_study):
    bus_id, _, networks, base = feeder_study
    result = IEC60909Calculator().calculate(
        networks,
        FaultSpecification(FaultType.SINGLE_LINE_TO_GROUND, bus_id),
        base,
        make_study(),
    )

    assert result.breaking_current_ka == pytest.approx(result.initial_symmetrical_current_ka)
    assert result.steady_state_current_ka == pytest.approx(result.initial_symmetrical_current_ka)
    assert result.current_method_references["Ib"].endswith(
        "/9.3/unbalanced-network-feeder-contributions"
    )
    assert result.current_method_references["Ik"].endswith(
        "/11.3/unbalanced-network-feeder-contributions"
    )


def test_clause_10_dc_and_asymmetrical_breaking_for_single_fed_radial_feeder(feeder_study):
    bus_id, impedances, networks, base = feeder_study
    separation_time = 0.08
    study = make_study(first_pole_contact_separation_time_s=separation_time)
    result = IEC60909Calculator().calculate(
        networks,
        FaultSpecification(FaultType.THREE_PHASE, bus_id),
        base,
        study,
    )
    ratio = impedances[SequenceType.POSITIVE].real / impedances[SequenceType.POSITIVE].imag
    expected_dc = (
        math.sqrt(2.0)
        * result.initial_symmetrical_current_ka
        * math.exp(-2.0 * math.pi * study.frequency_hz * separation_time * ratio)
    )
    assert result.dc_component_at_separation_ka == pytest.approx(expected_dc)
    assert result.asymmetrical_breaking_current_ka == pytest.approx(
        math.hypot(result.breaking_current_ka, expected_dc)
    )
    assert result.current_method_references["iDC_supplement"] == (
        "PFA-ENGINEERING/RX-DC-DECAY/single-fed-three-phase-network-feeder/v1"
    )
    assert (
        result.current_method_references["Ibasym_supplement"]
        == (result.current_method_references["iDC_supplement"])
    )
    assert "iDC" in result.unavailable_quantity_reasons
    assert "Ibasym" in result.unavailable_quantity_reasons
    assert "conformity has not been established" in result.unavailable_quantity_reasons["iDC"]


def test_clause_10_dc_is_unavailable_without_opening_time_or_outside_supported_scope(
    feeder_study,
):
    bus_id, _, networks, base = feeder_study
    default_study = make_study()
    result = IEC60909Calculator().calculate(
        networks, FaultSpecification(FaultType.THREE_PHASE, bus_id), base, default_study
    )
    assert result.dc_component_at_separation_ka is None
    assert result.asymmetrical_breaking_current_ka is None
    assert "iDC" in result.unavailable_quantity_reasons

    unbalanced = IEC60909Calculator().calculate(
        networks,
        FaultSpecification(FaultType.LINE_TO_LINE, bus_id),
        base,
        make_study(first_pole_contact_separation_time_s=0.08),
    )
    assert unbalanced.dc_component_at_separation_ka is None
    assert unbalanced.asymmetrical_breaking_current_ka is None
    assert "outside the restricted Clause 10" in unbalanced.unavailable_quantity_reasons["iDC"]


def test_rejects_non_bolted_fault(feeder_study):
    bus_id, _, networks, base = feeder_study
    with pytest.raises(IEC60909CalculationError, match="bolted faults only"):
        IEC60909Calculator().calculate(
            networks,
            FaultSpecification(FaultType.THREE_PHASE, bus_id, 0.01 + 0.0j),
            base,
            make_study(),
        )


def test_multiple_positive_sequence_feeders_report_network_feeder_breaking_and_steady_state(
    feeder_study,
):
    bus_id, _, networks, base = feeder_study
    positive = networks.positive
    extra = SequenceShunt(
        id=uuid4(),
        name="SECOND-GRID",
        node_id=bus_id,
        admittance_pu=1.0 - 2.0j,
        source_voltage_pu=1.0 + 0.0j,
        source_kind=SequenceSourceKind.NETWORK_FEEDER,
    )
    modified = SequenceNetworkSet(
        positive=SequenceNetwork(
            network_id=positive.network_id,
            sequence=SequenceType.POSITIVE,
            nodes=positive.nodes,
            branches=positive.branches,
            shunts=positive.shunts + (extra,),
        ),
        negative=networks.negative,
        zero=networks.zero,
    )
    result = IEC60909Calculator().calculate(
        modified,
        FaultSpecification(FaultType.THREE_PHASE, bus_id),
        base,
        make_study(),
    )
    assert result.initial_symmetrical_current_ka > 0.0
    assert result.peak_current_ka is None
    assert result.breaking_current_ka == pytest.approx(result.initial_symmetrical_current_ka)
    assert result.steady_state_current_ka == pytest.approx(result.initial_symmetrical_current_ka)
    assert result.thermal_equivalent_current_ka is None
    assert result.current_method_references["Ib"].endswith("/9.2/network-feeder-contribution")
    assert result.current_method_references["Ik"].endswith("/11.2.6/network-feeder-contribution")
    assert "ip" in result.unavailable_quantity_reasons
    assert any(item.code == "IEC60909-PEAK-NOT-EVALUATED" for item in result.diagnostics)
    with pytest.raises(IEC60909CalculationError, match="negative-sequence network must contain"):
        IEC60909Calculator().calculate(
            modified,
            FaultSpecification(FaultType.LINE_TO_LINE, bus_id),
            base,
            make_study(),
        )


def test_rejects_generic_thevenin_source(feeder_study):
    bus_id, _, networks, base = feeder_study
    positive = networks.positive
    source = positive.shunts[0]
    replacement = SequenceShunt(
        id=source.id,
        name=source.name,
        node_id=source.node_id,
        admittance_pu=source.admittance_pu,
        source_voltage_pu=source.source_voltage_pu,
        source_kind=SequenceSourceKind.EXPLICIT_THEVENIN,
    )
    modified = SequenceNetworkSet(
        positive=SequenceNetwork(
            network_id=positive.network_id,
            sequence=SequenceType.POSITIVE,
            nodes=positive.nodes,
            branches=positive.branches,
            shunts=(replacement,),
        ),
        negative=networks.negative,
        zero=networks.zero,
    )
    with pytest.raises(IEC60909CalculationError, match="Only ExternalGrid"):
        IEC60909Calculator().calculate(
            modified,
            FaultSpecification(FaultType.THREE_PHASE, bus_id),
            base,
            make_study(),
        )


def test_iec_method_omits_positive_sequence_line_shunt_admittances(feeder_study):
    bus_id, impedances, networks, _base = feeder_study
    remote_bus = uuid4()
    line = SequenceBranch(
        id=uuid4(),
        name="LINE-WITH-PI-SHUNTS",
        from_node_id=bus_id,
        to_node_id=remote_bus,
        series_impedance_pu=0.02 + 0.04j,
        shunt_admittance_from_pu=0.7 + 0.9j,
        shunt_admittance_to_pu=0.7 + 0.9j,
        length_km=5.0,
        equipment_kind=SequenceEquipmentKind.LINE,
    )

    def with_line(model):
        return SequenceNetwork(
            network_id=model.network_id,
            sequence=model.sequence,
            nodes=model.nodes + (SequenceNode(remote_bus, "REMOTE"),),
            branches=(line,),
            shunts=model.shunts,
        )

    line_networks = SequenceNetworkSet(
        with_line(networks.positive),
        with_line(networks.negative),
        with_line(networks.zero),
    )
    base = SystemBaseSet(100.0, {bus_id: 13.8, remote_bus: 13.8})
    result = IEC60909Calculator().calculate(
        line_networks,
        FaultSpecification(FaultType.THREE_PHASE, remote_bus),
        base,
        make_study(),
    )

    assert result.base_result.driving_point_impedances_pu[SequenceType.POSITIVE] == pytest.approx(
        impedances[SequenceType.POSITIVE] + line.series_impedance_pu
    )
    assert any(
        item.code == "IEC60909-POSITIVE-NEGATIVE-SHUNTS-NEGLECTED" for item in result.diagnostics
    )


def test_minimum_case_requires_line_resistance_temperature_factor(feeder_study):
    bus_id, _, networks, _base = feeder_study
    positive = networks.positive
    remote_bus = uuid4()
    line = SequenceBranch(
        id=uuid4(),
        name="LINE",
        from_node_id=bus_id,
        to_node_id=remote_bus,
        series_impedance_pu=0.01 + 0.02j,
        length_km=10.0,
        equipment_kind=SequenceEquipmentKind.LINE,
    )
    positive_with_line = SequenceNetwork(
        network_id=positive.network_id,
        sequence=SequenceType.POSITIVE,
        nodes=positive.nodes + (SequenceNode(remote_bus, "REMOTE"),),
        branches=(line,),
        shunts=positive.shunts,
    )
    negative = SequenceNetwork(
        network_id=positive.network_id,
        sequence=SequenceType.NEGATIVE,
        nodes=positive_with_line.nodes,
        branches=(line,),
        shunts=networks.negative.shunts,
    )
    zero = SequenceNetwork(
        network_id=positive.network_id,
        sequence=SequenceType.ZERO,
        nodes=positive_with_line.nodes,
        branches=(line,),
        shunts=networks.zero.shunts,
    )
    line_networks = SequenceNetworkSet(positive_with_line, negative, zero)
    with pytest.raises(IEC60909CalculationError, match="minimum_line_resistance_factor"):
        IEC60909Calculator().calculate(
            line_networks,
            FaultSpecification(FaultType.THREE_PHASE, remote_bus),
            SystemBaseSet(100.0, {bus_id: 13.8, remote_bus: 13.8}),
            make_study(IEC60909CurrentCase.MINIMUM),
        )


def test_minimum_case_multiplies_line_resistance_only(feeder_study):
    bus_id, impedances, networks, _base = feeder_study
    remote_bus = uuid4()
    line_z = 0.01 + 0.02j
    line = SequenceBranch(
        id=uuid4(),
        name="FEEDER-LINE",
        from_node_id=bus_id,
        to_node_id=remote_bus,
        series_impedance_pu=line_z,
        length_km=10.0,
        equipment_kind=SequenceEquipmentKind.LINE,
    )

    def with_line(model):
        return SequenceNetwork(
            network_id=model.network_id,
            sequence=model.sequence,
            nodes=model.nodes + (SequenceNode(remote_bus, "REMOTE"),),
            branches=(line,),
            shunts=model.shunts,
        )

    networks_with_line = SequenceNetworkSet(
        with_line(networks.positive),
        with_line(networks.negative),
        with_line(networks.zero),
    )
    base_with_remote = SystemBaseSet(100.0, {bus_id: 13.8, remote_bus: 13.8})
    result = IEC60909Calculator().calculate(
        networks_with_line,
        FaultSpecification(FaultType.THREE_PHASE, remote_bus),
        base_with_remote,
        make_study(
            IEC60909CurrentCase.MINIMUM,
            minimum_line_resistance_factor=2.5,
        ),
    )
    expected_z = impedances[SequenceType.POSITIVE] + complex(line_z.real * 2.5, line_z.imag)
    assert result.base_result.driving_point_impedances_pu[SequenceType.POSITIVE] == pytest.approx(
        expected_z
    )


def test_minimum_unbalanced_line_study_requires_distinct_zero_sequence_factor(feeder_study):
    bus_id, _, networks, _base = feeder_study
    remote_bus = uuid4()
    line = SequenceBranch(
        id=uuid4(),
        name="LINE-ZERO-RETURN",
        from_node_id=bus_id,
        to_node_id=remote_bus,
        series_impedance_pu=0.01 + 0.02j,
        length_km=10.0,
        equipment_kind=SequenceEquipmentKind.LINE,
    )

    def with_line(model):
        return SequenceNetwork(
            network_id=model.network_id,
            sequence=model.sequence,
            nodes=model.nodes + (SequenceNode(remote_bus, "REMOTE"),),
            branches=(line,),
            shunts=model.shunts,
        )

    line_networks = SequenceNetworkSet(
        with_line(networks.positive),
        with_line(networks.negative),
        with_line(networks.zero),
    )
    base = SystemBaseSet(100.0, {bus_id: 13.8, remote_bus: 13.8})
    fault = FaultSpecification(FaultType.SINGLE_LINE_TO_GROUND, remote_bus)
    study = make_study(
        IEC60909CurrentCase.MINIMUM,
        minimum_line_resistance_factor=2.0,
    )

    with pytest.raises(
        IEC60909CalculationError,
        match="minimum_zero_sequence_line_resistance_factor",
    ):
        IEC60909Calculator().calculate(line_networks, fault, base, study)


def test_minimum_unbalanced_line_study_scales_zero_sequence_resistance_separately(
    feeder_study,
):
    bus_id, impedances, networks, _base = feeder_study
    remote_bus = uuid4()
    line = SequenceBranch(
        id=uuid4(),
        name="LINE-ZERO-RETURN",
        from_node_id=bus_id,
        to_node_id=remote_bus,
        series_impedance_pu=0.01 + 0.02j,
        length_km=10.0,
        equipment_kind=SequenceEquipmentKind.LINE,
    )

    def with_line(model):
        return SequenceNetwork(
            network_id=model.network_id,
            sequence=model.sequence,
            nodes=model.nodes + (SequenceNode(remote_bus, "REMOTE"),),
            branches=(line,),
            shunts=model.shunts,
        )

    line_networks = SequenceNetworkSet(
        with_line(networks.positive),
        with_line(networks.negative),
        with_line(networks.zero),
    )
    base = SystemBaseSet(100.0, {bus_id: 13.8, remote_bus: 13.8})
    study = make_study(
        IEC60909CurrentCase.MINIMUM,
        minimum_line_resistance_factor=2.0,
        minimum_zero_sequence_line_resistance_factor=3.0,
    )
    result = IEC60909Calculator().calculate(
        line_networks,
        FaultSpecification(FaultType.SINGLE_LINE_TO_GROUND, remote_bus),
        base,
        study,
    )

    assert result.base_result.driving_point_impedances_pu[SequenceType.POSITIVE] == pytest.approx(
        impedances[SequenceType.POSITIVE] + 0.02 + 0.02j
    )
    assert result.base_result.driving_point_impedances_pu[SequenceType.NEGATIVE] == pytest.approx(
        impedances[SequenceType.NEGATIVE] + 0.02 + 0.02j
    )
    assert result.base_result.driving_point_impedances_pu[SequenceType.ZERO] == pytest.approx(
        impedances[SequenceType.ZERO] + 0.03 + 0.02j
    )


def test_three_phase_fault_ignores_unsupported_transformer_in_unused_zero_sequence(
    feeder_study,
):
    bus_id, _, networks, base = feeder_study
    zero = networks.zero
    other_bus = uuid4()
    unsupported = SequenceBranch(
        id=uuid4(),
        name="TR3-ZERO-ONLY",
        from_node_id=bus_id,
        to_node_id=other_bus,
        series_impedance_pu=0.01 + 0.1j,
        equipment_kind=SequenceEquipmentKind.THREE_WINDING_TRANSFORMER,
    )
    zero_with_transformer = SequenceNetwork(
        network_id=zero.network_id,
        sequence=SequenceType.ZERO,
        nodes=zero.nodes + (SequenceNode(other_bus, "OTHER"),),
        branches=(unsupported,),
        shunts=zero.shunts,
    )
    networks_with_unused_zero_transformer = SequenceNetworkSet(
        networks.positive,
        networks.negative,
        zero_with_transformer,
    )

    result = IEC60909Calculator().calculate(
        networks_with_unused_zero_transformer,
        FaultSpecification(FaultType.THREE_PHASE, bus_id),
        base,
        make_study(),
    )

    assert result.initial_symmetrical_current_ka > 0.0


def test_two_winding_transformer_correction_uses_cmax_in_minimum_case():
    network_id = uuid4()
    hv_bus = uuid4()
    lv_bus = uuid4()
    transformer_id = uuid4()
    source_z = 0.02 + 0.10j
    transformer_z = 0.01 + 0.08j
    transformer = SequenceBranch(
        id=transformer_id,
        name="TR-115-13.8",
        from_node_id=hv_bus,
        to_node_id=lv_bus,
        series_impedance_pu=transformer_z,
        equipment_kind=SequenceEquipmentKind.TWO_WINDING_TRANSFORMER,
        transformer_reactance_pu=0.08,
        transformer_correction_voltage_kv=13.8,
    )
    models = {}
    for sequence in SequenceType:
        shunts = ()
        if sequence is SequenceType.POSITIVE:
            shunts = (
                SequenceShunt(
                    id=uuid4(),
                    name="GRID",
                    node_id=hv_bus,
                    admittance_pu=1.0 / source_z,
                    source_kind=SequenceSourceKind.NETWORK_FEEDER,
                ),
            )
        models[sequence] = SequenceNetwork(
            network_id=network_id,
            sequence=sequence,
            nodes=(SequenceNode(hv_bus, "HV"), SequenceNode(lv_bus, "LV")),
            branches=(transformer,),
            shunts=shunts,
        )
    networks = SequenceNetworkSet(
        models[SequenceType.POSITIVE],
        models[SequenceType.NEGATIVE],
        models[SequenceType.ZERO],
    )
    base = SystemBaseSet(100.0, {hv_bus: 115.0, lv_bus: 13.8})
    study = make_study(IEC60909CurrentCase.MINIMUM)
    result = IEC60909Calculator().calculate(
        networks,
        FaultSpecification(FaultType.THREE_PHASE, lv_bus),
        base,
        study,
    )

    kt = 0.95 * 1.10 / (1.0 + 0.6 * 0.08)
    assert result.applied_transformer_correction_factors[str(transformer_id)] == pytest.approx(kt)
    assert result.base_result.driving_point_impedances_pu[SequenceType.POSITIVE] == pytest.approx(
        source_z + transformer_z * kt
    )


def test_rejects_three_winding_transformer_correction():
    network_id = uuid4()
    bus_a, bus_b, fault_bus = uuid4(), uuid4(), uuid4()
    branch = SequenceBranch(
        id=uuid4(),
        name="TR3-ARM",
        from_node_id=bus_a,
        to_node_id=fault_bus,
        series_impedance_pu=0.01 + 0.1j,
        equipment_kind=SequenceEquipmentKind.THREE_WINDING_TRANSFORMER,
    )
    shunt = SequenceShunt(
        id=uuid4(),
        name="GRID",
        node_id=bus_a,
        admittance_pu=1.0 / (0.01 + 0.1j),
        source_kind=SequenceSourceKind.NETWORK_FEEDER,
    )
    models = {
        sequence: SequenceNetwork(
            network_id=network_id,
            sequence=sequence,
            nodes=(
                SequenceNode(bus_a, "A"),
                SequenceNode(fault_bus, "F"),
                SequenceNode(bus_b, "B"),
            ),
            branches=(branch,),
            shunts=(shunt,) if sequence is SequenceType.POSITIVE else (),
        )
        for sequence in SequenceType
    }
    networks = SequenceNetworkSet(
        models[SequenceType.POSITIVE],
        models[SequenceType.NEGATIVE],
        models[SequenceType.ZERO],
    )
    with pytest.raises(IEC60909CalculationError, match="Three-winding transformer"):
        IEC60909Calculator().calculate(
            networks,
            FaultSpecification(FaultType.THREE_PHASE, fault_bus),
            SystemBaseSet(100.0, {bus_a: 115.0, bus_b: 13.8, fault_bus: 13.8}),
            make_study(),
        )


def test_meshed_component_does_not_use_radial_peak_factor(feeder_study):
    bus_id, _, networks, _base = feeder_study
    bus_b, bus_c = uuid4(), uuid4()
    positive = networks.positive
    nodes = positive.nodes + (SequenceNode(bus_b, "B"), SequenceNode(bus_c, "C"))
    branches = (
        SequenceBranch(uuid4(), "AB", bus_id, bus_b, 0.01 + 0.08j),
        SequenceBranch(uuid4(), "BC", bus_b, bus_c, 0.01 + 0.08j),
        SequenceBranch(uuid4(), "CA", bus_c, bus_id, 0.01 + 0.08j),
    )
    meshed_positive = SequenceNetwork(
        network_id=positive.network_id,
        sequence=SequenceType.POSITIVE,
        nodes=nodes,
        branches=branches,
        shunts=positive.shunts,
    )
    meshed = SequenceNetworkSet(meshed_positive, networks.negative, networks.zero)
    meshed_base = SystemBaseSet(
        100.0,
        {bus_id: 13.8, bus_b: 13.8, bus_c: 13.8},
    )

    result = IEC60909Calculator().calculate(
        meshed,
        FaultSpecification(FaultType.THREE_PHASE, bus_b),
        meshed_base,
        make_study(),
    )

    assert result.initial_symmetrical_current_ka > 0.0
    assert result.peak_current_factor is None
    assert result.peak_current_ka is None
    assert any(item.code == "IEC60909-PEAK-NOT-EVALUATED" for item in result.diagnostics)


def test_converter_source_is_rejected_for_this_network_feeder_subset(feeder_study):
    bus_id, _, networks, base = feeder_study
    positive = replace(networks.positive, nonlinear_source_ids=(uuid4(),))
    modified = SequenceNetworkSet(positive, networks.negative, networks.zero)

    with pytest.raises(IEC60909CalculationError, match="Converter current-source"):
        IEC60909Calculator().calculate(
            modified,
            FaultSpecification(FaultType.THREE_PHASE, bus_id),
            base,
            make_study(),
        )


def test_minimum_case_can_scale_the_declared_network_feeder_impedance(feeder_study):
    bus_id, impedances, networks, base = feeder_study
    result = IEC60909Calculator().calculate(
        networks,
        FaultSpecification(FaultType.THREE_PHASE, bus_id),
        base,
        make_study(
            IEC60909CurrentCase.MINIMUM,
            network_feeder_impedance_multiplier=1.5,
        ),
    )
    expected = 1.5 * impedances[SequenceType.POSITIVE]
    assert result.base_result.driving_point_impedances_pu[SequenceType.POSITIVE] == pytest.approx(
        expected
    )
    expected_current = base.for_bus(bus_id).base_current_ka / abs(expected)
    assert result.initial_symmetrical_current_ka == pytest.approx(expected_current)


def test_multi_feeder_calculates_initial_breaking_and_steady_currents(feeder_study):
    bus_id, impedances, networks, base = feeder_study
    second_id = uuid4()
    models = {}
    second_impedances = {
        SequenceType.POSITIVE: 0.12 + 0.30j,
        SequenceType.NEGATIVE: 0.15 + 0.36j,
        SequenceType.ZERO: 0.24 + 0.58j,
    }
    for sequence in SequenceType:
        model = networks.for_sequence(sequence)
        second_source = SequenceShunt(
            id=second_id,
            name=f"GRID-02-{sequence.value}",
            node_id=bus_id,
            admittance_pu=1.0 / second_impedances[sequence],
            source_voltage_pu=1.0 if sequence is SequenceType.POSITIVE else 0.0j,
            source_kind=SequenceSourceKind.NETWORK_FEEDER,
        )
        models[sequence] = replace(model, shunts=(*model.shunts, second_source))
    multi_networks = SequenceNetworkSet(
        positive=models[SequenceType.POSITIVE],
        negative=models[SequenceType.NEGATIVE],
        zero=models[SequenceType.ZERO],
    )

    result = IEC60909Calculator().calculate(
        multi_networks,
        FaultSpecification(FaultType.THREE_PHASE, bus_id),
        base,
        make_study(),
    )
    combined_impedance = 1.0 / (
        1.0 / impedances[SequenceType.POSITIVE] + 1.0 / second_impedances[SequenceType.POSITIVE]
    )
    expected_initial_ka = 1.10 / abs(combined_impedance) * base.for_bus(bus_id).base_current_ka

    assert result.initial_symmetrical_current_ka == pytest.approx(expected_initial_ka)
    assert result.peak_current_ka is None
    assert result.breaking_current_ka == pytest.approx(expected_initial_ka)
    assert result.steady_state_current_ka == pytest.approx(expected_initial_ka)
    assert result.current_method_references["Ib"].endswith("/9.2/network-feeder-contribution")
    assert result.current_method_references["Ik"].endswith("/11.2.6/network-feeder-contribution")
    assert result.current_method_references["I''k"].endswith(
        "/7.2/three-phase/initial-symmetrical-current"
    )
    assert result.thermal_equivalent_current_ka is None
    assert any(item.code == "IEC60909-PEAK-NOT-EVALUATED" for item in result.diagnostics)


def test_clause_10_opening_time_is_preserved_and_used_for_supported_case(feeder_study):
    bus_id, _, networks, base = feeder_study
    study = make_study(first_pole_contact_separation_time_s=0.075)

    result = IEC60909Calculator().calculate(
        networks,
        FaultSpecification(FaultType.THREE_PHASE, bus_id),
        base,
        study,
    )

    assert result.first_pole_contact_separation_time_s == pytest.approx(0.075)
    assert result.dc_component_at_separation_ka is not None
    assert result.asymmetrical_breaking_current_ka is not None
    assert "iDC" in result.unavailable_quantity_reasons
    assert "Ibasym" in result.unavailable_quantity_reasons
    assert "iDC_supplement" in result.current_method_references
    assert "Ibasym_supplement" in result.current_method_references


def test_clause_10_supplement_retains_zero_dc_after_numerical_decay(feeder_study):
    bus_id, _, networks, base = feeder_study
    result = IEC60909Calculator().calculate(
        networks,
        FaultSpecification(FaultType.THREE_PHASE, bus_id),
        base,
        make_study(first_pole_contact_separation_time_s=1000.0),
    )

    assert result.dc_component_at_separation_ka == 0.0
    assert result.asymmetrical_breaking_current_ka == pytest.approx(result.breaking_current_ka)
    assert "iDC" in result.unavailable_quantity_reasons
