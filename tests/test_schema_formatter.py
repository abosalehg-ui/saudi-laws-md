from pathlib import Path

from scripts.formatter import (
    UNCATEGORIZED,
    build_note,
    format_document,
    output_path,
    sanitize_filename,
)
from scripts.schema import (
    Article,
    LawDocument,
    sequence_warnings,
    validate_document,
)


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


def test_sanitize_filename_respects_byte_limit_for_arabic():
    # عناوين عربية طويلة (حرفان بالبايت لكل رمز UTF-8) قد تتجاوز حد نظام
    # الملفات (255 بايت غالبًا) رغم عدد أحرف صغير ظاهريًا
    long_title = "ن" * 200
    name = sanitize_filename(long_title)
    assert len(name.encode("utf-8")) <= 200
    assert name  # لا يفرغ الاسم تمامًا


def test_validate_document_flags_noise_empty_and_no_content():
    doc = make_doc()
    doc.articles.append(Article(number="الثالثة", text="", number_int=3))  # فارغة
    doc.articles.append(
        Article(number="الرابعة", text="نص فيه مشاركة المادة", number_int=4)
    )
    warnings = validate_document(doc)
    assert any("بقايا ضجيج واجهة" in w for w in warnings)
    assert any("مواد بلا متن" in w for w in warnings)

    empty_doc = LawDocument(title="فارغ", source="qanoonsa", source_url="")
    assert any("بلا محتوى" in w for w in validate_document(empty_doc))


def test_validate_document_accepts_prose_body():
    doc = LawDocument(
        title="دليل",
        source="qanoonsa",
        source_url="",
        doc_type="معايير",
        body="### قسم\n\nفقرة نظيفة.",
    )
    assert validate_document(doc) == []


def test_prose_body_document_renders_without_articles():
    doc = LawDocument(
        title="معايير الاحتساب",
        source="qanoonsa",
        source_url="https://qanoonsa.com/p/1/",
        doc_type="معايير",
        body="### القسم الأول\n\n| أ | ب |\n| --- | --- |\n| ١ | ٢ |",
    )
    md = format_document(doc)
    assert 'doc_type: "معايير"' in md
    assert "# معايير الاحتساب" in md
    assert "| أ | ب |" in md
    assert "المادة" not in md


def test_decision_document_omits_madda_prefix():
    doc = LawDocument(
        title="قرار مجلس الوزراء رقم (١٦)",
        source="qanoonsa",
        source_url="https://qanoonsa.com/p/516402/",
        is_decision=True,
        issued_date="١ من محرم ١٤٤٨هـ",
        articles=[
            Article(number="أولا", text="الموافقة على النظام."),
            Article(number="ثانيا", text="تشكيل لجنة."),
        ],
    )
    md = format_document(doc)
    assert 'issued_date: "١ من محرم ١٤٤٨هـ"' in md
    assert "## أولا" in md
    assert "## ثانيا" in md
    assert "المادة" not in md
    assert sequence_warnings(doc) == []
