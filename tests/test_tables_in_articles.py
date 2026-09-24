"""الجداول داخل المواد: جوهر المادة أحيانًا (غرامات، نقاط) — لا تُسقط ولا تُسطَّح.

عطل سابق: وضع المواد في qanoonsa لم يعالج <table> أصلًا، فخرجت مواد تنتهي
بـ «وفق الجدول الآتي:» بلا جدول، ومرّت عبر كل الفحوص بصمت.
"""

from pathlib import Path

from scripts.adapters import get_adapter
from scripts.formatter import format_document
from scripts.lint_corpus import lint_file
from scripts.schema import missing_table_lines, validate_document

FIXTURES = Path(__file__).parent / "fixtures"


def _qanoonsa_doc():
    html = (FIXTURES / "qanoonsa_table_in_article.html").read_text(encoding="utf-8")
    return get_adapter("qanoonsa").parse(html, "https://qanoonsa.com/p/999/")


def test_qanoonsa_table_kept_inside_its_article():
    doc = _qanoonsa_doc()
    assert [a.number for a in doc.articles] == ["الأولى", "الثانية"]
    first = doc.articles[0].text
    assert "| عدد أفراد الأسرة | النقاط |" in first
    assert "| --- | --- |" in first
    assert "| فرد واحد | ٥ |" in first
    # خلايا فيها <p> تبقى داخل الجدول لا فقرات مستقلة
    assert "| من اثنين إلى أربعة | ١٠ |" in first
    assert "\n\nمن اثنين إلى أربعة\n\n" not in first
    # الأنبوب داخل خلية يُهرَّب فلا يكسر الأعمدة
    assert "٢٠ \\| حد أقصى" in first
    # ترتيب المتن محفوظ: الجملة الواعدة، ثم الجدول، ثم ما بعده
    assert first.index("الجدول الآتي:") < first.index("| فرد واحد") < first.index("وللوزارة")
    assert "|" not in doc.articles[1].text


def test_qanoonsa_table_document_passes_validation_and_lint(tmp_path):
    doc = _qanoonsa_doc()
    assert not [w for w in validate_document(doc) if "جدول" in w]
    doc.category = "لائحة"
    path = tmp_path / "لائحة" / "x.md"
    path.parent.mkdir()
    path.write_text(format_document(doc), encoding="utf-8")
    errors, _ = lint_file(path, tmp_path)
    assert not errors


def test_nezams_table_kept_inside_its_article():
    html = """
    <html><body><h1>نظام تجريبي</h1><ul>
    <li class="subject"><h4>المادة الأولى</h4><div class="content">
      <p>تكون الرسوم وفق الجدول الآتي:</p>
      <table><tr><th>الخدمة</th><th>الرسم</th></tr>
             <tr><td>إصدار</td><td>١٠٠</td></tr>
             <tr><td>تجديد</td><td>٥٠</td></tr></table>
      <p>وتُحصَّل الرسوم مقدمًا.</p>
    </div></li>
    </ul></body></html>
    """
    doc = get_adapter("nezams").parse(html, "https://nezams.com/x/")
    text = doc.articles[0].text
    # صفوف الجدول متجاورة (لا فقرات فارغة بينها تمزّق جدول Markdown)
    assert "| الخدمة | الرسم |\n| --- | --- |\n| إصدار | ١٠٠ |\n| تجديد | ٥٠ |" in text
    assert text.index("الجدول الآتي:") < text.index("| إصدار") < text.index("وتُحصَّل")
    assert "\x00" not in text


def test_nezams_dropped_item_is_reported():
    html = """
    <html><body><h1>نظام تجريبي</h1><ul>
    <li class="subject"><h4>المادة الأولى</h4><div class="content"><p>نص المادة الأولى كاملًا.</p></div></li>
    <li class="subject"><h4>المادة الثانية</h4><div class="changed-markup"><p>نص ضائع</p></div></li>
    </ul></body></html>
    """
    doc = get_adapter("nezams").parse(html, "https://nezams.com/x/")
    assert doc.dropped_items == 1
    assert any("أُسقط 1 عنصر مادة" in w for w in validate_document(doc))


def test_missing_table_lines_detects_promise_without_table():
    text = "يمنح المتقدم نقاطا وفق الجدول الآتي:\n\nوللوزارة تعديل النقاط."
    assert missing_table_lines(text) == ["يمنح المتقدم نقاطا وفق الجدول الآتي:"]


def test_missing_table_lines_accepts_table_and_attached_schedule():
    with_table = "وفق الجدول الآتي:\n\n| أ | ب |\n| --- | --- |\n| ١ | ٢ |"
    attached = "وفق الجدول المرفق:\n\nوللوزارة تعديله."
    mid_sentence = "وفق الجدول الآتي بيانه في المادة الخامسة."
    assert missing_table_lines(with_table) == []
    assert missing_table_lines(attached) == []
    assert missing_table_lines(mid_sentence) == []


def test_missing_table_at_end_of_document_is_detected():
    assert missing_table_lines("تحدد الغرامات وفق الجداول التالية:\n") != []
