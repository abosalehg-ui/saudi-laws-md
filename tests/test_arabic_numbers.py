import pytest

from scripts.arabic_numbers import ARTICLE_LABEL_RE, parse_article_label


@pytest.mark.parametrize(
    "label, expected",
    [
        ("الأولى", 1),
        ("الثانية", 2),
        ("التاسعة", 9),
        ("العاشرة", 10),
        ("الحادية عشرة", 11),
        ("الثانية عشرة", 12),
        ("التاسعة عشرة", 19),
        ("العشرون", 20),
        ("الحادية والعشرون", 21),
        ("الخامسة والثلاثون", 35),
        ("التاسعة والسبعون", 79),
        ("التسعون", 90),
        ("التاسعة والتسعون", 99),
        ("المائة", 100),
        ("الأولى بعد المائة", 101),
        ("الحادية عشرة بعد المائة", 111),
        ("الخامسة والعشرون بعد المائتين", 225),
        ("٧٩", 79),
        ("245", 245),
    ],
)
def test_ordinals(label, expected):
    number, is_bis = parse_article_label(label)
    assert number == expected
    assert is_bis is False


@pytest.mark.parametrize(
    "label, expected",
    [
        ("٧٩ مكرر", 79),
        ("التاسعة والسبعون مكرر", 79),
        ("الثالثة مكرر", 3),
    ],
)
def test_bis(label, expected):
    number, is_bis = parse_article_label(label)
    assert number == expected
    assert is_bis is True


def test_unparseable():
    number, is_bis = parse_article_label("غير معروف")
    assert number is None
    assert is_bis is False


@pytest.mark.parametrize("label,expected", [
    ("الثالثة نطاق سريان اللائحة", 3),
    ("الحادية عشرة سجل المرخص لهم", 11),
    ("العشرون الإعفاء", 20),
    ("الحادية والعشرون قواعد التراخيص", 21),
])
def test_ordinal_with_embedded_subtitle(label, expected):
    # لوائح تدمج عنوان المادة في الترويسة؛ نشتق الرقم من البادئة الترتيبية
    number, is_bis = parse_article_label(label)
    assert number == expected
    assert is_bis is False


def test_subtitle_that_is_not_ordinal_still_none():
    # عنوان لا يبدأ بترقيم ترتيبي يبقى غير قابل للتحويل
    assert parse_article_label("نطاق سريان اللائحة") == (None, False)


def test_label_regex_in_running_text():
    text = (
        "المادة الحادية عشرة بعد المائة : نص المادة هنا. "
        "المادة ٧٩ مكرر : نص آخر."
    )
    labels = [m.group(1) for m in ARTICLE_LABEL_RE.finditer(text)]
    assert labels == ["الحادية عشرة بعد المائة", "٧٩ مكرر"]


def test_label_regex_stops_at_article_text():
    m = ARTICLE_LABEL_RE.search("المادة الثانية يقصد بالألفاظ الآتية")
    assert m.group(1) == "الثانية"
