"""User input table parsing.

Accepts the same shape as the KEGG Mapper "Color" tool: a KO identifier in the
first field, then either colours or numbers. The file is classified once, by
majority of parseable cells, so a whole file is either a colour file or a value
file and never a confusing mixture.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

KO_RE = re.compile(r"^K\d{5}$", re.IGNORECASE)
HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

# The CSS/SVG named colours users actually reach for. Anything outside this set
# has to be written as a hex triple.
NAMED_COLORS = frozenset(
    [
        "aqua",
        "aquamarine",
        "beige",
        "black",
        "blue",
        "brown",
        "chartreuse",
        "chocolate",
        "coral",
        "crimson",
        "cyan",
        "darkblue",
        "darkcyan",
        "darkgray",
        "darkgreen",
        "darkgrey",
        "darkmagenta",
        "darkorange",
        "darkred",
        "darkviolet",
        "deeppink",
        "dodgerblue",
        "firebrick",
        "forestgreen",
        "fuchsia",
        "gold",
        "gray",
        "green",
        "grey",
        "hotpink",
        "indigo",
        "ivory",
        "khaki",
        "lavender",
        "lightblue",
        "lightgray",
        "lightgreen",
        "lightgrey",
        "lightpink",
        "lightyellow",
        "lime",
        "limegreen",
        "magenta",
        "maroon",
        "navy",
        "olive",
        "orange",
        "orangered",
        "orchid",
        "pink",
        "plum",
        "purple",
        "red",
        "royalblue",
        "salmon",
        "seagreen",
        "sienna",
        "silver",
        "skyblue",
        "slateblue",
        "steelblue",
        "tan",
        "teal",
        "thistle",
        "tomato",
        "turquoise",
        "violet",
        "wheat",
        "white",
        "yellow",
        "yellowgreen",
    ]
)


class InputError(ValueError):
    """Raised for any malformed input row, always naming the 1-based line."""


@dataclass(frozen=True)
class Table:
    mode: str  # "color" or "value"
    rows: dict[str, tuple[str | float | None, ...]]
    n_cols: int
    fg: dict[str, str] = field(default_factory=dict)


def parse(fileobj) -> Table:
    records = _read_records(fileobj)
    if not records:
        raise InputError("input is empty: expected at least one KO row")
    records = _drop_header(records)
    if not records:
        raise InputError("input contains a header but no data rows")

    mode = _classify(records)
    n_cols = max(len(cells) for _, _, cells in records)

    rows: dict[str, tuple[str | float | None, ...]] = {}
    fg: dict[str, str] = {}
    seen_at: dict[str, int] = {}

    for lineno, ko, cells in records:
        if ko in seen_at:
            raise InputError(
                f"duplicate KO {ko} on line {lineno} (first seen on line {seen_at[ko]})"
            )
        seen_at[ko] = lineno
        parsed: list[str | float | None] = []
        for cell in cells:
            if not cell:
                parsed.append(None)
            elif mode == "color":
                bg, foreground = _parse_color_cell(cell, lineno)
                parsed.append(bg)
                if foreground:
                    fg[ko] = foreground
            else:
                parsed.append(_parse_value_cell(cell, lineno))
        parsed.extend([None] * (n_cols - len(parsed)))
        rows[ko] = tuple(parsed)

    return Table(mode=mode, rows=rows, n_cols=n_cols, fg=fg)


def _read_records(fileobj) -> list[tuple[int, str, list[str]]]:
    """Return (lineno, raw_first_field, remaining_cells) for each data line."""
    records = []
    for lineno, raw in enumerate(fileobj, start=1):
        line = raw.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        sep = "\t" if "\t" in line else ","
        fields = [f.strip() for f in line.split(sep)]
        records.append((lineno, fields[0].upper(), fields[1:]))
    return records


def _drop_header(records):
    """A first row whose first field is not a KO id is a header, not data."""
    if records and not KO_RE.match(records[0][1]):
        rest = records[1:]
        if rest and all(KO_RE.match(ko) for _, ko, _ in rest):
            return rest
    return records


def _classify(records) -> str:
    """Pick colour or value mode by majority of parseable non-blank cells."""
    color_hits = value_hits = 0
    for lineno, ko, cells in records:
        if not KO_RE.match(ko):
            raise InputError(f"line {lineno}: {ko!r} is not a KO identifier (expected K#####)")
        if not cells or not any(cells):
            raise InputError(f"line {lineno}: {ko} has no colour or value columns")
        for cell in cells:
            if not cell:
                continue
            if _is_color(cell.split(",")[0]):
                color_hits += 1
            elif _is_float(cell):
                value_hits += 1
    if color_hits == 0 and value_hits == 0:
        raise InputError("no cell in the input parsed as a colour or a number")
    return "color" if color_hits >= value_hits else "value"


def _is_color(text: str) -> bool:
    return bool(HEX_RE.match(text)) or text.lower() in NAMED_COLORS


def _is_float(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _parse_color_cell(cell: str, lineno: int) -> tuple[str, str | None]:
    """Split KEGG Mapper's optional ``bg,fg`` pair. Returns (background, fg|None)."""
    parts = [p.strip() for p in cell.split(",")]
    background = parts[0]
    if not _is_color(background):
        raise InputError(f"line {lineno}: {cell!r} is not a colour")
    foreground = parts[1] if len(parts) > 1 and _is_color(parts[1]) else None
    return background, foreground


def _parse_value_cell(cell: str, lineno: int) -> float:
    try:
        return float(cell)
    except ValueError:
        raise InputError(f"line {lineno}: {cell!r} is not a number") from None


def values(table: Table) -> list[float]:
    if table.mode != "value":
        return []
    return [c for row in table.rows.values() for c in row if isinstance(c, float)]
