from uuid import uuid4

import pytest

from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.advanced_protection import (
    DifferentialProtectionKind,
    DistanceCharacteristic,
)
from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.iec60909 import IEC60909CurrentCase
from power_fault_analyzer.domain.enums.protection import (
    CircuitBreakerStandard,
    IECInverseCurveType,
    ProtectionAssessmentStatus,
    ProtectionFunction,
)
from power_fault_analyzer.domain.enums.protection_network import (
    ProtectionFaultLocationKind,
    ProtectionRole,
)
from power_fault_analyzer.domain.value_objects.advanced_protection import (
    AdvancedProtectionFunctionBinding,
    AdvancedProtectionFunctionMeasurement,
    AdvancedProtectionScenarioMeasurements,
    CTExcitationPoint,
    CurrentTransformerPerformanceBinding,
    CurrentTransformerPerformanceModel,
    DifferentialMeasurement,
    DifferentialProtectionSettings,
    DifferentialSideSettings,
    DirectionalMeasurement,
    DirectionalOvercurrentSettings,
    DistanceMeasurement,
    DistanceProtectionSettings,
    DistanceZoneSettings,
    VoltageTransformerRatio,
)
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.iec60909_study import (
    IEC60909StudySpecification,
)
from power_fault_analyzer.domain.value_objects.impedance import Impedance
from power_fault_analyzer.domain.value_objects.line_fault_specification import (
    LineFaultSpecification,
)
from power_fault_analyzer.domain.value_objects.protection_devices import (
    CircuitBreaker,
    CurrentTransformerRatio,
    FuseLink,
    FuseTimeCurrentPoint,
    OvercurrentRelay,
)
from power_fault_analyzer.domain.value_objects.protection_network import (
    ProtectionBackupRelationship,
    ProtectionCurrentMeasurement,
    ProtectionDeviceBinding,
    ProtectionFaultScenario,
    ProtectionScenarioMeasurements,
    ProtectionZone,
)
from power_fault_analyzer.domain.value_objects.sequence_parameters import (
    AdmittancePerLength,
    ImpedancePerLength,
    SequenceAdmittancePerLengthSet,
    SequenceImpedancePerLengthSet,
)
from power_fault_analyzer.domain.value_objects.source_models import ExternalGridShortCircuitData
from power_fault_analyzer.domain.value_objects.voltage import Voltage
from power_fault_analyzer.equipment.sources.external_grid import ExternalGrid
from power_fault_analyzer.equipment.transmission.line import Line
from power_fault_analyzer.equipment.transmission.line_parameters import LineParameters
from power_fault_analyzer.infrastructure.numerical.line_fault import LineFaultSolver
from power_fault_analyzer.infrastructure.protection import (
    ProtectionFaultStudyRunner,
    ProtectionNetworkAnalyzer,
    ProtectionScenarioCatalog,
)
from power_fault_analyzer.infrastructure.protection.advanced import (
    AdvancedProtectionNetworkAnalyzer,
)
from power_fault_analyzer.network.protection import ProtectionNetworkBuilder
from power_fault_analyzer.network.sequence_networks.builder import SequenceNetworkBuilder
from power_fault_analyzer.network.sequence_networks.models import SystemBaseSet


def make_line_parameters():
    return LineParameters(
        series_impedance_per_km=SequenceImpedancePerLengthSet(
            positive=ImpedancePerLength(0.08, 0.35),
            negative=ImpedancePerLength(0.08, 0.35),
            zero=ImpedancePerLength(0.25, 1.0),
        ),
        shunt_admittance_per_km=SequenceAdmittancePerLengthSet(
            positive=AdmittancePerLength(1e-6, 3e-6),
            negative=AdmittancePerLength(1e-6, 3e-6),
            zero=AdmittancePerLength(0.4e-6, 1.5e-6),
        ),
        reference_frequency=Frequency(60.0),
    )


def build_feeder():
    network = Network("ND010 feeder")
    bus_a = Bus("BUS-A", Voltage.from_kv(13.8))
    bus_b = Bus("BUS-B", Voltage.from_kv(13.8))
    network.add_bus(bus_a)
    network.add_bus(bus_b)

    line_id = uuid4()
    terminals = (
        Terminal(line_id, "FROM", Voltage.from_kv(13.8)),
        Terminal(line_id, "TO", Voltage.from_kv(13.8)),
    )
    line = Line(
        id=line_id,
        name="LINE-AB",
        terminals=terminals,
        length_km=2.0,
        parameters=make_line_parameters(),
    )
    network.add_equipment(line)
    network.connect(terminals[0].id, bus_a.id)
    network.connect(terminals[1].id, bus_b.id)

    source_id = uuid4()
    source_terminal = Terminal(source_id, "GRID", Voltage.from_kv(13.8))
    source = ExternalGrid(
        id=source_id,
        name="GRID-01",
        terminal=source_terminal,
        frequency=Frequency(60.0),
        short_circuit_data=ExternalGridShortCircuitData(
            short_circuit_power_mva=2500.0,
            rx_ratio=0.1,
            negative_sequence_impedance_ohm=Impedance(0.002, 0.02),
            zero_sequence_impedance_ohm=Impedance(0.004, 0.04),
            prefault_voltage_pu=1.0 + 0.0j,
        ),
    )
    network.add_equipment(source)
    network.connect(source_terminal.id, bus_a.id)
    base = SystemBaseSet.from_network(network, 100.0)
    return network, bus_a, bus_b, line, terminals, base


def make_relay(name, *, pickup_secondary_a=1.0, tms=0.1, function=ProtectionFunction.PHASE):
    return OvercurrentRelay(
        id=uuid4(),
        name=name,
        current_transformer=CurrentTransformerRatio(600.0, 5.0),
        function=function,
        pickup_secondary_a=pickup_secondary_a,
        curve_type=IECInverseCurveType.STANDARD_INVERSE,
        time_multiplier=tms,
    )


def make_breaker(name="CB-13K8"):
    return CircuitBreaker(
        id=uuid4(),
        name=name,
        rated_voltage_kv=15.0,
        rated_current_a=630.0,
        standard=CircuitBreakerStandard.IEC_62271_100,
        rated_short_circuit_breaking_current_ka=25.0,
        opening_time_s=0.05,
        arcing_time_s=0.02,
    )


def test_protection_builder_resolves_ct_terminal_to_physical_bus():
    network, bus_a, _, line, terminals, _ = build_feeder()
    relay = make_relay("R-LINE-A")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone(
        name="LINE-AB ZONE",
        protected_element_ids=(line.id, bus_a.id),
        primary_device_ids=(relay.id,),
    )

    model = ProtectionNetworkBuilder().build(network, (binding,), (zone,))

    assert model.network_id == network.id
    assert model.binding_bus_ids[relay.id] == bus_a.id
    assert model.binding_equipment_names[relay.id] == line.name
    assert model.zones == (zone,)
    assert model.roles_by_device_id[relay.id] == (ProtectionRole.PRIMARY,)


def test_protection_builder_rejects_breaker_with_insufficient_voltage_rating():
    network, _, _, line, terminals, _ = build_feeder()
    relay = make_relay("R-LOW-VOLTAGE-CB")
    low_voltage_breaker = CircuitBreaker(
        id=uuid4(),
        name="CB-0K4",
        rated_voltage_kv=0.4,
        rated_current_a=630.0,
        standard=CircuitBreakerStandard.IEC_60947_2,
        ultimate_breaking_capacity_ka=25.0,
    )
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, low_voltage_breaker)
    zone = ProtectionZone("ZONE", (line.id,), (relay.id,))

    with pytest.raises(ValueError, match="voltage rating is below"):
        ProtectionNetworkBuilder().build(network, (binding,), (zone,))


def test_protection_builder_rejects_fuse_with_insufficient_voltage_rating():
    network, _, _, line, terminals, _ = build_feeder()
    fuse = FuseLink(
        id=uuid4(),
        name="FUSE-0K4",
        rated_current_a=200.0,
        rated_voltage_kv=0.4,
        breaking_capacity_ka=25.0,
        characteristic_points=(
            FuseTimeCurrentPoint(200.0, 10.0, 12.0),
            FuseTimeCurrentPoint(2000.0, 1.0, 1.2),
        ),
    )
    binding = ProtectionDeviceBinding(fuse, line.id, terminals[0].id)
    zone = ProtectionZone("ZONE", (line.id,), (fuse.id,))

    with pytest.raises(ValueError, match="Fuse .* voltage rating is below"):
        ProtectionNetworkBuilder().build(network, (binding,), (zone,))


def test_two_relays_can_share_one_physical_breaker():
    network, bus_a, _, line, terminals, _ = build_feeder()
    primary = make_relay("R-PRIMARY")
    backup = make_relay("R-BACKUP")
    shared_breaker = make_breaker()
    bindings = (
        ProtectionDeviceBinding(primary, line.id, terminals[0].id, shared_breaker),
        ProtectionDeviceBinding(backup, line.id, terminals[0].id, shared_breaker),
    )
    zone = ProtectionZone(
        "ZONE",
        (line.id, bus_a.id),
        (primary.id,),
        backup_device_ids=(backup.id,),
        backup_relationships=(ProtectionBackupRelationship(primary.id, backup.id, 0.2),),
    )

    model = ProtectionNetworkBuilder().build(network, bindings, (zone,))

    assert model.binding_by_device_id[primary.id].breaker is shared_breaker
    assert model.binding_by_device_id[backup.id].breaker is shared_breaker
    assert model.roles_by_device_id[primary.id] == (ProtectionRole.PRIMARY,)
    assert model.roles_by_device_id[backup.id] == (ProtectionRole.BACKUP,)


def test_protection_builder_rejects_terminal_from_another_equipment():
    network, _, _, line, _terminals, _ = build_feeder()
    relay = make_relay("R-BAD")
    binding = ProtectionDeviceBinding(relay, line.id, uuid4(), make_breaker())
    zone = ProtectionZone("ZONE", (line.id,), (relay.id,))
    with pytest.raises(ValueError, match="does not belong"):
        ProtectionNetworkBuilder().build(network, (binding,), (zone,))


def test_protection_builder_rejects_unconnected_monitored_terminal():
    network, _, _, line, terminals, _ = build_feeder()
    network.disconnect(terminals[0].id)
    relay = make_relay("R-OPEN")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("ZONE", (line.id,), (relay.id,))
    with pytest.raises(ValueError, match="not connected"):
        ProtectionNetworkBuilder().build(network, (binding,), (zone,))


def test_protection_builder_warns_for_unassigned_binding():
    network, _, _, line, terminals, _ = build_feeder()
    relay = make_relay("R-UNASSIGNED")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())

    model = ProtectionNetworkBuilder().build(network, (binding,), ())

    assert model.diagnostics[0].code == "PROTECTION-DEVICE-NOT-ASSIGNED-TO-ZONE"


def test_scenario_catalog_generates_bus_max_min_and_interior_line_locations():
    network, bus_a, bus_b, line, _, _ = build_feeder()
    scenarios = ProtectionScenarioCatalog().generate(
        network,
        fault_types=(FaultType.THREE_PHASE,),
        line_fault_fractions=(0.25, 0.75),
    )

    bus_scenarios = [
        item for item in scenarios if item.location_kind is ProtectionFaultLocationKind.BUS
    ]
    line_scenarios = [
        item for item in scenarios if item.location_kind is ProtectionFaultLocationKind.LINE
    ]
    assert len(bus_scenarios) == 4
    assert len(line_scenarios) == 2
    assert {item.location_id for item in bus_scenarios} == {bus_a.id, bus_b.id}
    assert {item.current_case for item in bus_scenarios} == {
        IEC60909CurrentCase.MAXIMUM,
        IEC60909CurrentCase.MINIMUM,
    }
    assert all(item.current_case is None for item in line_scenarios)
    assert {item.fraction_from for item in line_scenarios} == {0.25, 0.75}
    assert all(item.location_id == line.id for item in line_scenarios)


def test_scenario_catalog_rejects_explicit_empty_fault_selection():
    network, *_ = build_feeder()
    with pytest.raises(ValueError, match="fault_types must contain"):
        ProtectionScenarioCatalog().generate(network, fault_types=())


def test_scenario_catalog_rejects_boolean_line_fault_fraction():
    network, *_ = build_feeder()
    with pytest.raises(TypeError, match="real numeric values"):
        ProtectionScenarioCatalog().generate(
            network,
            fault_types=(FaultType.THREE_PHASE,),
            line_fault_fractions=(True,),
            include_bus_faults=False,
        )


def test_scenario_catalog_is_reproducible_for_same_topology():
    network, *_ = build_feeder()
    catalog = ProtectionScenarioCatalog()
    first = catalog.generate(network, fault_types=(FaultType.THREE_PHASE,))
    second = catalog.generate(network, fault_types=(FaultType.THREE_PHASE,))
    assert tuple(item.id for item in first) == tuple(item.id for item in second)


def test_zone_rejects_backup_relationship_with_wrong_membership():
    primary = uuid4()
    backup = uuid4()
    relationship = ProtectionBackupRelationship(primary, backup, 0.3)
    with pytest.raises(ValueError, match="not a backup zone device"):
        ProtectionZone(
            name="ZONE",
            protected_element_ids=(uuid4(),),
            primary_device_ids=(primary,),
            backup_device_ids=(),
            backup_relationships=(relationship,),
        )


def test_protection_builder_requires_every_backup_device_to_have_explicit_primary_relation():
    network, bus_a, _, line, terminals, _ = build_feeder()
    primary = make_relay("R-PRIMARY")
    backup = make_relay("R-BACKUP")
    bindings = (
        ProtectionDeviceBinding(primary, line.id, terminals[0].id, make_breaker()),
        ProtectionDeviceBinding(backup, line.id, terminals[1].id, make_breaker()),
    )
    zone = ProtectionZone(
        "ZONE",
        (line.id, bus_a.id),
        (primary.id,),
        backup_device_ids=(backup.id,),
    )

    with pytest.raises(ValueError, match="explicit primary-device relationship"):
        ProtectionNetworkBuilder().build(network, bindings, (zone,))


def test_network_analyzer_evaluates_primary_coverage_and_backup_margin():
    network, bus_a, _, line, terminals, _ = build_feeder()
    primary = make_relay("R-PRIMARY", tms=0.1)
    backup = make_relay("R-BACKUP", tms=1.0)
    primary_binding = ProtectionDeviceBinding(primary, line.id, terminals[0].id, make_breaker())
    backup_binding = ProtectionDeviceBinding(backup, line.id, terminals[1].id, make_breaker())
    zone = ProtectionZone(
        name="LINE-AB ZONE",
        protected_element_ids=(line.id, bus_a.id),
        primary_device_ids=(primary.id,),
        backup_device_ids=(backup.id,),
        backup_relationships=(ProtectionBackupRelationship(primary.id, backup.id, 0.2),),
    )
    model = ProtectionNetworkBuilder().build(network, (primary_binding, backup_binding), (zone,))
    scenario = ProtectionFaultScenario(
        name="BUS-A 3PH MAX",
        location_kind=ProtectionFaultLocationKind.BUS,
        location_id=bus_a.id,
        fault_type=FaultType.THREE_PHASE,
        current_case=IEC60909CurrentCase.MAXIMUM,
    )
    measurements = ProtectionScenarioMeasurements(
        scenario,
        {
            primary.id: ProtectionCurrentMeasurement(phase_current_a=6000.0, earth_current_a=0.0),
            backup.id: ProtectionCurrentMeasurement(phase_current_a=6000.0, earth_current_a=0.0),
        },
    )

    result = ProtectionNetworkAnalyzer().analyze(model, (measurements,))

    assessment = result.zone_assessments[0]
    assert assessment.primary_coverage is ProtectionAssessmentStatus.PASS
    assert assessment.backup_checks[0].status is ProtectionAssessmentStatus.PASS
    assert assessment.backup_checks[0].achieved_margin_s >= 0.2
    assert result.status is ProtectionAssessmentStatus.PASS


def test_network_analyzer_marks_zone_uncovered_when_no_primary_picks_up():
    network, bus_a, _, line, terminals, _ = build_feeder()
    relay = make_relay("R-INSENSITIVE", pickup_secondary_a=4.0)
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("ZONE", (line.id, bus_a.id), (relay.id,))
    model = ProtectionNetworkBuilder().build(network, (binding,), (zone,))
    scenario = ProtectionFaultScenario(
        "LOW CURRENT BUS-A",
        ProtectionFaultLocationKind.BUS,
        bus_a.id,
        FaultType.THREE_PHASE,
        IEC60909CurrentCase.MINIMUM,
    )
    inputs = ProtectionScenarioMeasurements(
        scenario,
        {relay.id: ProtectionCurrentMeasurement(phase_current_a=100.0, earth_current_a=0.0)},
    )

    result = ProtectionNetworkAnalyzer().analyze(model, (inputs,))

    assert result.zone_assessments[0].status is ProtectionAssessmentStatus.FAIL
    assert result.zone_assessments[0].primary_coverage is ProtectionAssessmentStatus.FAIL
    assert any(item.code == "PROTECTION-ZONE-UNCOVERED" for item in result.diagnostics)


def test_network_analyzer_does_not_claim_coverage_when_current_is_missing():
    network, bus_a, _, line, terminals, _ = build_feeder()
    relay = make_relay("R-MISSING")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("ZONE", (line.id, bus_a.id), (relay.id,))
    model = ProtectionNetworkBuilder().build(network, (binding,), (zone,))
    scenario = ProtectionFaultScenario(
        "BUS-A 3PH",
        ProtectionFaultLocationKind.BUS,
        bus_a.id,
        FaultType.THREE_PHASE,
        IEC60909CurrentCase.MAXIMUM,
    )

    result = ProtectionNetworkAnalyzer().analyze(
        model, (ProtectionScenarioMeasurements(scenario, {}),)
    )

    assert result.status is ProtectionAssessmentStatus.NOT_EVALUATED
    assert result.zone_assessments[0].primary_coverage is ProtectionAssessmentStatus.NOT_EVALUATED


def test_network_analyzer_uses_earth_element_residual_current():
    network, bus_a, _, line, terminals, _ = build_feeder()
    relay = make_relay("R-EARTH", function=ProtectionFunction.EARTH, tms=0.2)
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("ZONE", (line.id, bus_a.id), (relay.id,))
    model = ProtectionNetworkBuilder().build(network, (binding,), (zone,))
    scenario = ProtectionFaultScenario(
        "BUS-A AG",
        ProtectionFaultLocationKind.BUS,
        bus_a.id,
        FaultType.SINGLE_LINE_TO_GROUND,
        IEC60909CurrentCase.MAXIMUM,
    )
    measurements = ProtectionScenarioMeasurements(
        scenario,
        {relay.id: ProtectionCurrentMeasurement(phase_current_a=10000.0, earth_current_a=1200.0)},
    )

    result = ProtectionNetworkAnalyzer().analyze(model, (measurements,))

    operation = result.device_operations[0]
    assert operation.measured_current_a == pytest.approx(1200.0)
    assert operation.picked_up is True


def test_runner_calculates_max_min_bus_faults_and_reconstructs_branch_ct_current():
    network, _bus_a, bus_b, line, terminals, base = build_feeder()
    relay = make_relay("R-LINE-A", tms=0.1)
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone(
        name="LINE-AB ZONE",
        protected_element_ids=(line.id, bus_b.id),
        primary_device_ids=(relay.id,),
    )
    model = ProtectionNetworkBuilder().build(network, (binding,), (zone,))
    networks = SequenceNetworkBuilder(base).build_all(network)
    maximum = IEC60909StudySpecification(
        current_case=IEC60909CurrentCase.MAXIMUM,
        fault_duration_s=1.0,
        frequency_hz=60.0,
    )
    minimum = IEC60909StudySpecification(
        current_case=IEC60909CurrentCase.MINIMUM,
        fault_duration_s=1.0,
        frequency_hz=60.0,
        minimum_line_resistance_factor=1.2,
        minimum_zero_sequence_line_resistance_factor=1.2,
    )

    result = ProtectionFaultStudyRunner().run_bus_fault_matrix(
        network,
        model,
        networks,
        base,
        maximum_study=maximum,
        minimum_study=minimum,
        fault_types=(FaultType.THREE_PHASE,),
    )

    assert len(result.scenarios) == 4
    assert len(result.device_operations) == 4
    bus_b_operations = [
        item
        for item in result.device_operations
        if any(
            scenario.id == item.scenario_id and scenario.location_id == bus_b.id
            for scenario in result.scenarios
        )
    ]
    assert len(bus_b_operations) == 2
    assert all(
        item.measured_current_a is not None and item.measured_current_a > 0.0
        for item in bus_b_operations
    )
    assert all(item.picked_up is True for item in bus_b_operations)
    assert len(result.zone_assessments) == 2
    assert all(item.status is ProtectionAssessmentStatus.PASS for item in result.zone_assessments)
    assert result.status is ProtectionAssessmentStatus.FAIL
    assert any(
        item.code == "PROTECTION-FAULT-LOCATION-OUTSIDE-ALL-ZONES" for item in result.diagnostics
    )


def test_runner_rejects_maximum_and_minimum_studies_with_different_frequencies():
    network, _bus_a, bus_b, line, terminals, base = build_feeder()
    relay = make_relay("R-LINE-A")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("ZONE", (line.id, bus_b.id), (relay.id,))
    model = ProtectionNetworkBuilder().build(network, (binding,), (zone,))
    networks = SequenceNetworkBuilder(base).build_all(network)
    maximum = IEC60909StudySpecification(
        IEC60909CurrentCase.MAXIMUM,
        fault_duration_s=1.0,
        frequency_hz=50.0,
    )
    minimum = IEC60909StudySpecification(
        IEC60909CurrentCase.MINIMUM,
        fault_duration_s=1.0,
        frequency_hz=60.0,
        minimum_line_resistance_factor=1.1,
    )

    with pytest.raises(ValueError, match="same network frequency"):
        ProtectionFaultStudyRunner().run_bus_fault_matrix(
            network,
            model,
            networks,
            base,
            maximum_study=maximum,
            minimum_study=minimum,
            fault_types=(FaultType.THREE_PHASE,),
        )


def test_runner_rejects_case_specifications_in_wrong_order():
    network, _bus_a, bus_b, line, terminals, base = build_feeder()
    relay = make_relay("R-LINE-A")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("ZONE", (line.id, bus_b.id), (relay.id,))
    model = ProtectionNetworkBuilder().build(network, (binding,), (zone,))
    networks = SequenceNetworkBuilder(base).build_all(network)
    maximum = IEC60909StudySpecification(
        IEC60909CurrentCase.MINIMUM,
        fault_duration_s=1.0,
        frequency_hz=60.0,
        minimum_line_resistance_factor=1.1,
    )
    minimum = IEC60909StudySpecification(
        IEC60909CurrentCase.MAXIMUM,
        fault_duration_s=1.0,
        frequency_hz=60.0,
    )
    with pytest.raises(ValueError, match="maximum_study"):
        ProtectionFaultStudyRunner().run_bus_fault_matrix(
            network,
            model,
            networks,
            base,
            maximum_study=maximum,
            minimum_study=minimum,
            fault_types=(FaultType.THREE_PHASE,),
        )


def test_network_analyzer_fails_backup_sensitivity_when_measured_backup_does_not_pick_up():
    network, bus_a, _, line, terminals, _ = build_feeder()
    primary = make_relay("R-PRIMARY", tms=0.1)
    backup = make_relay("R-BACKUP", pickup_secondary_a=4.0, tms=1.0)
    primary_binding = ProtectionDeviceBinding(primary, line.id, terminals[0].id, make_breaker())
    backup_binding = ProtectionDeviceBinding(backup, line.id, terminals[1].id, make_breaker())
    zone = ProtectionZone(
        name="LINE-AB ZONE",
        protected_element_ids=(line.id, bus_a.id),
        primary_device_ids=(primary.id,),
        backup_device_ids=(backup.id,),
        backup_relationships=(ProtectionBackupRelationship(primary.id, backup.id, 0.2),),
    )
    model = ProtectionNetworkBuilder().build(network, (primary_binding, backup_binding), (zone,))
    scenario = ProtectionFaultScenario(
        "BUS-A 3PH",
        ProtectionFaultLocationKind.BUS,
        bus_a.id,
        FaultType.THREE_PHASE,
        IEC60909CurrentCase.MAXIMUM,
    )
    measurements = ProtectionScenarioMeasurements(
        scenario,
        {
            primary.id: ProtectionCurrentMeasurement(phase_current_a=5000.0, earth_current_a=0.0),
            backup.id: ProtectionCurrentMeasurement(phase_current_a=100.0, earth_current_a=0.0),
        },
    )

    result = ProtectionNetworkAnalyzer().analyze(model, (measurements,))

    assert result.zone_assessments[0].backup_checks[0].status is ProtectionAssessmentStatus.FAIL
    assert result.status is ProtectionAssessmentStatus.FAIL


def test_protection_builder_rejects_source_side_current_binding_until_source_model_exists():
    network, *_ = build_feeder()
    source = next(item for item in network.equipment if item.name == "GRID-01")
    relay = make_relay("R-SOURCE-INCOMER")
    binding = ProtectionDeviceBinding(relay, source.id, source.terminals[0].id, make_breaker())
    zone = ProtectionZone("GRID ZONE", (source.id,), (relay.id,))

    with pytest.raises(ValueError, match="only transmission branches and transformers"):
        ProtectionNetworkBuilder().build(network, (binding,), (zone,))


def test_protection_builder_requires_primary_device_to_monitor_inside_its_zone():
    network, _bus_a, bus_b, line, terminals, _ = build_feeder()
    relay = make_relay("R-WRONG-ZONE")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("BUS-B ONLY", (bus_b.id,), (relay.id,))

    with pytest.raises(ValueError, match="does not monitor an element inside protection zone"):
        ProtectionNetworkBuilder().build(network, (binding,), (zone,))


def test_runner_maps_nd007_interior_line_fault_terminal_current_to_protection_device():
    network, _bus_a, _bus_b, line, terminals, base = build_feeder()
    relay = make_relay("R-LINE-A", tms=0.1)
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("LINE-AB ZONE", (line.id,), (relay.id,))
    protection_model = ProtectionNetworkBuilder().build(network, (binding,), (zone,))
    sequence_networks = SequenceNetworkBuilder(base).build_all(network)
    line_result = LineFaultSolver().solve(
        sequence_networks,
        LineFaultSpecification(FaultType.THREE_PHASE, line.id, 0.4),
        base,
    )
    scenario = next(
        item
        for item in ProtectionScenarioCatalog().generate(
            network,
            fault_types=(FaultType.THREE_PHASE,),
            line_fault_fractions=(0.4,),
            include_bus_faults=False,
        )
        if item.location_id == line.id
    )

    runner = ProtectionFaultStudyRunner()
    measurements = runner.add_line_fault_measurements(protection_model, scenario, line_result)
    assessment = runner.assess_scenarios(protection_model, (measurements,))

    operation = assessment.device_operations[0]
    assert operation.device_id == relay.id
    assert operation.measured_current_a is not None
    assert operation.measured_current_a > 120.0
    assert operation.picked_up is True
    assert operation.clearing_time_s is not None
    assert assessment.zone_assessments[0].primary_coverage is ProtectionAssessmentStatus.PASS
    assert assessment.status is ProtectionAssessmentStatus.PASS


def test_analyzer_rejects_scenario_measurements_for_unknown_protection_device():
    network, bus_a, _, line, terminals, _ = build_feeder()
    relay = make_relay("R-VALID")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("ZONE", (line.id,), (relay.id,))
    model = ProtectionNetworkBuilder().build(network, (binding,), (zone,))
    scenario = ProtectionFaultScenario(
        "BUS-A 3PH",
        ProtectionFaultLocationKind.BUS,
        bus_a.id,
        FaultType.THREE_PHASE,
        IEC60909CurrentCase.MAXIMUM,
    )
    measurements = ProtectionScenarioMeasurements(
        scenario,
        {uuid4(): ProtectionCurrentMeasurement(phase_current_a=1000.0, earth_current_a=0.0)},
    )

    with pytest.raises(ValueError, match="outside this model"):
        ProtectionNetworkAnalyzer().analyze(model, (measurements,))


def test_protection_zone_rejects_duplicate_backup_relationship_pairs():
    primary = uuid4()
    backup = uuid4()
    relation = ProtectionBackupRelationship(primary, backup, 0.2)

    with pytest.raises(ValueError, match="duplicate device pairs"):
        ProtectionZone(
            "ZONE",
            (uuid4(),),
            (primary,),
            backup_device_ids=(backup,),
            backup_relationships=(relation, relation),
        )


# ND-011 advanced function integration tests


def make_line_differential():
    ct = CurrentTransformerRatio(600.0, 5.0)
    return DifferentialProtectionSettings(
        name="87L-AB",
        kind=DifferentialProtectionKind.LINE,
        sides=(
            DifferentialSideSettings("FROM", 600.0, ct),
            DifferentialSideSettings("TO", 600.0, ct),
        ),
        minimum_pickup_pu=0.2,
        low_slope=0.3,
        breakpoint_restraint_pu=2.0,
        high_slope=0.5,
        second_harmonic_block_ratio=0.15,
    )


def make_distance_function():
    return DistanceProtectionSettings(
        name="21-AB",
        current_transformer=CurrentTransformerRatio(600.0, 5.0),
        voltage_transformer=VoltageTransformerRatio(13_800.0 / 3**0.5, 110.0 / 3**0.5),
        zones=(
            DistanceZoneSettings(
                1,
                DistanceCharacteristic.MHO,
                0.1,
                reach_impedance_secondary_ohm=12.0 + 24.0j,
            ),
        ),
    )


def make_ct_performance():
    return CurrentTransformerPerformanceModel(
        name="CT-PX-600-5",
        current_transformer=CurrentTransformerRatio(600.0, 5.0),
        secondary_winding_resistance_ohm=0.2,
        burden_impedance_ohm=0.5 + 0.1j,
        knee_point_voltage_v=100.0,
        excitation_curve=(
            CTExcitationPoint(1.0, 0.01),
            CTExcitationPoint(10.0, 0.05),
            CTExcitationPoint(100.0, 1.0),
            CTExcitationPoint(110.0, 2.0),
        ),
        rated_frequency_hz=60.0,
    )


def test_protection_builder_binds_line_differential_function_to_zone():
    network, bus_a, _, line, terminals, _ = build_feeder()
    relay = make_relay("R-LINE-A")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("LINE-87 ZONE", (line.id, bus_a.id), (relay.id,))
    differential = make_line_differential()
    advanced_binding = AdvancedProtectionFunctionBinding(
        differential, line.id, zone.id, (terminals[0].id, terminals[1].id)
    )

    model = ProtectionNetworkBuilder().build(
        network,
        (binding,),
        (zone,),
        advanced_function_bindings=(advanced_binding,),
    )

    assert model.advanced_function_bindings == (advanced_binding,)
    assert model.advanced_function_bindings[0].id == differential.id


def test_protection_builder_rejects_advanced_function_for_zone_not_covering_equipment():
    network, bus_a, _, line, terminals, _ = build_feeder()
    relay = make_relay("R-LINE-A")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("WRONG ZONE", (bus_a.id,), (relay.id,))
    advanced_binding = AdvancedProtectionFunctionBinding(
        make_line_differential(), line.id, zone.id, (terminals[0].id, terminals[1].id)
    )
    with pytest.raises(ValueError, match="zone containing its equipment"):
        ProtectionNetworkBuilder().build(
            network, (binding,), (zone,), advanced_function_bindings=(advanced_binding,)
        )


def test_protection_builder_binds_ct_performance_model_to_matching_relay_ct():
    network, bus_a, _, line, terminals, _ = build_feeder()
    relay = make_relay("R-LINE-A")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("LINE ZONE", (line.id, bus_a.id), (relay.id,))
    ct_binding = CurrentTransformerPerformanceBinding(relay.id, make_ct_performance())

    model = ProtectionNetworkBuilder().build(
        network, (binding,), (zone,), ct_performance_bindings=(ct_binding,)
    )

    assert model.ct_performance_bindings == (ct_binding,)


def test_protection_builder_rejects_ct_performance_ratio_mismatch():
    network, bus_a, _, line, terminals, _ = build_feeder()
    relay = make_relay("R-LINE-A")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("LINE ZONE", (line.id, bus_a.id), (relay.id,))
    bad_model = CurrentTransformerPerformanceModel(
        name="CT-WRONG",
        current_transformer=CurrentTransformerRatio(800.0, 5.0),
        secondary_winding_resistance_ohm=0.2,
        burden_impedance_ohm=0.5 + 0.1j,
        knee_point_voltage_v=100.0,
        excitation_curve=(CTExcitationPoint(1.0, 0.01), CTExcitationPoint(100.0, 1.0)),
        rated_frequency_hz=60.0,
    )
    with pytest.raises(ValueError, match="ratio must match"):
        ProtectionNetworkBuilder().build(
            network,
            (binding,),
            (zone,),
            ct_performance_bindings=(CurrentTransformerPerformanceBinding(relay.id, bad_model),),
        )


def test_advanced_network_analyzer_assesses_expected_differential_operation():
    network, bus_a, _, line, terminals, _ = build_feeder()
    relay = make_relay("R-LINE-A")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("LINE-87 ZONE", (line.id, bus_a.id), (relay.id,))
    differential = make_line_differential()
    advanced_binding = AdvancedProtectionFunctionBinding(
        differential, line.id, zone.id, (terminals[0].id, terminals[1].id)
    )
    protection_model = ProtectionNetworkBuilder().build(
        network, (binding,), (zone,), advanced_function_bindings=(advanced_binding,)
    )
    scenario = AdvancedProtectionScenarioMeasurements(
        scenario_id=uuid4(),
        function_measurements={
            differential.id: AdvancedProtectionFunctionMeasurement(
                DifferentialMeasurement({"FROM": (1000 + 0j, 0j, 0j), "TO": (0j, 0j, 0j)}),
                expected_to_operate=True,
            )
        },
    )

    result = AdvancedProtectionNetworkAnalyzer().analyze(
        protection_model, (scenario,), system_frequency_hz=60.0
    )

    assert result.status is ProtectionAssessmentStatus.PASS
    assert result.scenarios[0].function_assessments[0].operated is True


def test_advanced_network_analyzer_marks_missing_function_measurement_not_evaluated():
    network, bus_a, _, line, terminals, _ = build_feeder()
    relay = make_relay("R-LINE-A")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("LINE-87 ZONE", (line.id, bus_a.id), (relay.id,))
    differential = make_line_differential()
    advanced_binding = AdvancedProtectionFunctionBinding(
        differential, line.id, zone.id, (terminals[0].id, terminals[1].id)
    )
    model = ProtectionNetworkBuilder().build(
        network, (binding,), (zone,), advanced_function_bindings=(advanced_binding,)
    )
    scenario = AdvancedProtectionScenarioMeasurements(uuid4(), {})

    result = AdvancedProtectionNetworkAnalyzer().analyze(
        model, (scenario,), system_frequency_hz=60.0
    )

    assert result.status is ProtectionAssessmentStatus.NOT_EVALUATED
    assert result.scenarios[0].function_assessments[0].operated is None


def test_protection_builder_binds_distance_function_at_line_terminal():
    network, bus_a, _, line, terminals, _ = build_feeder()
    relay = make_relay("R-LINE-A")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("LINE-21 ZONE", (line.id, bus_a.id), (relay.id,))
    distance = make_distance_function()
    advanced_binding = AdvancedProtectionFunctionBinding(
        distance, line.id, zone.id, (terminals[0].id,)
    )
    model = ProtectionNetworkBuilder().build(
        network, (binding,), (zone,), advanced_function_bindings=(advanced_binding,)
    )
    assert model.advanced_function_bindings[0].function is distance


def test_protection_builder_rejects_transformer_differential_settings_on_line():
    network, bus_a, _, line, terminals, _ = build_feeder()
    relay = make_relay("R-LINE-A")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("LINE ZONE", (line.id, bus_a.id), (relay.id,))
    line_settings = make_line_differential()
    transformer_settings = DifferentialProtectionSettings(
        name="87T-INCORRECT",
        kind=DifferentialProtectionKind.TRANSFORMER,
        sides=line_settings.sides,
        minimum_pickup_pu=0.2,
        low_slope=0.3,
        breakpoint_restraint_pu=2.0,
        high_slope=0.5,
    )
    advanced_binding = AdvancedProtectionFunctionBinding(
        transformer_settings, line.id, zone.id, (terminals[0].id, terminals[1].id)
    )
    with pytest.raises(ValueError, match="matching kind"):
        ProtectionNetworkBuilder().build(
            network, (binding,), (zone,), advanced_function_bindings=(advanced_binding,)
        )


def test_advanced_network_analyzer_evaluates_ct_performance_binding():
    network, bus_a, _, line, terminals, _ = build_feeder()
    relay = make_relay("R-LINE-A")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("LINE ZONE", (line.id, bus_a.id), (relay.id,))
    ct_binding = CurrentTransformerPerformanceBinding(relay.id, make_ct_performance())
    protection_model = ProtectionNetworkBuilder().build(
        network, (binding,), (zone,), ct_performance_bindings=(ct_binding,)
    )
    scenario = AdvancedProtectionScenarioMeasurements(
        scenario_id=uuid4(),
        function_measurements={},
        ct_primary_currents_a={relay.id: 1000.0},
    )
    result = AdvancedProtectionNetworkAnalyzer().analyze(
        protection_model, (scenario,), system_frequency_hz=60.0
    )
    assert result.status is ProtectionAssessmentStatus.PASS
    assert result.scenarios[0].ct_assessments[relay.id].status is ProtectionAssessmentStatus.PASS


def test_advanced_network_analyzer_marks_missing_ct_current_not_evaluated():
    network, bus_a, _, line, terminals, _ = build_feeder()
    relay = make_relay("R-LINE-A")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("LINE ZONE", (line.id, bus_a.id), (relay.id,))
    ct_binding = CurrentTransformerPerformanceBinding(relay.id, make_ct_performance())
    protection_model = ProtectionNetworkBuilder().build(
        network, (binding,), (zone,), ct_performance_bindings=(ct_binding,)
    )
    scenario = AdvancedProtectionScenarioMeasurements(uuid4(), {})
    result = AdvancedProtectionNetworkAnalyzer().analyze(
        protection_model, (scenario,), system_frequency_hz=60.0
    )
    assert result.status is ProtectionAssessmentStatus.NOT_EVALUATED
    assert not result.scenarios[0].ct_assessments
    assert any("not supplied" in item for item in result.scenarios[0].diagnostics)


def test_advanced_network_analyzer_dispatches_directional_protection():
    network, bus_a, _, line, terminals, _ = build_feeder()
    relay = make_relay("67-LINE-A")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("LINE-67 ZONE", (line.id, bus_a.id), (relay.id,))
    directional = DirectionalOvercurrentSettings(
        relay=relay,
        maximum_torque_angle_deg=0.0,
        minimum_polarizing_voltage_v=10.0,
    )
    advanced_binding = AdvancedProtectionFunctionBinding(
        directional, line.id, zone.id, (terminals[0].id,)
    )
    model = ProtectionNetworkBuilder().build(
        network, (binding,), (zone,), advanced_function_bindings=(advanced_binding,)
    )
    scenario = AdvancedProtectionScenarioMeasurements(
        uuid4(),
        {
            directional.id: AdvancedProtectionFunctionMeasurement(
                DirectionalMeasurement(1000 + 0j, 100 + 0j), True
            )
        },
    )
    result = AdvancedProtectionNetworkAnalyzer().analyze(
        model, (scenario,), system_frequency_hz=60.0
    )
    assert result.status is ProtectionAssessmentStatus.PASS
    assert result.scenarios[0].function_assessments[0].operated is True


def test_advanced_network_analyzer_dispatches_distance_protection():
    network, bus_a, _, line, terminals, _ = build_feeder()
    relay = make_relay("21-LINE-A")
    binding = ProtectionDeviceBinding(relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("LINE-21 ZONE", (line.id, bus_a.id), (relay.id,))
    distance = make_distance_function()
    advanced_binding = AdvancedProtectionFunctionBinding(
        distance, line.id, zone.id, (terminals[0].id,)
    )
    model = ProtectionNetworkBuilder().build(
        network, (binding,), (zone,), advanced_function_bindings=(advanced_binding,)
    )
    vt_ratio = distance.voltage_transformer.ratio
    voltage_secondary = (5 + 10j) * 10.0
    measurement = DistanceMeasurement(
        phase_voltages_primary_v=(voltage_secondary * vt_ratio, 0j, 0j),
        phase_currents_primary_a=(1200 + 0j, 0j, 0j),
    )
    scenario = AdvancedProtectionScenarioMeasurements(
        uuid4(),
        {distance.id: AdvancedProtectionFunctionMeasurement(measurement, True)},
    )
    result = AdvancedProtectionNetworkAnalyzer().analyze(
        model, (scenario,), system_frequency_hz=60.0
    )
    assert result.status is ProtectionAssessmentStatus.PASS
    assert result.scenarios[0].function_assessments[0].operated is True


def test_builder_rejects_directional_function_wrapping_unbound_relay():
    network, bus_a, _, line, terminals, _ = build_feeder()
    bound_relay = make_relay("51-BOUND")
    unbound_relay = make_relay("51-UNBOUND")
    base_binding = ProtectionDeviceBinding(bound_relay, line.id, terminals[0].id, make_breaker())
    zone = ProtectionZone("DIRECTIONAL ZONE", (line.id, bus_a.id), (bound_relay.id,))
    directional = DirectionalOvercurrentSettings(
        relay=unbound_relay,
        maximum_torque_angle_deg=0.0,
        minimum_polarizing_voltage_v=10.0,
    )
    advanced = AdvancedProtectionFunctionBinding(directional, line.id, zone.id, (terminals[0].id,))

    with pytest.raises(ValueError, match="exact 50/51 relay"):
        ProtectionNetworkBuilder().build(
            network, (base_binding,), (zone,), advanced_function_bindings=(advanced,)
        )


def test_advanced_analyzer_rejects_boolean_system_frequency():
    network, *_ = build_feeder()
    model = ProtectionNetworkBuilder().build(network, (), ())

    with pytest.raises(TypeError, match="real number, not bool"):
        AdvancedProtectionNetworkAnalyzer().analyze(model, (), system_frequency_hz=True)
