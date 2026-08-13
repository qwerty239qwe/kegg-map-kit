# kegg-svg

Colour KEGG pathway maps from a table of KEGG Ontology (KO) identifiers and
render the result as SVG. A scriptable, SVG-producing counterpart to the
[KEGG Mapper](https://www.genome.jp/kegg/mapper/) Color tool.

Zero runtime dependencies — Python 3.10+ and the standard library.

## Install

    uv tool install kegg-svg
    # or
    pip install kegg-svg

## Use

    kegg-svg ko00010 -i data.tsv -o map.svg

`data.tsv` holds a KO identifier per line, followed by either colours or numbers:

    K00844	#ff0000
    K01810	blue
    K00845	#00ff00,#000000    # KEGG Mapper bg,fg syntax

or values, which are mapped through a colormap and get a legend:

    K00844	2.0	1.4
    K01810	-1.5	-0.2

Several columns, or several KOs sharing one box, split that box into vertical
slices (up to 12).

## Options

| Flag | Default | Meaning |
| --- | --- | --- |
| `--mode raster\|vector` | `raster` | `raster` embeds KEGG's map PNG and paints on top; `vector` redraws boxes from KGML alone |
| `--cmap NAME` | `coolwarm` | `coolwarm`, `RdBu`, `viridis`, `Reds`, `Blues` |
| `--vmin` / `--vmax` | auto | Colour scale bounds. Diverging maps auto-scale symmetrically |
| `--opacity` | `0.75` | Overlay opacity in raster mode |
| `--offline` | off | Use the cache only, never the network |
| `--cache DIR` | `~/.cache/kegg-svg` | Cache location |
| `--kgml` / `--png` | — | Use local files instead of fetching |
| `--na-color HEX` | — | Fill for blank cells; blank cells are skipped by default |
| `--no-legend`, `--no-links` | — | Suppress the colorbar / the links to KEGG |
| `-q` | off | Suppress the summary line |

Coloured boxes carry hover text and link to their KEGG entry page.

KEGG data is cached indefinitely under `--cache`; delete that directory to
refresh.

## Scope

v0.1.0 handles KO-level maps (`ko#####`) and colours `rectangle` entries only.
Compounds, organism-specific gene IDs, and the line-based global maps such as
`ko01100` are not coloured.

## Licence

MIT. KEGG data is © Kanehisa Laboratories and is subject to the
[KEGG terms of use](https://www.kegg.jp/kegg/legal.html); this tool only
retrieves and renders it.
