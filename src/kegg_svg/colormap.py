"""Colormaps as anchor stops, interpolated to 256-entry lookup tables.

Anchor RGB values are sampled from the matplotlib colormaps of the same names.
Interpolating a handful of stops keeps the source readable and avoids a
dependency; the result is visually indistinguishable at 256 levels.
"""

from __future__ import annotations

LUT_SIZE = 256

CMAPS: dict[str, tuple[tuple[int, int, int], ...]] = {
    "coolwarm": ((59, 76, 192), (221, 221, 221), (180, 4, 38)),
    "RdBu": ((103, 0, 31), (247, 247, 247), (5, 48, 97)),
    "viridis": (
        (68, 1, 84),
        (59, 82, 139),
        (33, 145, 140),
        (94, 201, 98),
        (253, 231, 37),
    ),
    "Reds": ((255, 245, 240), (252, 146, 114), (203, 24, 29), (103, 0, 13)),
    "Blues": ((247, 251, 255), (107, 174, 214), (8, 81, 156), (8, 48, 107)),
}

DIVERGING = frozenset({"coolwarm", "RdBu"})

_CACHE: dict[str, list[str]] = {}


class UnknownColormap(ValueError):
    """Raised when a colormap name is not one of CMAPS."""


def names() -> list[str]:
    return sorted(CMAPS)


def is_diverging(name: str) -> bool:
    if name not in CMAPS:
        raise UnknownColormap(f"unknown colormap {name!r}; choose from {', '.join(names())}")
    return name in DIVERGING


def lut(name: str) -> list[str]:
    """Return the 256-entry hex lookup table for ``name``, building it once."""
    cached = _CACHE.get(name)
    if cached is not None:
        return cached
    if name not in CMAPS:
        raise UnknownColormap(f"unknown colormap {name!r}; choose from {', '.join(names())}")

    stops = CMAPS[name]
    segments = len(stops) - 1
    table: list[str] = []
    for i in range(LUT_SIZE):
        pos = i / (LUT_SIZE - 1) * segments
        lo = min(int(pos), segments - 1)
        frac = pos - lo
        start, end = stops[lo], stops[lo + 1]
        rgb = tuple(round(start[c] + (end[c] - start[c]) * frac) for c in range(3))
        table.append("#%02x%02x%02x" % rgb)
    _CACHE[name] = table
    return table


def resolve_scale(
    values: list[float], name: str, vmin: float | None, vmax: float | None
) -> tuple[float, float]:
    """Fill in whichever of vmin/vmax was not supplied.

    Diverging colormaps auto-scale symmetrically around zero so that the neutral
    midpoint colour lands on zero; sequential ones use the data min and max.
    """
    if vmin is not None and vmax is not None:
        return (vmin, vmax)
    if not values:
        auto_min, auto_max = 0.0, 1.0
    elif is_diverging(name):
        extent = max(abs(v) for v in values) or 1.0
        auto_min, auto_max = -extent, extent
    else:
        auto_min, auto_max = min(values), max(values)
    return (auto_min if vmin is None else vmin, auto_max if vmax is None else vmax)


def to_hex(value: float, name: str, vmin: float, vmax: float) -> str:
    table = lut(name)
    if vmax == vmin:
        return table[LUT_SIZE // 2]
    frac = (value - vmin) / (vmax - vmin)
    index = round(frac * (LUT_SIZE - 1))
    return table[max(0, min(LUT_SIZE - 1, index))]
