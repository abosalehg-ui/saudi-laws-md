from pathlib import Path

import pytest

from scripts.adapters import detect_source, get_adapter
from scripts.adapters.base import ParseError
from scripts.main import run
from scripts.schema import sequence_warnings

FIXTURES = Path(__file__).parent / "fixtures"

# الـ fixtures نسخ حقيقية (مقتطعة) من الموقعين، جُلبت في 2026-07-21:
# - qanoonsa_sample.html: https://qanoonsa.com/p/516403/ (نظام إدارة الأموال
#   المحجوزة والمصادرة، 15 مادة كاملة) بعد حذف script/style وأمثالها.
# - nezams_sample.html: https://nezams.com/نظام-العمل/ بعد إبقاء المواد 1-5
#   والمادة 79 و79 مكرر فقط من أصل 250.
# - qanoonsa_decision_sample.html: https://qanoonsa.com/p/516402/ (قرار مجلس
#   الوزراء رقم ١٦ الذي أقرّ النظام أعلاه) — صفحة قرار بلا مواد، بنودها
#   أولا/ثانيا/ثالثا فقط.

UI_NOISE = ["مشاركة المادة", "رابط المادة", "النص والرابط", "رقم المادة", "جميع الحقوق"]


def test_detect_source():
    assert detect_source("https://qanoonsa.com/p/516402/") == "qanoonsa"
    assert detect_source("https://nezams.com/نظام-العمل/") == "nezams"
    assert detect_source("https://www.nezams.com/x/") == "nezams"
    assert detect_source("https://example.com/law/") is None


@pytest.fixture
def qanoonsa_doc():
    html = (FIXTURES / "qanoonsa_sample.html").read_text(encoding="utf-8")
    return get_adapter("qanoonsa").parse(html, "https://qanoonsa.com/p/516403/")


@pytest.fixture
def qanoonsa_decision_doc():
    html = (FIXTURES / "qanoonsa_decision_sample.html").read_text(encoding="utf-8")
    return get_adapter("qanoonsa").parse(html, "https://qanoonsa.com/p/516402/")


@pytest.fixture
def nezams_doc():
    html = (FIXTURES / "nezams_sample.html").read_text(encoding="utf-8")
    return get_adapter("nezams").parse(html, "https://nezams.com/نظام-العمل/")


class TestQanoonsa:
    def test_metadata(self, qanoonsa_doc):
        # الـ h1 داخل header.entry-header ويجب التقاطه قبل حذف الأغلفة
        assert qanoonsa_doc.title.startswith("نظام إدارة الأموال المحجوزة")
        assert qanoonsa_doc.issued_by == "قرار مجلس الوزراء رقم (١٦)"
        assert "أم القرى" in qanoonsa_doc.gazette_ref
        assert "٥١٦٤" in qanoonsa_doc.gazette_ref

    def test_articles(self, qanoonsa_doc):
        assert [a.number_int for a in qanoonsa_doc.articles] == list(range(1, 16))
        assert sequence_warnings(qanoonsa_doc) == []
        # المادة الأولى (التعريفات) فقرات متعددة
        assert qanoonsa_doc.articles[0].text.count("\n\n") >= 5
        assert all(a.section is None for a in qanoonsa_doc.articles)
        assert all(not a.amendment_history for a in qanoonsa_doc.articles)

    def test_no_noise(self, qanoonsa_doc):
        last = qanoonsa_doc.articles[-1].text
        assert "أم القرى" not in last  # سطر النشر لا يلتصق بآخر مادة
        for noise in UI_NOISE:
            for art in qanoonsa_doc.articles:
                assert noise not in art.text

    def test_prose_page_becomes_body_not_failure(self):
        # صفحة بلا مواد لكن بمحتوى نصي تُحوَّل إلى body بدل رفعها كفشل
        doc = get_adapter("qanoonsa").parse(
            "<html><h1>عنوان</h1>"
            '<div class="entry-content"><p>فقرة أولى.</p><p>فقرة ثانية.</p></div></html>',
            "",
        )
        assert doc.articles == []
        assert "فقرة أولى." in doc.body
        assert "فقرة ثانية." in doc.body

    def test_truly_empty_page_raises(self):
        with pytest.raises(ParseError):
            get_adapter("qanoonsa").parse(
                '<html><h1>عنوان</h1><div class="entry-content"></div></html>', ""
            )


class TestQanoonsaDecision:
    def test_metadata(self, qanoonsa_decision_doc):
        assert qanoonsa_decision_doc.title.startswith("قرار مجلس الوزراء رقم (١٦)")
        assert qanoonsa_decision_doc.is_decision is True
        assert qanoonsa_decision_doc.issued_date == "١ من محرم ١٤٤٨هـ الموافق: ١٦ من يونيو ٢٠٢٦م"
        assert "أم القرى" in qanoonsa_decision_doc.gazette_ref

    def test_clauses(self, qanoonsa_decision_doc):
        assert [a.number for a in qanoonsa_decision_doc.articles] == ["أولا", "ثانيا", "ثالثا"]
        # لا تسلسل عددي للبنود، فلا تحذيرات رغم عدم وجود number_int
        assert sequence_warnings(qanoonsa_decision_doc) == []

    def test_no_noise(self, qanoonsa_decision_doc):
        for art in qanoonsa_decision_doc.articles:
            assert "رئيس مجلس الوزراء" not in art.text
            assert "صدر في" not in art.text
            assert "أم القرى" not in art.text

    def test_rendered_without_madda_prefix(self, qanoonsa_decision_doc):
        from scripts.formatter import format_document

        content = format_document(qanoonsa_decision_doc)
        assert "## أولا" in content
        assert "## المادة أولا" not in content


class TestNezams:
    def test_details_block(self, nezams_doc):
        assert nezams_doc.title == "نظام العمل"
        assert nezams_doc.approval_date_hijri == "1426/08/23 هـ"
        assert nezams_doc.issued_by == (
            "المرسوم الملكي رقم م/51 بتاريخ 23 / 8 / 1426 هـ"
            "؛ قرار مجلس الوزراء رقم 219 بتاريخ 22 / 8 / 1426 هـ"
        )
        assert nezams_doc.publish_date == "1426/09/25 هـ"
        assert nezams_doc.status == "ساري"
        assert nezams_doc.category == "الأنظمة السعودية – أنظمة العمل والرعاية الاجتماعية"
        assert nezams_doc.attachments == [
            "اللائحة التنفيذية للنظام وملحقاته بموجب القرار الوزاري رقم ١٩٨٢ وتاريخ ١٤٣٧/٠٦/٢٨هـ"
        ]
        assert len(nezams_doc.amendments) == 1
        assert "م/44" in nezams_doc.amendments[0]

    def test_articles_and_bis(self, nezams_doc):
        assert [a.number_int for a in nezams_doc.articles] == [1, 2, 3, 4, 5, 79, 79]
        assert [a.is_bis for a in nezams_doc.articles] == [
            False, False, False, False, False, False, True,
        ]
        assert nezams_doc.articles[-1].number == "التاسعة والسبعين مكرر"
        # الفجوة 5→79 متعمدة في الـ fixture المقتطع، ومكرر 79 يلي أصله بلا تحذير
        assert sequence_warnings(nezams_doc) == [
            "خلل في التسلسل: بعد المادة 5 جاءت المادة 79"
        ]

    def test_amendment_history(self, nezams_doc):
        art3 = nezams_doc.articles[2]
        assert len(art3.amendment_history) == 1
        assert "م/١٣٤" in art3.amendment_history[0]
        assert "تم بموجب" not in art3.text
        # النص الجديد المقتبس بعد جملة التعديل يبقى في المتن
        assert "دون أي تمييز" in art3.text
        art79bis = nezams_doc.articles[-1]
        assert len(art79bis.amendment_history) == 1
        assert "م/44" in art79bis.amendment_history[0]
        assert art79bis.text.startswith("«")

    def test_sections_absent(self, nezams_doc):
        # الموقع لا يعرض الأبواب/الفصول عناصر مستقلة؛ يبقى الحقل فارغًا
        assert all(a.section is None for a in nezams_doc.articles)

    def test_amendment_glued_to_quote_on_same_line(self):
        # في الصفحة الحقيقية ترد أحيانًا جملة التعديل والنص المقتبس الجديد
        # على السطر نفسه بلا فاصل (وجد ذلك فعليًا في المادة ٢٢٩ مكرر من
        # نظام العمل)؛ يجب ألا يبتلع regex التعديل النص المقتبس فيترك المادة
        # بلا متن.
        html = (
            '<html><body><h1>نظام تجريبي</h1>'
            '<ul class="all-subject"><li class="subject">'
            "<h4>المادة الأولى مكرر</h4>"
            '<div class="content"><p>'
            "تم إضافة هذه المادة بموجب المرسوم الملكي رقم (م/44) وتاريخ 1446/2/8هـ "
            "لتكون بالنص الآتي:«يعاقب كل من يخالف هذا النظام»"
            "</p></div></li></ul></body></html>"
        )
        doc = get_adapter("nezams").parse(html, "https://nezams.com/x/")
        art = doc.articles[0]
        assert art.text == "«يعاقب كل من يخالف هذا النظام»"
        assert len(art.amendment_history) == 1
        assert art.amendment_history[0].endswith("لتكون بالنص الآتي:")

    def test_no_noise(self, nezams_doc):
        for art in nezams_doc.articles:
            for noise in UI_NOISE:
                assert noise not in art.text
            assert "حجم الخط" not in art.text
            assert "عدد القراءات" not in art.text

    def test_missing_articles_raises(self):
        with pytest.raises(ParseError):
            get_adapter("nezams").parse("<html><h1>عنوان</h1><p>بدون مواد</p></html>", "")


class TestCli:
    def test_offline_mode_end_to_end(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        code = run([
            "--html", str(FIXTURES / "nezams_sample.html"),
            "--source", "nezams",
            "--url", "https://nezams.com/نظام-العمل/",
            "--out", str(tmp_path / "laws"),
        ])
        assert code == 0
        out_file = (
            tmp_path / "laws"
            / "الأنظمة السعودية – أنظمة العمل والرعاية الاجتماعية"
            / "نظام العمل.md"
        )
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert 'doc_type: "نظام"' in content
        assert "المادة الخامسة" in content
        assert "> **تعديلات المادة:**" in content
        for noise in ("مشاركة المادة", "النص والرابط"):
            assert noise not in content

    def test_done_log_round_trip(self, tmp_path):
        from scripts.main import load_done, log_done

        log = tmp_path / "done.txt"
        assert load_done(log) == set()
        log_done("https://qanoonsa.com/p/1/", log)
        log_done("https://qanoonsa.com/p/2/", log)
        assert load_done(log) == {
            "https://qanoonsa.com/p/1/",
            "https://qanoonsa.com/p/2/",
        }

    def test_failure_logged_not_fatal(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        bad = tmp_path / "bad.html"
        bad.write_text("<html><p>لا شيء هنا</p></html>", encoding="utf-8")
        code = run(["--html", str(bad), "--source", "qanoonsa", "--out", str(tmp_path / "laws")])
        assert code == 1
        log = tmp_path / "logs" / "failed.txt"
        assert log.exists()
        assert "bad.html" in log.read_text(encoding="utf-8")
