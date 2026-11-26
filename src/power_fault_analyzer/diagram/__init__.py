"""Diagram geometry and document export primitives."""
from .layout import *  # noqa: F403
from .routing import RouteResult, route_orthogonal_avoiding, snap_to_terminal
from .topology_layout import LayoutEdge, LayoutNode, TopologyLayout, layout_topology
from .svg_export import SvgLabel, SvgMetadata, SvgPath, SvgSymbol, render_svg

from .model_projection import (DiagramDocument, DiagramProjectionError, project_network_to_diagram, validate_diagram_document)
from .model_document_export import render_engineering_svg, export_engineering_svg, export_engineering_pdf
from .symbol_catalog import (
    EngineeringSymbolDefinition,
    SYMBOL_CATALOG,
    SYMBOL_DEFINITIONS,
    SymbolTerminal,
    SymbolPrimitive,
    get_symbol_definition,
)
