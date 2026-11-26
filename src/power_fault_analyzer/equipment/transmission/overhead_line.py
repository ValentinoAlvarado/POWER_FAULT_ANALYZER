"""Overhead transmission line domain entity."""

from uuid import UUID

from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.construction import ConductorMaterial
from power_fault_analyzer.domain.enums.line_model_kind import LineModelKind
from power_fault_analyzer.equipment.transmission.line import Line
from power_fault_analyzer.equipment.transmission.line_parameters import LineParameters


class OverheadLine(Line):
    """Overhead line whose sequence parameters are supplied or precomputed."""

    __slots__ = ("_bundle_subconductors", "_conductor_material")

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        terminals: tuple[Terminal, Terminal],
        length_km: float,
        parameters: LineParameters,
        conductor_material: ConductorMaterial = ConductorMaterial.ACSR,
        bundle_subconductors: int = 1,
        model_kind: LineModelKind = LineModelKind.NOMINAL_PI,
    ) -> None:
        if not isinstance(conductor_material, ConductorMaterial):
            raise TypeError("conductor_material must be a ConductorMaterial value.")
        if isinstance(bundle_subconductors, bool) or not isinstance(bundle_subconductors, int):
            raise TypeError("bundle_subconductors must be an integer, not bool.")
        if bundle_subconductors < 1:
            raise ValueError("bundle_subconductors must be at least one.")
        super().__init__(
            id=id,
            name=name,
            terminals=terminals,
            length_km=length_km,
            parameters=parameters,
            model_kind=model_kind,
        )
        self._conductor_material = conductor_material
        self._bundle_subconductors = bundle_subconductors

    @property
    def conductor_material(self) -> ConductorMaterial:
        return self._conductor_material

    @property
    def bundle_subconductors(self) -> int:
        return self._bundle_subconductors
