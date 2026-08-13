"""SVG construction.

Two modes share the same overlay logic. Raster mode base64-embeds KEGG's own map
PNG and paints translucent rectangles on top, so the output looks exactly like a
KEGG figure. Vector mode redraws the boxes and connections from KGML alone, which
loses KEGG's decorations but is fully editable.

A box is split into vertical slices, one per (matched KO x input column) pair, so
that a single box carrying several orthologs across several samples stays
readable.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from xml.sax.saxutils import escape, quoteattr

from . import colormap, fetch, intable, kgml

MAX_SLICES = 12
ENTRY_URL = "https://www.kegg.jp/entry/{ko}"
UNMATCHED_FILL = "#ffffff"
UNMATCHED_STROKE = "#999999"
LABEL_SIZE = 8


class RenderError(ValueError):
    """Raised when the requested render cannot be produced."""


@dataclass
class RenderOpts:
    mode: str = "raster"
    opacity: float = 0.75
    links: bool = True
    legend: bool = True
    na_color: str | None = None
    cmap: str = "coolwarm"
    vmin: float | None = None
    vmax: float | None = None


@dataclass
class Stats:
    input_kos: int = 0
    matched_kos: int = 0
    matched_boxes: int = 0
    capped_entries: int = 0


@dataclass(frozen=True)
class _Slice:
    fill: str
    tip: str


def render(
    pathway: kgml.Pathway,
    table: intable.Table,
    opts: RenderOpts,
    png: bytes | None = None,
) -> tuple[str, Stats]:
    if opts.mode not in ("raster", "vector"):
        raise RenderError(f"unknown render mode {opts.mode!r}")
    if opts.mode == "raster" and png is None:
        raise RenderError("raster mode needs the map PNG")

    vmin, vmax = colormap.resolve_scale(intable.values(table), opts.cmap, opts.vmin, opts.vmax)
    if opts.mode == "raster":
        px_w, px_h = fetch.png_size(png)
        width, height = float(px_w), float(px_h)
    else:
        width, height = kgml.bounds(pathway)

    stats = Stats(input_kos=len(table.rows))
    matched: set[str] = set()

    overlay: list[str] = []
    coloured: set[str] = set()
    for entry in pathway.entries:
        if entry.box is None:
            continue
        slices = _slices_for(entry, table, opts, vmin, vmax)
        if not slices:
            continue
        matched.update(k for k in entry.ko_ids if k in table.rows)
        coloured.add(entry.id)
        stats.matched_boxes += 1
        if len(slices) > MAX_SLICES:
            slices = slices[:MAX_SLICES]
            stats.capped_entries += 1
        overlay.append(_box_svg(entry, slices, table, opts))

    stats.matched_kos = len(matched)

    body: list[str] = []
    if opts.mode == "raster":
        payload = base64.b64encode(png).decode("ascii")
        body.append(
            f'<image x="0" y="0" width="{_n(width)}" height="{_n(height)}" '
            f'href="data:image/png;base64,{payload}"/>'
        )
    else:
        body.extend(_relation_lines(pathway))
        body.extend(_vector_base_boxes(pathway, coloured))

    body.append('<g id="kegg-svg-overlay">' + "".join(overlay) + "</g>")

    if opts.mode == "vector":
        body.extend(_vector_labels(pathway))

    body.append(_legend_svg(width, height, table, opts, vmin, vmax))

    header = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{_n(width)}" height="{_n(height)}" '
        f'viewBox="0 0 {_n(width)} {_n(height)}">'
    )
    title = f"<title>{escape(pathway.title or pathway.name)}</title>"
    return header + title + "".join(body) + "</svg>", stats


def _slices_for(
    entry: kgml.Entry,
    table: intable.Table,
    opts: RenderOpts,
    vmin: float,
    vmax: float,
) -> list[_Slice]:
    """One slice per (matched KO, input column), KGML order then column order."""
    out: list[_Slice] = []
    for ko in entry.ko_ids:
        row = table.rows.get(ko)
        if row is None:
            continue
        for cell in row:
            if cell is None:
                if opts.na_color is None:
                    continue
                out.append(_Slice(fill=opts.na_color, tip=f"{ko}: no data"))
            elif table.mode == "color":
                out.append(_Slice(fill=str(cell), tip=f"{ko}: {cell}"))
            else:
                value = float(cell)
                out.append(
                    _Slice(
                        fill=colormap.to_hex(value, opts.cmap, vmin, vmax),
                        tip=f"{ko}: {value:g}",
                    )
                )
    return out


def _box_svg(
    entry: kgml.Entry, slices: list[_Slice], table: intable.Table, opts: RenderOpts
) -> str:
    box = entry.box
    assert box is not None
    opacity = opts.opacity if opts.mode == "raster" else 1.0
    step = box.w / len(slices)

    parts = []
    for i, piece in enumerate(slices):
        x = box.x + i * step
        # The last slice absorbs the rounding remainder so the slices tile the
        # box exactly and no background shows through the seams.
        w = (box.x + box.w) - x if i == len(slices) - 1 else step
        parts.append(
            f'<rect x="{_n(x)}" y="{_n(box.y)}" width="{_n(w)}" height="{_n(box.h)}" '
            f'fill={quoteattr(piece.fill)} fill-opacity="{opacity:.2f}"/>'
        )

    label = entry.label or ",".join(entry.ko_ids)
    tip = escape(f"{label} — " + "; ".join(p.tip for p in slices))
    group = f"<g><title>{tip}</title>{''.join(parts)}</g>"

    # A box carrying several orthologs links to the first one the user actually
    # supplied, not the first one KGML happens to list.
    linked = next((k for k in entry.ko_ids if k in table.rows), None)
    if opts.links and linked is not None:
        href = ENTRY_URL.format(ko=linked)
        return f'<a href="{href}" target="_blank" rel="noopener">{group}</a>'
    return group


def _vector_base_boxes(pathway: kgml.Pathway, coloured: set[str]) -> list[str]:
    """Uncoloured rectangles get a neutral base so they are still visible.

    Boxes the overlay paints are left out: a base underneath them would be
    invisible anyway and would double the rectangle count of the document.
    """
    out = []
    for entry in pathway.entries:
        if entry.box is None or entry.id in coloured:
            continue
        box = entry.box
        out.append(
            f'<rect x="{_n(box.x)}" y="{_n(box.y)}" width="{_n(box.w)}" '
            f'height="{_n(box.h)}" fill="{UNMATCHED_FILL}" fill-opacity="1.00" '
            f'stroke="{UNMATCHED_STROKE}" stroke-width="0.5"/>'
        )
    return out


def _vector_labels(pathway: kgml.Pathway) -> list[str]:
    out = []
    for entry in pathway.entries:
        if entry.box is None or not entry.label:
            continue
        box = entry.box
        out.append(
            f'<text x="{_n(box.x + box.w / 2)}" y="{_n(box.y + box.h / 2)}" '
            f'text-anchor="middle" dominant-baseline="central" '
            f'font-family="sans-serif" font-size="{LABEL_SIZE}" fill="#000000">'
            f"{escape(entry.label)}</text>"
        )
    return out


def _relation_lines(pathway: kgml.Pathway) -> list[str]:
    by_id = kgml.entries_by_id(pathway)
    out = []
    for a, b in pathway.relations:
        first, second = by_id.get(a), by_id.get(b)
        if first is None or second is None or first.box is None or second.box is None:
            continue
        out.append(
            f'<line x1="{_n(first.box.x + first.box.w / 2)}" '
            f'y1="{_n(first.box.y + first.box.h / 2)}" '
            f'x2="{_n(second.box.x + second.box.w / 2)}" '
            f'y2="{_n(second.box.y + second.box.h / 2)}" '
            f'stroke="{UNMATCHED_STROKE}" stroke-width="0.75"/>'
        )
    return out


def _legend_svg(width, height, table, opts, vmin, vmax) -> str:
    """Filled in by Task 6."""
    return ""


def _n(value: float) -> str:
    return f"{value:.2f}"
