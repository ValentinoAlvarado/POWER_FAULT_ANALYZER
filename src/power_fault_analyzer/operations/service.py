"""Operating-topology analysis: switching, islands and source reachability."""
from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from itertools import combinations
from uuid import UUID

from .adapter import network_to_snapshot
from .models import (
    BusOperatingResult,
    BusOperatingState,
    DiagnosticSeverity,
    EquipmentOperatingResult,
    IslandResult,
    NetworkSnapshot,
    OperatingScenario,
    OperatingTopologyResult,
    OperationalDiagnostic,
    SwitchPosition,
)


class OperatingScenarioError(ValueError):
    """Scenario overrides do not match the physical network model."""


class OperatingTopologyService:
    """Analyze connectivity without mutating the physical network.

    Connectivity is calculated from explicit terminal-to-bus associations.
    Every in-service, closed, multi-terminal item joins its distinct connected
    buses.  Open switching devices and out-of-service equipment contribute no
    connectivity edge. Sources seed energization; reachability propagates over
    the resulting undirected graph.
    """

    def analyze(
        self,
        network: object,
        scenario: OperatingScenario,
        *,
        source_equipment_ids: tuple[UUID, ...] | None = None,
    ) -> OperatingTopologyResult:
        snapshot = network_to_snapshot(network, source_equipment_ids=source_equipment_ids)
        return self.analyze_snapshot(snapshot, scenario)

    def analyze_workspace(
        self,
        workspace: object,
        scenario: OperatingScenario,
        *,
        source_equipment_ids: tuple[UUID, ...] | None = None,
    ) -> OperatingTopologyResult:
        """Convenience entry point for PFA's NetworkWorkspace use-case object."""
        network = getattr(workspace, "network", None)
        if network is None:
            raise TypeError("workspace must expose its canonical Network as .network")
        return self.analyze(
            network, scenario, source_equipment_ids=source_equipment_ids
        )

    def analyze_snapshot(
        self,
        snapshot: NetworkSnapshot,
        scenario: OperatingScenario,
    ) -> OperatingTopologyResult:
        equipment_by_id = {item.equipment_id: item for item in snapshot.equipment}
        bus_by_id = {item.bus_id: item for item in snapshot.buses}
        switch_ids = {item.equipment_id for item in snapshot.equipment if item.is_switch}
        source_ids = {item.equipment_id for item in snapshot.equipment if item.is_source}

        self._validate_overrides(scenario, equipment_by_id, switch_ids, source_ids)

        terminal_to_bus = {item.terminal_id: item.bus_id for item in snapshot.connections}
        buses_by_equipment: dict[UUID, tuple[UUID, ...]] = {}
        for equipment in snapshot.equipment:
            connected = tuple(
                dict.fromkeys(
                    terminal_to_bus[terminal_id]
                    for terminal_id in equipment.terminal_ids
                    if terminal_id in terminal_to_bus
                )
            )
            buses_by_equipment[equipment.equipment_id] = connected

        adjacency: dict[UUID, set[UUID]] = {bus_id: set() for bus_id in bus_by_id}
        active_equipment: dict[UUID, bool] = {}
        switch_positions: dict[UUID, SwitchPosition | None] = {}
        source_enabled: dict[UUID, bool | None] = {}
        source_buses: dict[UUID, set[UUID]] = defaultdict(set)
        grounding_by_bus: dict[UUID, set[UUID]] = defaultdict(set)
        diagnostics: list[OperationalDiagnostic] = []

        for equipment in snapshot.equipment:
            equipment_id = equipment.equipment_id
            in_service = scenario.equipment_in_service.get(
                equipment_id, equipment.default_in_service
            )
            position = None
            if equipment.is_switch:
                position = scenario.switch_positions.get(
                    equipment_id, equipment.default_switch_position
                )
            enabled = scenario.source_enabled.get(equipment_id, True) if equipment.is_source else None
            is_active = in_service and (position is not SwitchPosition.OPEN)
            active_equipment[equipment_id] = is_active
            switch_positions[equipment_id] = position
            source_enabled[equipment_id] = enabled

            connected_buses = buses_by_equipment[equipment_id]
            expected_connections = len(equipment.terminal_ids)
            connected_terminal_count = sum(
                terminal_id in terminal_to_bus for terminal_id in equipment.terminal_ids
            )
            if expected_connections and connected_terminal_count == 0:
                diagnostics.append(
                    OperationalDiagnostic(
                        code="EQUIPMENT_WITHOUT_BUS_CONNECTION",
                        message=f"Equipment {equipment.name!r} has no connected terminal.",
                        entity_id=equipment_id,
                    )
                )
            elif connected_terminal_count < expected_connections:
                diagnostics.append(
                    OperationalDiagnostic(
                        code="EQUIPMENT_TERMINAL_UNCONNECTED",
                        message=(
                            f"Equipment {equipment.name!r} has {connected_terminal_count} of "
                            f"{expected_connections} terminals connected to buses."
                        ),
                        entity_id=equipment_id,
                    )
                )
            if equipment.is_source and in_service and enabled:
                if not connected_buses:
                    diagnostics.append(
                        OperationalDiagnostic(
                            code="SOURCE_NOT_CONNECTED",
                            message=f"Source {equipment.name!r} is enabled but has no connected bus.",
                            severity=DiagnosticSeverity.WARNING,
                            entity_id=equipment_id,
                        )
                    )
                else:
                    for bus_id in connected_buses:
                        source_buses[bus_id].add(equipment_id)

            # A source is a graph root, not a bus-to-bus branch.  A two-terminal
            # source is treated as a source boundary, not an inter-bus jumper.
            if equipment.is_grounding_switch:
                if is_active:
                    for bus_id in connected_buses:
                        grounding_by_bus[bus_id].add(equipment_id)
                    if len(connected_buses) > 1:
                        diagnostics.append(
                            OperationalDiagnostic(
                                code="GROUNDING_SWITCH_SPANS_MULTIPLE_BUSES",
                                message=(
                                    f"Grounding switch {equipment.name!r} is mapped to multiple buses; "
                                    "these buses are flagged grounded but are not electrically joined by this analysis."
                                ),
                                severity=DiagnosticSeverity.WARNING,
                                entity_id=equipment_id,
                            )
                        )
                continue
            if equipment.is_source or not is_active or len(connected_buses) < 2:
                continue
            for first, second in combinations(connected_buses, 2):
                adjacency[first].add(second)
                adjacency[second].add(first)

        components = self._components(tuple(bus_by_id), adjacency)
        bus_to_island: dict[UUID, int] = {}
        island_results: list[IslandResult] = []
        energized_bus_ids = self._reachable(source_buses.keys(), adjacency)

        for island_id, bus_ids in enumerate(components, start=1):
            for bus_id in bus_ids:
                bus_to_island[bus_id] = island_id
            island_sources = sorted(
                {source_id for bus_id in bus_ids for source_id in source_buses.get(bus_id, set())},
                key=str,
            )
            island_results.append(
                IslandResult(
                    island_id=island_id,
                    bus_ids=bus_ids,
                    bus_names=tuple(bus_by_id[item].name for item in bus_ids),
                    energized=any(item in energized_bus_ids for item in bus_ids),
                    source_equipment_ids=tuple(island_sources),
                )
            )

        bus_results = tuple(
            BusOperatingResult(
                bus_id=item.bus_id,
                bus_name=item.name,
                state=(
                    BusOperatingState.ENERGIZED
                    if item.bus_id in energized_bus_ids
                    else BusOperatingState.DEENERGIZED
                ),
                island_id=bus_to_island[item.bus_id],
                source_reachable=item.bus_id in energized_bus_ids,
                grounded=item.bus_id in grounding_by_bus,
                grounding_equipment_ids=tuple(sorted(grounding_by_bus.get(item.bus_id, set()), key=str)),
            )
            for item in snapshot.buses
        )

        equipment_results = tuple(
            EquipmentOperatingResult(
                equipment_id=item.equipment_id,
                equipment_name=item.name,
                family=item.family,
                in_service=scenario.equipment_in_service.get(
                    item.equipment_id, item.default_in_service
                ),
                switch_position=switch_positions[item.equipment_id],
                connected_bus_ids=buses_by_equipment[item.equipment_id],
                contributes_to_connectivity=(
                    active_equipment[item.equipment_id]
                    and not item.is_source
                    and not item.is_grounding_switch
                    and len(buses_by_equipment[item.equipment_id]) >= 2
                ),
                is_source=item.is_source,
                source_enabled=source_enabled[item.equipment_id],
            )
            for item in snapshot.equipment
        )

        for island in island_results:
            if not island.energized:
                diagnostics.append(
                    OperationalDiagnostic(
                        code="UNENERGIZED_ISLAND",
                        message=(
                            f"Island {island.island_id} ({', '.join(island.bus_names)}) "
                            "has no enabled source reachable through in-service equipment."
                        ),
                        severity=DiagnosticSeverity.WARNING,
                        entity_id=island.bus_ids[0] if island.bus_ids else None,
                    )
                )

        for bus_id in grounding_by_bus:
            if bus_id in energized_bus_ids:
                bus_name = bus_by_id[bus_id].name
                diagnostics.append(
                    OperationalDiagnostic(
                        code="ENERGIZED_BUS_GROUNDED",
                        message=(
                            f"Bus {bus_name!r} is source-reachable while a grounding switch is closed. "
                            "This is an operationally hazardous condition and requires engineering review."
                        ),
                        severity=DiagnosticSeverity.ERROR,
                        entity_id=bus_id,
                    )
                )

        # Open switches are operational breaks even though their terminals remain
        # connected in the canonical physical Network aggregate.
        for item in equipment_results:
            if item.switch_position is SwitchPosition.OPEN:
                diagnostics.append(
                    OperationalDiagnostic(
                        code="SWITCH_OPEN",
                        message=f"Switch {item.equipment_name!r} is open in scenario {scenario.name!r}.",
                        severity=DiagnosticSeverity.INFO,
                        entity_id=item.equipment_id,
                    )
                )

        return OperatingTopologyResult(
            network_id=snapshot.network_id,
            scenario_id=scenario.scenario_id,
            scenario_name=scenario.name,
            buses=bus_results,
            islands=tuple(island_results),
            equipment=equipment_results,
            diagnostics=tuple(diagnostics),
        )

    @staticmethod
    def _validate_overrides(
        scenario: OperatingScenario,
        equipment_by_id: dict[UUID, object],
        switch_ids: set[UUID],
        source_ids: set[UUID],
    ) -> None:
        all_ids = set(equipment_by_id)
        unknown = (
            set(scenario.switch_positions)
            | set(scenario.equipment_in_service)
            | set(scenario.source_enabled)
        ) - all_ids
        if unknown:
            raise OperatingScenarioError(f"Scenario references unknown equipment IDs: {sorted(map(str, unknown))}")
        wrong_switches = set(scenario.switch_positions) - switch_ids
        if wrong_switches:
            raise OperatingScenarioError(
                f"Switch-position overrides reference non-switch equipment: {sorted(map(str, wrong_switches))}"
            )
        wrong_sources = set(scenario.source_enabled) - source_ids
        if wrong_sources:
            raise OperatingScenarioError(
                f"Source-enable overrides reference non-source equipment: {sorted(map(str, wrong_sources))}"
            )

    @staticmethod
    def _components(
        bus_ids: tuple[UUID, ...], adjacency: dict[UUID, set[UUID]]
    ) -> tuple[tuple[UUID, ...], ...]:
        remaining = set(bus_ids)
        components: list[tuple[UUID, ...]] = []
        while remaining:
            root = min(remaining, key=str)
            queue = deque([root])
            remaining.remove(root)
            found: list[UUID] = []
            while queue:
                current = queue.popleft()
                found.append(current)
                for neighbour in sorted(adjacency[current], key=str):
                    if neighbour in remaining:
                        remaining.remove(neighbour)
                        queue.append(neighbour)
            components.append(tuple(sorted(found, key=str)))
        return tuple(components)

    @staticmethod
    def _reachable(
        roots: Iterable[UUID], adjacency: dict[UUID, set[UUID]]
    ) -> set[UUID]:
        reached = set(roots)
        queue = deque(sorted(reached, key=str))
        while queue:
            current = queue.popleft()
            for neighbour in adjacency[current]:
                if neighbour not in reached:
                    reached.add(neighbour)
                    queue.append(neighbour)
        return reached
