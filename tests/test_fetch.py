import urllib.error
from pathlib import Path

import pytest

from kegg_svg import fetch


@pytest.fixture
def cache(tmp_path):
    return tmp_path / "cache"


def install_fake(monkeypatch, payload=b"data", fail=False, status=200):
    """Replace the module's single network seam. No test opens a socket."""
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        if fail:
            raise urllib.error.URLError("no route to host")
        if status == 404:
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

        class Response:
            def read(self):
                return payload

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return Response()

    monkeypatch.setattr(fetch, "_urlopen", fake_urlopen)
    return calls


def test_normalize_pathway_accepts_common_spellings():
    assert fetch.normalize_pathway("ko00010") == "ko00010"
    assert fetch.normalize_pathway("00010") == "ko00010"
    assert fetch.normalize_pathway("map00010") == "ko00010"
    assert fetch.normalize_pathway("path:ko00010") == "ko00010"
    assert fetch.normalize_pathway("KO00010") == "ko00010"


def test_normalize_pathway_rejects_garbage():
    with pytest.raises(fetch.FetchError):
        fetch.normalize_pathway("glycolysis")


def test_get_kgml_downloads_and_caches(monkeypatch, cache):
    calls = install_fake(monkeypatch, payload=b"<pathway/>")
    assert fetch.get_kgml("ko00010", cache) == "<pathway/>"
    assert (cache / "ko00010.kgml").read_text() == "<pathway/>"
    assert calls == ["https://rest.kegg.jp/get/ko00010/kgml"]


def test_second_call_is_served_from_cache(monkeypatch, cache):
    install_fake(monkeypatch, payload=b"<pathway/>")
    fetch.get_kgml("ko00010", cache)
    calls = install_fake(monkeypatch, payload=b"SHOULD NOT BE USED")
    assert fetch.get_kgml("ko00010", cache) == "<pathway/>"
    assert calls == []


def test_png_url_and_cache_path(monkeypatch, cache):
    calls = install_fake(monkeypatch, payload=b"\x89PNG")
    assert fetch.get_map_png("ko00010", cache) == b"\x89PNG"
    assert (cache / "ko00010.png").read_bytes() == b"\x89PNG"
    assert calls == ["https://www.kegg.jp/kegg/pathway/ko/ko00010.png"]


def test_offline_with_warm_cache_never_calls_the_network(monkeypatch, cache):
    install_fake(monkeypatch, payload=b"<pathway/>")
    fetch.get_kgml("ko00010", cache)
    calls = install_fake(monkeypatch)
    assert fetch.get_kgml("ko00010", cache, offline=True) == "<pathway/>"
    assert calls == []


def test_offline_with_cold_cache_raises_naming_the_path(monkeypatch, cache):
    install_fake(monkeypatch)
    with pytest.raises(fetch.OfflineError) as exc:
        fetch.get_kgml("ko00010", cache, offline=True)
    assert "ko00010.kgml" in str(exc.value)


def test_network_failure_with_warm_cache_falls_back(monkeypatch, cache, tmp_path):
    cache.mkdir(parents=True)
    (cache / "ko00010.kgml").write_text("<cached/>")
    install_fake(monkeypatch, fail=True)
    assert fetch.get_kgml("ko00010", cache) == "<cached/>"


def test_network_failure_with_cold_cache_raises(monkeypatch, cache):
    install_fake(monkeypatch, fail=True)
    with pytest.raises(fetch.FetchError):
        fetch.get_kgml("ko00010", cache)


def test_http_404_raises_not_found_naming_the_url(monkeypatch, cache):
    install_fake(monkeypatch, status=404)
    with pytest.raises(fetch.NotFoundError) as exc:
        fetch.get_kgml("ko99999", cache)
    assert "rest.kegg.jp" in str(exc.value)


def test_interrupted_download_leaves_no_cache_entry(monkeypatch, cache):
    def exploding_urlopen(request, timeout=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(fetch, "_urlopen", exploding_urlopen)
    with pytest.raises(KeyboardInterrupt):
        fetch.get_kgml("ko00010", cache)
    assert not (cache / "ko00010.kgml").exists()
    assert list(cache.glob("*")) == [] or not cache.exists()


def test_png_size_reads_ihdr(fake_png):
    assert fetch.png_size(fake_png) == (1000, 800)


def test_png_size_rejects_non_png():
    with pytest.raises(fetch.FetchError):
        fetch.png_size(b"not a png at all, really not")


def test_write_failure_partway_leaves_no_partial_destination_file(monkeypatch, cache):
    """A failure during the write step must not leave a truncated file at the
    destination path. `_download` succeeds and returns real bytes; the final
    `Path.replace` step is the one that fails."""
    install_fake(monkeypatch, payload=b"<pathway/>")

    def exploding_replace(self, target):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", exploding_replace)
    with pytest.raises(OSError):
        fetch.get_kgml("ko00010", cache)
    assert not (cache / "ko00010.kgml").exists()


def test_cache_dir_honours_override(tmp_path):
    assert fetch.cache_dir(str(tmp_path / "x")) == tmp_path / "x"


def test_cache_dir_honours_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert fetch.cache_dir() == tmp_path / "kegg-svg"
