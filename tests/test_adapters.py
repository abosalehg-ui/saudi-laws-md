from pathlib import Path

import pytest

from scripts.adapters import detect_source, get_adapter
from scripts.adapters.base import ParseError
from scripts.main import run
from scripts.schema import sequence_warnings

FIXTURES = Path(__file__).parent / "fixtures"

UI_NOISE = ["مشاركة المادة", "رابط المادة", "النص والرابط", "الرئيسية", "جميع الحقوق"]


def test_detect_source():
    assert detect_source("https://qanoonsa.com/p/516402/") == "qanoonsa"
    assert detect_source("https://nezams.com/نظام-العمل/") == "nezams"
    assert detect_source("https://www.nezams.com/x/") == "nezams"
    assert detect_source("https://example.com/law/") is None


@pytest.fixture
def qanoonsa_doc():
    html = (FIXTURES / "qanoonsa_sample.html").read_text(encoding="utf-8")
    return get_adapter("qanoonsa").parse(html, "https://qanoonsa.com/p/516402/")


@pytest.fixture
def nezams_doc():
    html = (FIXTURES / "nezams_sample.html").read_text(encoding="utf-8")
    return get_adapter("nezams").parse(html, "https://nezams.com/نظام-العمل/")


class TestQanoonsa:
    def test_metadata(self, qanoonsa_doc):
        assert qanoonsa_doc.title.startswith("نظام إدارة الأموال المحجوزة")
        assert qanoonsa_doc.issued_by == "قرار مجلس الوزراء رقم (١٦) وتاريخ ٦/١/١٤٤٦هـ"
        assert "أم القرى" in qanoonsa_doc.gazette_ref
        assert "٥٠٤١" in qanoonsa_doc.gazette_ref

    def test_articles(self, qanoonsa_doc):
        assert [a.number_int for a in qanoonsa_doc.articles] == [1, 2, 3, 4]
        assert sequence_warnings(qanoonsa_doc) == []
        assert qanoonsa_doc.articles[0].text.count("\n\n") == 1  # فقرتان
        assert all(a.section is None for a in qanoonsa_doc.articles)
        assert all(not a.amendment_history for a in qanoonsa_doc.articles)

    def test_no_noise(self, qanoonsa_doc):
        last = qanoonsa_doc.articles[-1].text
        assert "أم القرى" not in last  # سطر النشر لا يلتصق بآخر مادة
        for noise in UI_NOISE:
            for art in qanoonsa_doc.articles:
                assert noise not in art.text

    def test_missing_articles_raises(self):
        with pytest.raises(ParseError):
            get_adapter("qanoonsa").parse("<html><h1>عنوان</h1><p>بدون مواد</p></html>", "")


class TestNezams:
    def test_details_block(self, nezams_doc):
        assert nezams_doc.title == "نظام العمل"
        assert nezams_doc.approval_date_hijri == "٢٣/٨/١٤٢٦هـ"
        assert nezams_doc.issued_by == "مرسوم ملكي رقم (م/٥١) وتاريخ ٢٣/٨/١٤٢٦هـ"
        assert nezams_doc.publish_date == "٢٥/٩/١٤٢٦هـ"
        assert nezams_doc.status == "نافذ"
        assert nezams_doc.category == "عمل"
        assert nezams_doc.attachments == [
            "اللائحة التنفيذية لنظام العمل",
            "لائحة عمال الخدمة المنزلية ومن في حكمهم",
        ]
        assert len(nezams_doc.amendments) == 2
        assert "م/٤٦" in nezams_doc.amendments[0]

    def test_articles_and_bis(self, nezams_doc):
        assert [a.number_int for a in nezams_doc.articles] == [1, 2, 3, 3, 4, 5]
        assert [a.is_bis for a in nezams_doc.articles] == [
            False, False, False, True, False, False,
        ]
        assert nezams_doc.articles[3].number == "الثالثة مكرر"
        assert sequence_warnings(nezams_doc) == []

    def test_amendment_history(self, nezams_doc):
        art2 = nezams_doc.articles[1]
        assert len(art2.amendment_history) == 1
        assert "م/٤٦" in art2.amendment_history[0]
        assert "تم تعديل" not in art2.text
        art3bis = nezams_doc.articles[3]
        assert len(art3bis.amendment_history) == 1
        assert "م/١٣٤" in art3bis.amendment_history[0]

    def test_sections(self, nezams_doc):
        arts = nezams_doc.articles
        assert arts[0].section == "الباب الأول: التعريفات والأحكام العامة — الفصل الأول: التعريفات"
        assert arts[1].section == arts[0].section
        assert arts[2].section == "الباب الأول: التعريفات والأحكام العامة — الفصل الثاني: الأحكام العامة"
        assert arts[4].section == "الباب الثاني: تنظيم عمليات التوظيف"
        assert arts[5].section == arts[4].section

    def test_no_noise(self, nezams_doc):
        for art in nezams_doc.articles:
            for noise in UI_NOISE:
                assert noise not in art.text
            assert "١ ٢ ٣" not in art.text
        # تفريغ الأرقام لا يظهر في أي حقل
        assert "١٠ ١١ ١٢" not in str(nezams_doc)

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
        out_file = tmp_path / "laws" / "عمل" / "نظام العمل.md"
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "### المادة الخامسة" in content
        assert "> **تعديلات المادة:**" in content
        for noise in ("مشاركة المادة", "النص والرابط"):
            assert noise not in content

    def test_failure_logged_not_fatal(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        bad = tmp_path / "bad.html"
        bad.write_text("<html><p>لا شيء هنا</p></html>", encoding="utf-8")
        code = run(["--html", str(bad), "--source", "qanoonsa", "--out", str(tmp_path / "laws")])
        assert code == 1
        log = tmp_path / "logs" / "failed.txt"
        assert log.exists()
        assert "bad.html" in log.read_text(encoding="utf-8")
