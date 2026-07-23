from scripts.lint_corpus import lint_file, run
from scripts.schema import (
    Article,
    LawDocument,
    clause_sequence_warnings,
    validate_document,
)

GOOD = (
    '---\ntitle: "نظام تجريبي"\nsource_url: "https://qanoonsa.com/p/1/"\n'
    'doc_type: "نظام"\ncategory: "ت"\n---\n\n# نظام تجريبي\n\n## المادة الأولى\n\nنص.\n'
)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_clean_file_has_no_errors(tmp_path):
    p = _write(tmp_path / "ت" / "نظام تجريبي.md", GOOD)
    errors, _ = lint_file(p, tmp_path)
    assert errors == []


def test_missing_required_field_is_error(tmp_path):
    p = _write(tmp_path / "ت" / "x.md", '---\ntitle: "س"\n---\n\n# س\n\nنص.\n')
    errors, _ = lint_file(p, tmp_path)
    assert any("source_url" in e for e in errors)


def test_broken_title_is_error(tmp_path):
    p = _write(
        tmp_path / "ت" / "b.md",
        '---\ntitle: "#REF!"\nsource_url: "https://q/1/"\n---\n\n# #REF!\n\nx.\n',
    )
    errors, _ = lint_file(p, tmp_path)
    assert any("عنوان معطوب" in e for e in errors)


def test_ui_noise_in_body_is_error(tmp_path):
    p = _write(
        tmp_path / "ت" / "n.md",
        '---\ntitle: "س"\nsource_url: "https://q/1/"\n---\n\n# س\n\nحجم الخط كبير.\n',
    )
    errors, _ = lint_file(p, tmp_path)
    assert any("ضجيج" in e for e in errors)


def test_legit_legal_text_not_flagged_as_noise(tmp_path):
    # "جميع الحقوق" و"رقم المادة" نص قانوني مشروع لا ضجيج (regression)
    body = "يعطي عماله جميع الحقوق والمزايا. ويُشار إلى رقم المادة السابقة."
    p = _write(
        tmp_path / "ت" / "L.md",
        f'---\ntitle: "س"\nsource_url: "https://q/1/"\n---\n\n# س\n\n{body}\n',
    )
    errors, _ = lint_file(p, tmp_path)
    assert errors == []


def test_duplicate_consecutive_paragraph_is_error(tmp_path):
    dup = "هذه فقرة قانونية طويلة بما يكفي لتجاوز الحد الأدنى للطول."
    p = _write(
        tmp_path / "ت" / "d.md",
        f'---\ntitle: "س"\nsource_url: "https://q/1/"\n---\n\n# س\n\n{dup}\n\n{dup}\n',
    )
    errors, _ = lint_file(p, tmp_path)
    assert any("مكرّرة" in e for e in errors)


def test_run_returns_zero_on_clean_tree(tmp_path):
    _write(tmp_path / "ت" / "نظام تجريبي.md", GOOD)
    assert run([str(tmp_path)]) == 0


def test_clause_sequence_warns_on_missing_first_clause():
    doc = LawDocument(title="قرار", source="qanoonsa", source_url="https://q/1/", is_decision=True)
    doc.articles = [Article(number="ثانيا", text="نص")]
    warnings = clause_sequence_warnings(doc)
    assert any("بلا ما قبله" in w for w in warnings)


def test_clause_sequence_ok_when_ordered():
    doc = LawDocument(title="قرار", source="qanoonsa", source_url="https://q/1/", is_decision=True)
    doc.articles = [Article(number="أولا", text="a"), Article(number="ثانيا", text="b")]
    assert clause_sequence_warnings(doc) == []
    # ومتكامل مع validate_document
    assert not any("تسلسل البنود" in w for w in validate_document(doc))
