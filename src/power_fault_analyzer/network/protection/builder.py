"""Validate protection-device attachments and protection-zone topology references."""

from __future__ import annotations

from collections.abc import Sequence

from power_fault_analyzer.domain.enums.advanced_protection import DifferentialProtectionKind
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.interfaces.network_contracts import NetworkAggregate
from power_fault_analyzer.domain.value_objects.advanced_protection import (
    AdvancedProtectionFunctionBinding,
    CurrentTransformerPerformanceBinding,
    DifferentialProtectionSettings,
    DirectionalOvercurrentSettings,
    DistanceProtectionSettings,
)
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)
from power_fault_analyzer.domain.value_objects.protection_devices import (
    FuseLink,
    OvercurrentRelay,
)
from power_fault_analyzer.domain.value_objects.protection_network import (
    ProtectionDeviceBinding,
    ProtectionNetworkModel,
    ProtectionZone,
)


class ProtectionNetworkBuilder:
    """Build a protection model against the authoritative electrical network."""

    def build(
        self,
        network: NetworkAggregate,
        bindings: Sequence[ProtectionDeviceBinding],
        zones: Sequence[ProtectionZone],
        *,
        advanced_function_bindings: Sequence[AdvancedProtectionFunctionBinding] = (),
        ct_performance_bindings: Sequence[CurrentTransformerPerformanceBinding] = (),
    ) -> ProtectionNetworkModel:
        if not isinstance(network, NetworkAggregate):
            raise TypeError("network must implement NetworkAggregate.")
        binding_tuple = tuple(bindings)
        zone_tuple = tuple(zones)
        advanced_tuple = tuple(advanced_function_bindings)
        ct_performance_tuple = tuple(ct_performance_bindings)
        if any(not isinstance(item, ProtectionDeviceBinding) for item in binding_tuple):
            raise TypeError("Every binding must be a ProtectionDeviceBinding.")
        if any(not isinstance(item, ProtectionZone) for item in zone_tuple):
            raise TypeError("Every zone must be a ProtectionZone.")
        if any(not isinstance(item, AdvancedProtectionFunctionBinding) for item in advanced_tuple):
            raise TypeError("Every advanced function must be an AdvancedProtectionFunctionBinding.")
        if any(
            not isinstance(item, CurrentTransformerPerformanceBinding)
            for item in ct_performance_tuple
        ):
            raise TypeError("Every CT model must be a CurrentTransformerPerformanceBinding.")

        equipment_by_id = {item.id: item for item in network.equipment}
        buses_by_id = {item.id: item for item in network.buses}
        terminals_by_id = {item.id: item for item in network.terminals}
        connections = {item.terminal_id: item.bus_id for item in network.connections}
        known_element_ids = set(equipment_by_id) | {item.id for item in network.buses}
        binding_ids = [item.id for item in binding_tuple]
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("A protection device can only be bound once.")

        resolved_bus_ids: dict = {}
        resolved_equipment_names: dict = {}
        diagnostics: list[DomainDiagnostic] = []
        for binding in binding_tuple:
            equipment = equipment_by_id.get(binding.monitored_equipment_id)
            if equipment is None:
                raise ValueError(
                    f"Protection device '{binding.device.name}' monitors unknown equipment."
                )
            terminal = terminals_by_id.get(binding.monitored_terminal_id)
            if terminal is None or terminal.equipment_id != equipment.id:
                raise ValueError(
                    f"Protection device '{binding.device.name}' terminal does not belong to "
                    "its monitored equipment."
                )
            if equipment.family not in {
                EquipmentFamily.TRANSMISSION,
                EquipmentFamily.TRANSFORMER,
            }:
                raise ValueError(
                    "Automatic protection-current extraction currently supports only "
                    "transmission branches and transformers. Source, load, switching and "
                    "other equipment current models are not implemented in this increment."
                )
            if len(equipment.terminals) < 2:
                raise ValueError(
                    "Protection current measurement requires a multi-terminal element."
                )
            bus_id = connections.get(binding.monitored_terminal_id)
            if bus_id is None:
                raise ValueError(
                    f"Monitored terminal '{terminal.designation}' is not connected to a bus."
                )
            resolved_bus_ids[binding.id] = bus_id
            resolved_equipment_names[binding.id] = equipment.name
            nominal_voltage_kv = buses_by_id[bus_id].nominal_voltage.value_kv
            if (
                binding.breaker is not None
                and binding.breaker.rated_voltage_kv + 1e-9 < nominal_voltage_kv
            ):
                raise ValueError(
                    f"Circuit breaker '{binding.breaker.name}' voltage rating is below the "
                    f"monitored bus '{buses_by_id[bus_id].name}' nominal voltage."
                )
            if (
                isinstance(binding.device, FuseLink)
                and binding.device.rated_voltage_kv + 1e-9 < nominal_voltage_kv
            ):
                raise ValueError(
                    f"Fuse '{binding.device.name}' voltage rating is below the monitored bus "
                    f"'{buses_by_id[bus_id].name}' nominal voltage."
                )

        zone_ids = [item.id for item in zone_tuple]
        if len(zone_ids) != len(set(zone_ids)):
            raise ValueError("Protection-zone IDs must be unique.")
        known_binding_ids = set(binding_ids)
        assigned: set = set()
        for zone in zone_tuple:
            unknown_elements = set(zone.protected_element_ids) - known_element_ids
            if unknown_elements:
                raise ValueError(f"Zone '{zone.name}' references unknown network elements.")
            referenced = set(zone.primary_device_ids) | set(zone.backup_device_ids)
            missing_devices = referenced - known_binding_ids
            if missing_devices:
                raise ValueError(f"Zone '{zone.name}' references unknown protection devices.")
            for relationship in zone.backup_relationships:
                if relationship.primary_device_id not in zone.primary_device_ids:
                    raise ValueError("Backup relationship primary is not assigned to its zone.")
                if relationship.backup_device_id not in zone.backup_device_ids:
                    raise ValueError("Backup relationship backup is not assigned to its zone.")
            if set(zone.backup_device_ids) != {
                item.backup_device_id for item in zone.backup_relationships
            }:
                raise ValueError(
                    f"Every backup device in zone '{zone.name}' must have an explicit "
                    "primary-device relationship."
                )
            for primary_id in zone.primary_device_ids:
                binding = next(item for item in binding_tuple if item.id == primary_id)
                if (
                    binding.monitored_equipment_id not in zone.protected_element_ids
                    and resolved_bus_ids[primary_id] not in zone.protected_element_ids
                ):
                    raise ValueError(
                        f"Primary device '{binding.device.name}' does not monitor an element "
                        f"inside protection zone '{zone.name}'."
                    )
            assigned.update(referenced)
        for binding in binding_tuple:
            if binding.id not in assigned:
                diagnostics.append(
                    DomainDiagnostic(
                        code="PROTECTION-DEVICE-NOT-ASSIGNED-TO-ZONE",
                        message=(
                            f"Protection device '{binding.device.name}' is attached to the "
                            "network but is not assigned to a protection zone."
                        ),
                        severity=DiagnosticSeverity.WARNING,
                        entity_id=binding.id,
                    )
                )

        advanced_ids = [item.id for item in advanced_tuple]
        if len(advanced_ids) != len(set(advanced_ids)):
            raise ValueError("Advanced protection function IDs must be unique.")
        if set(advanced_ids) & set(binding_ids):
            raise ValueError("Advanced function IDs cannot collide with primary device IDs.")
        zones_by_id = {item.id: item for item in zone_tuple}
        for advanced_binding in advanced_tuple:
            equipment = equipment_by_id.get(advanced_binding.protected_equipment_id)
            if equipment is None:
                raise ValueError("Advanced protection function references unknown equipment.")
            zone = zones_by_id.get(advanced_binding.zone_id)
            if zone is None or equipment.id not in zone.protected_element_ids:
                raise ValueError(
                    "Advanced protection function must reference a zone containing its equipment."
                )
            if any(
                terminal_id not in terminals_by_id
                or terminals_by_id[terminal_id].equipment_id != equipment.id
                for terminal_id in advanced_binding.monitored_terminal_ids
            ):
                raise ValueError(
                    "Advanced protection terminals must belong to monitored equipment."
                )
            if any(item not in connections for item in advanced_binding.monitored_terminal_ids):
                raise ValueError("Every advanced protection terminal must be connected to a bus.")
            function = advanced_binding.function
            if isinstance(function, DifferentialProtectionSettings):
                expected_family = (
                    EquipmentFamily.TRANSMISSION
                    if function.kind is DifferentialProtectionKind.LINE
                    else EquipmentFamily.TRANSFORMER
                )
                if equipment.family is not expected_family or len(equipment.terminals) != 2:
                    raise ValueError(
                        "87 differential settings currently require a two-terminal line/cable "
                        "or two-winding transformer of the matching kind."
                    )
            elif isinstance(function, DistanceProtectionSettings):
                if equipment.family is not EquipmentFamily.TRANSMISSION:
                    raise ValueError(
                        "Distance protection 21 currently supports lines and cables only."
                    )
            elif isinstance(function, DirectionalOvercurrentSettings):
                if equipment.family not in {
                    EquipmentFamily.TRANSMISSION,
                    EquipmentFamily.TRANSFORMER,
                }:
                    raise ValueError("Directional overcurrent requires a supported branch element.")
                relay_binding = next(
                    (item for item in binding_tuple if item.id == function.relay.id), None
                )
                if relay_binding is None or relay_binding.device != function.relay:
                    raise ValueError(
                        "Directional supervision must wrap the exact 50/51 relay bound "
                        "to the protection network."
                    )
                if (
                    relay_binding.monitored_equipment_id != equipment.id
                    or relay_binding.monitored_terminal_id
                    != advanced_binding.monitored_terminal_ids[0]
                ):
                    raise ValueError(
                        "Directional relay binding must use the advanced function's "
                        "equipment and monitored terminal."
                    )

        ct_device_ids = [item.protection_device_id for item in ct_performance_tuple]
        if len(ct_device_ids) != len(set(ct_device_ids)):
            raise ValueError("A protection device can only have one CT performance model.")
        ct_model_ids = [item.performance_model.id for item in ct_performance_tuple]
        if len(ct_model_ids) != len(set(ct_model_ids)):
            raise ValueError("CT performance model IDs must be unique.")
        bindings_by_id = {item.id: item for item in binding_tuple}
        for ct_binding in ct_performance_tuple:
            device_binding = bindings_by_id.get(ct_binding.protection_device_id)
            if device_binding is None or not isinstance(device_binding.device, OvercurrentRelay):
                raise ValueError("CT performance models must reference a bound overcurrent relay.")
            if (
                device_binding.device.current_transformer
                != ct_binding.performance_model.current_transformer
            ):
                raise ValueError("CT performance ratio must match the relay CT ratio.")

        return ProtectionNetworkModel(
            network_id=network.id,
            bindings=binding_tuple,
            zones=zone_tuple,
            binding_bus_ids=resolved_bus_ids,
            binding_equipment_names=resolved_equipment_names,
            diagnostics=tuple(diagnostics),
            advanced_function_bindings=advanced_tuple,
            ct_performance_bindings=ct_performance_tuple,
        )
