"""Publication-oriented, editable SVG primitives for electrical diagrams."""
from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sin
from html import escape
from typing import Iterable

from .symbol_catalog import get_symbol_definition

from .layout import Point, Rect


@dataclass(frozen=True, slots=True)
class SvgLabel:
    text: str
    position: Point
    size_pt: float = 7.5
    anchor: str = "middle"
    identifier: str = ""
    font_family: str = "STIX Two Text, Cambria, Times New Roman, serif"
    weight: str = "normal"
    color: str = "#172033"
    rotation_deg: float = 0.0
    visible: bool = True
    layer: str = "annotations"


@dataclass(frozen=True, slots=True)
class SvgPath:
    points: tuple[Point, ...]
    width_pt: float = 0.65
    dash: str | None = None
    identifier: str = "conductor"
    color: str = "#172033"


@dataclass(frozen=True, slots=True)
class SvgSymbol:
    family: str
    center: Point
    width: float
    height: float
    identifier: str
    state: str | None = None
    orientation_deg: float = 0.0
    symbol_id: str = ""
    terminal_points: tuple[Point, ...] = ()
    terminal_designations: tuple[str, ...] = ()
    terminal_ids: tuple[str, ...] = ()
    standard_reference: str = ""
    normative_status: str = "NOT_VERIFIED"
    provenance: str = ""
    source_license: str = ""
    definition_hash: str = ""


@dataclass(frozen=True, slots=True)
class SvgMetadata:
    title: str
    author: str = ""
    project: str = ""
    revision: str = ""
    description: str = ""


def _f(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".") or "0"


def render_svg(
    *, width_mm: float, height_mm: float, symbols: Iterable[SvgSymbol] = (),
    paths: Iterable[SvgPath] = (), labels: Iterable[SvgLabel] = (),
    metadata: SvgMetadata = SvgMetadata("POWER_FAULT_ANALYZER diagram"),
    view_box: Rect | None = None, show_grid: bool = False,
) -> str:
    """Render vector linework at exact physical page dimensions.

    Text and line widths are converted from typographic points into viewBox units,
    keeping physical output independent of scene-coordinate scale.
    """
    if width_mm <= 0 or height_mm <= 0:
        raise ValueError("Physical SVG dimensions must be positive.")
    symbols, paths, labels = tuple(symbols), tuple(paths), tuple(labels)
    generated_view_box = view_box is None
    if view_box is None:
        extents_x: list[float] = []
        extents_y: list[float] = []
        for symbol in symbols:
            extents_x.extend((symbol.center.x - symbol.width / 2,
                              symbol.center.x + symbol.width / 2))
            extents_y.extend((symbol.center.y - symbol.height / 2,
                              symbol.center.y + symbol.height / 2))
        for path in paths:
            extents_x.extend(point.x for point in path.points)
            extents_y.extend(point.y for point in path.points)
        for label in labels:
            extents_x.append(label.position.x)
            extents_y.append(label.position.y)
        if not extents_x:
            view_box = Rect(0, 0, 100, 100)
        else:
            pad = 40.0
            left, top = min(extents_x) - pad, min(extents_y) - pad
            view_box = Rect(left, top,
                            max(1.0, max(extents_x) - min(extents_x) + 2 * pad),
                            max(1.0, max(extents_y) - min(extents_y) + 2 * pad))
    point_width = width_mm * 72.0 / 25.4
    point_height = height_mm * 72.0 / 25.4
    page_aspect = width_mm / height_mm
    box_aspect = view_box.width / view_box.height
    if generated_view_box and abs(box_aspect - page_aspect) > 1e-4:
        if box_aspect > page_aspect:
            adjusted_height = view_box.width / page_aspect
            delta = (adjusted_height - view_box.height) / 2.0
            view_box = Rect(view_box.x, view_box.y - delta, view_box.width, adjusted_height)
        else:
            adjusted_width = view_box.height * page_aspect
            delta = (adjusted_width - view_box.width) / 2.0
            view_box = Rect(view_box.x - delta, view_box.y, adjusted_width, view_box.height)
    scale_x = view_box.width / point_width
    scale_y = view_box.height / point_height
    if abs(scale_x - scale_y) > max(scale_x, scale_y) * 1e-4:
        raise ValueError("viewBox aspect ratio must match the physical page aspect ratio.")
    scene_per_pt = (scale_x + scale_y) / 2.0
    title = escape(metadata.title)
    description = escape(metadata.description)
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
        f'width="{_f(width_mm)}mm" height="{_f(height_mm)}mm" '
        f'viewBox="{_f(view_box.x)} {_f(view_box.y)} {_f(view_box.width)} {_f(view_box.height)}">',
        f'<title>{title}</title><desc>{description}</desc>',
        '<metadata>',
        f'<pfa:document xmlns:pfa="https://power-fault-analyzer.org/ns/diagram/1.0" '
        f'author="{escape(metadata.author, quote=True)}" '
        f'project="{escape(metadata.project, quote=True)}" '
        f'revision="{escape(metadata.revision, quote=True)}" />',
        '</metadata>',
        f'<rect id="page-background" x="{_f(view_box.x)}" y="{_f(view_box.y)}" '
        f'width="{_f(view_box.width)}" height="{_f(view_box.height)}" fill="#FFFFFF"/>',
    ]
    if show_grid:
        lines.append('<g id="editor-grid" fill="none" stroke="#E8EDF2" stroke-width="0.25">')
        step = 20.0
        x = (view_box.x // step) * step
        while x <= view_box.right:
            lines.append(f'<path d="M {_f(x)} {_f(view_box.y)} V {_f(view_box.bottom)}"/>')
            x += step
        y = (view_box.y // step) * step
        while y <= view_box.bottom:
            lines.append(f'<path d="M {_f(view_box.x)} {_f(y)} H {_f(view_box.right)}"/>')
            y += step
        lines.append('</g>')

    lines.append('<g id="conductors" fill="none" stroke-linecap="square" '
                 'stroke-linejoin="miter">')
    for index, path in enumerate(paths):
        if len(path.points) < 2:
            continue
        commands = " ".join(
            ("M" if point_index == 0 else "L")
            + f" {_f(point.x)} {_f(point.y)}"
            for point_index, point in enumerate(path.points)
        )
        dash = f' stroke-dasharray="{escape(path.dash, quote=True)}"' if path.dash else ""
        lines.append(
            f'<path id="{escape(path.identifier, quote=True)}-{index}" d="{commands}" '
            f'stroke="{escape(path.color, quote=True)}" '
            f'stroke-width="{_f(path.width_pt * scene_per_pt)}"{dash}/>'
        )
    lines.append('</g>')

    lines.append('<g id="equipment" fill="#FFFFFF" stroke="#172033" '
                 f'stroke-width="{_f(0.7 * scene_per_pt)}" stroke-linecap="round" '
                 'stroke-linejoin="round">')
    for symbol in symbols:
        cx, cy, width, height = symbol.center.x, symbol.center.y, symbol.width, symbol.height
        x, y = -width / 2.0, -height / 2.0
        identifier = escape(symbol.identifier, quote=True)
        definition_id = escape(symbol.symbol_id, quote=True)
        lines.append(
            f'<g id="equipment-{identifier}" data-symbol-id="{definition_id}" '
            f'data-family="{escape(symbol.family, quote=True)}" '
            f'data-standard-reference="{escape(symbol.standard_reference, quote=True)}" '
            f'data-normative-status="{escape(symbol.normative_status, quote=True)}" '
            f'data-provenance="{escape(symbol.provenance, quote=True)}" '
            f'data-source-license="{escape(symbol.source_license, quote=True)}" '
            f'data-definition-sha256="{escape(symbol.definition_hash, quote=True)}" '
            f'transform="translate({_f(cx)} {_f(cy)}) rotate({_f(symbol.orientation_deg)})">'
        )
        if symbol.family == "busbar":
            # Busbar envelopes are already rotated in the projected document.
            if width >= height:
                lines.append(
                    f'<path d="M {_f(-width/2)} 0 H {_f(width/2)}" '
                    f'stroke-width="{_f(2.0 * scene_per_pt)}" stroke-linecap="square"/>'
                )
            else:
                lines.append(
                    f'<path d="M 0 {_f(-height/2)} V {_f(height/2)}" '
                    f'stroke-width="{_f(2.0 * scene_per_pt)}" stroke-linecap="square"/>'
                )
        elif symbol.family in {"source", "generator"}:
            radius = min(width, height) * 0.44
            lines.append(f'<circle cx="0" cy="0" r="{_f(radius)}"/>')
            glyph = "~" if symbol.family == "source" else "G"
            lines.append(
                f'<text x="0" y="{_f(0.28 * radius)}" text-anchor="middle" '
                'fill="#172033" stroke="none" '
                f'font-family="STIX Two Text, Cambria, Times New Roman, serif" '
                f'font-size="{_f(11.0 * scene_per_pt)}">{glyph}</text>'
            )
        elif symbol.family == "transformer":
            # The catalogue is the single source of truth for both Qt and SVG.
            # IEC 60617 S00841 Form 1 has overlapping circles, not separated
            # circles. No white fill is used: both complete circumferences remain
            # visible through the lens-shaped intersection.
            definition = get_symbol_definition("transformer")
            for primitive in definition.primitives:
                if primitive.kind == "circle":
                    px, py, radius = primitive.coordinates
                    lines.append(
                        f'<circle class="symbol-winding" cx="{_f(px)}" '
                        f'cy="{_f(py)}" r="{_f(radius)}" fill="none"/>'
                    )
                elif primitive.kind == "line":
                    x1, y1, x2, y2 = primitive.coordinates
                    terminal_id = (
                        symbol.terminal_ids[primitive.terminal_index]
                        if primitive.terminal_index is not None
                        and primitive.terminal_index < len(symbol.terminal_ids) else ""
                    )
                    designation = (
                        symbol.terminal_designations[primitive.terminal_index]
                        if primitive.terminal_index is not None
                        and primitive.terminal_index < len(symbol.terminal_designations)
                        else ""
                    )
                    lines.append(
                        f'<path class="symbol-terminal-lead" '
                        f'data-terminal="{escape(designation, quote=True)}" '
                        f'data-terminal-id="{escape(terminal_id, quote=True)}" '
                        f'd="M {_f(x1)} {_f(y1)} L {_f(x2)} {_f(y2)}" fill="none"/>'
                    )
        elif symbol.family in {"circuit_breaker", "disconnector", "earthing_switch"}:
            left, right = -width / 2.0, width / 2.0
            contact_r = 2.0 * scene_per_pt
            first_id = symbol.terminal_ids[0] if len(symbol.terminal_ids) > 0 else ""
            second_id = symbol.terminal_ids[1] if len(symbol.terminal_ids) > 1 else ""
            first_designation = symbol.terminal_designations[0] if len(symbol.terminal_designations) > 0 else "T1"
            second_designation = symbol.terminal_designations[1] if len(symbol.terminal_designations) > 1 else "T2"
            lines.append(
                f'<circle cx="{_f(left)}" cy="0" r="{_f(contact_r)}" fill="#172033" '
                f'data-terminal="{escape(first_designation, quote=True)}" data-terminal-id="{escape(first_id, quote=True)}"/>'
            )
            lines.append(
                f'<circle cx="{_f(right)}" cy="0" r="{_f(contact_r)}" fill="#172033" '
                f'data-terminal="{escape(second_designation, quote=True)}" data-terminal-id="{escape(second_id, quote=True)}"/>'
            )
            if symbol.family == "circuit_breaker":
                if symbol.state == "closed":
                    # A heavier bridge distinguishes a closed breaker from a
                    # plain conductor even at a single-column print scale.
                    lines.append(
                        f'<path d="M {_f(left)} 0 H {_f(right)}" fill="none" '
                        f'stroke-width="{_f(1.55 * scene_per_pt)}"/>'
                    )
                else:
                    lines.append(
                        f'<path d="M {_f(left)} 0 L {_f(2.0)} {_f(-height*0.32)}" '
                        f'fill="none" stroke-width="{_f(1.15 * scene_per_pt)}"/>'
                    )
                mark_y = -height * 0.43
                radius = 3.2 * scene_per_pt
                lines.append(
                    f'<path class="breaker-function-mark" data-function-mark="iec-60617-07-13-05-candidate" '
                    f'd="M {_f(right*1.0-radius)} {_f(mark_y-radius)} '
                    f'L {_f(right+radius)} {_f(mark_y+radius)} '
                    f'M {_f(right-radius)} {_f(mark_y+radius)} '
                    f'L {_f(right+radius)} {_f(mark_y-radius)}" fill="none" '
                    f'stroke-width="{_f(0.7 * scene_per_pt)}"/> '
                )
            else:
                blade_end = 3.0 if symbol.state != "closed" else right
                blade_y = -height * 0.34 if symbol.state != "closed" else 0.0
                lines.append(f'<path d="M {_f(left)} 0 L {_f(blade_end)} {_f(blade_y)}" fill="none"/>')
                if symbol.family == "disconnector":
                    mark_y = -height * 0.43
                    mark_half = 4.5 * scene_per_pt
                    lines.append(
                        f'<path class="disconnector-function-mark" data-function-mark="iec-60617-07-13-06-candidate" '
                        f'd="M {_f(right-mark_half)} {_f(mark_y)} H {_f(right+mark_half)}" '
                        f'fill="none" stroke-width="{_f(0.7 * scene_per_pt)}"/> '
                    )
                if symbol.family == "earthing_switch":
                    ground_x = right + 6.0 * scene_per_pt
                    ground_y = height * 0.28
                    lines.append(
                        f'<path d="M {_f(ground_x)} {_f(-ground_y)} V {_f(-ground_y/2)} '
                        f'M {_f(ground_x-5*scene_per_pt)} {_f(-ground_y/2)} '
                        f'H {_f(ground_x+5*scene_per_pt)} '
                        f'M {_f(ground_x-3.5*scene_per_pt)} {_f(0)} '
                        f'H {_f(ground_x+3.5*scene_per_pt)}" fill="none"/>'
                    )
        elif symbol.family == "junction":
            terminal_id = symbol.terminal_ids[0] if symbol.terminal_ids else ""
            lines.append(
                f'<circle cx="0" cy="0" r="{_f(1.7 * scene_per_pt)}" fill="#172033" stroke="none" '
                f'data-terminal-id="{escape(terminal_id, quote=True)}"/>'
            )
        elif symbol.family == "generic":
            lines.append(f'<rect x="{_f(x)}" y="{_f(y)}" width="{_f(width)}" '
                         f'height="{_f(height)}"/>')
            lines.append(
                f'<text x="0" y="{_f(3.0 * scene_per_pt)}" text-anchor="middle" '
                f'font-size="{_f(6.0 * scene_per_pt)}" fill="#172033" stroke="none">?</text>'
            )
        # Terminal markers are independent geometry tied to canonical terminal IDs.
        terminal_markers_embedded = symbol.family in {
            "transformer", "circuit_breaker", "disconnector", "earthing_switch", "junction"
        }
        for terminal_index, point in enumerate(symbol.terminal_points):
            if terminal_markers_embedded:
                continue
            dx, dy = point.x - cx, point.y - cy
            angle = radians(symbol.orientation_deg)
            local_x = dx * cos(angle) + dy * sin(angle)
            local_y = -dx * sin(angle) + dy * cos(angle)
            designation = (
                symbol.terminal_designations[terminal_index]
                if terminal_index < len(symbol.terminal_designations) else f"T{terminal_index + 1}"
            )
            terminal_id = (
                symbol.terminal_ids[terminal_index]
                if terminal_index < len(symbol.terminal_ids) else ""
            )
            marker_fill = "#172033" if symbol.family == "line" else "#FFFFFF"
            lines.append(
                f'<circle cx="{_f(local_x)}" cy="{_f(local_y)}" '
                f'r="{_f(1.35 * scene_per_pt)}" fill="{marker_fill}" '
                f'data-terminal="{escape(designation, quote=True)}" '
                f'data-terminal-id="{escape(terminal_id, quote=True)}"/>'
            )
        lines.append('</g>')
    lines.append('</g>')

    lines.append('<g id="annotations" stroke="none">')
    for index, label in enumerate(labels):
        if not label.visible:
            continue
        text_x = label.position.x
        text_y = label.position.y
        rotate = (
            f' transform="rotate({_f(label.rotation_deg)} {_f(text_x)} {_f(text_y)})"'
            if abs(label.rotation_deg) > 1e-9 else ""
        )
        lines.append(
            f'<text id="{escape(label.identifier or f"label-{index}", quote=True)}" '
            f'x="{_f(text_x)}" y="{_f(text_y)}" '
            f'text-anchor="{escape(label.anchor, quote=True)}" '
            f'font-family="{escape(label.font_family, quote=True)}" '
            f'font-size="{_f(label.size_pt * scene_per_pt)}" '
            f'font-weight="{escape(label.weight, quote=True)}" '
            f'fill="{escape(label.color, quote=True)}"{rotate}>'
            f'{escape(label.text)}</text>'
        )
    lines.append('</g></svg>')
    return "\n".join(lines)
