from bs4 import BeautifulSoup

from scripts.htmlmd import prose_to_markdown, table_to_markdown


def _soup(html):
    return BeautifulSoup(html, "lxml")


def test_table_to_markdown_basic():
    table = _soup(
        "<table><tr><th>أ</th><th>ب</th></tr>"
        "<tr><td>١</td><td>٢</td></tr></table>"
    ).find("table")
    md = table_to_markdown(table)
    assert md.splitlines() == ["| أ | ب |", "| --- | --- |", "| ١ | ٢ |"]


def test_table_escapes_pipe_and_pads_ragged_rows():
    table = _soup(
        "<table><tr><th>ع</th><th>ق</th></tr>"
        "<tr><td>a|b</td></tr></table>"
    ).find("table")
    md = table_to_markdown(table)
    assert "a\\|b" in md
    # الصف الناقص يُكمَّل بخلية فارغة ليطابق عرض الترويسة
    assert md.splitlines()[-1] == "| a\\|b |  |"


def test_prose_skips_given_lines_and_renders_headings():
    content = _soup(
        '<div><p>English</p><h3>عنوان فرعي</h3>'
        "<p>فقرة مهمة.</p><li>عنصر قائمة</li></div>"
    ).find("div")
    md = prose_to_markdown(content, skip=frozenset({"English"}))
    assert "English" not in md
    assert "### عنوان فرعي" in md
    assert "فقرة مهمة." in md
    assert "- عنصر قائمة" in md


def test_prose_does_not_duplicate_paragraphs_nested_in_tables():
    # فقرات داخل خلايا الجدول يجب أن تظهر مرة واحدة (ضمن الجدول) لا مرتين
    content = _soup(
        "<div><table><tr><th>#</th><th>ن</th></tr>"
        "<tr><td>١</td><td><p>نص داخل الخلية</p></td></tr></table></div>"
    ).find("div")
    md = prose_to_markdown(content)
    assert md.count("نص داخل الخلية") == 1


def test_prose_does_not_duplicate_paragraphs_nested_in_li_or_blockquote():
    # p داخل li/blockquote يُلتقط نصه ضمن حاويه؛ يجب ألا يتكرر (M-4)
    content = _soup(
        "<div><ul><li><p>بند داخل قائمة</p></li></ul>"
        "<blockquote><p>نص مقتبس</p></blockquote></div>"
    ).find("div")
    md = prose_to_markdown(content)
    assert md.count("بند داخل قائمة") == 1
    assert md.count("نص مقتبس") == 1
