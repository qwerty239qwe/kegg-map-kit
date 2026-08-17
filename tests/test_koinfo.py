import pytest

from kegg_svg import koinfo

SAMPLE = (
    "K00001\tADH; alcohol dehydrogenase [EC:1.1.1.1]\n"
    "K00226\tpyrD; dihydroorotate dehydrogenase (fumarate) [EC:1.3.98.1]\n"
    "K06016\tpydC; beta-ureidopropionase / N-carbamoyl-L-amino-acid hydrolase "
    "[EC:3.5.1.6 3.5.1.87]\n"
    "K00002\tAKR1A1, adh; alcohol dehydrogenase (NADP+) [EC:1.1.1.2]\n"
    "K99999\tsome protein with no symbol and no ec\n"
)


def test_parse_returns_one_entry_per_line():
    assert set(koinfo.parse(SAMPLE)) == {"K00001", "K00226", "K06016", "K00002", "K99999"}


def test_symbol_is_the_text_before_the_semicolon():
    assert koinfo.parse(SAMPLE)["K00226"].symbol == "pyrD"


def test_symbol_takes_the_first_of_a_comma_list():
    assert koinfo.parse(SAMPLE)["K00002"].symbol == "AKR1A1"


def test_ec_is_extracted_from_the_bracket():
    assert koinfo.parse(SAMPLE)["K00226"].ec == "1.3.98.1"


def test_first_ec_wins_when_several_are_listed():
    assert koinfo.parse(SAMPLE)["K06016"].ec == "3.5.1.6"


def test_entries_without_symbol_or_ec_degrade_gracefully():
    entry = koinfo.parse(SAMPLE)["K99999"]
    assert entry.symbol is None
    assert entry.ec is None
    assert entry.name.startswith("some protein")


def test_name_excludes_the_symbol_and_the_ec_bracket():
    assert koinfo.parse(SAMPLE)["K00226"].name == "dihydroorotate dehydrogenase (fumarate)"


def test_blank_and_malformed_lines_are_skipped():
    assert koinfo.parse("\n\nnotatabline\nK00001\tADH; x [EC:1.1.1.1]\n") == {
        "K00001": koinfo.parse("K00001\tADH; x [EC:1.1.1.1]\n")["K00001"]
    }


@pytest.mark.parametrize(
    ("style", "expected"),
    [("ko", "K00226"), ("symbol", "pyrD"), ("ec", "1.3.98.1")],
)
def test_label_for_each_style(style, expected):
    assert koinfo.label_for("K00226", koinfo.parse(SAMPLE), style) == expected


def test_label_falls_back_to_the_ko_id_when_the_field_is_missing():
    names = koinfo.parse(SAMPLE)
    assert koinfo.label_for("K99999", names, "symbol") == "K99999"
    assert koinfo.label_for("K99999", names, "ec") == "K99999"


def test_label_falls_back_when_the_ko_is_absent_entirely():
    assert koinfo.label_for("K12345", {}, "symbol") == "K12345"


def test_unknown_style_raises():
    with pytest.raises(ValueError):
        koinfo.label_for("K00226", koinfo.parse(SAMPLE), "nonsense")
