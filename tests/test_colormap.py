import pytest

from kegg_svg import colormap


def test_lut_has_256_entries_of_hex():
    table = colormap.lut("viridis")
    assert len(table) == 256
    assert all(len(c) == 7 and c.startswith("#") for c in table)


def test_lut_endpoints_match_anchor_stops():
    table = colormap.lut("viridis")
    first, last = colormap.CMAPS["viridis"][0], colormap.CMAPS["viridis"][-1]
    assert table[0] == f"#{first[0]:02x}{first[1]:02x}{first[2]:02x}"
    assert table[255] == f"#{last[0]:02x}{last[1]:02x}{last[2]:02x}"


def test_lut_is_cached_and_returns_equal_tables():
    assert colormap.lut("Reds") == colormap.lut("Reds")


def test_unknown_colormap_raises():
    with pytest.raises(colormap.UnknownColormap):
        colormap.lut("nope")


def test_to_hex_maps_bounds_to_lut_ends():
    assert colormap.to_hex(-2.0, "coolwarm", -2.0, 2.0) == colormap.lut("coolwarm")[0]
    assert colormap.to_hex(2.0, "coolwarm", -2.0, 2.0) == colormap.lut("coolwarm")[255]


def test_to_hex_clamps_out_of_range_values():
    table = colormap.lut("coolwarm")
    assert colormap.to_hex(-99.0, "coolwarm", -2.0, 2.0) == table[0]
    assert colormap.to_hex(99.0, "coolwarm", -2.0, 2.0) == table[255]


def test_to_hex_degenerate_range_returns_midpoint():
    table = colormap.lut("coolwarm")
    assert colormap.to_hex(1.0, "coolwarm", 1.0, 1.0) == table[128]


def test_resolve_scale_diverging_is_symmetric():
    assert colormap.resolve_scale([-1.0, 3.0], "coolwarm", None, None) == (-3.0, 3.0)


def test_resolve_scale_sequential_uses_min_max():
    assert colormap.resolve_scale([1.0, 3.0], "viridis", None, None) == (1.0, 3.0)


def test_resolve_scale_respects_explicit_bounds():
    assert colormap.resolve_scale([1.0, 3.0], "viridis", 0.0, None) == (0.0, 3.0)
    assert colormap.resolve_scale([1.0, 3.0], "viridis", None, 9.0) == (1.0, 9.0)
    assert colormap.resolve_scale([1.0, 3.0], "viridis", 0.0, 9.0) == (0.0, 9.0)


def test_resolve_scale_empty_values_falls_back_to_unit_range():
    assert colormap.resolve_scale([], "viridis", None, None) == (0.0, 1.0)


def test_is_diverging():
    assert colormap.is_diverging("coolwarm")
    assert not colormap.is_diverging("viridis")
