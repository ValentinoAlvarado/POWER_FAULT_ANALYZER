"""Export canonical network projections as publication-ready vector documents."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from .layout import Rect
from .model_projection import DiagramDocument, EngineeringLabel, _rotated_bounds
from .svg_export import SvgLabel, SvgMetadata, SvgPath, SvgSymbol, render_svg
from .symbol_catalog import get_symbol_definition

JOURNAL_PRESETS_MM: dict[str, tuple[float, float]] = {
    "single-column": (88.0, 62.0),
    "double-column": (180.0, 120.0),
    "landscape": (180.0, 92.0),
}


def _as_svg_label(label: EngineeringLabel, index: int) -> SvgLabel:
    return SvgLabel(
        label.text,
        label.position,
        label.size_pt,
        label.anchor,
        str(label.label_id or f"label-{index}"),
        f"{label.font_family}, Arial, Helvetica, sans-serif",
        label.weight,
        label.color,
        label.rotation_deg,
        label.visible,
        label.layer,
    )


def _diagram_view_box(
    document: DiagramDocument, symbols: list[SvgSymbol], paths: list[SvgPath],
    labels: list[SvgLabel], width_mm: float, height_mm: float,
) -> Rect:
    xs: list[float] = []
    ys: list[float] = []
    for symbol in symbols:
        bounds = _rotated_bounds(symbol.center, symbol.width, symbol.height,
                                 symbol.orientation_deg)
        xs.extend((bounds.x, bounds.right))
        ys.extend((bounds.y, bounds.bottom))
    for path in paths:
        xs.extend(point.x for point in path.points)
        ys.extend(point.y for point in path.points)
    for label in labels:
        estimated_width = max(24.0, len(label.text) * label.size_pt * 0.54 * 2.8)
        estimated_height = max(12.0, label.size_pt * 1.25 * 2.8)
        if label.anchor == "middle":
            label_left = label.position.x - estimated_width / 2.0
        elif label.anchor == "end":
            label_left = label.position.x - estimated_width
        else:
            label_left = label.position.x
        xs.extend((label_left, label_left + estimated_width))
        ys.extend((label.position.y - estimated_height, label.position.y))
    if not xs:
        return Rect(0.0, 0.0, 100.0, 100.0)
    pad_x, pad_y = 105.0, 85.0
    left, right = min(xs) - pad_x, max(xs) + pad_x
    top, bottom = min(ys) - pad_y, max(ys) + pad_y
    drawing_width, drawing_height = right - left, bottom - top
    page_aspect = width_mm / height_mm
    drawing_aspect = drawing_width / drawing_height
    if drawing_aspect > page_aspect:
        required_height = drawing_width / page_aspect
        extra = (required_height - drawing_height) / 2.0
        top -= extra
        bottom += extra
    else:
        required_width = drawing_height * page_aspect
        extra = (required_width - drawing_width) / 2.0
        left -= extra
        right += extra
    return Rect(left, top, right - left, bottom - top)


def render_engineering_svg(
    document: DiagramDocument, *, width_mm: float = 180.0, height_mm: float = 92.0,
    title: str | None = None, author: str = "", revision: str = "",
    preset: Literal["single-column", "double-column", "landscape"] | None = None,
) -> str:
    """Render diagram geometry and annotations without rasterizing any layer."""
    if preset is not None:
        try:
            width_mm, height_mm = JOURNAL_PRESETS_MM[preset]
        except KeyError as exc:
            raise ValueError(f"Unknown publication preset: {preset!r}.") from exc
    busbar_definition = get_symbol_definition("busbar")
    symbols = [
        SvgSymbol(
            "busbar", item.center, item.bounds.width, item.bounds.height,
            str(item.bus_id), orientation_deg=0.0, symbol_id=busbar_definition.symbol_id,
            standard_reference=busbar_definition.standard_reference,
            normative_status=busbar_definition.normative_status,
            provenance=busbar_definition.provenance,
            source_license=busbar_definition.source_license,
            definition_hash=busbar_definition.definition_hash,
        )
        for item in document.buses
    ]
    for item in document.symbols:
        definition = get_symbol_definition(item.family)
        symbols.append(SvgSymbol(
            item.family, item.center, item.width, item.height,
            str(item.equipment_id), item.state, item.orientation_deg,
            item.symbol_id, item.terminal_points, item.terminal_designations,
            tuple(str(identifier) for identifier in item.terminal_ids),
            definition.standard_reference, definition.normative_status,
            definition.provenance, definition.source_license, definition.definition_hash,
        ))
    # Connection markers are rendered at the explicit model-to-busbar tap points.
    junction_seen: set[tuple[float, float]] = set()
    for index, conductor in enumerate(document.conductors):
        if not conductor.points:
            continue
        tap = conductor.points[0]
        key = (round(tap.x, 4), round(tap.y, 4))
        if key not in junction_seen:
            junction_seen.add(key)
            symbols.append(SvgSymbol(
                "junction", tap, 4.0, 4.0,
                f"{conductor.bus_id}-{index}",
                symbol_id="PFA-TOPOLOGY-JUNCTION-001",
                terminal_ids=(str(conductor.terminal_id),),
                standard_reference="PFA topology marker; not an IEC equipment symbol",
                normative_status="NOT_APPLICABLE",
                provenance="PFA topology overlay",
                source_license="Project-authored vector construction",
            ))
    paths = [
        SvgPath(item.points, width_pt=0.62, identifier=f"terminal-{item.terminal_id}")
        for item in document.conductors if len(item.points) >= 2
    ]
    # A line is a conductor-bearing branch, not an invented box or generic blob.
    # Its model terminal identities remain explicit at both ends.
    for item in document.symbols:
        if item.family == "line" and len(item.terminal_points) == 2:
            paths.append(SvgPath(
                item.terminal_points, width_pt=0.72,
                identifier=f"branch-{item.equipment_id}",
            ))
    labels = [_as_svg_label(item, index) for index, item in enumerate(document.labels)]
    view_box = _diagram_view_box(document, symbols, paths, labels, width_mm, height_mm)
    return render_svg(
        width_mm=width_mm,
        height_mm=height_mm,
        symbols=symbols,
        paths=paths,
        labels=labels,
        view_box=view_box,
        metadata=SvgMetadata(
            title or document.network_name,
            author,
            document.network_name,
            revision,
            "Generated from canonical POWER_FAULT_ANALYZER Network model. Geometry and labels are "
            "presentation metadata; connectivity is defined by equipment terminal IDs "
            "and explicit terminal-to-bus connections.",
        ),
    )


def export_engineering_svg(document: DiagramDocument, path: str | Path, **kwargs) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_engineering_svg(document, **kwargs), encoding="utf-8")
    return target


def export_engineering_pdf(document: DiagramDocument, path: str | Path, **kwargs) -> Path:
    try:
        import cairosvg
    except ImportError as exc:
        raise RuntimeError("PDF vector export requires the optional CairoSVG dependency.") from exc
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    svg = render_engineering_svg(document, **kwargs)
    cairosvg.svg2pdf(bytestring=svg.encode("utf-8"), write_to=str(target))
    return target


def export_engineering_png(
    document: DiagramDocument, path: str | Path, *, output_width_px: int = 3600,
    output_height_px: int | None = None, **kwargs,
) -> Path:
    """Render review PNGs from the same vector document used by SVG/PDF."""
    try:
        import cairosvg
    except ImportError as exc:
        raise RuntimeError("PNG export requires the optional CairoSVG dependency.") from exc
    if output_width_px < 300:
        raise ValueError("output_width_px must be at least 300 pixels.")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    svg = render_engineering_svg(document, **kwargs)
    cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        write_to=str(target),
        output_width=output_width_px,
        output_height=output_height_px,
    )
    return target
