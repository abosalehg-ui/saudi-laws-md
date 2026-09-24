import pytest

import scripts.discover as discover_mod
from scripts.discover import discover
from scripts.fetch import FetchError

INDEX = """<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://nezams.com/post-sitemap.xml</loc></sitemap>
  <sitemap><loc>https://nezams.com/nezam_update-sitemap.xml</loc></sitemap>
  <sitemap><loc>https://nezams.com/category-sitemap.xml</loc></sitemap>
  <sitemap><loc>https://nezams.com/author-sitemap.xml</loc></sitemap>
</sitemapindex>"""

POSTS = """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://nezams.com/نظام-العمل/</loc></url>
  <url><loc>https://nezams.com/نظام-المرور/</loc></url>
  <url><loc>https://evil.example.com/x/</loc></url>
</urlset>"""

UPDATES = """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://nezams.com/تحديثات-الأنظمة/تعديل-مادة/</loc></url>
</urlset>"""


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages
        self.requested = []

    def get(self, url):
        self.requested.append(url)
        return self.pages[url]


def _fetcher():
    return FakeFetcher(
        {
            "https://nezams.com/sitemap_index.xml": INDEX,
            "https://nezams.com/post-sitemap.xml": POSTS,
            "https://nezams.com/nezam_update-sitemap.xml": UPDATES,
        }
    )


def test_discover_filters_taxonomies_updates_and_foreign_hosts():
    urls = discover("nezams", _fetcher())
    assert urls == [
        "https://nezams.com/نظام-العمل/",
        "https://nezams.com/نظام-المرور/",
    ]
    # لا خرائط تصنيفات/مؤلفين (لم تُطلب أصلًا)، ولا رابط خارج النطاق
    assert not any("evil" in u for u in urls)


def test_discover_never_fetches_skipped_submaps():
    f = _fetcher()
    discover("nezams", f)
    assert "https://nezams.com/category-sitemap.xml" not in f.requested
    assert "https://nezams.com/author-sitemap.xml" not in f.requested
    assert "https://nezams.com/nezam_update-sitemap.xml" not in f.requested


def test_discover_include_updates_flag():
    urls = discover("nezams", _fetcher(), include_updates=True)
    assert "https://nezams.com/تحديثات-الأنظمة/تعديل-مادة/" in urls


def test_discover_unknown_source_raises():
    with pytest.raises(ValueError):
        discover("unknown", _fetcher())


def test_site_index_and_allowed_hosts_derived_from_registry():
    # SITE_INDEX ومقرّر السماح بالمضيف يُشتقّان من سجل adapters (A-1)
    from scripts.adapters import ADAPTERS, host_allowed
    from scripts.discover import SITE_INDEX

    assert SITE_INDEX == {a.source: a.sitemap_index for a in ADAPTERS if a.sitemap_index}
    assert "qanoonsa" in SITE_INDEX and "nezams" in SITE_INDEX
    for adapter in ADAPTERS:
        for host in adapter.hosts:
            assert host_allowed(f"https://{host}/x/")
            assert host_allowed(f"https://sub.{host}/x/")
    # القائمة البيضاء لا تُخدع بمضيف يلحق اسم المصدر كلاحقة
    assert not host_allowed("https://qanoonsa.com.evil.com/x/")
    assert not host_allowed("https://169.254.169.254/latest/meta-data/")


def test_nested_sitemap_index_is_followed_not_listed():
    """فهرس داخل فهرس: روابطه خرائط تُتبع، لا وثائق تُضاف إلى القائمة."""
    f = FakeFetcher(
        {
            "https://nezams.com/sitemap_index.xml": INDEX.replace(
                "https://nezams.com/post-sitemap.xml", "https://nezams.com/nested-index.xml"
            ),
            "https://nezams.com/nested-index.xml": """<sitemapindex>
          <sitemap><loc>https://nezams.com/post-sitemap.xml</loc></sitemap>
          <sitemap><loc>https://nezams.com/nested-index.xml</loc></sitemap>
        </sitemapindex>""",
            "https://nezams.com/post-sitemap.xml": POSTS,
        }
    )
    urls = discover("nezams", f)
    assert urls == ["https://nezams.com/نظام-العمل/", "https://nezams.com/نظام-المرور/"]
    assert not any(u.endswith(".xml") for u in urls)
    # الفهرس الدائري لا يُجلب مرتين
    assert f.requested.count("https://nezams.com/nested-index.xml") == 1


def test_flat_sitemap_without_index_is_read_directly():
    f = FakeFetcher({"https://nezams.com/sitemap_index.xml": POSTS})
    assert discover("nezams", f) == ["https://nezams.com/نظام-العمل/", "https://nezams.com/نظام-المرور/"]


def test_foreign_submap_is_never_fetched():
    f = FakeFetcher(
        {
            "https://nezams.com/sitemap_index.xml": """<sitemapindex>
          <sitemap><loc>https://evil.example.com/sitemap.xml</loc></sitemap>
          <sitemap><loc>https://nezams.com/post-sitemap.xml</loc></sitemap>
        </sitemapindex>""",
            "https://nezams.com/post-sitemap.xml": POSTS,
        }
    )
    discover("nezams", f)
    assert not any("evil" in u for u in f.requested)


def test_failed_submap_is_skipped_and_others_continue(capsys):
    class Failing(FakeFetcher):
        def get(self, url):
            if url.endswith("post-sitemap.xml"):
                raise FetchError("HTTP 500")
            return super().get(url)

    f = Failing(
        {
            "https://nezams.com/sitemap_index.xml": INDEX,
            "https://nezams.com/nezam_update-sitemap.xml": UPDATES,
        }
    )
    urls = discover("nezams", f, include_updates=True)
    assert urls == ["https://nezams.com/تحديثات-الأنظمة/تعديل-مادة/"]
    assert "تعذّر جلب خريطة فرعية" in capsys.readouterr().err


def test_cli_writes_urls_to_file(monkeypatch, tmp_path):
    monkeypatch.setattr(discover_mod, "Fetcher", lambda **kw: _fetcher())
    out = tmp_path / "urls.txt"
    assert discover_mod.run(["nezams", "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").splitlines() == [
        "https://nezams.com/نظام-العمل/",
        "https://nezams.com/نظام-المرور/",
    ]


def test_cli_prints_to_stdout_and_fails_when_nothing_found(monkeypatch, capsys):
    monkeypatch.setattr(discover_mod, "Fetcher", lambda **kw: _fetcher())
    assert discover_mod.run(["nezams"]) == 0
    assert "نظام-العمل" in capsys.readouterr().out
    empty = FakeFetcher({"https://nezams.com/sitemap_index.xml": "<urlset></urlset>"})
    monkeypatch.setattr(discover_mod, "Fetcher", lambda **kw: empty)
    assert discover_mod.run(["nezams"]) == 1


def test_cli_rejects_unknown_source():
    with pytest.raises(SystemExit):
        discover_mod.run(["example"])
