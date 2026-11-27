"""Documented vector symbol catalogue for PFA single-line diagrams.

The catalogue records terminal semantics, dimensions and provenance separately
from electrical equipment.  The built-in glyphs are original engineering
constructions; IEC cross-reference is intentionally marked pending verification.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite


@dataclass(frozen=True, slots=True)
class SymbolTerminal:
    designation: str
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class SymbolPrimitive:
    """Parametric, renderer-neutral primitive in symbol-local coordinates.

    ``circle`` coordinates are ``(center_x, center_y, radius)``. ``line``
    coordinates are ``(x1, y1, x2, y2)``. A line may identify one electrical
    terminal so SVG metadata can preserve the terminal identity on the glyph.
    """

    kind: str
    coordinates: tuple[float, ...]
    terminal_index: int | None = None

    def __post_init__(self) -> None:
        expected = {"circle": 3, "line": 4}
        if self.kind not in expected:
            raise ValueError(f"Unsupported symbol primitive: {self.kind!r}.")
        if len(self.coordinates) != expected[self.kind]:
            raise ValueError(
                f"{self.kind} primitive requires {expected[self.kind]} coordinates."
            )
        if not all(isfinite(float(value)) for value in self.coordinates):
            raise ValueError("Symbol primitive coordinates must be finite.")
        if self.kind == "circle" and self.coordinates[2] <= 0:
            raise ValueError("Symbol circle radius must be positive.")
        if self.terminal_index is not None and self.terminal_index < 0:
            raise ValueError("Symbol primitive terminal_index must be non-negative.")


@dataclass(frozen=True, slots=True)
class EngineeringSymbolDefinition:
    symbol_id: str
    family: str
    width: float
    height: float
    terminals: tuple[SymbolTerminal, ...]
    visual_description: str
    standard_reference: str = "IEC 60617 — cross-reference pending"
    normative_status: str = "NOT_VERIFIED"
    provenance: str = "PFA original vector construction"
    source_license: str = "Project-authored geometry; no third-party artwork"
    standard_edition: str = "IEC 60617 cross-reference not established"
    source_uri: str = "internal://power-fault-analyzer/symbol-catalog"
    primitives: tuple[SymbolPrimitive, ...] = ()
    text_glyph: str = ""

    @property
    def definition_hash(self) -> str:
        payload = "|".join((
            self.symbol_id, self.family, str(self.width), str(self.height),
            ";".join(f"{item.designation}:{item.x:g}:{item.y:g}" for item in self.terminals),
            self.visual_description, self.standard_reference, self.normative_status,
            self.provenance, self.source_license, self.standard_edition, self.source_uri,
            ";".join(
                f"{primitive.kind}:{','.join(f'{value:g}' for value in primitive.coordinates)}:"
                f"{primitive.terminal_index}"
                for primitive in self.primitives
            ),
            self.text_glyph,
        ))
        return sha256(payload.encode("utf-8")).hexdigest()


_DEFINITIONS = (
    EngineeringSymbolDefinition(
        "PFA-SLD-BUSBAR-001", "busbar", 204.0, 6.0, (),
        "Straight busbar with finite extent; tap points reference canonical terminal links.",
    ),
    EngineeringSymbolDefinition(
        "PFA-SLD-CONNECTION-NODE-001", "connection_node", 12.0, 12.0, (),
        "Explicit electrical connection node, rendered as a filled junction point.",
        normative_status="NOT_APPLICABLE",
    ),
    EngineeringSymbolDefinition(
        "PFA-SLD-LOAD-001", "load", 52.0, 52.0,
        (SymbolTerminal("LOAD", 0.0, -26.0),),
        "Distinct static load marker with a circular demand symbol and P/Q glyph.",
        primitives=(SymbolPrimitive("circle", (0.0, 0.0, 19.0)),),
        text_glyph="P/Q",
    ),
    EngineeringSymbolDefinition(
        "PFA-SLD-CAPACITOR-001", "capacitor", 48.0, 56.0,
        (SymbolTerminal("LINE", 0.0, -28.0),),
        "Shunt capacitor with separated plate lines and an explicit unresolved state marker when data are missing.",
        primitives=(
            SymbolPrimitive("line", (0.0, -28.0, 0.0, -4.0)),
            SymbolPrimitive("line", (-17.0, -3.0, 17.0, -3.0)),
            SymbolPrimitive("line", (-17.0, 5.0, 17.0, 5.0)),
        ),
        text_glyph="C",
    ),
    EngineeringSymbolDefinition(
        "PFA-SLD-REACTOR-001", "reactor", 52.0, 64.0,
        (SymbolTerminal("LINE", 0.0, -32.0),),
        "Shunt reactor represented by a vertical inductive coil and terminal stem.",
        primitives=(
            SymbolPrimitive("line", (0.0, -32.0, 0.0, -22.0)),
            SymbolPrimitive("circle", (0.0, -15.0, 7.0)),
            SymbolPrimitive("circle", (0.0, 0.0, 7.0)),
            SymbolPrimitive("circle", (0.0, 15.0, 7.0)),
            SymbolPrimitive("line", (0.0, 22.0, 0.0, 30.0)),
        ),
        text_glyph="L",
    ),
    EngineeringSymbolDefinition(
        "PFA-SLD-COMPENSATION-001", "compensation", 52.0, 52.0,
        (SymbolTerminal("LINE", 0.0, -26.0),),
        "Generic reactive compensation unit shown as a diamond and Q glyph; subtype remains explicit in metadata.",
        primitives=(
            SymbolPrimitive("line", (0.0, -22.0, 22.0, 0.0)),
            SymbolPrimitive("line", (22.0, 0.0, 0.0, 22.0)),
            SymbolPrimitive("line", (0.0, 22.0, -22.0, 0.0)),
            SymbolPrimitive("line", (-22.0, 0.0, 0.0, -22.0)),
        ),
        text_glyph="Q",
    ),
    EngineeringSymbolDefinition(
        "PFA-SLD-SOURCE-001", "source", 44.0, 44.0,
        (SymbolTerminal("GRID", 0.0, 22.0),),
        "Circular external equivalent/source marker with sinusoidal glyph.",
    ),
    EngineeringSymbolDefinition(
        "PFA-SLD-GENERATOR-001", "generator", 44.0, 44.0,
        (SymbolTerminal("STATOR", 0.0, -22.0),),
        "Circular synchronous-generator marker with G glyph.",
    ),
    EngineeringSymbolDefinition(
        "PFA-SLD-TRANSFORMER-2W-001", "transformer", 68.0, 42.0,
        (SymbolTerminal("HV", -34.0, 0.0), SymbolTerminal("LV", 34.0, 0.0)),
        "Two genuinely overlapping winding circles on the vertical single-line axis, "
        "with short external terminal leads. Local geometry is horizontal and is rotated "
        "90 degrees by the two-terminal bay projection.",
        standard_reference=(
            "IEC 60617 S00841 Form 1 — two overlapping circles; "
            "reference shape cross-checked, project dimensional conformance NOT_VERIFIED"
        ),
        normative_status="NOT_VERIFIED",
        provenance=(
            "PFA-authored parametric vector geometry cross-checked against the IEC 60617 "
            "S00841 Form 1 database description; no IEC artwork copied"
        ),
        standard_edition=(
            "IEC 60617 database snapshot 2019-03-05; S00841 Form 1, standard status, "
            "released 2001-07-01; alternative form S00842"
        ),
        source_uri=(
            "https://library.iec.ch/grasymb/grasymb.nsf/"
            "5FDC3327D03AD13DC125846A00501C93/$FILE/IEC60617_Snapshot_2019-03-05.pdf"
        ),
        primitives=(
            # Local X becomes the vertical one-line axis after the projection's
            # 90-degree equipment rotation. Centre spacing 20 < diameter 32,
            # producing a 12-unit overlap rather than separated/tangent circles.
            SymbolPrimitive("circle", (-10.0, 0.0, 16.0)),
            SymbolPrimitive("circle", (10.0, 0.0, 16.0)),
            SymbolPrimitive("line", (-34.0, 0.0, -26.0, 0.0), terminal_index=0),
            SymbolPrimitive("line", (26.0, 0.0, 34.0, 0.0), terminal_index=1),
        ),
    ),
    EngineeringSymbolDefinition(
        "PFA-SLD-CB-001", "circuit_breaker", 44.0, 28.0,
        (SymbolTerminal("LINE", -22.0, 0.0), SymbolTerminal("BUS", 22.0, 0.0)),
        "State-dependent contact bridge with circuit-breaker function cross at the fixed contact; candidate IEC 60617 07-13-05 mapping.",
        standard_reference="IEC 60617 07-13-05 — cross-reference pending; candidate mapping pending licensed catalogue review",
    ),
    EngineeringSymbolDefinition(
        "PFA-SLD-DISCONNECTOR-001", "disconnector", 44.0, 28.0,
        (SymbolTerminal("LINE", -22.0, 0.0), SymbolTerminal("BUS", 22.0, 0.0)),
        "Two terminals, visible isolating blade, and disconnector function bar at the fixed contact; candidate IEC 60617 07-13-06 mapping.",
        standard_reference="IEC 60617 07-13-06 — cross-reference pending; candidate mapping pending licensed catalogue review",
    ),
    EngineeringSymbolDefinition(
        "PFA-SLD-EARTHING-SWITCH-001", "earthing_switch", 44.0, 32.0,
        (SymbolTerminal("LINE", -22.0, 0.0), SymbolTerminal("EARTH", 22.0, 0.0)),
        "Switching blade with explicit earth-side terminal and ground mark.",
    ),
    EngineeringSymbolDefinition(
        "PFA-SLD-LINE-001", "line", 44.0, 18.0,
        (SymbolTerminal("FROM", -22.0, 0.0), SymbolTerminal("TO", 22.0, 0.0)),
        "Transmission branch represented by conductor with independent label.",
    ),
    EngineeringSymbolDefinition(
        "PFA-SLD-GENERIC-1T-001", "generic", 40.0, 40.0,
        (SymbolTerminal("TERMINAL", 0.0, -20.0),),
        "Explicitly generic unresolved one-terminal equipment marker.",
    ),
)

SYMBOL_CATALOG: dict[str, EngineeringSymbolDefinition] = {
    item.family: item for item in _DEFINITIONS
}
SYMBOL_DEFINITIONS: tuple[EngineeringSymbolDefinition, ...] = _DEFINITIONS


def get_symbol_definition(family: str) -> EngineeringSymbolDefinition:
    """Return a documented symbol or fail explicitly instead of drawing a guess."""
    try:
        return SYMBOL_CATALOG[family]
    except KeyError as exc:
        raise KeyError(f"No documented PFA engineering symbol for family {family!r}.") from exc
