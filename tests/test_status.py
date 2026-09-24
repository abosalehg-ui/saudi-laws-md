import pytest

from scripts.status import AMENDED, IN_FORCE, REPEALED, normalize_status


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ساري", IN_FORCE),
        ("نافذ اعتبارا من 1446", IN_FORCE),
        ("غير ساري؛ ألغي بصدور نظام الشركات", REPEALED),
        ("إلغي هذا النظام بصدور نظام الأسماء التجارية", REPEALED),
        ("ملغي", REPEALED),
        ("معدل", AMENDED),
        # «الغ» داخل كلمة ليست إلغاءً: «البالغ»، «المبالغ»
        ("ساري - البالغ عدده خمس مواد", IN_FORCE),
        ("ساري وتُستحق المبالغ المقررة", IN_FORCE),
    ],
)
def test_normalize_status(raw, expected):
    assert normalize_status(raw)[0] == expected


def test_unknown_status_is_kept_as_note_not_guessed():
    assert normalize_status("لم يدخل حيز النفاذ بعد") == (None, "لم يدخل حيز النفاذ بعد")
