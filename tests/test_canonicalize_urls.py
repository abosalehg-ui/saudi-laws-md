"""اختبارات سكربت تطبيع الروابط — سكربت يعيد كتابة آلاف الملفات، فيجب
أن يكون سلوكه (وخصوصًا معاينته) مثبتًا."""

from scripts.canonicalize_urls import canonicalize_file, run

ENCODED = "https://nezams.com/%d9%86%d8%b8%d8%a7%d9%85-%d8%a7%d9%84%d8%b9%d9%85%d9%84/"
DECODED = "https://nezams.com/نظام-العمل/"


def _write(tmp_path, name, front):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{front}\n---\n\n# عنوان\n\nمتن.\n", encoding="utf-8")
    return path


def test_encoded_source_url_is_decoded(tmp_path):
    p = _write(tmp_path, "a.md", f'title: "س"\nsource_url: "{ENCODED}"')
    assert canonicalize_file(p) == (True, False)
    assert DECODED in p.read_text(encoding="utf-8")


def test_already_canonical_is_untouched(tmp_path):
    p = _write(tmp_path, "a.md", f'title: "س"\nsource_url: "{DECODED}"')
    before = p.read_text(encoding="utf-8")
    assert canonicalize_file(p) == (False, False)
    assert p.read_text(encoding="utf-8") == before


def test_self_link_is_dropped_from_also_available(tmp_path):
    """الرابط الذاتي بترميز مختلف كان يظهر كنسخة أخرى — يُسقَط."""
    p = _write(
        tmp_path,
        "a.md",
        f'title: "س"\nsource_url: "{DECODED}"\n'
        f'also_available_from: ["{ENCODED}", "https://qanoonsa.com/p/1/"]',
    )
    assert canonicalize_file(p) == (False, True)
    text = p.read_text(encoding="utf-8")
    assert 'also_available_from: ["https://qanoonsa.com/p/1/"]' in text


def test_dry_run_reports_without_writing(tmp_path):
    """المعاينة تحسب بنفس منطق التنفيذ ولا تكتب — كانت نسخة ثانية من المنطق."""
    p = _write(tmp_path, "a.md", f'title: "س"\nsource_url: "{ENCODED}"')
    before = p.read_text(encoding="utf-8")
    assert canonicalize_file(p, dry_run=True) == (True, False)
    assert p.read_text(encoding="utf-8") == before


def test_run_is_idempotent(tmp_path):
    p = _write(tmp_path, "ت/a.md", f'title: "س"\nsource_url: "{ENCODED}"')
    assert run([str(tmp_path)]) == 0
    once = p.read_text(encoding="utf-8")
    assert run([str(tmp_path)]) == 0
    assert p.read_text(encoding="utf-8") == once


def test_generated_directory_readme_is_skipped(tmp_path):
    readme = tmp_path / "ت" / "README.md"
    readme.parent.mkdir(parents=True)
    readme.write_text("# فهرس المجلد\n\n| عنوان |\n", encoding="utf-8")
    assert run([str(tmp_path)]) == 0
    assert readme.read_text(encoding="utf-8").startswith("# فهرس المجلد")
