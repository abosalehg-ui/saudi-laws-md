from scripts.fetch import FetchResult
from scripts.main import run

EXISTING_FRONT_MATTER = (
    '---\ntitle: "نظام العمل"\nsource: qanoonsa\n'
    'source_url: "https://qanoonsa.com/p/1/"\n'
    'doc_type: "نظام"\ncategory: "نظام"\n'
    'etag: "abc123"\nlast_modified: "Wed, 01 Jan 2026 00:00:00 GMT"\n'
    'retrieved_at: 2020-01-01\n---\n\n# نظام العمل\n\n## المادة الأولى\n\nنص قديم.\n'
)


def _seed_existing(out):
    path = out / "نظام" / "نظام العمل.md"
    path.parent.mkdir(parents=True)
    path.write_text(EXISTING_FRONT_MATTER, encoding="utf-8")
    return path


def test_check_updates_skips_rewrite_when_not_modified(tmp_path, monkeypatch):
    import scripts.main as main_mod

    out = tmp_path / "laws"
    existing_file = _seed_existing(out)
    original = existing_file.read_text(encoding="utf-8")
    seen = {}

    class FakeFetcher:
        def __init__(self, *a, **k):
            pass

        def get_conditional(self, url, etag=None, last_modified=None):
            seen["etag"] = etag
            seen["last_modified"] = last_modified
            return FetchResult(text=None, etag=etag, last_modified=last_modified, not_modified=True)

    monkeypatch.setattr(main_mod, "Fetcher", FakeFetcher)
    monkeypatch.chdir(tmp_path)

    code = run([
        "https://qanoonsa.com/p/1/",
        "--out", str(out),
        "--check-updates",
    ])

    assert code == 0
    assert seen == {"etag": "abc123", "last_modified": "Wed, 01 Jan 2026 00:00:00 GMT"}
    assert existing_file.read_text(encoding="utf-8") == original  # لا إعادة كتابة


def test_check_updates_rewrites_and_persists_new_etag_when_modified(tmp_path, monkeypatch):
    import scripts.main as main_mod

    out = tmp_path / "laws"
    existing_file = _seed_existing(out)
    new_html = (
        "<html><h1>نظام العمل</h1>"
        '<div class="entry-content"><h2>المادة الأولى</h2><p>نص جديد بعد التعديل.</p></div></html>'
    )

    class FakeFetcher:
        def __init__(self, *a, **k):
            pass

        def get_conditional(self, url, etag=None, last_modified=None):
            return FetchResult(
                text=new_html, etag="new-etag",
                last_modified="Thu, 02 Jan 2026 00:00:00 GMT", not_modified=False,
            )

    monkeypatch.setattr(main_mod, "Fetcher", FakeFetcher)
    monkeypatch.chdir(tmp_path)

    code = run([
        "https://qanoonsa.com/p/1/",
        "--out", str(out),
        "--category", "نظام",
        "--check-updates",
    ])

    assert code == 0
    content = existing_file.read_text(encoding="utf-8")
    assert "نص جديد بعد التعديل" in content
    assert 'etag: "new-etag"' in content
    assert 'last_modified: "Thu, 02 Jan 2026 00:00:00 GMT"' in content


def test_check_updates_falls_back_to_full_fetch_for_unseen_url(tmp_path, monkeypatch):
    # رابط لم يُستورد من قبل: لا يوجد إدخال existing له، فيُستخدم fetcher.get العادي
    import scripts.main as main_mod

    out = tmp_path / "laws"
    calls = {"get": 0, "get_conditional": 0}
    html = (
        "<html><h1>نظام جديد</h1>"
        '<div class="entry-content"><h2>المادة الأولى</h2><p>نص.</p></div></html>'
    )

    class FakeFetcher:
        def __init__(self, *a, **k):
            pass

        def get(self, url):
            calls["get"] += 1
            return html

        def get_conditional(self, url, etag=None, last_modified=None):
            calls["get_conditional"] += 1
            raise AssertionError("لا يُستدعى لرابط جديد")

    monkeypatch.setattr(main_mod, "Fetcher", FakeFetcher)
    monkeypatch.chdir(tmp_path)

    code = run([
        "https://qanoonsa.com/p/2/",
        "--out", str(out),
        "--check-updates",
    ])

    assert code == 0
    assert calls == {"get": 1, "get_conditional": 0}
