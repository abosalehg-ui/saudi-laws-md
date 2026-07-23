"""اختبارات حرّاس سلامة البيانات في main.py: تصادم المسار (M-3) ورفض طمس
ملف ذي مواد بناتج نثري (M-1)."""

from scripts.main import run

ARTICLE_PAGE = (
    '<html><h1>{title}</h1><div class="entry-content">'
    "<h2>المادة الأولى</h2><p>نص المادة الأولى.</p></div></html>"
)
PROSE_PAGE = (
    '<html><h1>{title}</h1><div class="entry-content">'
    "<p>فقرة نثرية بلا أي تقطيع لمواد.</p></div></html>"
)


def _write(tmp_path, name, html):
    p = tmp_path / name
    p.write_text(html, encoding="utf-8")
    return p


def test_collision_between_different_docs_is_disambiguated(tmp_path, monkeypatch):
    # وثيقتان بعنوان وتصنيف متطابقين لكن رابطين مختلفين يجب ألا تطمس
    # إحداهما الأخرى؛ الثانية تأخذ اسمًا مميّزًا مشتقًا من رابطها (M-3)
    monkeypatch.chdir(tmp_path)
    out = str(tmp_path / "laws")
    page = _write(tmp_path, "a.html", ARTICLE_PAGE.format(title="نظام مكرر العنوان"))

    assert run(["--html", str(page), "--source", "qanoonsa",
                "--url", "https://qanoonsa.com/p/111/", "--category", "ت", "--out", out]) == 0
    assert run(["--html", str(page), "--source", "qanoonsa",
                "--url", "https://qanoonsa.com/p/222/", "--category", "ت", "--out", out]) == 0

    files = sorted(p.name for p in (tmp_path / "laws" / "ت").glob("*.md"))
    assert files == ["نظام مكرر العنوان (222).md", "نظام مكرر العنوان.md"]
    # كل ملف يحمل رابطه الأصلي (لا طمس)
    first = (tmp_path / "laws" / "ت" / "نظام مكرر العنوان.md").read_text(encoding="utf-8")
    second = (tmp_path / "laws" / "ت" / "نظام مكرر العنوان (222).md").read_text(encoding="utf-8")
    assert "p/111" in first and "p/222" in second


def test_collision_guard_is_idempotent(tmp_path, monkeypatch):
    # إعادة تشغيل نفس الوثيقتين لا تنتج نسخًا جديدة ولا تتذبذب (idempotency)
    monkeypatch.chdir(tmp_path)
    out = str(tmp_path / "laws")
    page = _write(tmp_path, "a.html", ARTICLE_PAGE.format(title="نظام مكرر العنوان"))
    common = ["--html", str(page), "--source", "qanoonsa", "--category", "ت", "--out", out]
    for _ in range(2):
        assert run(common + ["--url", "https://qanoonsa.com/p/111/"]) == 0
        assert run(common + ["--url", "https://qanoonsa.com/p/222/"]) == 0
    assert len(list((tmp_path / "laws" / "ت").glob("*.md"))) == 2


def test_prose_result_refuses_to_clobber_existing_article_file(tmp_path, monkeypatch):
    # ناتج نثري بلا مواد لنفس الرابط يجب ألا يطمس ملفًا قائمًا يحوي مواد (M-1)
    monkeypatch.chdir(tmp_path)
    out = str(tmp_path / "laws")
    url = "https://qanoonsa.com/p/333/"
    good = _write(tmp_path, "good.html", ARTICLE_PAGE.format(title="نظام مهم"))
    assert run(["--html", str(good), "--source", "qanoonsa", "--url", url,
                "--category", "ت", "--out", out]) == 0
    target = tmp_path / "laws" / "ت" / "نظام مهم.md"
    original = target.read_text(encoding="utf-8")
    assert "## المادة الأولى" in original

    bad = _write(tmp_path, "bad.html", PROSE_PAGE.format(title="نظام مهم"))
    code = run(["--html", str(bad), "--source", "qanoonsa", "--url", url,
                "--category", "ت", "--out", out])
    assert code == 1  # رُفض وسُجّل فشلًا
    assert target.read_text(encoding="utf-8") == original  # الملف الجيد بلا مساس
    failed = (tmp_path / "logs" / "failed.txt").read_text(encoding="utf-8")
    assert "بنية المصدر" in failed


def test_new_prose_doc_still_allowed(tmp_path, monkeypatch):
    # الحارس لا يمنع وثيقة نثرية جديدة لا ملف قائم لها
    monkeypatch.chdir(tmp_path)
    out = str(tmp_path / "laws")
    page = _write(tmp_path, "p.html", PROSE_PAGE.format(title="دليل إجرائي"))
    assert run(["--html", str(page), "--source", "qanoonsa",
                "--url", "https://qanoonsa.com/p/444/", "--category", "ت", "--out", out]) == 0
    assert (tmp_path / "laws" / "ت" / "دليل إجرائي.md").exists()
