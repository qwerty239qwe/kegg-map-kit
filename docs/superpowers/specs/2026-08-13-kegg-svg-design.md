# kegg-svg — Design

**Date:** 2026-08-13
**Status:** Approved

## Purpose

A command-line tool that takes a KEGG pathway ID and a table of KEGG Ontology (KO)
identifiers with associated colors or numeric values, and produces an SVG of the
pathway map with the matching boxes colored.

It is the SVG-producing, scriptable counterpart to the KEGG Mapper "Color" web tool
(https://www.genome.jp/kegg/mapper/), and accepts the same input syntax so existing
KEGG Mapper input files work unchanged.

## Scope

**In scope (v1):**

- KO-level maps only (`ko#####` pathway IDs, `K#####` entries).
- Two render modes: raster-backed and pure vector.
- Color input (explicit colors) and value input (numeric, mapped through a colormap).
- Multiple colors per box, rendered as vertical slices.
- Clickable links to KEGG entry pages.
- Color legend for value mode.

**Out of scope (v1):**

- Compound (`C#####`) coloring.
- Organism-specific gene IDs (`hsa:`, `eco:`, …) and organism maps.
- Global/overview maps (`ko01100` and friends), which use line-based graphics rather
  than boxes. These will render, but only entries with `graphics type="rectangle"`
  are colored; anything else is left untouched.
- Any output format other than SVG.

## Distribution

- Python package named `kegg-svg`, installable with `pip install kegg-svg` or
  `uv tool install kegg-svg`.
- Console script entry point: `kegg-svg`.
- Requires Python 3.10+.
- **Zero runtime dependencies.** Everything comes from the standard library:
  `urllib.request` (HTTP), `xml.etree.ElementTree` (KGML), `base64` (PNG embedding),
  `csv`, `argparse`. Colormaps ship as bundled lookup tables rather than pulling in
  matplotlib.
- Dev dependencies: `pytest`, `ruff`.

## CLI

```
kegg-svg PATHWAY -i INPUT -o OUTPUT [options]
```

**Positional**

- `PATHWAY` — KEGG pathway ID, e.g. `ko00010`. A bare number (`00010`) or a `map`
  prefix (`map00010`) is normalized to the `ko` prefix.

**Required**

- `-i, --input PATH` — input table. `-` reads stdin.
- `-o, --output PATH` — output SVG. `-` writes stdout.

**Options**

| Flag | Default | Meaning |
| --- | --- | --- |
| `--mode {raster,vector}` | `raster` | Render backend. |
| `--cmap NAME` | `coolwarm` | Colormap for value mode. One of `coolwarm`, `RdBu`, `viridis`, `Reds`, `Blues`. |
| `--vmin FLOAT` | auto | Lower bound of the color scale. |
| `--vmax FLOAT` | auto | Upper bound of the color scale. |
| `--opacity FLOAT` | `0.75` | Fill opacity of overlay rectangles (raster mode). Vector mode uses `1.0` regardless. |
| `--offline` | off | Never touch the network; use cache and local files only. |
| `--cache DIR` | `$XDG_CACHE_HOME/kegg-svg` or `~/.cache/kegg-svg` | Cache location. |
| `--kgml PATH` | — | Use this KGML file instead of fetching. |
| `--png PATH` | — | Use this map PNG instead of fetching (raster mode only). |
| `--no-legend` | off | Suppress the legend. |
| `--no-links` | off | Suppress `<a>` wrappers. |
| `--na-color HEX` | none | Fill for KOs present in the input but with a missing/blank value. Default: leave the box untouched. |
| `-q, --quiet` | off | Suppress the match-summary line on stderr. |

Exit codes: `0` success, `1` user error (bad input, unknown pathway, offline cache
miss), `2` network failure with no usable cache.

## Input format

One record per line. Fields separated by tab or comma (sniffed; tab wins on ties).
Blank lines and lines starting with `#` are skipped. A header line is detected and
skipped if the first field is not a valid KO ID.

**Field 1** is always a KO ID matching `^K\d{5}$` (case-insensitive, normalized to
uppercase).

**Remaining fields** are all colors or all values — the file is classified once, by
majority of parseable non-blank cells in the remaining columns:

- *Color mode* — cells are `#rgb`, `#rrggbb`, or an SVG/CSS named color. KEGG
  Mapper's `bg,fg` pair syntax (`K00844 #ff0000,#000000`) is accepted; the
  foreground half sets the box's text color in vector mode and is ignored in raster
  mode.
- *Value mode* — cells parse as floats. Each column becomes one slice, colored
  through `--cmap` with the shared `--vmin`/`--vmax` scale.

If a file mixes both, color cells win: any row with a parseable color uses it, and
value cells in that same row are an error. Mixed *columns* (some rows color, some
numeric, in the same column) are an error naming the first offending line.

Auto-scaling when `--vmin`/`--vmax` are not given: diverging colormaps (`coolwarm`,
`RdBu`) use a symmetric range `[-m, +m]` where `m = max(|values|)`; sequential
colormaps use `[min, max]`. Specifying only one bound leaves the other auto.

A KO appearing on more than one line is an error (first duplicate reported), rather
than a silent last-wins.

## Architecture

Data flow:

```
PATHWAY + INPUT
   |
   +--> fetch.py   -> KGML text, map PNG bytes   (cache-first)
   +--> intable.py -> {KO: [cell, ...]}, mode
             |
   kgml.py --+--> [Entry(id, ko_ids, box)]
             |
   colormap.py ---> {KO: [hex, ...]}
             |
   render.py -----> SVG string  (+ legend.py)
             |
           OUTPUT
```

### Modules

Each module is independently testable and has no knowledge of the CLI.

**`fetch.py`** — KEGG REST access with an on-disk cache.

- `get_kgml(pathway, cache, offline) -> str`, from `https://rest.kegg.jp/get/{pathway}/kgml`.
- `get_map_png(pathway, cache, offline) -> bytes`, from `https://www.kegg.jp/kegg/pathway/ko/{pathway}.png`.
- Cache files are `{cache}/{pathway}.kgml` and `{cache}/{pathway}.png`. Presence is
  the only validity check; there is no TTL. Downloads are written to a temp file and
  renamed, so an interrupted run cannot leave a truncated cache entry.
- With `--offline`, a cache miss raises rather than fetching.
- A network failure with a warm cache logs a warning and uses the cache.
- Sends a descriptive `User-Agent`. Single retry on transient failure.

**`kgml.py`** — KGML parsing. No network, no color logic.

- `parse(kgml_text) -> Pathway`, holding `title`, `image_width`, `image_height`,
  and `entries`.
- `Entry(id, ko_ids: list[str], label: str, box: Box | None, link: str)`.
  `ko_ids` comes from splitting the `name` attribute on whitespace and keeping
  `ko:K#####` tokens, stripped to `K#####`.
- `Box(x, y, w, h)` in SVG top-left coordinates. **KGML `graphics/@x,@y` is the box
  center**, so `x_left = x - w/2`, `y_top = y - h/2`. Getting this wrong shifts every
  box; it is covered by a dedicated test.
- Entries whose `graphics/@type` is not `rectangle` get `box = None` and are never
  colored.
- Canvas size comes from the `<pathway>` element's `image` dimensions when present;
  otherwise it is computed from the bounding box of all entries plus a margin.

**`intable.py`** — input parsing. No I/O beyond a passed-in file object.

- `parse(fileobj) -> Table(mode: "color" | "value", rows: dict[str, list[Cell]], n_cols: int)`.
- Rows shorter than `n_cols` are padded with blanks; blank cells are "no data" and
  take `--na-color`.
- Errors carry the 1-based line number and the offending text.

**`colormap.py`** — value → color.

- Bundled colormaps as 256-entry RGB lookup tables generated once and checked in as
  a Python literal, so there is no generation step at runtime.
- `scale(values, cmap, vmin, vmax) -> (vmin, vmax)` resolves auto bounds.
- `to_hex(value, cmap, vmin, vmax) -> str`, clamping out-of-range values to the end
  colors.
- `is_diverging(cmap) -> bool` drives symmetric auto-scaling.

**`render.py`** — SVG construction. Pure function of parsed inputs.

- `render(pathway, colors, opts) -> str`.
- Shared logic: for each entry with a box and ≥1 matched KO, split the box into `n`
  equal-width vertical slices, where `n` is the number of slices contributed by that
  entry, and emit one `<rect>` per slice.
- **Slice ordering.** An entry can contribute slices two ways, and they compose: for
  each of the entry's KO IDs that appear in the input (in KGML order), for each input
  column (left to right), one slice. So an entry matching 2 KOs with a 3-column input
  gets 6 slices. Slice width is `w / n`, with the last slice absorbing rounding
  remainder so the slices exactly tile the box.
- To keep boxes readable, `n` is capped at 12; entries exceeding the cap render the
  first 12 slices and are counted in a stderr warning.
- Each colored box is wrapped in
  `<a href="https://www.kegg.jp/entry/{first_ko}" target="_blank" rel="noopener">`
  unless `--no-links`. Multi-KO entries link to the first matched KO.
- Every colored box carries a `<title>` child for hover text: the entry label, its
  matched KO IDs, and the values or colors applied.
- *raster*: emits `<image>` with the PNG base64-embedded as a `data:` URI at native
  size, then the overlay group at `--opacity`. Unmatched entries are untouched, so
  the original KEGG artwork shows through.
- *vector*: no image. Emits, in order, relation/reaction lines from KGML, then a
  `<rect>` per entry (matched entries filled with their slice colors, unmatched with
  `#ffffff` and a `#999999` stroke), then the entry label as centered `<text>` using
  the first `,`-separated name from `graphics/@name`. Fill opacity is 1.0.
- Output is deterministic: attribute order is fixed and floats are formatted to 2
  decimal places, so identical inputs yield byte-identical SVGs.

**`legend.py`** — colorbar.

- Only drawn in value mode; color mode has no meaningful scale. `--no-legend` and
  color mode both suppress it.
- Drawn as an overlay in the bottom-right of the existing canvas, over the map image
  in raster mode. The canvas is not padded. A semi-opaque white backing rectangle
  keeps it legible against underlying artwork.
- Contents: a 20 × 160 px gradient bar sampled from the colormap LUT, tick labels at
  vmin / midpoint / vmax, and the colormap name.
- If the canvas is smaller than the legend plus margins, the legend is skipped and a
  warning is logged.

**`cli.py`** — argument parsing, orchestration, error presentation. Contains no
rendering or parsing logic; it wires the modules together and converts exceptions
into exit codes and messages.

## Error handling

| Situation | Behavior |
| --- | --- |
| Unknown/invalid pathway ID | Exit 1, message naming the REST URL tried. |
| Network failure, cache warm | Warn on stderr, proceed from cache. |
| Network failure, cache cold | Exit 2, suggest `--kgml`/`--png`. |
| `--offline` and cache miss | Exit 1, print the expected cache paths. |
| Malformed input row | Exit 1, report 1-based line number and the offending text. |
| Duplicate KO in input | Exit 1, name the KO and both line numbers. |
| Mixed color/value column | Exit 1, name the first offending line. |
| KO in input, absent from map | Not an error. Counted for the summary. |
| No KO matched at all | Exit 0, write the uncolored SVG, warn loudly on stderr. |
| Entry exceeds 12-slice cap | Warn once on stderr with the count of affected entries. |
| `--png` given with `--mode vector` | Exit 1; the flag has no meaning there. |

Unless `-q`, every run prints one summary line to stderr:
`kegg-svg: 142/2001 input KOs matched 96 boxes on ko00010`.

## Testing

`pytest`, run offline. No test touches the network.

Fixtures checked into `tests/fixtures/`: a hand-trimmed KGML with ~6 entries covering
single-KO, multi-KO, non-rectangle, and no-KO cases, plus a small PNG.

- `fetch.py`: cache hit/miss, offline behavior, warm-cache fallback on network error,
  temp-file-then-rename atomicity. `urllib` is monkeypatched; the network layer is
  never exercised for real.
- `kgml.py`: center-to-top-left conversion against known coordinates; multi-KO name
  splitting; non-rectangle entries yield `box = None`.
- `intable.py`: color vs value classification, KEGG Mapper `bg,fg` syntax, header
  detection, blank cells, and each error case.
- `colormap.py`: LUT endpoints, clamping, symmetric auto-scale for diverging
  colormaps, min/max for sequential ones.
- `render.py`: assertions on parsed SVG structure — rect count, positions, fills,
  slice tiling exactly covering the box, `<a>` present/absent, `<title>` contents —
  not byte-for-byte golden files. One determinism test renders twice and compares
  bytes.
- `cli.py`: end-to-end runs against fixtures with `--offline`, asserting exit codes
  and stderr summaries.

## Future work

Deliberately deferred, listed so the v1 interfaces do not foreclose them: compound
coloring, organism-specific gene IDs, a `--legend-position` flag, and PDF/PNG output
by way of an external converter.
