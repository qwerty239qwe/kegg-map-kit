"""KEGG REST access with a cache-first disk cache.

Cached files never expire: KEGG maps change on the order of months, and a
reproducible figure is worth more than a fresh one. Delete the cache directory
to force a refresh.
"""

from __future__ import annotations

import os
import re
import struct
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__

KGML_URL = "https://rest.kegg.jp/get/{pathway}/kgml"
PNG_URL = "https://www.kegg.jp/kegg/pathway/ko/{pathway}.png"
USER_AGENT = f"kegg-svg/{__version__} (+https://pypi.org/project/kegg-svg/)"
TIMEOUT = 30
PATHWAY_RE = re.compile(r"^(?:path:)?(?:ko|map)?(\d{5})$", re.IGNORECASE)
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Single network seam. Tests monkeypatch this attribute; nothing else in the
# package calls urllib directly.
_urlopen = urllib.request.urlopen


class FetchError(Exception):
    """Any failure to obtain KEGG data.

    Raised bare only for transport failure. Every failure the user can act on
    is one of the subclasses below, so callers can map exit codes by type.
    """


class OfflineError(FetchError):
    """Offline mode was requested and the cache did not have the file."""


class NotFoundError(FetchError):
    """KEGG returned 404 for the requested pathway."""


class PathwayIdError(FetchError):
    """The pathway id given is not a well-formed KEGG pathway id."""


class BadImageError(FetchError):
    """The bytes we hold for a map image are not a usable PNG."""


def normalize_pathway(raw: str) -> str:
    match = PATHWAY_RE.match(raw.strip())
    if not match:
        raise PathwayIdError(
            f"{raw!r} is not a KEGG pathway id; expected something like ko00010, "
            "map00010 or 00010"
        )
    return f"ko{match.group(1)}"


def cache_dir(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".cache"
    return root / "kegg-svg"


def get_kgml(pathway: str, cache: Path, offline: bool = False) -> str:
    data = _get(KGML_URL.format(pathway=pathway), cache / f"{pathway}.kgml", offline)
    return data.decode("utf-8", errors="replace")


def get_map_png(pathway: str, cache: Path, offline: bool = False) -> bytes:
    return _get(PNG_URL.format(pathway=pathway), cache / f"{pathway}.png", offline)


def _get(url: str, path: Path, offline: bool) -> bytes:
    if path.exists():
        return path.read_bytes()
    if offline:
        raise OfflineError(f"--offline was given but {path} is not cached (would fetch {url})")
    try:
        data = _download(url)
    except NotFoundError:
        raise
    except FetchError:
        if path.exists():
            return path.read_bytes()
        raise
    _write_atomic(path, data)
    return data


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last: Exception | None = None
    for _ in range(2):  # one retry; KEGG rate-limits rather than failing hard
        try:
            with _urlopen(request, timeout=TIMEOUT) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise NotFoundError(f"KEGG returned 404 for {url}") from exc
            last = exc
        except urllib.error.URLError as exc:
            last = exc
    raise FetchError(f"could not fetch {url}: {last}")


def _write_atomic(path: Path, data: bytes) -> None:
    """Write via a temp file so an interrupted run cannot leave a truncated cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


def png_size(data: bytes) -> tuple[int, int]:
    """Read width and height out of the PNG IHDR chunk."""
    if len(data) < 24 or not data.startswith(PNG_MAGIC):
        raise BadImageError("map image is not a PNG")
    width, height = struct.unpack(">II", data[16:24])
    return (width, height)
