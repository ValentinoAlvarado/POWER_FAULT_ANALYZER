"""Network aggregate root enforcing topology and connection invariants."""

from __future__ import annotations

from uuid import UUID, uuid4

from power_fault_analyzer.domain.entities._validation import validate_non_empty_name
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.exceptions.network_exceptions import (
    DuplicateEntityError,
    EntityInUseError,
    EntityNotFoundError,
    EquipmentConfigurationError,
    InvalidEquipmentError,
    TerminalAlreadyConnectedError,
    VoltageIncompatibilityError,
)
from power_fault_analyzer.domain.interfaces.network_contracts import (
    BusContract,
    ElectricalEquipment,
    TerminalContract,
)
from power_fault_analyzer.domain.interfaces.validation_contracts import (
    VoltageCompatibilityPolicy,
)
from power_fault_analyzer.domain.services.voltage_compatibility_policy import (
    NominalVoltageCompatibilityPolicy,
)
from power_fault_analyzer.domain.value_objects.connection import Connection
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)
from power_fault_analyzer.domain.value_objects.voltage import (
    Voltage,
    VoltageReference,
)


class Network:
    """Aggregate root for a physical balanced three-phase electrical network.

    The aggregate owns the authoritative indexes for buses, equipment,
    terminals, and terminal-to-bus connections. It exposes immutable tuple
    snapshots so callers cannot mutate its internal collections.

    Operating switch positions are intentionally outside this aggregate's
    initial scope; they belong to operating scenarios.
    """

    __slots__ = (
        "_buses",
        "_connections",
        "_equipment",
        "_id",
        "_name",
        "_terminals",
        "_voltage_policy",
    )

    def __init__(
        self,
        name: str,
        *,
        id: UUID | None = None,
        voltage_compatibility_policy: VoltageCompatibilityPolicy | None = None,
    ) -> None:
        validate_non_empty_name(name)
        if id is not None and not isinstance(id, UUID):
            raise TypeError("id must be a UUID or None.")
        if voltage_compatibility_policy is None:
            voltage_compatibility_policy = NominalVoltageCompatibilityPolicy()
        if not callable(getattr(voltage_compatibility_policy, "are_compatible", None)):
            raise TypeError("voltage_compatibility_policy must implement are_compatible().")

        self._id = id if id is not None else uuid4()
        self._name = name.strip()
        self._buses: dict[UUID, BusContract] = {}
        self._equipment: dict[UUID, ElectricalEquipment] = {}
        self._terminals: dict[UUID, TerminalContract] = {}
        self._connections: dict[UUID, Connection] = {}
        self._voltage_policy: VoltageCompatibilityPolicy = voltage_compatibility_policy

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def buses(self) -> tuple[BusContract, ...]:
        return tuple(self._buses.values())

    @property
    def equipment(self) -> tuple[ElectricalEquipment, ...]:
        return tuple(self._equipment.values())

    @property
    def terminals(self) -> tuple[TerminalContract, ...]:
        return tuple(self._terminals.values())

    @property
    def connections(self) -> tuple[Connection, ...]:
        return tuple(self._connections.values())

    def add_bus(self, bus: BusContract) -> None:
        self._validate_bus_contract(bus)
        if (
            bus.id == self.id
            or bus.id in self._buses
            or bus.id in self._equipment
            or bus.id in self._terminals
        ):
            raise DuplicateEntityError(
                f"Electrical identifier '{bus.id}' is already registered in this network."
            )
        self._ensure_unique_name(bus.name)
        self._buses[bus.id] = bus

    def add_equipment(self, equipment: ElectricalEquipment) -> None:
        self._validate_equipment_contract(equipment)
        if (
            equipment.id == self.id
            or equipment.id in self._equipment
            or equipment.id in self._buses
            or equipment.id in self._terminals
        ):
            raise DuplicateEntityError(
                f"Electrical identifier '{equipment.id}' is already registered in this network."
            )
        self._ensure_unique_name(equipment.name)

        terminal_ids = [terminal.id for terminal in equipment.terminals]
        if len(terminal_ids) != len(set(terminal_ids)):
            raise InvalidEquipmentError("Equipment contains duplicate terminal IDs.")
        registered_ids = set(self._buses) | set(self._equipment) | set(self._terminals)
        collisions = set(terminal_ids).intersection(registered_ids | {equipment.id, self.id})
        if collisions:
            collision = next(iter(collisions))
            raise DuplicateEntityError(
                f"Terminal ID '{collision}' is already registered in this network."
            )

        diagnostics = equipment.validate_configuration()
        if not isinstance(diagnostics, tuple) or any(
            not isinstance(item, DomainDiagnostic) for item in diagnostics
        ):
            raise InvalidEquipmentError(
                "validate_configuration() must return tuple[DomainDiagnostic, ...]."
            )
        errors = tuple(item for item in diagnostics if item.severity is DiagnosticSeverity.ERROR)
        if errors:
            summary = "; ".join(f"{item.code}: {item.message}" for item in errors)
            raise EquipmentConfigurationError(summary)

        # Mutations occur only after every validation has succeeded.
        self._equipment[equipment.id] = equipment
        self._terminals.update({terminal.id: terminal for terminal in equipment.terminals})

    def replace_equipment(self, equipment: ElectricalEquipment) -> None:
        """Replace an equipment revision while preserving its identity and terminals.

        This operation is intentionally narrower than remove/add: existing terminal
        connections remain valid, so only parameters or operating state may change.
        """
        self._validate_equipment_contract(equipment)
        try:
            current = self._equipment[equipment.id]
        except KeyError as exc:
            raise EntityNotFoundError("Equipment", equipment.id) from exc
        current_terminal_ids = tuple(item.id for item in current.terminals)
        replacement_terminal_ids = tuple(item.id for item in equipment.terminals)
        if (
            current.family is not equipment.family
            or current_terminal_ids != replacement_terminal_ids
            or current.terminals != equipment.terminals
        ):
            raise InvalidEquipmentError(
                "Equipment replacement must preserve family, terminal identity, order and data."
            )
        diagnostics = equipment.validate_configuration()
        if not isinstance(diagnostics, tuple) or any(
            not isinstance(item, DomainDiagnostic) for item in diagnostics
        ):
            raise InvalidEquipmentError(
                "validate_configuration() must return tuple[DomainDiagnostic, ...]."
            )
        errors = tuple(item for item in diagnostics if item.severity is DiagnosticSeverity.ERROR)
        if errors:
            summary = "; ".join(f"{item.code}: {item.message}" for item in errors)
            raise EquipmentConfigurationError(summary)
        self._equipment[equipment.id] = equipment

    def connect(self, terminal_id: UUID, bus_id: UUID) -> Connection:
        terminal = self._get_terminal(terminal_id)
        bus = self.get_bus(bus_id)

        if terminal_id in self._connections:
            existing = self._connections[terminal_id]
            raise TerminalAlreadyConnectedError(
                f"Terminal '{terminal_id}' is already connected to bus "
                f"'{existing.bus_id}'. Disconnect it before reconnecting."
            )

        compatible = self._voltage_policy.are_compatible(
            terminal.rated_voltage, bus.nominal_voltage
        )
        if not isinstance(compatible, bool):
            raise TypeError("VoltageCompatibilityPolicy.are_compatible() must return bool.")
        if not compatible:
            raise VoltageIncompatibilityError(
                f"Terminal '{terminal.designation}' rated at "
                f"{terminal.rated_voltage.value_kv:g} kV is incompatible with "
                f"bus '{bus.name}' at {bus.nominal_voltage.value_kv:g} kV."
            )

        connection = Connection(terminal_id=terminal_id, bus_id=bus_id)
        self._connections[terminal_id] = connection
        return connection

    def disconnect(self, terminal_id: UUID) -> None:
        self._get_terminal(terminal_id)
        if terminal_id not in self._connections:
            raise EntityNotFoundError("Connection", terminal_id)
        del self._connections[terminal_id]

    def remove_bus(self, bus_id: UUID) -> None:
        self.get_bus(bus_id)
        connected_terminals = tuple(
            connection.terminal_id
            for connection in self._connections.values()
            if connection.bus_id == bus_id
        )
        if connected_terminals:
            raise EntityInUseError(
                f"Bus '{bus_id}' cannot be removed while {len(connected_terminals)} "
                "terminal connection(s) reference it. Disconnect them first."
            )
        del self._buses[bus_id]

    def remove_equipment(self, equipment_id: UUID) -> None:
        self.get_equipment(equipment_id)
        # Use the aggregate-owned terminal index rather than a live plugin property.
        # This keeps deletion consistent with the registration snapshot.
        terminal_ids = tuple(
            terminal_id
            for terminal_id, terminal in self._terminals.items()
            if terminal.equipment_id == equipment_id
        )
        for terminal_id in terminal_ids:
            self._connections.pop(terminal_id, None)
            self._terminals.pop(terminal_id, None)
        del self._equipment[equipment_id]

    def get_bus(self, bus_id: UUID) -> BusContract:
        if not isinstance(bus_id, UUID):
            raise TypeError("bus_id must be a UUID.")
        try:
            return self._buses[bus_id]
        except KeyError as exc:
            raise EntityNotFoundError("Bus", bus_id) from exc

    def get_equipment(self, equipment_id: UUID) -> ElectricalEquipment:
        if not isinstance(equipment_id, UUID):
            raise TypeError("equipment_id must be a UUID.")
        try:
            return self._equipment[equipment_id]
        except KeyError as exc:
            raise EntityNotFoundError("Equipment", equipment_id) from exc

    def get_terminal(self, terminal_id: UUID) -> TerminalContract:
        return self._get_terminal(terminal_id)

    def get_connection(self, terminal_id: UUID) -> Connection:
        self._get_terminal(terminal_id)
        try:
            return self._connections[terminal_id]
        except KeyError as exc:
            raise EntityNotFoundError("Connection", terminal_id) from exc

    def _get_terminal(self, terminal_id: UUID) -> TerminalContract:
        if not isinstance(terminal_id, UUID):
            raise TypeError("terminal_id must be a UUID.")
        try:
            return self._terminals[terminal_id]
        except KeyError as exc:
            raise EntityNotFoundError("Terminal", terminal_id) from exc

    def _ensure_unique_name(self, name: str) -> None:
        normalized = name.strip().casefold()
        existing_names = (
            item.name.strip().casefold()
            for item in (*self._buses.values(), *self._equipment.values())
        )
        if normalized in existing_names:
            raise DuplicateEntityError(
                f"An electrical element named '{name}' already exists in this network."
            )

    @staticmethod
    def _validate_bus_contract(bus: BusContract) -> None:
        if not isinstance(bus.id, UUID):
            raise TypeError("Bus contract id must be a UUID.")
        if not isinstance(bus.name, str) or not bus.name.strip():
            raise TypeError("Bus contract name must be a non-empty string.")
        if not isinstance(bus.nominal_voltage, Voltage):
            raise TypeError("Bus contract nominal_voltage must be a Voltage.")
        if bus.nominal_voltage.reference is not VoltageReference.LINE_TO_LINE:
            raise InvalidEquipmentError("Bus nominal voltage must use the line-to-line reference.")

    @staticmethod
    def _validate_equipment_contract(equipment: ElectricalEquipment) -> None:
        required_attributes = ("id", "name", "terminals", "family")
        missing = [name for name in required_attributes if not hasattr(equipment, name)]
        if missing:
            raise InvalidEquipmentError(
                f"Equipment is missing required contract members: {', '.join(missing)}."
            )
        if not isinstance(equipment.id, UUID):
            raise InvalidEquipmentError("Equipment id must be a UUID.")
        if not isinstance(equipment.name, str) or not equipment.name.strip():
            raise InvalidEquipmentError("Equipment name must be a non-empty string.")
        if not isinstance(equipment.family, EquipmentFamily):
            raise InvalidEquipmentError("Equipment family must be an EquipmentFamily.")
        if not isinstance(equipment.terminals, tuple) or not equipment.terminals:
            raise InvalidEquipmentError("Equipment terminals must be a non-empty immutable tuple.")
        if not callable(getattr(equipment, "validate_configuration", None)):
            raise InvalidEquipmentError("Equipment must implement validate_configuration().")
        terminals = equipment.terminals
        for terminal in terminals:
            if not isinstance(terminal, TerminalContract):
                raise InvalidEquipmentError(
                    "Every equipment terminal must satisfy TerminalContract."
                )
            if not isinstance(terminal.id, UUID):
                raise InvalidEquipmentError("Terminal id must be a UUID.")
            if not isinstance(terminal.equipment_id, UUID):
                raise InvalidEquipmentError("Terminal equipment_id must be a UUID.")
            if not isinstance(terminal.designation, str) or not terminal.designation.strip():
                raise InvalidEquipmentError("Terminal designation must be a non-empty string.")
            if not isinstance(terminal.rated_voltage, Voltage):
                raise InvalidEquipmentError("Terminal rated_voltage must be a Voltage.")
            if terminal.rated_voltage.reference is not VoltageReference.LINE_TO_LINE:
                raise InvalidEquipmentError(
                    "Terminal rated_voltage must use line-to-line reference."
                )
            if terminal.id == equipment.id:
                raise InvalidEquipmentError("A terminal ID cannot equal its owning equipment ID.")
            if terminal.equipment_id != equipment.id:
                raise InvalidEquipmentError(
                    f"Terminal '{terminal.id}' belongs to a different equipment ID."
                )
        terminal_ids = [terminal.id for terminal in terminals]
        if len(terminal_ids) != len(set(terminal_ids)):
            raise InvalidEquipmentError("Equipment contains duplicate terminal IDs.")
        designations = {terminal.designation.casefold() for terminal in terminals}
        if len(designations) != len(terminals):
            raise InvalidEquipmentError("Terminal designations must be unique within equipment.")
