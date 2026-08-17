import pytest

from kegg_map_kit import kgml


def test_parse_reads_pathway_metadata(kgml_text):
    pathway = kgml.parse(kgml_text)
    assert pathway.name == "ko00010"
    assert pathway.title == "Glycolysis / Gluconeogenesis"
    assert len(pathway.entries) == 6


def test_graphics_xy_is_the_box_centre_not_the_corner(kgml_text):
    entry = kgml.entries_by_id(kgml.parse(kgml_text))["1"]
    # KGML says x=737 y=180 width=46 height=17, and those coordinates are the
    # centre of the box. Top-left is therefore (737 - 23, 180 - 8.5).
    assert entry.box == kgml.Box(x=714.0, y=171.5, w=46.0, h=17.0)


def test_single_ko_entry(kgml_text):
    entry = kgml.entries_by_id(kgml.parse(kgml_text))["1"]
    assert entry.ko_ids == ("K00844",)
    assert entry.label == "K00844"
    assert entry.link.endswith("K00844")


def test_multi_ko_entry_keeps_kgml_order(kgml_text):
    entry = kgml.entries_by_id(kgml.parse(kgml_text))["2"]
    assert entry.ko_ids == ("K01810", "K06859", "K13810")


def test_label_takes_first_comma_separated_name(kgml_text):
    assert kgml.entries_by_id(kgml.parse(kgml_text))["2"].label == "K01810"


def test_non_rectangle_entries_have_no_box(kgml_text):
    by_id = kgml.entries_by_id(kgml.parse(kgml_text))
    assert by_id["3"].box is None  # circle
    assert by_id["4"].box is None  # roundrectangle
    assert by_id["6"].box is None  # line, and no x/y at all


def test_entries_without_ko_ids_are_kept_but_empty(kgml_text):
    by_id = kgml.entries_by_id(kgml.parse(kgml_text))
    assert by_id["3"].ko_ids == ()
    assert by_id["4"].ko_ids == ()
    assert by_id["6"].ko_ids == ()


def test_relations_are_entry_id_pairs(kgml_text):
    assert kgml.parse(kgml_text).relations == (("1", "2"), ("2", "5"))


def test_bounds_covers_all_boxes_plus_margin(kgml_text):
    # Rightmost box right edge is 737 + 23 = 760; lowest bottom edge is
    # 300 + 8.5 = 308.5. Only rectangle entries count.
    assert kgml.bounds(kgml.parse(kgml_text), margin=20.0) == (780.0, 328.5)


def test_bounds_of_pathway_with_no_boxes_is_nonzero():
    empty = kgml.parse(
        '<?xml version="1.0"?><pathway name="path:ko99999" title="x"></pathway>'
    )
    width, height = kgml.bounds(empty)
    assert width > 0 and height > 0


def test_malformed_xml_raises_kgml_error():
    with pytest.raises(kgml.KgmlError):
        kgml.parse("<pathway><entry>")


def test_non_pathway_root_raises_kgml_error():
    with pytest.raises(kgml.KgmlError):
        kgml.parse('<?xml version="1.0"?><html><body>404</body></html>')
