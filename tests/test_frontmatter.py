from scripts.frontmatter import read_field, set_field


def test_read_field_scoped_to_front_matter_block():
    # سطر في المتن يبدأ بالحقل نفسه يجب ألا يُقرأ كقيمته (M-7)
    text = (
        '---\ntitle: "الحقيقي"\nsource_url: "https://q/1/"\n---\n\n'
        "# الحقيقي\n\nsource_url: هذا سطر في نموذج مقتبس داخل المتن\n"
    )
    assert read_field(text, "source_url") == "https://q/1/"
    assert read_field(text, "title") == "الحقيقي"


def test_read_field_absent_returns_none():
    text = '---\ntitle: "س"\n---\n\n# س\n'
    assert read_field(text, "category") is None


def test_set_then_read_roundtrip():
    text = '---\ntitle: "س"\n---\n\n# س\n\nمتن.\n'
    text = set_field(text, "category", "ت")
    assert read_field(text, "category") == "ت"
    # المتن سليم
    assert text.rstrip().endswith("متن.")
