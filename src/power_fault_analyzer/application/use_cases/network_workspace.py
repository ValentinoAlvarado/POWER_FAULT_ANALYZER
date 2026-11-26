"""Application workspace state; diagram coordinates are presentation metadata only."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from math import isfinite
from uuid import UUID, uuid4

from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult


@dataclass(frozen=True, slots=True)
class NetworkStudyRecord:
    """Immutable historical result snapshot for one physical-network fault study."""

    run_id: UUID
    executed_at: datetime
    project_name: str
    study_name: str
    network_id: UUID
    fault_bus_id: UUID
    fault_bus_name: str
    result: ShortCircuitResult

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, UUID)
            for value in (self.run_id, self.network_id, self.fault_bus_id)
        ):
            raise TypeError("run_id, network_id and fault_bus_id must be UUID values.")
        if not isinstance(self.executed_at, datetime) or self.executed_at.tzinfo is None:
            raise ValueError("executed_at must be a timezone-aware datetime.")
        for name in ("project_name", "study_name", "fault_bus_name"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")
        if not isinstance(self.result, ShortCircuitResult):
            raise TypeError("result must be a ShortCircuitResult.")
        if self.result.bus_id != self.fault_bus_id:
            raise ValueError("Study record fault bus differs from the numerical result.")

    @classmethod
    def create(
        cls,
        *,
        project_name: str,
        study_name: str,
        network_id: UUID,
        fault_bus_id: UUID,
        fault_bus_name: str,
        result: ShortCircuitResult,
    ) -> NetworkStudyRecord:
        return cls(
            run_id=uuid4(),
            executed_at=datetime.now(UTC),
            project_name=project_name,
            study_name=study_name,
            network_id=network_id,
            fault_bus_id=fault_bus_id,
            fault_bus_name=fault_bus_name,
            result=result,
        )


@dataclass(frozen=True, slots=True)
class DiagramSymbolPlacement:
    """Source-pinned symbol placement with optional explicit domain-terminal mapping.

    The placement is still presentation metadata. It never creates an equipment
    object or infers topology from overlaps; mappings only reference pre-existing
    equipment terminals and terminal-to-node connections.
    """

    instance_id: UUID
    asset_id: str
    x: float
    y: float
    rotation_deg: float = 0.0
    equipment_id: UUID | None = None
    terminal_mappings: tuple[tuple[str, UUID], ...] = ()
    label: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.instance_id, UUID):
            raise TypeError("instance_id must be a UUID.")
        if self.equipment_id is not None and not isinstance(self.equipment_id, UUID):
            raise TypeError("equipment_id must be a UUID or None.")
        if not isinstance(self.terminal_mappings, tuple):
            raise TypeError("terminal_mappings must be an immutable tuple.")
        source_ids: set[str] = set()
        equipment_ids: set[UUID] = set()
        for source_terminal_id, equipment_terminal_id in self.terminal_mappings:
            if not isinstance(source_terminal_id, str) or not source_terminal_id.strip():
                raise ValueError("Mapped source terminal identifiers cannot be empty.")
            if not isinstance(equipment_terminal_id, UUID):
                raise TypeError("Mapped equipment terminal identifiers must be UUID values.")
            if source_terminal_id in source_ids or equipment_terminal_id in equipment_ids:
                raise ValueError("Terminal mappings must be one-to-one.")
            source_ids.add(source_terminal_id)
            equipment_ids.add(equipment_terminal_id)
        if self.terminal_mappings and self.equipment_id is None:
            raise ValueError("Terminal mappings require an equipment_id.")
        if self.label is not None and (not isinstance(self.label, str) or not self.label.strip()):
            raise ValueError("label must be a non-empty string or None.")
        if not isinstance(self.asset_id, str) or not self.asset_id.strip():
            raise ValueError("asset_id must be a non-empty source asset identifier.")
        object.__setattr__(self, "asset_id", self.asset_id.strip())
        coordinates = (float(self.x), float(self.y), float(self.rotation_deg))
        if not all(isfinite(value) and abs(value) < 1e9 for value in coordinates):
            raise ValueError("Diagram symbol coordinates and rotation must be finite and bounded.")
        object.__setattr__(self, "x", coordinates[0])
        object.__setattr__(self, "y", coordinates[1])
        object.__setattr__(self, "rotation_deg", coordinates[2] % 360.0)
        if self.label is not None:
            object.__setattr__(self, "label", self.label.strip())

    @classmethod
    def create(
        cls,
        asset_id: str,
        x: float,
        y: float,
        rotation_deg: float = 0.0,
        *,
        equipment_id: UUID | None = None,
        terminal_mappings: tuple[tuple[str, UUID], ...] = (),
        label: str | None = None,
    ) -> DiagramSymbolPlacement:
        return cls(uuid4(), asset_id, x, y, rotation_deg, equipment_id, terminal_mappings, label)


@dataclass(frozen=True, slots=True)
class DiagramLabelPlacement:
    """Independently editable annotation stored outside the electrical model."""

    label_id: UUID
    owner_id: UUID | None
    text: str
    x: float
    y: float
    anchor: str = "middle"
    font_family: str = "STIX Two Text"
    size_pt: float = 7.5
    weight: str = "normal"
    color: str = "#172033"
    rotation_deg: float = 0.0
    visible: bool = True
    layer: str = "annotations"
    priority: int = 50
    unit: str | None = None
    number_format: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.label_id, UUID):
            raise TypeError("label_id must be a UUID.")
        if self.owner_id is not None and not isinstance(self.owner_id, UUID):
            raise TypeError("owner_id must be a UUID or None.")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("Diagram label text must be non-empty.")
        if self.anchor not in {"start", "middle", "end"}:
            raise ValueError("Diagram label anchor must be start, middle or end.")
        if self.weight not in {"normal", "medium", "semibold", "bold"}:
            raise ValueError("Unsupported diagram label weight.")
        if (not isinstance(self.color, str) or len(self.color) != 7
                or not self.color.startswith("#")
                or any(character not in "0123456789abcdefABCDEF" for character in self.color[1:])):
            raise ValueError("Diagram label color must be a six-digit hexadecimal color.")
        if not isinstance(self.font_family, str) or not self.font_family.strip():
            raise ValueError("Diagram label font family must be non-empty.")
        if not isinstance(self.layer, str) or not self.layer.strip():
            raise ValueError("Diagram label layer must be non-empty.")
        if not isinstance(self.visible, bool):
            raise TypeError("Diagram label visible must be bool.")
        values = (float(self.x), float(self.y), float(self.size_pt), float(self.rotation_deg))
        if not all(isfinite(value) for value in values):
            raise ValueError("Diagram label geometry must be finite.")
        if values[2] <= 0 or values[2] > 72:
            raise ValueError("Diagram label size must be in the range (0, 72] pt.")
        if any(abs(value) >= 1e9 for value in values):
            raise ValueError("Diagram label geometry exceeds supported bounds.")
        object.__setattr__(self, "text", self.text.strip())
        object.__setattr__(self, "font_family", self.font_family.strip())
        object.__setattr__(self, "color", self.color.upper())
        object.__setattr__(self, "layer", self.layer.strip())
        object.__setattr__(self, "x", values[0])
        object.__setattr__(self, "y", values[1])
        object.__setattr__(self, "size_pt", values[2])
        object.__setattr__(self, "rotation_deg", values[3] % 360.0)
        if self.unit is not None and not isinstance(self.unit, str):
            raise TypeError("Diagram label unit must be a string or None.")
        if self.number_format is not None and not isinstance(self.number_format, str):
            raise TypeError("Diagram label number_format must be a string or None.")

    @classmethod
    def create(
        cls, text: str, x: float, y: float, *, owner_id: UUID | None = None,
        anchor: str = "middle", font_family: str = "STIX Two Text",
        size_pt: float = 7.5, weight: str = "normal", color: str = "#172033",
        rotation_deg: float = 0.0, visible: bool = True,
        layer: str = "annotations", priority: int = 50,
        unit: str | None = None, number_format: str | None = None,
    ) -> "DiagramLabelPlacement":
        return cls(
            label_id=uuid4(), owner_id=owner_id, text=text, x=x, y=y, anchor=anchor,
            font_family=font_family, size_pt=size_pt, weight=weight, color=color,
            rotation_deg=rotation_deg, visible=visible, layer=layer, priority=priority,
            unit=unit, number_format=number_format,
        )


@dataclass(slots=True)
class NetworkWorkspace:
    """A physical network plus a separate map of diagram positions.

    The coordinate map never participates in topology or electrical calculations.
    Keys are domain element UUIDs; values are (x, y) scene coordinates.
    """

    network: Network = field(default_factory=lambda: Network("Network 1"))
    diagram_positions: dict[UUID, tuple[float, float]] = field(default_factory=dict)
    diagram_rotations: dict[UUID, float] = field(default_factory=dict)
    grid_spacing: float = 20.0
    snap_enabled: bool = True
    study_history: tuple[NetworkStudyRecord, ...] = ()
    diagram_symbols: dict[UUID, DiagramSymbolPlacement] = field(default_factory=dict)
    diagram_labels: dict[UUID, DiagramLabelPlacement] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.network, Network):
            raise TypeError("network must be a Network aggregate.")
        if not isinstance(self.diagram_positions, dict):
            raise TypeError("diagram_positions must be a dictionary keyed by element UUID.")
        allowed_ids = {item.id for item in self.network.buses} | {
            item.id for item in self.network.equipment
        }
        connected_terminal_ids = {item.terminal_id for item in self.network.connections}
        normalized: dict[UUID, tuple[float, float]] = {}
        for identifier, position in self.diagram_positions.items():
            if not isinstance(identifier, UUID):
                raise TypeError("Diagram position keys must be UUID values.")
            if identifier not in allowed_ids:
                raise ValueError(
                    f"Diagram position references an unknown network element: {identifier}."
                )
            if not isinstance(position, tuple) or len(position) != 2:
                raise TypeError("Every diagram position must be an (x, y) tuple.")
            x, y = float(position[0]), float(position[1])
            if not (-1e9 < x < 1e9 and -1e9 < y < 1e9):
                raise ValueError("Diagram coordinates must be finite and bounded.")
            normalized[identifier] = (x, y)
        self.diagram_positions = normalized
        if not isinstance(self.diagram_rotations, dict):
            raise TypeError("diagram_rotations must be a dictionary keyed by bus UUID.")
        bus_ids = {item.id for item in self.network.buses}
        normalized_rotations: dict[UUID, float] = {}
        for identifier, rotation in self.diagram_rotations.items():
            if not isinstance(identifier, UUID):
                raise TypeError("Diagram rotation keys must be UUID values.")
            if identifier not in bus_ids:
                raise ValueError(f"Diagram rotation references an unknown bus: {identifier}.")
            value = float(rotation)
            if not isfinite(value) or abs(value) >= 1e9:
                raise ValueError("Diagram rotations must be finite and bounded.")
            normalized_rotations[identifier] = value % 360.0
        self.diagram_rotations = normalized_rotations
        if not isinstance(self.diagram_symbols, dict):
            raise TypeError("diagram_symbols must be a dictionary keyed by placement UUID.")
        normalized_symbols: dict[UUID, DiagramSymbolPlacement] = {}
        for identifier, placement in self.diagram_symbols.items():
            if not isinstance(identifier, UUID):
                raise TypeError("Diagram symbol placement keys must be UUID values.")
            if not isinstance(placement, DiagramSymbolPlacement):
                raise TypeError("Every diagram symbol must be a DiagramSymbolPlacement.")
            if identifier != placement.instance_id:
                raise ValueError("Diagram symbol dictionary key must match placement.instance_id.")
            if placement.equipment_id is not None:
                equipment = next(
                    (item for item in self.network.equipment if item.id == placement.equipment_id),
                    None,
                )
                if equipment is None:
                    raise ValueError(
                        f"Diagram symbol maps to an unknown equipment id: {placement.equipment_id}."
                    )
                equipment_terminal_ids = {item.id for item in equipment.terminals}
                mapped_terminal_ids = {item[1] for item in placement.terminal_mappings}
                if not mapped_terminal_ids.issubset(equipment_terminal_ids):
                    raise ValueError("Diagram symbol maps a terminal not owned by its equipment.")
                if not mapped_terminal_ids.issubset(connected_terminal_ids):
                    raise ValueError(
                        "Diagram symbol maps an equipment terminal without an explicit network connection."
                    )
            normalized_symbols[identifier] = placement
        self.diagram_symbols = normalized_symbols
        if not isinstance(self.diagram_labels, dict):
            raise TypeError("diagram_labels must be a dictionary keyed by label UUID.")
        normalized_labels: dict[UUID, DiagramLabelPlacement] = {}
        for identifier, label in self.diagram_labels.items():
            if not isinstance(identifier, UUID) or not isinstance(label, DiagramLabelPlacement):
                raise TypeError("Every diagram label must be keyed by its UUID.")
            if identifier != label.label_id:
                raise ValueError("Diagram label dictionary key must match label.label_id.")
            if label.owner_id is not None and label.owner_id not in allowed_ids:
                raise ValueError(f"Diagram label references an unknown owner: {label.owner_id}.")
            normalized_labels[identifier] = label
        self.diagram_labels = normalized_labels
        self.grid_spacing = float(self.grid_spacing)
        if not 2.0 <= self.grid_spacing <= 200.0:
            raise ValueError("grid_spacing must be between 2 and 200 scene units.")
        if not isinstance(self.snap_enabled, bool):
            raise TypeError("snap_enabled must be bool.")
        if not isinstance(self.study_history, tuple) or any(
            not isinstance(item, NetworkStudyRecord) for item in self.study_history
        ):
            raise TypeError("study_history must be a tuple of NetworkStudyRecord values.")
        if any(item.network_id != self.network.id for item in self.study_history):
            raise ValueError("Every stored study record must reference this physical network.")
        identifiers = tuple(item.run_id for item in self.study_history)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Network study run identifiers must be unique.")

    def update_diagram_rotation(self, bus_id: UUID, rotation_deg: float) -> float:
        """Update a busbar's drawing orientation without changing electrical topology."""
        if not isinstance(bus_id, UUID):
            raise TypeError("bus_id must be a UUID.")
        if not any(item.id == bus_id for item in self.network.buses):
            raise KeyError(f"Unknown bus for diagram rotation: {bus_id}.")
        value = float(rotation_deg)
        if not isfinite(value) or abs(value) >= 1e9:
            raise ValueError("Diagram rotation must be finite and bounded.")
        normalized = value % 360.0
        self.diagram_rotations[bus_id] = normalized
        return normalized

    def add_diagram_symbol(self, placement: DiagramSymbolPlacement) -> None:
        if not isinstance(placement, DiagramSymbolPlacement):
            raise TypeError("placement must be a DiagramSymbolPlacement.")
        if placement.instance_id in self.diagram_symbols:
            raise ValueError(f"Diagram symbol '{placement.instance_id}' already exists.")
        if placement.equipment_id is not None:
            equipment = self.network.get_equipment(placement.equipment_id)
            equipment_terminal_ids = {item.id for item in equipment.terminals}
            mapped_terminal_ids = {item[1] for item in placement.terminal_mappings}
            if not mapped_terminal_ids.issubset(equipment_terminal_ids):
                raise ValueError("Diagram symbol maps a terminal not owned by its equipment.")
            connected_terminal_ids = {item.terminal_id for item in self.network.connections}
            if not mapped_terminal_ids.issubset(connected_terminal_ids):
                raise ValueError(
                    "Diagram symbol maps an equipment terminal without an explicit network connection."
                )
        self.diagram_symbols[placement.instance_id] = placement

    def remove_diagram_symbol(self, instance_id: UUID) -> DiagramSymbolPlacement:
        if not isinstance(instance_id, UUID):
            raise TypeError("instance_id must be a UUID.")
        try:
            return self.diagram_symbols.pop(instance_id)
        except KeyError as exc:
            raise KeyError(f"Unknown diagram symbol placement '{instance_id}'.") from exc

    def update_diagram_symbol(
        self,
        instance_id: UUID,
        *,
        x: float | None = None,
        y: float | None = None,
        rotation_deg: float | None = None,
        label: str | None = None,
    ) -> DiagramSymbolPlacement:
        try:
            current = self.diagram_symbols[instance_id]
        except KeyError as exc:
            raise KeyError(f"Unknown diagram symbol placement '{instance_id}'.") from exc
        updated = replace(
            current,
            x=current.x if x is None else x,
            y=current.y if y is None else y,
            rotation_deg=current.rotation_deg if rotation_deg is None else rotation_deg,
            label=current.label if label is None else label,
        )
        self.diagram_symbols[instance_id] = updated
        return updated

    def upsert_diagram_label(self, label: DiagramLabelPlacement) -> None:
        """Persist an editable text annotation without changing the network."""
        if not isinstance(label, DiagramLabelPlacement):
            raise TypeError("label must be a DiagramLabelPlacement.")
        allowed_ids = {item.id for item in self.network.buses} | {
            item.id for item in self.network.equipment
        }
        if label.owner_id is not None and label.owner_id not in allowed_ids:
            raise KeyError(f"Unknown diagram label owner: {label.owner_id}.")
        self.diagram_labels[label.label_id] = label

    def remove_diagram_label(self, label_id: UUID) -> DiagramLabelPlacement:
        if not isinstance(label_id, UUID):
            raise TypeError("label_id must be a UUID.")
        try:
            return self.diagram_labels.pop(label_id)
        except KeyError as exc:
            raise KeyError(f"Unknown diagram label '{label_id}'.") from exc

    def record_study(self, record: NetworkStudyRecord) -> None:
        if not isinstance(record, NetworkStudyRecord):
            raise TypeError("record must be a NetworkStudyRecord.")
        if record.network_id != self.network.id:
            raise ValueError("Study record belongs to a different physical network.")
        if any(item.run_id == record.run_id for item in self.study_history):
            raise ValueError(f"Study run '{record.run_id}' is already recorded.")
        self.study_history = (*self.study_history, record)
