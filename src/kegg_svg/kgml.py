"""KGML parsing.

KEGG serves pathway structure as KGML, an XML format where every drawable item
is an <entry> with a nested <graphics>. The important subtlety is that
graphics/@x and @y give the *centre* of the shape, while SVG wants the top-left
corner, so every box is shifted by half its width and height on the way in.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

DEFAULT_MARGIN = 20.0
FALLBACK_CANVAS = (400.0, 300.0)


class KgmlError(ValueError):
    """Raised when the KGML is malformed or is not KGML at all."""


@dataclass(frozen=True)
class Box:
    """Rectangle in SVG coordinates: x, y are the top-left corner."""

    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class Entry:
    id: str
    ko_ids: tuple[str, ...]
    label: str
    box: Box | None
    link: str


@dataclass(frozen=True)
class Pathway:
    name: str
    title: str
    entries: tuple[Entry, ...]
    relations: tuple[tuple[str, str], ...]


def parse(kgml_text: str) -> Pathway:
    try:
        root = ET.fromstring(kgml_text)
    except ET.ParseError as exc:
        raise KgmlError(f"could not parse KGML: {exc}") from exc
    if root.tag != "pathway":
        raise KgmlError(f"expected a <pathway> root element, found <{root.tag}>")

    entries = tuple(_parse_entry(el) for el in root.findall("entry"))
    relations = tuple(
        (el.get("entry1", ""), el.get("entry2", ""))
        for el in root.findall("relation")
        if el.get("entry1") and el.get("entry2")
    )
    return Pathway(
        name=_strip_prefix(root.get("name", "")),
        title=root.get("title", ""),
        entries=entries,
        relations=relations,
    )


def _parse_entry(el: ET.Element) -> Entry:
    graphics = el.find("graphics")
    name_attr = graphics.get("name", "") if graphics is not None else ""
    return Entry(
        id=el.get("id", ""),
        ko_ids=_ko_ids(el.get("name", "")),
        label=name_attr.split(",")[0].strip(),
        box=_box(graphics),
        link=el.get("link", ""),
    )


def _ko_ids(name_attr: str) -> tuple[str, ...]:
    return tuple(
        token[3:].upper() for token in name_attr.split() if token.lower().startswith("ko:k")
    )


def _box(graphics: ET.Element | None) -> Box | None:
    """Only rectangles are colourable, and only if they carry a full geometry."""
    if graphics is None or graphics.get("type") != "rectangle":
        return None
    try:
        cx = float(graphics.get("x"))  # type: ignore[arg-type]
        cy = float(graphics.get("y"))  # type: ignore[arg-type]
        w = float(graphics.get("width"))  # type: ignore[arg-type]
        h = float(graphics.get("height"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return Box(x=cx - w / 2, y=cy - h / 2, w=w, h=h)


def _strip_prefix(name: str) -> str:
    return name.split(":", 1)[1] if ":" in name else name


def entries_by_id(pathway: Pathway) -> dict[str, Entry]:
    return {entry.id: entry for entry in pathway.entries}


def bounds(pathway: Pathway, margin: float = DEFAULT_MARGIN) -> tuple[float, float]:
    """Canvas size for vector mode: bounding box of all boxes, plus a margin."""
    boxes = [e.box for e in pathway.entries if e.box is not None]
    if not boxes:
        return FALLBACK_CANVAS
    width = max(b.x + b.w for b in boxes) + margin
    height = max(b.y + b.h for b in boxes) + margin
    return (width, height)
