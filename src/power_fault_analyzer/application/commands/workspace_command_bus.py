"""Atomic command dispatcher for the shared PFA NetworkWorkspace.

The desktop UI keeps its native QUndoStack for user-facing undo/redo.  This
application-level bus is the transaction boundary used by both that UI and the
Python automation API: a command either commits a fully validated workspace or
restores the exact pre-command state.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from threading import RLock
from uuid import UUID, uuid4

from power_fault_analyzer.application.commands.workspace_commands import (
    AddBus,
    AddSynchronousGenerator,
    AddTheveninSource,
    AddTransmissionLine,
    MoveDiagramElements,
    MoveDiagramSymbol,
    RegisterEquipment,
    RemoveBus,
    RemoveDiagramLabel,
    RemoveDiagramPosition,
    RemoveDiagramRotation,
    RemoveDiagramSymbol,
    RemoveEquipment,
    RemoveOperatingScenario,
    RotateBusbar,
    SetActiveOperatingScenario,
    SetDiagramGrid,
    SetEquipmentSwitchPosition,
    SetOperatingScenarioSwitchPosition,
    UpdateBus,
    UpsertDiagramLabel,
    UpsertDiagramSymbol,
    UpsertOperatingScenario,
    WorkspaceCommand,
)
from power_fault_analyzer.application.use_cases.network_editing import (
    LineInput,
    SynchronousGeneratorInput,
)
from power_fault_analyzer.application.use_cases.network_workspace import (
    DiagramLabelPlacement,
    DiagramSymbolPlacement,
    NetworkWorkspace,
)
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.enums.bus_kind import BusKind
from power_fault_analyzer.domain.enums.switching_device import SwitchPosition
from power_fault_analyzer.domain.interfaces.network_contracts import ElectricalEquipment
from power_fault_analyzer.operations.models import (
    OperatingScenario,
)
from power_fault_analyzer.operations.models import (
    SwitchPosition as OperatingSwitchPosition,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WorkspaceCommandEvent:
    command_id: UUID
    command_name: str
    source: str
    network_id: UUID
    revision: int
    committed_at: datetime


class WorkspaceCommandBus:
    """Serialize, validate and atomically commit commands against one workspace."""

    def __init__(self, workspace: NetworkWorkspace, *, source: str = "application") -> None:
        if not isinstance(workspace, NetworkWorkspace):
            raise TypeError("workspace must be a NetworkWorkspace.")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source must be a non-empty string.")
        self.workspace = workspace
        self.source = source.strip()
        self._revision = 0
        self._lock = RLock()
        self._listeners: dict[UUID, Callable[[WorkspaceCommandEvent], None]] = {}
        self._events: list[WorkspaceCommandEvent] = []

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    @property
    def events(self) -> tuple[WorkspaceCommandEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def subscribe(self, listener: Callable[[WorkspaceCommandEvent], None]) -> Callable[[], None]:
        if not callable(listener):
            raise TypeError("listener must be callable.")
        token = uuid4()
        with self._lock:
            self._listeners[token] = listener

        def unsubscribe() -> None:
            with self._lock:
                self._listeners.pop(token, None)

        return unsubscribe

    def execute(self, command: WorkspaceCommand, *, expected_revision: int | None = None):
        """Execute one command; restore the workspace in place if it fails."""
        return self.execute_many((command,), expected_revision=expected_revision)[0]

    def execute_many(
        self,
        commands: Iterable[WorkspaceCommand],
        *,
        expected_revision: int | None = None,
    ) -> tuple[object, ...]:
        """Commit a group as one transaction, or roll the entire group back."""
        batch = tuple(commands)
        if not batch:
            raise ValueError("At least one workspace command is required.")
        for command in batch:
            if not isinstance(command, WorkspaceCommand):
                raise TypeError("Every command must expose a name and execute(workspace).")
            if not isinstance(command.name, str) or not command.name.strip():
                raise ValueError("Command names must be non-empty strings.")

        with self._lock:
            if expected_revision is not None and expected_revision != self._revision:
                raise RuntimeError(
                    f"Stale workspace revision {expected_revision}; "
                    f"current revision is {self._revision}."
                )
            before = copy.deepcopy(self.workspace)
            try:
                results = tuple(command.execute(self.workspace) for command in batch)
                # Re-run aggregate/workspace invariants after all command mutations.
                self.workspace.__post_init__()
            except Exception:
                self._restore(before)
                raise

            self._revision += 1
            event = WorkspaceCommandEvent(
                command_id=uuid4(),
                command_name=" + ".join(command.name for command in batch),
                source=self.source,
                network_id=self.workspace.network.id,
                revision=self._revision,
                committed_at=datetime.now(UTC),
            )
            self._events.append(event)
            if len(self._events) > 1000:
                del self._events[:-1000]
            listeners = tuple(self._listeners.values())

        # Observer failures must never roll back an already committed domain command.
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                _LOGGER.exception("Workspace command event listener failed.")
        return results

    def _restore(self, snapshot: NetworkWorkspace) -> None:
        # Preserve both workspace and aggregate identity. External adapters may
        # hold references to the aggregate while a transaction is in progress.
        current_network = self.workspace.network
        snapshot_network = copy.deepcopy(snapshot.network)
        for attribute in Network.__slots__:
            setattr(
                current_network,
                attribute,
                copy.deepcopy(getattr(snapshot_network, attribute)),
            )
        for descriptor in fields(NetworkWorkspace):
            if descriptor.name == "network":
                continue
            setattr(
                self.workspace,
                descriptor.name,
                copy.deepcopy(getattr(snapshot, descriptor.name)),
            )


class NetworkWorkspaceCommands:
    """Shared imperative API used by Workbench widgets and Code & Automation."""

    def __init__(self, workspace: NetworkWorkspace, *, source: str = "api") -> None:
        self.workspace = workspace
        self.bus = WorkspaceCommandBus(workspace, source=source)

    @property
    def revision(self) -> int:
        return self.bus.revision

    def subscribe(self, listener: Callable[[WorkspaceCommandEvent], None]) -> Callable[[], None]:
        return self.bus.subscribe(listener)

    def execute(self, command: WorkspaceCommand, *, expected_revision: int | None = None):
        return self.bus.execute(command, expected_revision=expected_revision)

    def execute_many(
        self, commands: Iterable[WorkspaceCommand], *, expected_revision: int | None = None
    ) -> tuple[object, ...]:
        return self.bus.execute_many(commands, expected_revision=expected_revision)

    def move_elements(self, positions: dict[UUID, tuple[float, float]]):
        command = MoveDiagramElements(
            tuple(
                (identifier, coordinates[0], coordinates[1])
                for identifier, coordinates in positions.items()
            )
        )
        return self.bus.execute(command)

    def clear_diagram_position(self, element_id: UUID):
        return self.bus.execute(RemoveDiagramPosition(element_id))

    def clear_diagram_rotation(self, bus_id: UUID):
        return self.bus.execute(RemoveDiagramRotation(bus_id))

    def move_symbol(
        self,
        instance_id: UUID,
        x: float,
        y: float,
        *,
        rotation_deg: float | None = None,
        label: str | None = None,
    ):
        return self.bus.execute(MoveDiagramSymbol(instance_id, x, y, rotation_deg, label))

    def rotate_bus(self, bus_id: UUID, rotation_deg: float) -> float:
        return self.bus.execute(RotateBusbar(bus_id, rotation_deg))

    def upsert_symbol(self, placement: DiagramSymbolPlacement) -> DiagramSymbolPlacement:
        return self.bus.execute(UpsertDiagramSymbol(placement))

    def remove_symbol(self, instance_id: UUID) -> DiagramSymbolPlacement:
        return self.bus.execute(RemoveDiagramSymbol(instance_id))

    def upsert_operating_scenario(self, scenario: OperatingScenario) -> OperatingScenario | None:
        return self.bus.execute(UpsertOperatingScenario(scenario))

    def remove_operating_scenario(self, scenario_id: UUID) -> OperatingScenario:
        return self.bus.execute(RemoveOperatingScenario(scenario_id))

    def set_active_operating_scenario(self, scenario_id: UUID | None) -> UUID | None:
        return self.bus.execute(SetActiveOperatingScenario(scenario_id))

    def set_operating_switch_position(
        self, scenario_id: UUID, equipment_id: UUID, position: OperatingSwitchPosition
    ) -> OperatingScenario:
        return self.bus.execute(
            SetOperatingScenarioSwitchPosition(scenario_id, equipment_id, position)
        )

    def set_switch_position(self, equipment_id: UUID, position: SwitchPosition):
        """Change the physical model state; use set_operating_switch_position for simulation."""
        return self.bus.execute(SetEquipmentSwitchPosition(equipment_id, position))

    def upsert_label(self, label: DiagramLabelPlacement) -> DiagramLabelPlacement:
        return self.bus.execute(UpsertDiagramLabel(label))

    def remove_label(self, label_id: UUID) -> DiagramLabelPlacement:
        return self.bus.execute(RemoveDiagramLabel(label_id))

    def register_equipment(
        self,
        equipment: ElectricalEquipment,
        connections: tuple[tuple[UUID, UUID], ...],
        *,
        position: tuple[float, float] | None = None,
    ) -> ElectricalEquipment:
        return self.bus.execute(RegisterEquipment(equipment, connections, position))

    def add_equivalent_source(
        self,
        *,
        name: str,
        bus_id: UUID,
        base_power_mva: float,
        positive_sequence_pu: complex,
        negative_sequence_pu: complex,
        zero_sequence_pu: complex,
        prefault_voltage_pu: complex,
        frequency_hz: float = 60.0,
        position: tuple[float, float] | None = None,
    ):
        return self.bus.execute(
            AddTheveninSource(
                name, bus_id, base_power_mva, positive_sequence_pu,
                negative_sequence_pu, zero_sequence_pu, prefault_voltage_pu,
                frequency_hz, position,
            )
        )

    def add_generator(
        self,
        specification: SynchronousGeneratorInput,
        *,
        position: tuple[float, float] | None = None,
    ):
        return self.bus.execute(AddSynchronousGenerator(specification, position))

    def add_line(self, specification: LineInput):
        return self.bus.execute(AddTransmissionLine(specification))

    def add_bus(
        self,
        name: str,
        nominal_voltage_kv: float,
        x: float,
        y: float,
        *,
        kind: BusKind = BusKind.BUSBAR,
    ):
        return self.bus.execute(AddBus(name, nominal_voltage_kv, x, y, kind))

    def update_bus(self, bus_id: UUID, new_name: str, nominal_voltage_kv: float):
        return self.bus.execute(UpdateBus(bus_id, new_name, nominal_voltage_kv))

    def remove_bus(self, bus_id: UUID) -> None:
        self.bus.execute(RemoveBus(bus_id))

    def remove_equipment(self, equipment_id: UUID) -> None:
        self.bus.execute(RemoveEquipment(equipment_id))

    def set_grid(self, spacing: float, enabled: bool) -> tuple[float, bool]:
        return self.bus.execute(SetDiagramGrid(spacing, enabled))
