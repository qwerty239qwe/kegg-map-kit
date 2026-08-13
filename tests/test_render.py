import xml.etree.ElementTree as ET

import pytest

from kegg_svg import intable, kgml, render

SVG = "{http://www.w3.org/2000/svg}"
XLINK = "{http://www.w3.org/1999/xlink}"


def parse_table(text):
    import io

    return intable.parse(io.StringIO(text))


def rects(svg_text):
    root = ET.fromstring(svg_text)
    return root.findall(f".//{SVG}rect")


def overlay_rects(svg_text):
    """Rects inside the overlay group, i.e. the coloured ones."""
    root = ET.fromstring(svg_text)
    group = root.find(f'.//{SVG}g[@id="kegg-svg-overlay"]')
    return group.findall(f".//{SVG}rect") if group is not None else []


def split_rects(svg_text):
    """Split every rect into (outside the overlay group, inside it)."""
    root = ET.fromstring(svg_text)
    group = root.find(f'.//{SVG}g[@id="kegg-svg-overlay"]')
    inside = group.findall(f".//{SVG}rect") if group is not None else []
    seen = {id(r) for r in inside}
    outside = [r for r in root.findall(f".//{SVG}rect") if id(r) not in seen]
    return outside, inside


@pytest.fixture
def pathway(kgml_text):
    return kgml.parse(kgml_text)


def test_raster_embeds_the_png_as_a_data_uri(pathway, fake_png):
    svg, _ = render.render(
        pathway, parse_table("K00844\tred\n"), render.RenderOpts(mode="raster"), png=fake_png
    )
    image = ET.fromstring(svg).find(f".//{SVG}image")
    assert image is not None
    assert image.get("href", "").startswith("data:image/png;base64,")


def test_raster_canvas_matches_the_png_header(pathway, fake_png):
    svg, _ = render.render(
        pathway, parse_table("K00844\tred\n"), render.RenderOpts(mode="raster"), png=fake_png
    )
    root = ET.fromstring(svg)
    assert root.get("width") == "1000.00"
    assert root.get("height") == "800.00"


def test_raster_without_png_raises(pathway):
    with pytest.raises(render.RenderError):
        render.render(pathway, parse_table("K00844\tred\n"), render.RenderOpts(mode="raster"))


def test_vector_has_no_image_and_uses_bounding_box(pathway):
    svg, _ = render.render(pathway, parse_table("K00844\tred\n"), render.RenderOpts(mode="vector"))
    root = ET.fromstring(svg)
    assert root.find(f".//{SVG}image") is None
    assert root.get("width") == "780.00"
    assert root.get("height") == "328.50"


def test_single_ko_single_column_makes_one_full_width_slice(pathway, fake_png):
    svg, _ = render.render(
        pathway, parse_table("K00844\tred\n"), render.RenderOpts(mode="raster"), png=fake_png
    )
    found = overlay_rects(svg)
    assert len(found) == 1
    assert found[0].get("x") == "714.00"
    assert found[0].get("y") == "171.50"
    assert found[0].get("width") == "46.00"
    assert found[0].get("fill") == "red"


def test_three_columns_make_three_slices_left_to_right(pathway, fake_png):
    svg, _ = render.render(
        pathway,
        parse_table("K00844\t#ff0000\t#00ff00\t#0000ff\n"),
        render.RenderOpts(mode="raster"),
        png=fake_png,
    )
    found = overlay_rects(svg)
    assert [r.get("fill") for r in found] == ["#ff0000", "#00ff00", "#0000ff"]
    assert [r.get("x") for r in found] == ["714.00", "729.33", "744.67"]


def test_slices_tile_the_box_exactly(pathway, fake_png):
    svg, _ = render.render(
        pathway,
        parse_table("K00844\t#ff0000\t#00ff00\t#0000ff\n"),
        render.RenderOpts(mode="raster"),
        png=fake_png,
    )
    found = overlay_rects(svg)
    left = float(found[0].get("x"))
    right = float(found[-1].get("x")) + float(found[-1].get("width"))
    assert left == pytest.approx(714.0)
    assert right == pytest.approx(760.0)


def test_multi_ko_entry_slices_per_matched_ko_in_kgml_order(pathway, fake_png):
    # Entry 2 lists K01810, K06859, K13810. Only two are in the input, so the
    # box gets two slices, ordered as KGML lists them, not as the file does.
    svg, _ = render.render(
        pathway,
        parse_table("K13810\t#0000ff\nK01810\t#ff0000\n"),
        render.RenderOpts(mode="raster"),
        png=fake_png,
    )
    assert [r.get("fill") for r in overlay_rects(svg)] == ["#ff0000", "#0000ff"]


def test_matched_kos_times_columns_gives_the_slice_count(pathway, fake_png):
    svg, _ = render.render(
        pathway,
        parse_table("K01810\t#111111\t#222222\nK13810\t#333333\t#444444\n"),
        render.RenderOpts(mode="raster"),
        png=fake_png,
    )
    assert [r.get("fill") for r in overlay_rects(svg)] == [
        "#111111",
        "#222222",
        "#333333",
        "#444444",
    ]


def test_slice_count_is_capped(pathway, fake_png):
    columns = "\t".join(["#ff0000"] * 20)
    svg, stats = render.render(
        pathway,
        parse_table(f"K00844\t{columns}\n"),
        render.RenderOpts(mode="raster"),
        png=fake_png,
    )
    assert len(overlay_rects(svg)) == render.MAX_SLICES
    assert stats.capped_entries == 1


def test_unmatched_entries_are_not_drawn_in_raster(pathway, fake_png):
    svg, _ = render.render(
        pathway, parse_table("K00844\tred\n"), render.RenderOpts(mode="raster"), png=fake_png
    )
    assert len(overlay_rects(svg)) == 1


def test_vector_draws_every_box_including_unmatched(pathway):
    svg, _ = render.render(pathway, parse_table("K00844\tred\n"), render.RenderOpts(mode="vector"))
    outside, inside = split_rects(svg)
    # Entries 2 (x=528) and 5 (x=177) are unmatched and get a neutral base each.
    assert [r.get("x") for r in outside] == ["528.00", "177.00"]
    # Entry 1 (x=714) is matched, so it is drawn by the overlay instead, once.
    slices = [r for r in inside if r.get("fill") != "none"]
    assert [r.get("x") for r in slices] == ["714.00"]
    assert [r.get("fill") for r in slices] == ["red"]
    # Every rectangle entry is drawn exactly once, as a base or as a slice.
    assert sorted(r.get("x") for r in outside + slices) == ["177.00", "528.00", "714.00"]


def test_vector_outlines_matched_boxes_like_unmatched_ones(pathway, fake_png):
    svg, _ = render.render(pathway, parse_table("K00844\tred\n"), render.RenderOpts(mode="vector"))
    outside, inside = split_rects(svg)
    outlines = [r for r in inside if r.get("fill") == "none"]
    assert [r.get("x") for r in outlines] == ["714.00"]
    unmatched = outside[0]
    for outline in outlines:
        assert outline.get("stroke") == unmatched.get("stroke") == "#999999"
        assert outline.get("stroke-width") == unmatched.get("stroke-width") == "0.5"
        assert outline.get("width") == unmatched.get("width")
        assert outline.get("height") == unmatched.get("height")
    # Raster mode must not outline anything: KEGG's own artwork draws the borders.
    raster, _ = render.render(
        pathway, parse_table("K00844\tred\n"), render.RenderOpts(mode="raster"), png=fake_png
    )
    assert [r.get("stroke") for r in overlay_rects(raster)] == [None]


def test_vector_labels_every_box(pathway):
    svg, _ = render.render(pathway, parse_table("K00844\tred\n"), render.RenderOpts(mode="vector"))
    labels = {t.text for t in ET.fromstring(svg).findall(f".//{SVG}text")}
    assert {"K00844", "K01810", "K00845"} <= labels


def test_vector_draws_relation_lines(pathway):
    svg, _ = render.render(pathway, parse_table("K00844\tred\n"), render.RenderOpts(mode="vector"))
    assert len(ET.fromstring(svg).findall(f".//{SVG}line")) == 2


def test_value_mode_colours_through_the_colormap(pathway, fake_png):
    from kegg_svg import colormap

    svg, _ = render.render(
        pathway,
        parse_table("K00844\t2.0\nK00845\t-2.0\n"),
        render.RenderOpts(mode="raster", cmap="coolwarm"),
        png=fake_png,
    )
    fills = [r.get("fill") for r in overlay_rects(svg)]
    assert colormap.lut("coolwarm")[255] in fills
    assert colormap.lut("coolwarm")[0] in fills


def test_explicit_vmin_vmax_are_used(pathway, fake_png):
    from kegg_svg import colormap

    svg, _ = render.render(
        pathway,
        parse_table("K00844\t1.0\n"),
        render.RenderOpts(mode="raster", cmap="viridis", vmin=0.0, vmax=1.0),
        png=fake_png,
    )
    assert overlay_rects(svg)[0].get("fill") == colormap.lut("viridis")[255]


def test_na_cells_use_na_colour_when_given(pathway, fake_png):
    svg, _ = render.render(
        pathway,
        parse_table("K00844\t1.0\t\n"),
        render.RenderOpts(mode="raster", na_color="#cccccc"),
        png=fake_png,
    )
    assert [r.get("fill") for r in overlay_rects(svg)][1] == "#cccccc"


def test_na_cells_are_skipped_without_na_colour(pathway, fake_png):
    svg, _ = render.render(
        pathway, parse_table("K00844\t1.0\t\n"), render.RenderOpts(mode="raster"), png=fake_png
    )
    assert len(overlay_rects(svg)) == 1


def test_links_wrap_coloured_boxes(pathway, fake_png):
    svg, _ = render.render(
        pathway, parse_table("K00844\tred\n"), render.RenderOpts(mode="raster"), png=fake_png
    )
    anchors = ET.fromstring(svg).findall(f".//{SVG}a")
    assert len(anchors) == 1
    assert anchors[0].get("href") == "https://www.kegg.jp/entry/K00844"


def test_link_targets_the_first_matched_ko_not_the_first_listed(pathway, fake_png):
    # Entry 2 lists K01810, K06859, K13810; only K13810 is in the input, so the
    # link must point at the KO the user actually supplied.
    svg, _ = render.render(
        pathway, parse_table("K13810\tred\n"), render.RenderOpts(mode="raster"), png=fake_png
    )
    anchors = ET.fromstring(svg).findall(f".//{SVG}a")
    assert len(anchors) == 1
    assert anchors[0].get("href") == "https://www.kegg.jp/entry/K13810"


def test_no_links_option_suppresses_anchors(pathway, fake_png):
    svg, _ = render.render(
        pathway,
        parse_table("K00844\tred\n"),
        render.RenderOpts(mode="raster", links=False),
        png=fake_png,
    )
    assert ET.fromstring(svg).findall(f".//{SVG}a") == []


def test_every_coloured_box_has_a_title(pathway, fake_png):
    svg, _ = render.render(
        pathway, parse_table("K00844\t1.5\n"), render.RenderOpts(mode="raster"), png=fake_png
    )
    titles = [t.text for t in ET.fromstring(svg).findall(f".//{SVG}title")]
    assert any("K00844" in (t or "") and "1.5" in (t or "") for t in titles)


def test_opacity_is_applied_in_raster_and_not_in_vector(pathway, fake_png):
    raster, _ = render.render(
        pathway,
        parse_table("K00844\tred\n"),
        render.RenderOpts(mode="raster", opacity=0.5),
        png=fake_png,
    )
    assert overlay_rects(raster)[0].get("fill-opacity") == "0.50"
    vector, _ = render.render(
        pathway,
        parse_table("K00844\tred\n"),
        render.RenderOpts(mode="vector", opacity=0.5),
        png=fake_png,
    )
    fills = [r.get("fill-opacity") for r in rects(vector)]
    assert all(f == "1.00" for f in fills)


def test_labels_and_ampersands_are_escaped(fake_png):
    text = (
        '<?xml version="1.0"?><pathway name="path:ko1" title="A &amp; B">'
        '<entry id="1" name="ko:K00001" type="ortholog" link="x">'
        '<graphics name="a &amp; b" type="rectangle" x="50" y="50" '
        'width="40" height="20"/></entry></pathway>'
    )
    svg, _ = render.render(
        kgml.parse(text), parse_table("K00001\tred\n"), render.RenderOpts(mode="vector")
    )
    ET.fromstring(svg)  # must still be well-formed XML
    assert "&amp;" in svg


def test_stats_are_reported(pathway, fake_png):
    _, stats = render.render(
        pathway,
        parse_table("K00844\tred\nK01810\tblue\nK99999\tgreen\n"),
        render.RenderOpts(mode="raster"),
        png=fake_png,
    )
    assert stats.input_kos == 3
    assert stats.matched_kos == 2
    assert stats.matched_boxes == 2
    assert stats.capped_entries == 0


def test_no_matches_still_renders(pathway, fake_png):
    svg, stats = render.render(
        pathway, parse_table("K99999\tred\n"), render.RenderOpts(mode="raster"), png=fake_png
    )
    assert stats.matched_kos == 0
    assert overlay_rects(svg) == []
    ET.fromstring(svg)


def test_output_is_deterministic(pathway, fake_png):
    args = (pathway, parse_table("K00844\t1.0\t2.0\n"), render.RenderOpts(mode="raster"))
    first, _ = render.render(*args, png=fake_png)
    second, _ = render.render(*args, png=fake_png)
    assert first == second


def test_value_mode_renders_a_legend(pathway, fake_png):
    svg, _ = render.render(
        pathway,
        parse_table("K00844\t1.0\n"),
        render.RenderOpts(mode="raster", legend=True),
        png=fake_png,
    )
    assert ET.fromstring(svg).find(f'.//{SVG}g[@id="kegg-svg-legend"]') is not None


def test_colour_mode_never_renders_a_legend(pathway, fake_png):
    svg, _ = render.render(
        pathway,
        parse_table("K00844\tred\n"),
        render.RenderOpts(mode="raster", legend=True),
        png=fake_png,
    )
    assert ET.fromstring(svg).find(f'.//{SVG}g[@id="kegg-svg-legend"]') is None


def test_no_legend_option_suppresses_it(pathway, fake_png):
    svg, _ = render.render(
        pathway,
        parse_table("K00844\t1.0\n"),
        render.RenderOpts(mode="raster", legend=False),
        png=fake_png,
    )
    assert ET.fromstring(svg).find(f'.//{SVG}g[@id="kegg-svg-legend"]') is None
