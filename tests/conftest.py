import struct
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def kgml_text() -> str:
    return (FIXTURES / "ko00010_mini.kgml").read_text()


@pytest.fixture
def fake_png() -> bytes:
    """A PNG with a valid 24-byte header and junk payload.

    Nothing under test decodes pixels: fetch.png_size reads the IHDR width and
    height, and render base64-embeds the bytes verbatim. A real image would only
    make the fixture bigger.
    """
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", 1000, 800)
        + b"\x08\x06\x00\x00\x00"
        + b"\x00" * 16
    )
