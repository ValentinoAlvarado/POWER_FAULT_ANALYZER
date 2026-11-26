from __future__ import annotations

import hashlib

import pytest

from power_fault_analyzer.infrastructure.symbols.qet_elmt import (
    QETSymbolFormatError,
    QETSymbolIntegrityError,
    SymbolProvenance,
    git_blob_sha1,
    parse_qet_elmt,
)

QET_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<definition version="0.100.0" type="element" link_type="simple" width="40" height="50" hotspot_x="12" hotspot_y="25">
  <uuid uuid="{26db39e2-fbe4-99dc-3da4-86e3592f42bb}" />
  <names>
    <name lang="en">Synchronous generator, three-phase</name>
    <name lang="es">Generador sincrono trifasico</name>
  </names>
  <informations>Author: The QElectroTech team
License: see https://qelectrotech.org/wiki/doc/elements_license</informations>
  <description>
    <ellipse x="-20" y="-20" width="40" height="40" style="line-style:normal;line-weight:normal;filling:none;color:black" />
    <line x1="0" y1="-40" x2="0" y2="-20" style="line-style:normal;line-weight:normal;filling:none;color:black" />
    <arc x="-10" y="5" width="10" height="10" start="0" angle="180" style="line-style:normal;line-weight:normal;filling:none;color:black" />
    <polygon x1="0" y1="0" x2="10" y2="0" x3="5" y3="10" style="line-style:normal;line-weight:normal;filling:none;color:black" />
    <text text="GS" x="-5" y="0" rotation="0" font="Segoe UI,9" color="#000000" />
    <dynamic_text x="1" y="2" text_from="ElementInfo"><text></text></dynamic_text>
    <terminal uuid="{81e0bf81-a12f-4d93-8bce-76e1c640c7ec}" name="L1" x="-10" y="-40" orientation="n" type="Generic" />
    <terminal uuid="{e582c79f-c61b-412b-ae15-fb53f86cb00d}" name="N" x="10" y="40" orientation="s" type="Generic" />
  </description>
</definition>
"""


def _provenance(data: bytes, *, expected: str | None = None) -> SymbolProvenance:
    return SymbolProvenance(
        repository="qelectrotech/qelectrotech-elements",
        source_commit="661f5e9ce5caa76277cafd3ebf0e0320fc4af229",
        source_path="fixture/generator.elmt",
        expected_git_blob_sha1=expected if expected is not None else git_blob_sha1(data),
        license_identifier="CC-BY-3.0",
        asset_id="IEC-GEN-SYNC-3PH-NEUTRAL",
        normative_status="candidate",
    )


def test_parse_qet_symbol_preserves_identity_geometry_terminals_and_source() -> None:
    symbol = parse_qet_elmt(QET_XML, provenance=_provenance(QET_XML), locale="es-PE")

    assert symbol.source_uuid == "26db39e2-fbe4-99dc-3da4-86e3592f42bb"
    assert symbol.display_name == "Generador sincrono trifasico"
    assert symbol.name_for("en-US") == "Synchronous generator, three-phase"
    assert symbol.format_version == "0.100.0"
    assert symbol.source_width == 40.0
    assert symbol.source_height == 50.0
    assert symbol.hotspot.x == 12.0
    assert symbol.hotspot.y == 25.0
    assert symbol.author == "The QElectroTech team"
    assert symbol.provenance.license_identifier == "CC-BY-3.0"
    assert symbol.provenance.normative_status == "candidate"
    assert symbol.source_sha256 == hashlib.sha256(QET_XML).hexdigest()
    assert symbol.source_git_blob_sha1 == git_blob_sha1(QET_XML)
    assert symbol.original_xml == QET_XML
    assert [item.kind for item in symbol.visual_primitives] == [
        "ellipse",
        "line",
        "arc",
        "polygon",
        "text",
    ]
    assert len(symbol.terminals) == 2
    assert symbol.terminal("81e0bf81-a12f-4d93-8bce-76e1c640c7ec").name == "L1"
    assert symbol.bounds.left == -20.0
    assert symbol.bounds.right == 20.0
    assert symbol.bounds.top == -40.0
    assert symbol.bounds.bottom == 40.0


def test_parse_qet_symbol_rejects_pinned_git_blob_mismatch() -> None:
    wrong = _provenance(QET_XML, expected="0" * 40)
    with pytest.raises(QETSymbolIntegrityError, match="Git blob mismatch"):
        parse_qet_elmt(QET_XML, provenance=wrong)


def test_parse_qet_symbol_rejects_non_element_root() -> None:
    bad_xml = b"<qet-element><uuid uuid='abc'/></qet-element>"
    with pytest.raises(QETSymbolFormatError, match="definition type='element'"):
        parse_qet_elmt(bad_xml, provenance=_provenance(bad_xml))


def test_parse_qet_symbol_rejects_non_finite_geometry() -> None:
    bad_xml = QET_XML.replace(b'x="-20"', b'x="nan"', 1)
    with pytest.raises(QETSymbolFormatError, match="Invalid numeric value"):
        parse_qet_elmt(bad_xml, provenance=_provenance(bad_xml))


def test_unknown_visual_elements_are_preserved_but_not_connectable() -> None:
    changed = QET_XML.replace(
        b"<description>",
        b"<description><bezier x1='0' y1='0' x2='1' y2='1' />",
        1,
    )
    symbol = parse_qet_elmt(changed, provenance=_provenance(changed))
    assert symbol.unsupported_elements == ("bezier",)
    assert "<bezier" in symbol.primitives[0].raw_xml
    with pytest.raises(QETSymbolFormatError, match="unsupported visual elements"):
        symbol.require_connectable()


def test_connectable_symbol_requires_explicit_terminal_definitions() -> None:
    changed = QET_XML.replace(b"<terminal ", b"<terminal ", 1)
    changed = changed.replace(
        b'    <terminal uuid="{81e0bf81-a12f-4d93-8bce-76e1c640c7ec}" name="L1" x="-10" y="-40" orientation="n" type="Generic" />\n',
        b"",
    ).replace(
        b'    <terminal uuid="{e582c79f-c61b-412b-ae15-fb53f86cb00d}" name="N" x="10" y="40" orientation="s" type="Generic" />\n',
        b"",
    )
    symbol = parse_qet_elmt(changed, provenance=_provenance(changed))
    with pytest.raises(QETSymbolFormatError, match="no explicit terminal"):
        symbol.require_connectable()
