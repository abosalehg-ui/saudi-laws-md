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


def test_read_field_unescapes_quoted_values():
    """القيمة المقتبسة تعود نصًّا أصليًا — لا نسخة مهرَّبة تتسرّب إلى index.json."""
    text = '---\ntitle: "قرار \\"أ\\" بمسار C:\\\\x"\netag: "\\"abc\\""\nsource: nezams\n---\n'
    assert read_field(text, "title") == 'قرار "أ" بمسار C:\\x'
    assert read_field(text, "etag") == '"abc"'
    assert read_field(text, "source") == "nezams"


def test_read_field_roundtrips_set_field_values():
    for value in ['عنوان "مقتبس"', "ينتهي بشرطة \\", 'W/"etag-1"']:
        text = set_field('---\ntitle: "x"\n---\n', "title", value)
        assert read_field(text, "title") == value


def test_split_and_body_text():
    from scripts.frontmatter import body_text, split

    text = '---\ntitle: "س"\n---\n\n# س\n\nالمتن.\n'
    block, body = split(text)
    assert block == 'title: "س"'
    assert body == "\n# س\n\nالمتن.\n"
    assert body_text(text) == "المتن."
    assert split("بلا front matter") == (None, "بلا front matter")
