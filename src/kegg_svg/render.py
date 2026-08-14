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

from . import colormap, fetch, intable, kgml, legend

MAX_SLICES = 12
ENTRY_URL = "https://www.kegg.jp/entry/{ko}"
UNMATCHED_FILL = "#ffffff"
UNMATCHED_STROKE = "#999999"
OUTLINE_WIDTH = "0.5"
LABEL_SIZE = 8
LABEL_FILL = "#000000"


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
    label_values: bool = False
    label_size: float = 7.0
    unmapped_color: str | None = None


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
    annotations: list[str] = []
    unmapped: list[str] = []
    coloured: set[str] = set()
    # Entries already given a flat fill, so the vector base pass skips them.
    painted: set[str] = set()
    for entry in pathway.entries:
        if entry.box is None:
            continue
        slices = _slices_for(entry, table, opts, vmin, vmax)
        if not slices:
            # An ortholog box the user supplied no data for. Boxes carrying no
            # KO at all — compounds, links to other pathways — are not "missing
            # data" and are left as KEGG drew them.
            if opts.unmapped_color and entry.ko_ids:
                unmapped.append(_unmapped_svg(entry, opts))
                painted.add(entry.id)
            continue
        matched.update(k for k in entry.ko_ids if k in table.rows)
        coloured.add(entry.id)
        painted.add(entry.id)
        stats.matched_boxes += 1
        if len(slices) > MAX_SLICES:
            slices = slices[:MAX_SLICES]
            stats.capped_entries += 1
        overlay.append(_box_svg(entry, slices, table, opts))
        if opts.label_values:
            annotations.append(_value_label_svg(entry, table, opts))

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
        body.extend(_vector_base_boxes(pathway, painted))

    if opts.unmapped_color:
        body.append('<g id="kegg-svg-unmapped">' + "".join(unmapped) + "</g>")

    body.append('<g id="kegg-svg-overlay">' + "".join(overlay) + "</g>")

    if opts.mode == "vector":
        body.extend(_vector_labels(pathway, table))

    if opts.label_values:
        body.append('<g id="kegg-svg-values">' + "".join(annotations) + "</g>")

    body.append(_legend_svg(width, height, table, opts, vmin, vmax))

    header = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
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


def _unmapped_svg(entry: kgml.Entry, opts: RenderOpts) -> str:
    """Flat fill over an ortholog box the input said nothing about."""
    box = entry.box
    assert box is not None
    opacity = opts.opacity if opts.mode == "raster" else 1.0
    stroke = (
        f' stroke="{UNMATCHED_STROKE}" stroke-width="{OUTLINE_WIDTH}"'
        if opts.mode == "vector"
        else ""
    )
    tip = escape(f"{entry.label or ','.join(entry.ko_ids)} — no data")
    return (
        f"<g><title>{tip}</title>"
        f'<rect x="{_n(box.x)}" y="{_n(box.y)}" width="{_n(box.w)}" height="{_n(box.h)}" '
        f"fill={quoteattr(opts.unmapped_color or '')} fill-opacity=\"{opacity:.2f}\"{stroke}/>"
        "</g>"
    )


def _value_lines(entry: kgml.Entry, table: intable.Table) -> list[str]:
    """One formatted line per matched KO, in KGML order, so line N reads against
    slice N of the box. A KO measured across several columns keeps its values on
    a single line rather than pushing the stack taller than the box it labels."""
    if table.mode != "value":
        return []
    lines = []
    for ko in entry.ko_ids:
        row = table.rows.get(ko)
        if row is None:
            continue
        cells = [f"{float(c):+.2f}" for c in row if c is not None]
        if cells:
            lines.append(", ".join(cells))
    return lines


def _value_label_svg(entry: kgml.Entry, table: intable.Table, opts: RenderOpts) -> str:
    box = entry.box
    assert box is not None
    lines = _value_lines(entry, table)
    if not lines:
        return ""

    # Stacked under the box: KEGG packs boxes side by side far more often than
    # it stacks them, so below collides least. The white halo is painted first
    # (paint-order) so the digits stay readable over map artwork.
    cx = box.x + box.w / 2
    top = box.y + box.h + opts.label_size
    step = opts.label_size * 1.15
    return "".join(
        f'<text x="{_n(cx)}" y="{_n(top + i * step)}" text-anchor="middle" '
        f'font-family="sans-serif" font-size="{_n(opts.label_size)}" '
        f'fill="#000000" stroke="#ffffff" stroke-width="{_n(opts.label_size / 4)}" '
        f'paint-order="stroke">{escape(line)}</text>'
        for i, line in enumerate(lines)
    )


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

    if opts.mode == "vector":
        # The neutral base rect is skipped under a coloured box, so its outline
        # has to be redrawn here or a matched box would lose the border every
        # unmatched box keeps. Raster mode gets no outline: KEGG's own artwork
        # already draws the borders and must not be overpainted.
        parts.append(_outline(box))

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
            f'stroke="{UNMATCHED_STROKE}" stroke-width="{OUTLINE_WIDTH}"/>'
        )
    return out


def _outline(box: kgml.Box) -> str:
    """The border a base rect would have drawn, without its opaque fill."""
    return (
        f'<rect x="{_n(box.x)}" y="{_n(box.y)}" width="{_n(box.w)}" '
        f'height="{_n(box.h)}" fill="none" fill-opacity="1.00" '
        f'stroke="{UNMATCHED_STROKE}" stroke-width="{OUTLINE_WIDTH}"/>'
    )


def _vector_labels(pathway: kgml.Pathway, table: intable.Table) -> list[str]:
    out = []
    for entry in pathway.entries:
        if entry.box is None or not entry.label:
            continue
        box = entry.box
        fill = _label_fill(entry, table)
        out.append(
            f'<text x="{_n(box.x + box.w / 2)}" y="{_n(box.y + box.h / 2)}" '
            f'text-anchor="middle" dominant-baseline="central" '
            f'font-family="sans-serif" font-size="{LABEL_SIZE}" fill={quoteattr(fill)}>'
            f"{escape(entry.label)}</text>"
        )
    return out


def _label_fill(entry: kgml.Entry, table: intable.Table) -> str:
    """KEGG Mapper's ``bg,fg`` foreground for this box, else black.

    Resolved through the same "first KO the user actually supplied" rule the
    link target uses, so a box carrying several orthologs takes its text colour
    from the same row it links to.
    """
    linked = next((k for k in entry.ko_ids if k in table.rows), None)
    if linked is None:
        return LABEL_FILL
    return table.fg.get(linked, LABEL_FILL)


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
    # A colour-mode table has no numeric scale, so a colourbar would be a lie.
    if not opts.legend or table.mode != "value":
        return ""
    return legend.draw(width, height, opts.cmap, vmin, vmax)


def _n(value: float) -> str:
    return f"{value:.2f}"
