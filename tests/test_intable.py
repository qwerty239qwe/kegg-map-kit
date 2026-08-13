import io

import pytest

from kegg_svg import intable


def parse(text):
    return intable.parse(io.StringIO(text))


def test_tab_separated_colours():
    table = parse("K00844\t#ff0000\nK00845\tblue\n")
    assert table.mode == "color"
    assert table.n_cols == 1
    assert table.rows == {"K00844": ("#ff0000",), "K00845": ("blue",)}


def test_comma_separated_is_sniffed():
    assert parse("K00844,#ff0000\n").rows == {"K00844": ("#ff0000",)}


def test_kegg_mapper_bg_fg_pair_splits_into_fg_map():
    table = parse("K00844\t#ff0000,#000000\n")
    assert table.rows == {"K00844": ("#ff0000",)}
    assert table.fg == {"K00844": "#000000"}


def test_three_digit_hex_is_accepted():
    assert parse("K00844\t#f00\n").mode == "color"


def test_numeric_input_is_value_mode():
    table = parse("K00844\t-1.5\t2\nK00845\t0\t0.25\n")
    assert table.mode == "value"
    assert table.n_cols == 2
    assert table.rows == {"K00844": (-1.5, 2.0), "K00845": (0.0, 0.25)}


def test_values_collects_every_numeric_cell():
    assert sorted(intable.values(parse("K00844\t-1.5\t2\nK00845\t0\t0.25\n"))) == [
        -1.5,
        0.0,
        0.25,
        2.0,
    ]


def test_values_of_a_colour_table_is_empty():
    assert intable.values(parse("K00844\tred\n")) == []


def test_header_line_is_skipped():
    table = parse("ko\tsampleA\nK00844\t1.0\n")
    assert table.rows == {"K00844": (1.0,)}


def test_comments_and_blank_lines_are_skipped():
    table = parse("# a comment\n\nK00844\tred\n\n")
    assert table.rows == {"K00844": ("red",)}


def test_ko_ids_are_uppercased():
    assert "K00844" in parse("k00844\tred\n").rows


def test_short_rows_are_padded_with_none():
    table = parse("K00844\t1.0\t2.0\nK00845\t3.0\n")
    assert table.rows["K00845"] == (3.0, None)


def test_blank_cells_become_none():
    assert parse("K00844\t1.0\t\t3.0\n").rows["K00844"] == (1.0, None, 3.0)


def test_colour_wins_when_a_row_has_both_kinds_of_cell():
    # Classification is by majority across the whole file; here colour cells
    # dominate, so a stray numeric cell in a colour file is an error.
    with pytest.raises(intable.InputError) as exc:
        parse("K00844\tred\nK00845\tblue\nK00846\t1.5\n")
    assert "line 3" in str(exc.value)


def test_invalid_ko_id_raises_with_line_number():
    with pytest.raises(intable.InputError) as exc:
        parse("K00844\tred\nnotako\tblue\n")
    assert "line 2" in str(exc.value)


def test_duplicate_ko_raises_naming_both_lines():
    with pytest.raises(intable.InputError) as exc:
        parse("K00844\tred\nK00844\tblue\n")
    message = str(exc.value)
    assert "K00844" in message and "line 1" in message and "line 2" in message


def test_unparseable_cell_raises():
    with pytest.raises(intable.InputError):
        parse("K00844\tnot-a-colour-or-number\n")


def test_ko_with_no_data_columns_raises():
    with pytest.raises(intable.InputError):
        parse("K00844\n")


def test_empty_input_raises():
    with pytest.raises(intable.InputError):
        parse("")
