"""Safe, loss-aware importer for QElectroTech ``.elmt`` vector definitions.

The importer deliberately keeps source coordinates, XML fragments, terminal UUIDs,
source hashes and licence provenance.  It does not claim IEC conformity: imported
items retain the normative status supplied by the pinned source manifest.
"""

from __future__ import annotations

import hashlib
import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_MAX_XML_BYTES: Final = 5 * 1024 * 1024
_MAX_XML_ELEMENTS: Final = 20_000
_ALLOWED_VISUAL_PRIMITIVES: Final = frozenset(
    {"line", "ellipse", "rect", "rectangle", "arc", "polygon", "text"}
)
_NON_VISUAL_ELEMENTS: Final = frozenset({"terminal", "dynamic_text", "input"})
_FLOAT_PATTERN: Final = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


class QETSymbolError(ValueError):
    """Base exception for malformed or unsupported QElectroTech symbols."""


class QETSymbolFormatError(QETSymbolError):
    """Raised when an ``.elmt`` document violates the supported source format."""


class QETSymbolIntegrityError(QETSymbolError):
    """Raised when the source bytes do not match the pinned source manifest."""


@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Bounds:
    """Axis-aligned bounds in the exact coordinate system stored in the source."""

    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass(frozen=True, slots=True)
class SymbolProvenance:
    repository: str
    source_commit: str
    source_path: str
    expected_git_blob_sha1: str
    license_identifier: str
    asset_id: str | None = None
    normative_status: str = "candidate"
    normative_reference: str | None = None
    normative_edition: str | None = None


@dataclass(frozen=True, slots=True)
class TerminalDefinition:
    uuid: str
    name: str
    position: Point
    orientation: str
    terminal_type: str


@dataclass(frozen=True, slots=True)
class SymbolPrimitive:
    """A source primitive with its original attributes and XML preserved."""

    kind: str
    attributes: tuple[tuple[str, str], ...]
    raw_xml: str

    def get(self, name: str, default: str | None = None) -> str | None:
        return dict(self.attributes).get(name, default)

    def number(self, name: str, default: float | None = None) -> float:
        raw = self.get(name)
        if raw is None:
            if default is None:
                raise QETSymbolFormatError(
                    f"Primitive {self.kind!r} is missing numeric attribute {name!r}."
                )
            return default
        return _parse_float(raw, f"{self.kind}.{name}")


@dataclass(frozen=True, slots=True)
class SymbolDefinition:
    source_uuid: str
    display_name: str
    names: tuple[tuple[str, str], ...]
    source_width: float
    source_height: float
    hotspot: Point
    primitives: tuple[SymbolPrimitive, ...]
    terminals: tuple[TerminalDefinition, ...]
    provenance: SymbolProvenance
    author: str | None
    source_license_notice: str | None
    format_version: str
    source_sha256: str
    source_git_blob_sha1: str
    original_xml: bytes
    unsupported_elements: tuple[str, ...] = ()

    def name_for(self, locale: str = "en") -> str:
        names = dict(self.names)
        language = locale.replace("-", "_")
        return (
            names.get(language)
            or names.get(language.split("_")[0])
            or names.get("en")
            or self.display_name
        )

    @property
    def visual_primitives(self) -> tuple[SymbolPrimitive, ...]:
        return tuple(item for item in self.primitives if item.kind in _ALLOWED_VISUAL_PRIMITIVES)

    @property
    def bounds(self) -> Bounds:
        points: list[Point] = [terminal.position for terminal in self.terminals]
        for primitive in self.visual_primitives:
            points.extend(_primitive_points(primitive))
        if not points:
            # The source width and height are retained as a safe fallback for
            # definitions that contain only metadata and no drawable geometry.
            points = [Point(0.0, 0.0), Point(self.source_width, self.source_height)]
        left = min(point.x for point in points)
        right = max(point.x for point in points)
        top = min(point.y for point in points)
        bottom = max(point.y for point in points)
        if math.isclose(left, right):
            right = left + 1.0
        if math.isclose(top, bottom):
            bottom = top + 1.0
        return Bounds(left, top, right, bottom)

    def terminal(self, terminal_uuid: str) -> TerminalDefinition:
        for terminal in self.terminals:
            if terminal.uuid == terminal_uuid:
                return terminal
        raise KeyError(f"Symbol {self.source_uuid} has no terminal {terminal_uuid!r}.")

    def require_connectable(self) -> None:
        if self.unsupported_elements:
            names = ", ".join(self.unsupported_elements)
            raise QETSymbolFormatError(
                f"Symbol contains unsupported visual elements: {names}. It cannot be rendered for connection use."
            )
        if not self.terminals:
            raise QETSymbolFormatError(
                "Symbol has no explicit terminal definitions and cannot be used as a connectable symbol."
            )


def git_blob_sha1(data: bytes) -> str:
    """Return the Git blob object hash for *data*, not a plain SHA-1 digest."""

    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def parse_qet_elmt(
    source: bytes | str,
    *,
    provenance: SymbolProvenance,
    locale: str = "es",
) -> SymbolDefinition:
    """Parse one QET element, verifying its pinned Git blob hash first.

    ``str`` input is treated as XML text. Production callers should use
    :func:`load_qet_elmt` or pass raw bytes so that source hashes are byte-exact.
    """

    data = source.encode("utf-8") if isinstance(source, str) else bytes(source)
    if not data or len(data) > _MAX_XML_BYTES:
        raise QETSymbolFormatError(
            f"Symbol XML size must be between 1 byte and {_MAX_XML_BYTES} bytes."
        )
    upper_data = data.upper()
    if b"<!DOCTYPE" in upper_data or b"<!ENTITY" in upper_data:
        raise QETSymbolFormatError(
            "DOCTYPE and ENTITY declarations are not accepted in QET symbol XML."
        )

    actual_git_sha = git_blob_sha1(data)
    if (
        provenance.expected_git_blob_sha1
        and actual_git_sha.lower() != provenance.expected_git_blob_sha1.lower()
    ):
        raise QETSymbolIntegrityError(
            f"Pinned Git blob mismatch for {provenance.source_path}: "
            f"expected {provenance.expected_git_blob_sha1}, got {actual_git_sha}."
        )

    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise QETSymbolFormatError(f"Invalid QET XML in {provenance.source_path}: {exc}") from exc

    if root.tag != "definition" or root.get("type") != "element":
        raise QETSymbolFormatError("QET file must have a <definition type='element'> root.")
    if sum(1 for _ in root.iter()) > _MAX_XML_ELEMENTS:
        raise QETSymbolFormatError(f"QET symbol exceeds {_MAX_XML_ELEMENTS} XML elements.")

    uuid_node = root.find("uuid")
    source_uuid = uuid_node.get("uuid", "").strip("{}") if uuid_node is not None else ""
    if not source_uuid:
        raise QETSymbolFormatError("QET symbol is missing its source UUID.")

    names_node = root.find("names")
    names: tuple[tuple[str, str], ...] = ()
    if names_node is not None:
        names = tuple(
            (entry.get("lang", ""), (entry.text or "").strip())
            for entry in names_node.findall("name")
            if entry.get("lang") and (entry.text or "").strip()
        )
    names_by_language = dict(names)
    display_name = (
        names_by_language.get(locale.replace("-", "_"))
        or names_by_language.get(locale.split("-")[0])
        or names_by_language.get("en")
        or source_uuid
    )

    width = _attribute_float(root, "width", default=1.0)
    height = _attribute_float(root, "height", default=1.0)
    hotspot = Point(
        _attribute_float(root, "hotspot_x", default=0.0),
        _attribute_float(root, "hotspot_y", default=0.0),
    )

    description = root.find("description")
    if description is None:
        raise QETSymbolFormatError("QET symbol is missing its <description> node.")

    primitives: list[SymbolPrimitive] = []
    terminals: list[TerminalDefinition] = []
    terminal_uuids: set[str] = set()
    unsupported: list[str] = []
    for element in description:
        if element.tag == "terminal":
            terminal_uuid = element.get("uuid", "").strip("{}")
            if not terminal_uuid:
                raise QETSymbolFormatError("A QET terminal is missing its UUID.")
            if terminal_uuid in terminal_uuids:
                raise QETSymbolFormatError(f"Duplicate QET terminal UUID {terminal_uuid!r}.")
            terminal_uuids.add(terminal_uuid)
            terminals.append(
                TerminalDefinition(
                    uuid=terminal_uuid,
                    name=element.get("name", ""),
                    position=Point(
                        _attribute_float(element, "x", default=0.0),
                        _attribute_float(element, "y", default=0.0),
                    ),
                    orientation=element.get("orientation", ""),
                    terminal_type=element.get("type", "Generic"),
                )
            )
            continue

        primitive = SymbolPrimitive(
            kind=element.tag,
            attributes=tuple(element.attrib.items()),
            raw_xml=ET.tostring(element, encoding="unicode"),
        )
        primitives.append(primitive)
        if element.tag in _ALLOWED_VISUAL_PRIMITIVES:
            # Validate all geometric coordinates at import time, not lazily at render.
            tuple(_primitive_points(primitive))
        elif element.tag not in _NON_VISUAL_ELEMENTS:
            unsupported.append(element.tag)

    info_node = root.find("informations")
    information = info_node.text if info_node is not None else ""
    author = _extract_info_value(information or "", "Author")
    license_notice = _extract_info_value(information or "", "License")

    return SymbolDefinition(
        source_uuid=source_uuid,
        display_name=display_name,
        names=names,
        source_width=width,
        source_height=height,
        hotspot=hotspot,
        primitives=tuple(primitives),
        terminals=tuple(terminals),
        provenance=provenance,
        author=author,
        source_license_notice=license_notice,
        format_version=root.get("version", "unknown"),
        source_sha256=hashlib.sha256(data).hexdigest(),
        source_git_blob_sha1=actual_git_sha,
        original_xml=data,
        unsupported_elements=tuple(sorted(set(unsupported))),
    )


def load_qet_elmt(
    path: str | Path,
    *,
    provenance: SymbolProvenance,
    locale: str = "es",
) -> SymbolDefinition:
    """Load and parse a pinned QET symbol file from disk."""

    file_path = Path(path)
    try:
        data = file_path.read_bytes()
    except OSError as exc:
        raise QETSymbolError(f"Cannot read QET symbol file {file_path}: {exc}") from exc
    return parse_qet_elmt(data, provenance=provenance, locale=locale)


def _parse_float(raw: str, label: str) -> float:
    if not _FLOAT_PATTERN.fullmatch(raw.strip()):
        raise QETSymbolFormatError(f"Invalid numeric value for {label}: {raw!r}.")
    value = float(raw)
    if not math.isfinite(value):
        raise QETSymbolFormatError(f"Non-finite numeric value for {label}: {raw!r}.")
    return value


def _attribute_float(element: ET.Element, key: str, *, default: float) -> float:
    value = element.get(key)
    return default if value is None else _parse_float(value, f"{element.tag}.{key}")


def _extract_info_value(information: str, key: str) -> str | None:
    prefix = f"{key}:"
    for line in information.splitlines():
        if line.strip().startswith(prefix):
            return line.strip()[len(prefix) :].strip() or None
    return None


def _primitive_points(primitive: SymbolPrimitive) -> Iterable[Point]:
    kind = primitive.kind
    if kind == "line":
        yield Point(primitive.number("x1"), primitive.number("y1"))
        yield Point(primitive.number("x2"), primitive.number("y2"))
    elif kind in {"ellipse", "rect", "rectangle", "arc"}:
        x, y = primitive.number("x"), primitive.number("y")
        width, height = primitive.number("width"), primitive.number("height")
        yield Point(x, y)
        yield Point(x + width, y + height)
    elif kind == "polygon":
        attributes = dict(primitive.attributes)
        coordinate_pairs = sorted(
            {int(match.group(1)) for key in attributes if (match := re.fullmatch(r"x(\d+)", key))}
        )
        for index in coordinate_pairs:
            y_key = f"y{index}"
            if y_key not in attributes:
                raise QETSymbolFormatError(f"Polygon is missing {y_key!r}.")
            yield Point(
                _parse_float(attributes[f"x{index}"], f"polygon.x{index}"),
                _parse_float(attributes[y_key], f"polygon.y{index}"),
            )
    elif kind == "text":
        yield Point(primitive.number("x"), primitive.number("y"))
