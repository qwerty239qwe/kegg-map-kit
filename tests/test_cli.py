import io
import xml.etree.ElementTree as ET

import pytest

from kegg_svg import cli

SVG = "{http://www.w3.org/2000/svg}"


@pytest.fixture
def warm_cache(tmp_path, kgml_text, fake_png):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "ko00010.kgml").write_text(kgml_text)
    (cache / "ko00010.png").write_bytes(fake_png)
    return cache


@pytest.fixture
def input_file(tmp_path):
    path = tmp_path / "data.tsv"
    path.write_text("K00844\t2.0\nK01810\t-1.0\n")
    return path


def invoke(argv):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(argv, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def test_end_to_end_writes_an_svg(tmp_path, warm_cache, input_file):
    out = tmp_path / "map.svg"
    code, _, _err = invoke(
        ["ko00010", "-i", str(input_file), "-o", str(out), "--cache", str(warm_cache), "--offline"]
    )
    assert code == 0
    root = ET.fromstring(out.read_text())
    assert root.tag == f"{SVG}svg"
    assert root.find(f'.//{SVG}g[@id="kegg-svg-overlay"]') is not None


def test_summary_line_goes_to_stderr(tmp_path, warm_cache, input_file):
    out = tmp_path / "map.svg"
    _, _, err = invoke(
        ["ko00010", "-i", str(input_file), "-o", str(out), "--cache", str(warm_cache), "--offline"]
    )
    assert "2/2" in err
    assert "ko00010" in err


def test_quiet_suppresses_the_summary(tmp_path, warm_cache, input_file):
    out = tmp_path / "map.svg"
    _, _, err = invoke(
        ["ko00010", "-i", str(input_file), "-o", str(out), "--cache", str(warm_cache),
         "--offline", "-q"]
    )
    assert err == ""


def test_output_dash_writes_to_stdout(warm_cache, input_file):
    code, out, _ = invoke(
        ["ko00010", "-i", str(input_file), "-o", "-", "--cache", str(warm_cache), "--offline"]
    )
    assert code == 0
    assert out.startswith("<svg")


def test_vector_mode_needs_no_png(tmp_path, kgml_text, input_file):
    cache = tmp_path / "c"
    cache.mkdir()
    (cache / "ko00010.kgml").write_text(kgml_text)
    out = tmp_path / "map.svg"
    code, _, _ = invoke(
        ["ko00010", "-i", str(input_file), "-o", str(out), "--cache", str(cache),
         "--offline", "--mode", "vector"]
    )
    assert code == 0


def test_local_kgml_and_png_flags_bypass_the_cache(tmp_path, kgml_text, fake_png, input_file):
    kgml_path = tmp_path / "p.kgml"
    kgml_path.write_text(kgml_text)
    png_path = tmp_path / "p.png"
    png_path.write_bytes(fake_png)
    out = tmp_path / "map.svg"
    code, _, _ = invoke(
        ["ko00010", "-i", str(input_file), "-o", str(out),
         "--kgml", str(kgml_path), "--png", str(png_path)]
    )
    assert code == 0


def test_png_flag_with_vector_mode_is_an_error(tmp_path, fake_png, input_file):
    png_path = tmp_path / "p.png"
    png_path.write_bytes(fake_png)
    code, _, err = invoke(
        ["ko00010", "-i", str(input_file), "-o", "-", "--mode", "vector", "--png", str(png_path)]
    )
    assert code == 1
    assert "vector" in err


def test_offline_cache_miss_exits_1(tmp_path, input_file):
    code, _, err = invoke(
        ["ko00010", "-i", str(input_file), "-o", "-", "--cache", str(tmp_path / "empty"),
         "--offline"]
    )
    assert code == 1
    assert "ko00010.kgml" in err


def test_bad_pathway_id_exits_1(input_file):
    code, _, err = invoke(["glycolysis", "-i", str(input_file), "-o", "-"])
    assert code == 1
    assert "pathway id" in err


def test_malformed_input_exits_1_with_line_number(tmp_path, warm_cache):
    bad = tmp_path / "bad.tsv"
    bad.write_text("K00844\tred\nnotako\tblue\n")
    code, _, err = invoke(
        ["ko00010", "-i", str(bad), "-o", "-", "--cache", str(warm_cache), "--offline"]
    )
    assert code == 1
    assert "line 2" in err


def test_unknown_colormap_exits_1(tmp_path, warm_cache, input_file):
    code, _, _err = invoke(
        ["ko00010", "-i", str(input_file), "-o", "-", "--cache", str(warm_cache),
         "--offline", "--cmap", "nope"]
    )
    assert code == 1


def test_no_matches_warns_but_succeeds(tmp_path, warm_cache):
    data = tmp_path / "none.tsv"
    data.write_text("K99999\t1.0\n")
    code, out, err = invoke(
        ["ko00010", "-i", str(data), "-o", "-", "--cache", str(warm_cache), "--offline"]
    )
    assert code == 0
    assert "no KO" in err.lower() or "0/1" in err
    assert out.startswith("<svg")


def test_network_failure_with_cold_cache_exits_2(monkeypatch, tmp_path, input_file):
    import urllib.error

    from kegg_svg import fetch

    def boom(request, timeout=None):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(fetch, "_urlopen", boom)
    code, _, _err = invoke(
        ["ko00010", "-i", str(input_file), "-o", "-", "--cache", str(tmp_path / "cold")]
    )
    assert code == 2


def test_stdin_input(monkeypatch, warm_cache):
    monkeypatch.setattr("sys.stdin", io.StringIO("K00844\t1.0\n"))
    code, out, _ = invoke(
        ["ko00010", "-i", "-", "-o", "-", "--cache", str(warm_cache), "--offline"]
    )
    assert code == 0
    assert out.startswith("<svg")


def test_capped_entries_warn(tmp_path, warm_cache):
    data = tmp_path / "wide.tsv"
    data.write_text("K00844\t" + "\t".join(["1.0"] * 20) + "\n")
    code, _, err = invoke(
        ["ko00010", "-i", str(data), "-o", "-", "--cache", str(warm_cache), "--offline"]
    )
    assert code == 0
    assert "12" in err


def test_bad_pathway_id_is_a_user_error_not_a_network_one(input_file):
    from kegg_svg import fetch

    with pytest.raises(fetch.PathwayIdError):
        fetch.normalize_pathway("glycolysis")
    code, _, err = invoke(["glycolysis", "-i", str(input_file), "-o", "-"])
    assert code == 1
    assert code != 2
    assert "pathway id" in err


def test_corrupt_png_exits_1(tmp_path, kgml_text, input_file):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "ko00010.kgml").write_text(kgml_text)
    (cache / "ko00010.png").write_bytes(b"not a png at all, really not")
    code, _, err = invoke(
        ["ko00010", "-i", str(input_file), "-o", "-", "--cache", str(cache), "--offline"]
    )
    assert code == 1
    assert "PNG" in err


def test_missing_required_flag_exits_1(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["ko00010", "-o", "-"])
    assert exc.value.code == 1
    assert capsys.readouterr().err != ""


def test_bad_mode_choice_exits_1(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["ko00010", "-i", "-", "-o", "-", "--mode", "bogus"])
    assert exc.value.code == 1
    assert "bogus" in capsys.readouterr().err


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "0.1.0" in capsys.readouterr().out


def test_unwritable_output_path_exits_1(warm_cache, input_file):
    code, _, err = invoke(
        ["ko00010", "-i", str(input_file), "-o", "/nope/does/not/exist/x.svg",
         "--cache", str(warm_cache), "--offline"]
    )
    assert code == 1
    assert err.startswith("kegg-svg:")


def test_bad_na_color_exits_1(warm_cache, input_file):
    code, _, err = invoke(
        ["ko00010", "-i", str(input_file), "-o", "-", "--cache", str(warm_cache),
         "--offline", "--na-color", "totally-not-a-colour"]
    )
    assert code == 1
    assert "totally-not-a-colour" in err


def test_valid_na_color_is_accepted(warm_cache, input_file):
    code, out, _ = invoke(
        ["ko00010", "-i", str(input_file), "-o", "-", "--cache", str(warm_cache),
         "--offline", "--na-color", "#cccccc"]
    )
    assert code == 0
    assert out.startswith("<svg")


def test_malformed_input_with_cold_cache_exits_1_not_2(monkeypatch, tmp_path):
    import urllib.error

    from kegg_svg import fetch

    def boom(request, timeout=None):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(fetch, "_urlopen", boom)
    bad = tmp_path / "bad.tsv"
    bad.write_text("K00844\tred\nnotako\tblue\n")
    code, _, err = invoke(
        ["ko00010", "-i", str(bad), "-o", "-", "--cache", str(tmp_path / "cold")]
    )
    assert code == 1
    assert "line 2" in err


def test_label_values_flag_annotates_the_svg(tmp_path, warm_cache, input_file):
    code, out, _ = invoke(
        ["ko00010", "-i", str(input_file), "-o", "-", "--cache", str(warm_cache),
         "--offline", "--label-values"]
    )
    assert code == 0
    group = ET.fromstring(out).find(f'.//{SVG}g[@id="kegg-svg-values"]')
    assert group is not None
    assert [t.text for t in group.findall(f".//{SVG}text")] == ["+2.00", "-1.00"]


def test_labels_absent_without_the_flag(warm_cache, input_file):
    _, out, _ = invoke(
        ["ko00010", "-i", str(input_file), "-o", "-", "--cache", str(warm_cache), "--offline"]
    )
    assert ET.fromstring(out).find(f'.//{SVG}g[@id="kegg-svg-values"]') is None


def test_label_size_reaches_the_renderer(warm_cache, input_file):
    _, out, _ = invoke(
        ["ko00010", "-i", str(input_file), "-o", "-", "--cache", str(warm_cache),
         "--offline", "--label-values", "--label-size", "12"]
    )
    group = ET.fromstring(out).find(f'.//{SVG}g[@id="kegg-svg-values"]')
    assert group.findall(f".//{SVG}text")[0].get("font-size") == "12.00"


def test_unmapped_color_greys_boxes_without_data(warm_cache, input_file):
    code, out, _ = invoke(
        ["ko00010", "-i", str(input_file), "-o", "-", "--cache", str(warm_cache),
         "--offline", "--unmapped-color", "lightgrey"]
    )
    assert code == 0
    group = ET.fromstring(out).find(f'.//{SVG}g[@id="kegg-svg-unmapped"]')
    assert group is not None
    fills = {r.get("fill") for r in group.findall(f".//{SVG}rect")}
    assert fills == {"lightgrey"}


def test_no_unmapped_group_without_the_flag(warm_cache, input_file):
    _, out, _ = invoke(
        ["ko00010", "-i", str(input_file), "-o", "-", "--cache", str(warm_cache), "--offline"]
    )
    assert ET.fromstring(out).find(f'.//{SVG}g[@id="kegg-svg-unmapped"]') is None


def test_bad_unmapped_color_exits_1(warm_cache, input_file):
    code, _, err = invoke(
        ["ko00010", "-i", str(input_file), "-o", "-", "--cache", str(warm_cache),
         "--offline", "--unmapped-color", "not-a-colour"]
    )
    assert code == 1
    assert "--unmapped-color" in err
