"""Colorbar drawn as an overlay in the bottom-right of the canvas.

KEGG maps almost always have whitespace there, and overlaying keeps the output
the same size as the original map, so the SVG lines up with the PNG a reader may
already have. A semi-opaque backing rectangle covers the cases where it does not.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from . import colormap

LEGEND_W = 92.0
LEGEND_H = 200.0
MARGIN = 12.0
BAR_W = 20.0
BAR_H = 160.0
BAR_STEPS = 64
FONT = 9


def draw(canvas_w: float, canvas_h: float, cmap: str, vmin: float, vmax: float) -> str:
    if canvas_w < LEGEND_W + 2 * MARGIN or canvas_h < LEGEND_H + 2 * MARGIN:
        return ""

    left = canvas_w - LEGEND_W - MARGIN
    top = canvas_h - LEGEND_H - MARGIN
    bar_x = left + 10
    bar_y = top + 26

    table = colormap.lut(cmap)
    parts = [
        (
            f'<rect x="{_n(left)}" y="{_n(top)}" width="{_n(LEGEND_W)}" '
            f'height="{_n(LEGEND_H)}" fill="#ffffff" fill-opacity="0.85" '
            'stroke="#666666" stroke-width="0.5"/>'
        ),
        (
            f'<text x="{_n(left + 8)}" y="{_n(top + 16)}" font-family="sans-serif" '
            f'font-size="{FONT}" fill="#000000">{escape(cmap)}</text>'
        ),
    ]

    # Bottom of the bar is vmin, top is vmax, matching how a reader expects a
    # vertical scale to run.
    step_h = BAR_H / BAR_STEPS
    for i in range(BAR_STEPS):
        index = round((BAR_STEPS - 1 - i) / (BAR_STEPS - 1) * (len(table) - 1))
        parts.append(
            f'<rect x="{_n(bar_x)}" y="{_n(bar_y + i * step_h)}" width="{_n(BAR_W)}" '
            f'height="{_n(step_h + 0.5)}" fill="{table[index]}" fill-opacity="1.00"/>'
        )
    parts.append(
        f'<rect x="{_n(bar_x)}" y="{_n(bar_y)}" width="{_n(BAR_W)}" height="{_n(BAR_H)}" '
        'fill="none" stroke="#666666" stroke-width="0.5"/>'
    )

    mid = (vmin + vmax) / 2
    for value, y in ((vmax, bar_y), (mid, bar_y + BAR_H / 2), (vmin, bar_y + BAR_H)):
        parts.append(
            f'<text x="{_n(bar_x + BAR_W + 6)}" y="{_n(y)}" dominant-baseline="central" '
            f'font-family="sans-serif" font-size="{FONT}" fill="#000000">'
            f"{_tick(value)}</text>"
        )

    return f'<g id="kegg-map-kit-legend">{"".join(parts)}</g>'


def _tick(value: float) -> str:
    return f"{value:g}"


def _n(value: float) -> str:
    return f"{value:.2f}"
