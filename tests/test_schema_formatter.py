from pathlib import Path

from scripts.formatter import (
    UNCATEGORIZED,
    build_note,
    format_document,
    output_path,
    sanitize_filename,
)
from scripts.schema import Article, LawDocument, sequence_warnings


def make_doc(**overrides):
    doc = LawDocument(
        title="نظام تجريبي",
        source="qanoonsa",
        source_url="https://qanoonsa.com/p/1/",
        articles=[
            Article(number="الأولى", text="نص المادة الأولى.", number_int=1),
            Article(
                number="الثانية",
                text="نص المادة الثانية.",
                number_int=2,
                amendment_history=["تم تعديل هذه المادة بموجب المرسوم الملكي رقم (م/١)."],
            ),
        ],
    )
    for key, value in overrides.items():
        setattr(doc, key, value)
    return doc


def test_full_template():
    doc = make_doc(
        issued_by="قرار مجلس الوزراء رقم (١٦)",
        gazette_ref="نُشر في عدد جريدة أم القرى رقم (٥٠٤١)",
        retrieved_at="2026-07-21",
    )
    expected = (
        "---\n"
        'title: "نظام تجريبي"\n'
        "source: qanoonsa\n"
        'source_url: "https://qanoonsa.com/p/1/"\n'
        'issued_by: "قرار مجلس الوزراء رقم (١٦)"\n'
        'gazette_ref: "نُشر في عدد جريدة أم القرى رقم (٥٠٤١)"\n'
        "retrieved_at: 2026-07-21\n"
        f'note: "{build_note("qanoonsa")}"\n'
        "---\n"
        "\n"
        "# نظام تجريبي\n"
        "\n"
        "## المادة الأولى\n"
        "\n"
        "نص المادة الأولى.\n"
        "\n"
        "## المادة الثانية\n"
        "\n"
        "نص المادة الثانية.\n"
        "\n"
        "> **تعديلات المادة:**\n"
        "> - تم تعديل هذه المادة بموجب المرسوم الملكي رقم (م/١).\n"
    )
    assert format_document(doc) == expected


def test_none_fields_omitted():
    md = format_document(make_doc())
    for key in ("issued_by", "approval_date_hijri", "publish_date", "gazette_ref",
                "status", "category", "attachments", "amendments", "retrieved_at"):
        assert f"\n{key}:" not in md


def test_lists_in_front_matter():
    md = format_document(
        make_doc(attachments=["اللائحة التنفيذية", "لائحة ثانية"], amendments=["تعديل ١"])
    )
    assert 'attachments: ["اللائحة التنفيذية", "لائحة ثانية"]' in md
    assert 'amendments: ["تعديل ١"]' in md


def test_sections_promote_articles_to_h3():
    doc = make_doc()
    doc.articles[0].section = "الباب الأول: التعريفات"
    doc.articles[1].section = "الباب الأول: التعريفات"
    md = format_document(doc)
    assert md.count("## الباب الأول: التعريفات") == 1
    assert "### المادة الأولى" in md
    assert "### المادة الثانية" in md


def test_sequence_warnings():
    doc = make_doc()
    assert sequence_warnings(doc) == []
    doc.articles.append(Article(number="الرابعة", text="نص", number_int=4))
    assert len(sequence_warnings(doc)) == 1
    doc.articles.append(Article(number="مجهولة", text="نص"))
    assert len(sequence_warnings(doc)) == 2


def test_bis_does_not_break_sequence():
    doc = make_doc()
    doc.articles.append(Article(number="الثانية مكرر", text="نص", number_int=2, is_bis=True))
    doc.articles.append(Article(number="الثالثة", text="نص", number_int=3))
    assert sequence_warnings(doc) == []


def test_output_path_and_filename():
    doc = make_doc(category="جرائم")
    assert output_path(doc, Path("laws")) == Path("laws/جرائم/نظام تجريبي.md")
    doc.category = None
    assert output_path(doc, Path("laws")) == Path(f"laws/{UNCATEGORIZED}/نظام تجريبي.md")
    assert sanitize_filename('نظام "الأموال": نسخة/معدلة') == "نظام الأموال نسخة معدلة"
