"""KO identifier metadata, parsed from KEGG's `list/ko` endpoint.

Each line looks like::

    K00226\tpyrD; dihydroorotate dehydrogenase (fumarate) [EC:1.3.98.1]

The EC number matters more than it looks: it is the string KEGG prints inside
the box on a rendered pathway map, so relabelling a box with its EC number
reproduces the map's own typography instead of looking pasted on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

EC_RE = re.compile(r"\[EC:([^\]]+)\]")
STYLES = ("ko", "symbol", "ec")


@dataclass(frozen=True)
class KoName:
    symbol: str | None
    name: str
    ec: str | None


def parse(text: str) -> dict[str, KoName]:
    out: dict[str, KoName] = {}
    for line in text.splitlines():
        ko, sep, rest = line.partition("\t")
        if not sep or not ko:
            continue
        out[ko.removeprefix("ko:").strip()] = _parse_definition(rest.strip())
    return out


def _parse_definition(definition: str) -> KoName:
    ec_match = EC_RE.search(definition)
    ec = ec_match.group(1).split()[0] if ec_match else None
    body = EC_RE.sub("", definition).strip()

    symbol, sep, remainder = body.partition(";")
    if sep:
        # "AKR1A1, adh" — several aliases, the first is the one KEGG leads with.
        symbol = symbol.split(",")[0].strip()
        name = remainder.strip()
    else:
        symbol, name = None, body
    return KoName(symbol=symbol or None, name=name, ec=ec)


def label_for(ko: str, names: dict[str, KoName], style: str) -> str:
    """Text to draw inside a box, falling back to the KO id when unavailable."""
    if style not in STYLES:
        raise ValueError(f"unknown label style {style!r}; choose from {', '.join(STYLES)}")
    if style == "ko":
        return ko
    entry = names.get(ko)
    if entry is None:
        return ko
    return (entry.symbol if style == "symbol" else entry.ec) or ko
