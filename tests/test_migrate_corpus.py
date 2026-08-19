"""اختبارات هجرة حقول المُدوَّنة: الحالة المغلقة، التواريخ الآلية، الوثائق الناقصة."""

from scripts.migrate_corpus import body_text, migrate, migrate_text

LONG_BODY = "يسري هذا النظام على جميع المنشآت وفروعها العاملة في المملكة، " * 3


def _doc(front: str, body: str = LONG_BODY) -> str:
    return f"---\n{front}\n---\n\n# عنوان\n\n{body}\n"


def test_free_text_status_is_split_into_closed_value_and_note():
    text = _doc('title: "س"\nstatus: "ملغي بصدور نظام الاستثمار الجديد"')
    out, changed = migrate_text(text)
    assert "status" in changed
    assert 'status: "ملغى"' in out
    assert 'status_note: "ملغي بصدور نظام الاستثمار الجديد"' in out


def test_bare_status_gets_no_redundant_note():
    out, _ = migrate_text(_doc('title: "س"\nstatus: "ساري"'))
    assert 'status: "نافذ"' in out
    assert "status_note" not in out


def test_sortable_dates_are_derived_without_touching_the_original():
    original = "٤ من شوال ١٤٤٣هـ الموافق: ٥ من مايو ٢٠٢٢م"
    out, changed = migrate_text(_doc(f'title: "س"\nissued_date: "{original}"'))
    assert "issued_date_hijri" in changed
    assert 'issued_date_hijri: "1443-10-04"' in out
    assert f'issued_date: "{original}"' in out  # النصّ البشري كما هو


def test_gregorian_date_derived_from_gazette_reference():
    out, _ = migrate_text(
        _doc('title: "س"\ngazette_ref: "نشر في عدد جريدة أم القرى رقم (٥١٢٠) '
             'الصادر في ٧ من نوفمبر ٢٠٢٥م."')
    )
    assert 'publish_date_gregorian: "2025-11-07"' in out


def test_hollow_document_is_marked_incomplete():
    out, changed = migrate_text(_doc('title: "أمر"', body="صدر في: ٤ من شوال ١٤٤٣هـ"))
    assert "content_status" in changed
    assert 'content_status: "ناقص"' in out


def test_stale_incomplete_mark_is_removed_when_body_returns():
    """لو أُعيد سحب الوثيقة وصار لها متن، تُرفع العلامة تلقائيًا."""
    out, changed = migrate_text(_doc('title: "س"\ncontent_status: "ناقص"'))
    assert "content_status" in changed
    assert "content_status" not in out


def test_migration_is_idempotent(tmp_path):
    path = tmp_path / "a.md"
    path.write_text(
        _doc('title: "س"\nstatus: "غير ساري"\nissued_date: "1443/10/4هـ"'), encoding="utf-8"
    )
    assert migrate(tmp_path)[0] == 1
    once = path.read_text(encoding="utf-8")
    assert migrate(tmp_path)[0] == 0
    assert path.read_text(encoding="utf-8") == once


def test_generated_directory_readme_is_skipped(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# فهرس المجلد\n", encoding="utf-8")
    assert migrate(tmp_path)[0] == 0


def test_body_text_strips_front_matter_and_title():
    assert body_text('---\ntitle: "س"\n---\n\n# س\n\nالمتن.\n') == "المتن."
