"""Command-line entry point.

This is the only module that touches argv, stdout, stderr, exit codes, or the
filesystem by path. Everything below it raises exceptions and returns values.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NoReturn

from . import __version__, colormap, fetch, intable, kgml, render

EXIT_OK = 0
EXIT_USER = 1
EXIT_NETWORK = 2


class _Parser(argparse.ArgumentParser):
    """An ArgumentParser whose usage errors exit 1, not argparse's default 2.

    Exit 2 is reserved for network failure, so a mistyped flag must not claim
    it. `--version` and `--help` are separate actions and still exit 0.
    """

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(EXIT_USER)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="kegg-svg",
        description="Colour a KEGG pathway map from a table of KO identifiers, as SVG.",
    )
    parser.add_argument("pathway", help="KEGG pathway id, e.g. ko00010, map00010 or 00010")
    parser.add_argument("-i", "--input", required=True, help="input table, or - for stdin")
    parser.add_argument("-o", "--output", required=True, help="output SVG, or - for stdout")
    parser.add_argument("--mode", choices=("raster", "vector"), default="raster")
    # Deliberately not argparse `choices`: an unknown name should exit 1 like
    # every other user error, not argparse's own 2, which means network failure
    # here. Validated in _build instead.
    parser.add_argument(
        "--cmap",
        default="coolwarm",
        help=f"colormap, one of: {', '.join(colormap.names())} (default: coolwarm)",
    )
    parser.add_argument("--vmin", type=float, default=None)
    parser.add_argument("--vmax", type=float, default=None)
    parser.add_argument("--opacity", type=float, default=0.75)
    parser.add_argument("--offline", action="store_true", help="never use the network")
    parser.add_argument("--cache", default=None, help="cache directory")
    parser.add_argument("--kgml", default=None, help="use this KGML file instead of fetching")
    parser.add_argument("--png", default=None, help="use this map PNG instead of fetching")
    parser.add_argument("--no-legend", dest="legend", action="store_false")
    parser.add_argument("--no-links", dest="links", action="store_false")
    parser.add_argument("--na-color", default=None, help="fill for cells with no value")
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("--version", action="version", version=f"kegg-svg {__version__}")
    return parser


def main(argv: list[str] | None = None, stdout=None, stderr=None) -> int:
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    args = build_parser().parse_args(argv)

    try:
        svg, stats, pathway_id = _build(args)
        # The write lives inside the try so an unwritable --output path is a
        # clean exit 1, not a traceback.
        if args.output == "-":
            out.write(svg)
        else:
            Path(args.output).write_text(svg, encoding="utf-8")
    except (
        fetch.OfflineError,
        fetch.NotFoundError,
        fetch.PathwayIdError,
        fetch.BadImageError,
    ) as exc:
        # Must precede the bare FetchError clause: all four are subclasses.
        print(f"kegg-svg: {exc}", file=err)
        return EXIT_USER
    except fetch.FetchError as exc:
        # What is left is transport failure with no usable cache.
        print(f"kegg-svg: {exc}", file=err)
        return EXIT_NETWORK
    except (
        intable.InputError,
        kgml.KgmlError,
        render.RenderError,
        colormap.UnknownColormap,
    ) as exc:
        print(f"kegg-svg: {exc}", file=err)
        return EXIT_USER
    except OSError as exc:
        print(f"kegg-svg: {exc}", file=err)
        return EXIT_USER

    if not args.quiet:
        print(
            f"kegg-svg: {stats.matched_kos}/{stats.input_kos} input KOs matched "
            f"{stats.matched_boxes} boxes on {pathway_id}",
            file=err,
        )
        if stats.matched_kos == 0:
            print("kegg-svg: warning: no KO matched this map; the SVG is uncoloured", file=err)
        if stats.capped_entries:
            print(
                f"kegg-svg: warning: {stats.capped_entries} boxes needed more than "
                f"{render.MAX_SLICES} slices and were truncated",
                file=err,
            )
    return EXIT_OK


def _build(args) -> tuple[str, render.Stats, str]:
    colormap.lut(args.cmap)  # raises UnknownColormap before any work is done
    if args.png and args.mode == "vector":
        raise render.RenderError("--png has no meaning in vector mode")

    if args.na_color is not None and not intable.is_color(args.na_color):
        raise intable.InputError(f"--na-color {args.na_color!r} is not a colour")

    pathway_id = fetch.normalize_pathway(args.pathway)
    cache = fetch.cache_dir(args.cache)

    # The input table is parsed before anything is fetched: on a cold cache a
    # malformed table should fail instantly and accurately, not after a slow
    # network round trip that reports the wrong problem.
    if args.input == "-":
        table = intable.parse(sys.stdin)
    else:
        with open(args.input, encoding="utf-8") as handle:
            table = intable.parse(handle)

    if args.kgml:
        kgml_text = Path(args.kgml).read_text(encoding="utf-8")
    else:
        kgml_text = fetch.get_kgml(pathway_id, cache, args.offline)
    pathway = kgml.parse(kgml_text)

    png = None
    if args.mode == "raster":
        if args.png:
            png = Path(args.png).read_bytes()
        else:
            png = fetch.get_map_png(pathway_id, cache, args.offline)

    opts = render.RenderOpts(
        mode=args.mode,
        opacity=args.opacity,
        links=args.links,
        legend=args.legend,
        na_color=args.na_color,
        cmap=args.cmap,
        vmin=args.vmin,
        vmax=args.vmax,
    )
    svg, stats = render.render(pathway, table, opts, png=png)
    return svg, stats, pathway_id


def run() -> None:
    sys.exit(main())
