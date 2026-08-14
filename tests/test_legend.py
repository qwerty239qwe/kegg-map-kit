import xml.etree.ElementTree as ET

from kegg_svg import colormap, legend

SVG = "{http://www.w3.org/2000/svg}"


def wrap(fragment):
    return ET.fromstring(f'<svg xmlns="http://www.w3.org/2000/svg">{fragment}</svg>')


def test_draw_returns_a_well_formed_fragment():
    root = wrap(legend.draw(1000, 800, "coolwarm", -2.0, 2.0))
    assert root.find(f'.//{SVG}g[@id="kegg-svg-legend"]') is not None


def test_legend_sits_in_the_bottom_right():
    root = wrap(legend.draw(1000, 800, "coolwarm", -2.0, 2.0))
    backing = root.find(f".//{SVG}rect")
    assert float(backing.get("x")) + float(backing.get("width")) <= 1000
    assert float(backing.get("y")) + float(backing.get("height")) <= 800
    assert float(backing.get("x")) > 800
    assert float(backing.get("y")) > 550


def test_bar_is_built_from_lut_samples():
    root = wrap(legend.draw(1000, 800, "viridis", 0.0, 1.0))
    fills = {r.get("fill") for r in root.findall(f".//{SVG}rect")}
    table = colormap.lut("viridis")
    assert table[0] in fills
    assert table[255] in fills


def test_tick_labels_show_min_mid_max():
    root = wrap(legend.draw(1000, 800, "coolwarm", -2.0, 2.0))
    labels = {t.text for t in root.findall(f".//{SVG}text")}
    assert {"-2", "0", "2"} <= labels


def test_colormap_name_is_shown():
    root = wrap(legend.draw(1000, 800, "coolwarm", -2.0, 2.0))
    assert "coolwarm" in {t.text for t in root.findall(f".//{SVG}text")}


def test_bar_colour_matches_position_not_just_presence():
    """vmax must be drawn at the top of the bar and vmin at the bottom.

    Selects bar segments by their y attribute (not by emission order/index), so
    the test stays honest if the emission order ever changes.
    """
    root = wrap(legend.draw(1000, 800, "viridis", 0.0, 1.0))
    table = colormap.lut("viridis")
    # Bar segments are the coloured (non-outline, non-backing) rects: width 20,
    # a real hex fill (the outline rect has fill="none", the backing is 92 wide).
    segments = [
        r
        for r in root.findall(f".//{SVG}rect")
        if r.get("width") == "20.00" and (r.get("fill") or "").startswith("#")
    ]
    assert segments
    top = min(segments, key=lambda r: float(r.get("y")))
    bottom = max(segments, key=lambda r: float(r.get("y")))
    assert top.get("fill") == table[255]
    assert bottom.get("fill") == table[0]


def test_tick_labels_sit_beside_their_end_of_the_bar():
    """vmax's label must be above (smaller y) vmin's label, with the midpoint between."""
    root = wrap(legend.draw(1000, 800, "coolwarm", -2.0, 2.0))
    texts = root.findall(f".//{SVG}text")
    y_by_text = {t.text: float(t.get("y")) for t in texts if t.text in {"-2", "0", "2"}}
    assert y_by_text["2"] < y_by_text["0"] < y_by_text["-2"]


def test_tiny_canvas_gets_no_legend():
    assert legend.draw(50, 40, "coolwarm", -2.0, 2.0) == ""


def test_draw_is_deterministic():
    assert legend.draw(1000, 800, "Reds", 0.0, 5.0) == legend.draw(1000, 800, "Reds", 0.0, 5.0)
