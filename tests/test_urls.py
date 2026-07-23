from scripts.fetch import FetchResult
from scripts.main import run
from scripts.urls import canonical_url

ENC = "https://nezams.com/%d9%86%d8%b8%d8%a7%d9%85-%d8%a7%d9%84%d8%b9%d9%85%d9%84/"
DEC = "https://nezams.com/نظام-العمل/"


def test_encoded_and_decoded_are_equal():
    assert canonical_url(ENC) == canonical_url(DEC) == DEC


def test_host_lowercased_and_scheme_normalised():
    assert canonical_url("HTTPS://Nezams.com/x/") == "https://nezams.com/x/"


def test_idempotent():
    assert canonical_url(canonical_url(ENC)) == canonical_url(ENC)


def test_trailing_slash_preserved():
    # لا نلمس الشرطة الأخيرة (قد تكون ذات دلالة على الخادم)
    assert canonical_url("https://qanoonsa.com/p/1") == "https://qanoonsa.com/p/1"
    assert canonical_url("https://qanoonsa.com/p/1/") == "https://qanoonsa.com/p/1/"


def _seed(out, url):
    path = out / "نظام" / "نظام العمل.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        f'---\ntitle: "نظام العمل"\nsource: qanoonsa\nsource_url: "{url}"\n'
        'doc_type: "نظام"\ncategory: "نظام"\netag: "abc123"\n'
        'retrieved_at: 2020-01-01\n---\n\n# نظام العمل\n\n## المادة الأولى\n\nقديم.\n',
        encoding="utf-8",
    )
    return path


def test_resume_with_check_updates_still_checks_known_links(tmp_path, monkeypatch):
    # التركيب --resume --check-updates يجب أن يمرّر الروابط المعروفة على
    # الجلب الشرطي، لا أن يتخطّاها بصمت (M-5)
    import scripts.main as main_mod

    out = tmp_path / "laws"
    _seed(out, "https://qanoonsa.com/p/1/")
    checked = []

    class FakeFetcher:
        def __init__(self, *a, **k):
            pass

        def get_conditional(self, url, etag=None, last_modified=None):
            checked.append((url, etag))
            return FetchResult(text=None, etag=etag, last_modified=None, not_modified=True)

    monkeypatch.setattr(main_mod, "Fetcher", FakeFetcher)
    monkeypatch.chdir(tmp_path)

    code = run([
        "https://qanoonsa.com/p/1/",
        "--out", str(out), "--resume", "--check-updates",
    ])
    assert code == 0
    # لم يُتخطَّ: مرّ فعلًا على الجلب الشرطي بالـ etag المحفوظ
    assert checked == [("https://qanoonsa.com/p/1/", "abc123")]


def test_resume_without_check_updates_skips_known_links(tmp_path, monkeypatch):
    # السلوك المعاكس: بلا --check-updates تُتخطّى الروابط المعروفة كالمعتاد
    import scripts.main as main_mod

    out = tmp_path / "laws"
    _seed(out, "https://qanoonsa.com/p/1/")
    calls = []

    class FakeFetcher:
        def __init__(self, *a, **k):
            pass

        def get(self, url):
            calls.append(url)
            return ""

    monkeypatch.setattr(main_mod, "Fetcher", FakeFetcher)
    monkeypatch.chdir(tmp_path)

    code = run(["https://qanoonsa.com/p/1/", "--out", str(out), "--resume"])
    assert code == 0
    assert calls == []  # تُخطّي بلا أي جلب


def test_index_matches_across_encodings(tmp_path, monkeypatch):
    # ملف مخزَّن برابط مُرمَّز يجب أن يُطابَق برابط غير مُرمَّز في --resume
    import scripts.main as main_mod

    out = tmp_path / "laws"
    _seed(out, ENC)  # الملف يخزّن الصيغة المُرمَّزة
    calls = []

    class FakeFetcher:
        def __init__(self, *a, **k):
            pass

        def get(self, url):
            calls.append(url)
            return ""

    monkeypatch.setattr(main_mod, "Fetcher", FakeFetcher)
    monkeypatch.chdir(tmp_path)

    # نمرّر الصيغة غير المُرمَّزة؛ يجب أن تُطابق وتُتخطّى
    code = run([DEC, "--out", str(out), "--resume"])
    assert code == 0
    assert calls == []
