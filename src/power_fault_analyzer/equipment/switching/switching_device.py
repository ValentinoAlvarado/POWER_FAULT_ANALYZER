"""Two-terminal switchgear whose state changes network connectivity, not impedance."""

from __future__ import annotations

from uuid import UUID

from power_fault_analyzer.domain.entities.electrical_equipment import TwoTerminalEquipmentBase
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.enums.switching_device import SwitchingDeviceKind, SwitchPosition


class SwitchingDevice(TwoTerminalEquipmentBase):
    """Circuit breaker/disconnector with explicit open/closed state.

    The sequence-network adapter treats a closed device as a topological merge
    and an open device as an interruption. No artificial near-zero or huge
    impedance is stamped into the electrical model.
    """

    __slots__ = ("_device_kind", "_position")

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        terminals: tuple[Terminal, Terminal],
        device_kind: SwitchingDeviceKind,
        position: SwitchPosition,
    ) -> None:
        if not isinstance(device_kind, SwitchingDeviceKind):
            raise TypeError("device_kind must be a SwitchingDeviceKind value.")
        if not isinstance(position, SwitchPosition):
            raise TypeError("position must be a SwitchPosition value.")
        if len(terminals) == 2 and terminals[0].rated_voltage != terminals[1].rated_voltage:
            raise ValueError("Both switch terminals must have the same rated voltage.")
        super().__init__(
            id=id,
            name=name,
            terminals=terminals,
            family=EquipmentFamily.SWITCHING,
        )
        self._device_kind = device_kind
        self._position = position

    @property
    def device_kind(self) -> SwitchingDeviceKind:
        return self._device_kind

    @property
    def position(self) -> SwitchPosition:
        return self._position

    @property
    def is_closed(self) -> bool:
        return self.position is SwitchPosition.CLOSED

    def with_position(self, position: SwitchPosition) -> SwitchingDevice:
        return SwitchingDevice(
            id=self.id,
            name=self.name,
            terminals=self.terminals,
            device_kind=self.device_kind,
            position=position,
        )
