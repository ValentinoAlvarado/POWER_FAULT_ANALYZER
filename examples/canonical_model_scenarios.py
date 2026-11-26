"""Three canonical Network-model scenarios used by PFA-SYNC-001 integration tests.

The source positive-sequence values are the existing REF-3PH-001 benchmark.
Transformer/line/generator data not supplied by an engineering source remain
explicitly unresolved; they are topology-bearing placeholders and are not
calculation-ready numerical models.
"""
from __future__ import annotations
from uuid import uuid4

from power_fault_analyzer.application.use_cases.network_workspace import NetworkWorkspace
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.bus_kind import BusKind
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.enums.equipment_interface import ParameterEvidenceStatus
from power_fault_analyzer.domain.enums.switching_device import SwitchingDeviceKind, SwitchPosition
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.voltage import Voltage
from power_fault_analyzer.equipment.interfaces.unresolved_equipment import EngineeringParameter, UnresolvedEquipmentInterface
from power_fault_analyzer.equipment.interfaces.unresolved_branch import UnresolvedTwoTerminalEquipment
from power_fault_analyzer.equipment.interfaces.unresolved_single_terminal import UnresolvedSingleTerminalEquipment
from power_fault_analyzer.equipment.switching.switching_device import SwitchingDevice


def _bus(network: Network, name: str, kv: float) -> Bus:
    item = Bus(name, Voltage.from_kv(kv), kind=BusKind.BUSBAR)
    network.add_bus(item)
    return item


def _source(network: Network, bus: Bus, name: str = "GRID-EQUIVALENT") -> UnresolvedSingleTerminalEquipment:
    identifier = uuid4()
    terminal = Terminal(identifier, "GRID", bus.nominal_voltage)
    # REF-3PH-001 supplies the declared base and positive-sequence Z1 only.
    # E1, Z2 and Z0 are absent from the benchmark record and remain unresolved.
    confirmed = ParameterEvidenceStatus.USER_CONFIRMED
    parameters = (
        EngineeringParameter("base_power_mva", "MVA", 100.0, confirmed, "REF-3PH-001"),
        EngineeringParameter("base_voltage_kv", "kV line-line", 13.8, confirmed, "REF-3PH-001"),
        EngineeringParameter("z1_resistance_pu", "pu", 0.08, confirmed, "REF-3PH-001"),
        EngineeringParameter("z1_reactance_pu", "pu", 0.24, confirmed, "REF-3PH-001"),
        EngineeringParameter("prefault_voltage_pu", "pu"),
        EngineeringParameter("z2_pu", "pu"),
        EngineeringParameter("z0_pu", "pu"),
    )
    item = UnresolvedSingleTerminalEquipment(
        id=identifier, name=name, terminal=terminal, equipment_kind="source",
        family=EquipmentFamily.SOURCE, parameters=parameters,
    )
    network.add_equipment(item)
    network.connect(terminal.id, bus.id)
    return item


def _placeholder(network: Network, name: str, kind: str, family: EquipmentFamily,
                 from_bus: Bus, to_bus: Bus, params: tuple[EngineeringParameter, ...]):
    identifier = uuid4()
    terminals = (Terminal(identifier, "FROM", from_bus.nominal_voltage),
                 Terminal(identifier, "TO", to_bus.nominal_voltage))
    item = UnresolvedTwoTerminalEquipment(id=identifier, name=name, terminals=terminals,
                                          equipment_kind=kind, family=family,
                                          parameters=params)
    network.add_equipment(item)
    network.connect(terminals[0].id, from_bus.id)
    network.connect(terminals[1].id, to_bus.id)
    return item


def _unresolved_parameters(*names: tuple[str, str]) -> tuple[EngineeringParameter, ...]:
    return tuple(EngineeringParameter(name, unit) for name, unit in names)


def build_single_bus_substation() -> NetworkWorkspace:
    network = Network("REF-SYNC-01 Single-bus substation")
    bus_hv = _bus(network, "BUS-13K8-A", 13.8)
    bus_cb = _bus(network, "BUS-13K8-B", 13.8)
    bus_lv = _bus(network, "BUS-04K-A", 0.4)
    bus_remote = _bus(network, "BUS-04K-B", 0.4)
    _source(network, bus_hv)
    breaker_id = uuid4()
    breaker_terms = (Terminal(breaker_id, "LINE", bus_hv.nominal_voltage),
                     Terminal(breaker_id, "BUS", bus_hv.nominal_voltage))
    breaker = SwitchingDevice(id=breaker_id, name="CB-01", terminals=breaker_terms,
                               device_kind=SwitchingDeviceKind.CIRCUIT_BREAKER,
                               position=SwitchPosition.CLOSED)
    network.add_equipment(breaker)
    network.connect(breaker_terms[0].id, bus_hv.id); network.connect(breaker_terms[1].id, bus_cb.id)
    _placeholder(network, "T-01", "transformer", EquipmentFamily.TRANSFORMER,
                 bus_cb, bus_lv, _unresolved_parameters(("rated_power_mva","MVA"),
                 ("hv_connection","winding connection"),("lv_connection","winding connection"),
                 ("vector_group","clock notation"),("z1_pu","pu"),("z2_pu","pu"),("z0_pu","pu")))
    _placeholder(network, "LINE-01", "line", EquipmentFamily.TRANSMISSION,
                 bus_lv, bus_remote, _unresolved_parameters(("length_km","km"),
                 ("r1_ohm_km","ohm/km"),("x1_ohm_km","ohm/km"),
                 ("r2_ohm_km","ohm/km"),("x2_ohm_km","ohm/km"),
                 ("r0_ohm_km","ohm/km"),("x0_ohm_km","ohm/km")))
    return NetworkWorkspace(network=network)


def build_double_bus_substation() -> NetworkWorkspace:
    network = Network("REF-SYNC-02 Double-bus substation")
    bus_a = _bus(network, "BUS-A", 13.8)
    bus_b = _bus(network, "BUS-B", 13.8)
    feeder_a = _bus(network, "FEEDER-A", 13.8)
    feeder_b = _bus(network, "FEEDER-B", 13.8)
    _source(network, bus_a)
    coupler_id = uuid4()
    terminals = (Terminal(coupler_id,"BUS-A",bus_a.nominal_voltage),
                 Terminal(coupler_id,"BUS-B",bus_b.nominal_voltage))
    coupler = SwitchingDevice(id=coupler_id,name="BC-01",terminals=terminals,
                              device_kind=SwitchingDeviceKind.CIRCUIT_BREAKER,
                              position=SwitchPosition.OPEN)
    network.add_equipment(coupler)
    network.connect(terminals[0].id,bus_a.id); network.connect(terminals[1].id,bus_b.id)
    line_params = _unresolved_parameters(("length_km","km"),("r1_ohm_km","ohm/km"),
                                         ("x1_ohm_km","ohm/km"),("r2_ohm_km","ohm/km"),
                                         ("x2_ohm_km","ohm/km"),("r0_ohm_km","ohm/km"),
                                         ("x0_ohm_km","ohm/km"))
    _placeholder(network,"LINE-A","line",EquipmentFamily.TRANSMISSION,bus_a,feeder_a,line_params)
    _placeholder(network,"LINE-B","line",EquipmentFamily.TRANSMISSION,bus_b,feeder_b,line_params)
    # Explicit drawing layout keeps the double-bus bars parallel and each feeder
    # bay on its own horizontal level; these coordinates do not affect studies.
    # Each bus owns a distinct horizontal row.  Coupler and feeder equipment
    # are placed in vertical bays between rows; no branch device is drawn inline
    # with a busbar.  These coordinates affect presentation only.
    return NetworkWorkspace(network=network, diagram_positions={
        bus_a.id: (360.0, 220.0), bus_b.id: (500.0, 440.0),
        feeder_a.id: (220.0, 620.0), feeder_b.id: (500.0, 800.0),
    })


def build_multibus_network() -> NetworkWorkspace:
    network = Network("REF-SYNC-03 Multi-bus power network")
    b1 = _bus(network,"BUS-01",13.8); b2 = _bus(network,"BUS-02",13.8)
    b3 = _bus(network,"BUS-03",13.8); b4 = _bus(network,"BUS-04",0.4)
    _source(network,b1,"GRID-01")
    generator_id=uuid4()
    generator_terminal=Terminal(generator_id,"STATOR",b3.nominal_voltage)
    generator=UnresolvedSingleTerminalEquipment(
        id=generator_id,name="GEN-01",terminal=generator_terminal,
        equipment_kind="generator",family=EquipmentFamily.SOURCE,
        parameters=_unresolved_parameters(("rated_power_mva","MVA"),
            ("rated_voltage_kv","kV"),("xd_subtransient_pu","pu"),
            ("xd_transient_pu","pu"),("x2_pu","pu"),("x0_pu","pu")))
    network.add_equipment(generator); network.connect(generator_terminal.id,b3.id)
    line_params=_unresolved_parameters(("length_km","km"),("r1_ohm_km","ohm/km"),
        ("x1_ohm_km","ohm/km"),("r2_ohm_km","ohm/km"),("x2_ohm_km","ohm/km"),
        ("r0_ohm_km","ohm/km"),("x0_ohm_km","ohm/km"))
    _placeholder(network,"LINE-12","line",EquipmentFamily.TRANSMISSION,b1,b2,line_params)
    _placeholder(network,"LINE-23","line",EquipmentFamily.TRANSMISSION,b2,b3,line_params)
    _placeholder(network,"T-04","transformer",EquipmentFamily.TRANSFORMER,b3,b4,
        _unresolved_parameters(("rated_power_mva","MVA"),("hv_voltage_kv","kV"),
            ("lv_voltage_kv","kV"),("vector_group","clock notation"),("z1_pu","pu"),
            ("z2_pu","pu"),("z0_pu","pu")))
    return NetworkWorkspace(network=network)
