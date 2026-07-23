import pytest

from scripts.discover import discover

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
    return FakeFetcher({
        "https://nezams.com/sitemap_index.xml": INDEX,
        "https://nezams.com/post-sitemap.xml": POSTS,
        "https://nezams.com/nezam_update-sitemap.xml": UPDATES,
    })


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
    # SITE_INDEX و_ALLOWED_HOSTS يُشتقّان من سجل adapters لا يُكرّران يدويًا (A-1)
    from scripts.adapters import ADAPTERS
    from scripts.discover import _ALLOWED_HOSTS, SITE_INDEX

    assert SITE_INDEX == {a.source: a.sitemap_index for a in ADAPTERS if a.sitemap_index}
    assert _ALLOWED_HOSTS == {h for a in ADAPTERS for h in a.hosts}
    assert "qanoonsa" in SITE_INDEX and "nezams" in SITE_INDEX
