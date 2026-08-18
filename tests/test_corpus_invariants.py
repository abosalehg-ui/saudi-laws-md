"""ثوابت على مستوى المُدوَّنة المُلتزَمة، لا على وثيقة مفردة.

هذه هي فئة الاختبارات التي كانت غائبة: كل اختبار آخر يفحص وثيقة يصنعها
هو بنفسه، فلا شيء كان يفحص الـ 2737 ملفًا المُخزَّنة فعلًا — وهكذا تراكمت
197 وثيقة جوفاء ومرّت عبر CI بصمت.

تُشغَّل على المُدوَّنة الحقيقية إن وُجدت (تُتخطّى في مستودع بلا laws/).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.formatter import MAX_FILES_PER_DIR
from scripts.frontmatter import read_field
from scripts.migrate_corpus import body_text
from scripts.schema import CONTENT_INCOMPLETE, INCOMPLETE_BODY_NOTE, MIN_BODY_CHARS, NOISE_PATTERNS
from scripts.status import VALID_STATUSES

CORPUS = Path("laws")
INDEX = Path("index.json")

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="لا مُدوَّنة في هذا المستودع")


def _documents() -> list[Path]:
    return [p for p in sorted(CORPUS.rglob("*.md")) if p.name != "README.md"]


@pytest.fixture(scope="module")
def docs() -> list[tuple[Path, str]]:
    return [(p, p.read_text(encoding="utf-8")) for p in _documents()]


def test_corpus_is_not_empty(docs):
    assert len(docs) > 100, "المُدوَّنة أصغر من المتوقّع — يُحتمل خطأ في المسار"


def test_every_document_has_front_matter_and_required_fields(docs):
    missing = [
        str(p) for p, text in docs
        if not text.startswith("---\n") or not read_field(text, "title")
        or not read_field(text, "source_url")
    ]
    assert missing == [], f"وثائق بلا front matter أو بحقول إلزامية ناقصة: {missing[:5]}"


def test_status_values_are_from_the_closed_set(docs):
    bad = {
        read_field(text, "status") for _, text in docs
        if read_field(text, "status") and read_field(text, "status") not in VALID_STATUSES
    }
    assert bad == set(), f"قيم status خارج المجموعة المغلقة: {sorted(bad)[:5]}"


def test_no_interface_noise_leaks_into_any_body(docs):
    """أثر ازدواج/فشل استخراج: بقايا واجهة داخل نصّ قانوني."""
    offenders = [
        (str(p), pattern) for p, text in docs
        for pattern in NOISE_PATTERNS
        if pattern in body_text(text)
    ]
    assert offenders == [], f"ضجيج واجهة في المتن: {offenders[:5]}"


def test_hollow_documents_are_explicitly_marked(docs):
    """الوثيقة بلا نصّ تُعلَّم صراحةً؛ بلا ذلك تبدو نصًّا قانونيًا مبتورًا."""
    unmarked = [
        str(p) for p, text in docs
        if (len(body_text(text)) < MIN_BODY_CHARS or body_text(text) == INCOMPLETE_BODY_NOTE)
        and read_field(text, "content_status") != CONTENT_INCOMPLETE
    ]
    assert unmarked == [], f"وثائق جوفاء بلا علامة: {unmarked[:5]}"


def test_incomplete_mark_is_not_stale(docs):
    """علامة النقص لا تبقى على وثيقة صار لها متن كامل."""
    stale = [
        str(p) for p, text in docs
        if read_field(text, "content_status") == CONTENT_INCOMPLETE
        and len(body_text(text)) >= MIN_BODY_CHARS
        and body_text(text) != INCOMPLETE_BODY_NOTE
    ]
    assert stale == [], f"علامة نقص على وثائق كاملة: {stale[:5]}"


def test_iso_date_fields_are_well_formed(docs):
    """الحقول الآلية قابلة للفرز فعلًا: YYYY-MM-DD لا نصّ حرّ."""
    bad = [
        (str(p), field, value)
        for p, text in docs
        for field in ("issued_date_hijri", "publish_date_gregorian")
        if (value := read_field(text, field))
        and not (len(value) == 10 and value[4] == value[7] == "-" and
                 value.replace("-", "").isdigit())
    ]
    assert bad == [], f"تواريخ آلية بصيغة غير ISO: {bad[:5]}"


def test_no_directory_exceeds_the_browsable_limit():
    """عارض GitHub يقطع المجلد عند 1000 عنصر؛ ما فوق الحدّ يصير غير مرئي."""
    oversized = [
        (str(d), n) for d in CORPUS.rglob("*") if d.is_dir()
        if (n := sum(1 for f in d.glob("*.md") if f.name != "README.md")) > MAX_FILES_PER_DIR
    ]
    assert oversized == [], f"مجلدات تجاوزت الحدّ المقروء: {oversized}"


def test_index_matches_the_corpus_on_disk(docs):
    """الفهرس ليس ملفًا يدويًا يتقادم: يجب أن يطابق ما على القرص وثيقةً بوثيقة."""
    if not INDEX.exists():
        pytest.skip("لا index.json")
    entries = json.loads(INDEX.read_text(encoding="utf-8"))
    assert [e["path"] for e in entries] == [p.as_posix() for p, _ in docs]


def test_every_document_directory_has_a_generated_readme(docs):
    directories = {p.parent for p, _ in docs}
    missing = [str(d) for d in sorted(directories) if not (d / "README.md").exists()]
    assert missing == [], f"مجلدات بلا فهرس تصفّح: {missing[:5]}"
