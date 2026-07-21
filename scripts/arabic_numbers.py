"""تحويل الترقيم الترتيبي العربي لأرقام المواد إلى أعداد صحيحة.

يدعم الصيغ المؤنثة المستخدمة مع كلمة "المادة":
"الأولى"، "الحادية عشرة"، "التاسعة والسبعون"، "الحادية عشرة بعد المائة"،
إضافة إلى الأرقام ("٧٩" أو "79") وعلامة "مكرر".
"""

from __future__ import annotations

import re

_DIACRITICS_RE = re.compile(r"[ً-ْٰـ]")
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize(text: str) -> str:
    """إزالة التشكيل والتطويل وتوحيد صور الهمزة على الألف."""
    text = _DIACRITICS_RE.sub("", text)
    return text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")


# المفاتيح بصيغتها المطبَّعة (بعد normalize)
_UNITS = {
    "الاولى": 1,
    "الواحدة": 1,
    "الحادية": 1,
    "الثانية": 2,
    "الثالثة": 3,
    "الرابعة": 4,
    "الخامسة": 5,
    "السادسة": 6,
    "السابعة": 7,
    "الثامنة": 8,
    "التاسعة": 9,
    "العاشرة": 10,
}

_TENS = {
    "العشرون": 20, "العشرين": 20,
    "الثلاثون": 30, "الثلاثين": 30,
    "الاربعون": 40, "الاربعين": 40,
    "الخمسون": 50, "الخمسين": 50,
    "الستون": 60, "الستين": 60,
    "السبعون": 70, "السبعين": 70,
    "الثمانون": 80, "الثمانين": 80,
    "التسعون": 90, "التسعين": 90,
}

_HUNDREDS = {
    "المائة": 100, "المئة": 100,
    "المائتين": 200, "المائتان": 200, "المئتين": 200, "المئتان": 200,
    "الثلاثمائة": 300, "الثلاثمئة": 300,
    "الاربعمائة": 400, "الاربعمئة": 400,
    "الخمسمائة": 500, "الخمسمئة": 500,
}

_BIS_RE = re.compile(r"مكرر(?:ا|ة)?")


def _strip_waw(token: str) -> str:
    if token.startswith("و") and (token[1:] in _UNITS or token[1:] in _TENS):
        return token[1:]
    return token


def _parse_below_hundred(tokens: list[str]) -> int | None:
    tokens = [_strip_waw(t) for t in tokens]
    if len(tokens) == 1:
        t = tokens[0]
        if t in _UNITS:
            return _UNITS[t]
        if t in _TENS:
            return _TENS[t]
        return None
    if len(tokens) == 2:
        first, second = tokens
        if first in _UNITS and second in ("عشرة", "عشر") and _UNITS[first] <= 9:
            return _UNITS[first] + 10
        if first in _UNITS and second in _TENS:
            return _UNITS[first] + _TENS[second]
        return None
    return None


def _is_ordinal_token(token: str) -> bool:
    """هل الكلمة جزء من الترقيم الترتيبي (وحدة/عشرة/عشرات/مئات/بعد/رقم)؟"""
    if re.fullmatch(r"\d+", token):
        return True
    stripped = _strip_waw(token)
    return (
        stripped in _UNITS
        or stripped in _TENS
        or stripped in _HUNDREDS
        or token in ("عشرة", "عشر", "بعد")
    )


def _leading_ordinal_prefix(tokens: list[str]) -> list[str]:
    """أطول بادئة من الكلمات الترتيبية؛ يُسقِط عنوان المادة الملحق بالترقيم.

    بعض اللوائح تدمج عنوان المادة في الترويسة ("المادة الثالثة نطاق سريان
    اللائحة")؛ نأخذ "الثالثة" فقط لاشتقاق الرقم ونتجاهل بقية العنوان.
    """
    prefix: list[str] = []
    for token in tokens:
        if _is_ordinal_token(token):
            prefix.append(token)
        else:
            break
    return prefix


def parse_article_label(label: str) -> tuple[int | None, bool]:
    """تحويل تسمية مادة إلى (رقم تسلسلي، هل هي مكررة).

    يعيد (None, is_bis) إذا تعذّر التحويل.
    """
    raw = normalize(label)
    is_bis = bool(_BIS_RE.search(raw))
    raw = _BIS_RE.sub(" ", raw)
    raw = raw.translate(_ARABIC_DIGITS)
    raw = re.sub(r"[()\[\]:،,.]", " ", raw)
    tokens = raw.split()
    if not tokens:
        return None, is_bis

    # إن تعذّر تحليل التسمية كاملة، جرّب البادئة الترتيبية وحدها (عنوان ملحق)
    prefix = _leading_ordinal_prefix(tokens)
    if prefix and prefix != tokens:
        number, _ = parse_article_label(" ".join(prefix))
        if number is not None:
            return number, is_bis

    if re.fullmatch(r"\d+", tokens[0]):
        return int(tokens[0]), is_bis

    if "بعد" in tokens:
        i = tokens.index("بعد")
        left, right = tokens[:i], tokens[i + 1:]
        if len(right) != 1 or right[0] not in _HUNDREDS:
            return None, is_bis
        base = _HUNDREDS[right[0]]
        if not left:
            return None, is_bis
        small = _parse_below_hundred(left)
        if small is None:
            return None, is_bis
        return base + small, is_bis

    if len(tokens) == 1 and tokens[0] in _HUNDREDS:
        return _HUNDREDS[tokens[0]], is_bis

    return _parse_below_hundred(tokens), is_bis


def _spelling_variants(word: str) -> set[str]:
    # الصيغ المطبَّعة لا تحتوي همزات؛ نضيف الصيغ الإملائية الشائعة بالهمزة
    variants = {word}
    if word.startswith("الا"):
        variants.add("الأ" + word[3:])
    return variants


_ALL_WORDS: set[str] = set()
for _vocab in (_UNITS, _TENS, _HUNDREDS):
    for _w in _vocab:
        _ALL_WORDS |= _spelling_variants(_w)
_ALL_WORDS |= {"عشرة", "عشر", "بعد", "مكرر", "مكررا", "مكرراً"}

_ALL_WORDS_PATTERN = "|".join(sorted(_ALL_WORDS, key=len, reverse=True))
_TOKEN = rf"(?:و?(?:{_ALL_WORDS_PATTERN})|[0-9٠-٩]+)"

# يطابق "المادة <تسمية ترتيبية>" في نص متصل، ويلتقط التسمية كاملة
ARTICLE_LABEL_RE = re.compile(rf"المادة\s+({_TOKEN}(?:\s+{_TOKEN})*)")
