"""Underground cable domain entity."""

import math
from numbers import Real
from uuid import UUID

from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.construction import (
    ConductorMaterial,
    InsulationMaterial,
    ScreenBonding,
)
from power_fault_analyzer.domain.enums.line_model_kind import LineModelKind
from power_fault_analyzer.equipment.transmission.line import Line
from power_fault_analyzer.equipment.transmission.line_parameters import LineParameters


class UndergroundCable(Line):
    """Underground cable with explicit construction metadata.

    Electrical sequence parameters remain explicit inputs until a dedicated
    geometry/construction-based parameter calculator is implemented.
    """

    __slots__ = (
        "_conductor_cross_section_mm2",
        "_conductor_material",
        "_insulation_material",
        "_screen_bonding",
    )

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        terminals: tuple[Terminal, Terminal],
        length_km: float,
        parameters: LineParameters,
        conductor_material: ConductorMaterial,
        conductor_cross_section_mm2: float,
        insulation_material: InsulationMaterial,
        screen_bonding: ScreenBonding,
        model_kind: LineModelKind = LineModelKind.NOMINAL_PI,
    ) -> None:
        if not isinstance(conductor_material, ConductorMaterial):
            raise TypeError("conductor_material must be a ConductorMaterial value.")
        if not isinstance(insulation_material, InsulationMaterial):
            raise TypeError("insulation_material must be an InsulationMaterial value.")
        if not isinstance(screen_bonding, ScreenBonding):
            raise TypeError("screen_bonding must be a ScreenBonding value.")
        if isinstance(conductor_cross_section_mm2, bool) or not isinstance(
            conductor_cross_section_mm2, Real
        ):
            raise TypeError("conductor_cross_section_mm2 must be a real number.")
        cross_section = float(conductor_cross_section_mm2)
        if not math.isfinite(cross_section) or cross_section <= 0.0:
            raise ValueError("conductor_cross_section_mm2 must be finite and greater than zero.")
        super().__init__(
            id=id,
            name=name,
            terminals=terminals,
            length_km=length_km,
            parameters=parameters,
            model_kind=model_kind,
        )
        self._conductor_material = conductor_material
        self._conductor_cross_section_mm2 = cross_section
        self._insulation_material = insulation_material
        self._screen_bonding = screen_bonding

    @property
    def conductor_material(self) -> ConductorMaterial:
        return self._conductor_material

    @property
    def conductor_cross_section_mm2(self) -> float:
        return self._conductor_cross_section_mm2

    @property
    def insulation_material(self) -> InsulationMaterial:
        return self._insulation_material

    @property
    def screen_bonding(self) -> ScreenBonding:
        return self._screen_bonding
