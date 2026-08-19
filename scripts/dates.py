"""تطبيع التواريخ العربية إلى صيغة قابلة للفرز.

المشكلة: حقول التواريخ في المُدوَّنة نصّ بشري بصيغ متعددة وبأرقام مختلطة
(عربية-هندية ولاتينية في نفس الحقل)، فلا يمكن فرزها ولا الاستعلام عنها آليًا:

    issued_date: "٤ من شوال ١٤٤٣هـ الموافق: ٥ من مايو ٢٠٢٢م"
    approval_date_hijri: "1446/03/19هـ"
    status: "… بتاريخ 22 / 6 / 1443 هـ"

الحل المتبع: **لا نمسّ النص البشري** (إعادة كتابة أرقامه إلى اللاتينية تُفسد
قراءة النصّ العربي)، بل نشتقّ منه حقولًا آلية مرافقة بصيغة ISO قابلة للفرز
(``issued_date_hijri`` و``publish_date_gregorian``) تُكتب إلى جانب الأصل.

كل الاشتقاق حتمي ومطابقة نصية بحتة — لا تحويل بين التقويمين (الهجري
والميلادي)، لأن التحويل الحسابي تقريبي وقد يخطئ بيوم أو يومين، وخطأ في
تاريخ نصّ قانوني أسوأ من غياب الحقل.
"""

from __future__ import annotations

import re

ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# نطاق السنوات المقبول: هجريًا 1300–1500، وميلاديًا 1900–2099. خارجه غالبًا
# رقم قرار أو رقم عدد جريدة لا سنة، فيُرفض بدل أن يُكتب تاريخًا خاطئًا.
_HIJRI_YEAR_RANGE = range(1300, 1501)
_GREGORIAN_YEAR_RANGE = range(1900, 2100)

HIJRI_MONTHS: dict[str, int] = {
    "محرم": 1,
    "صفر": 2,
    "ربيع الأول": 3, "ربيع الاول": 3, "ربيع أول": 3,
    "ربيع الآخر": 4, "ربيع الاخر": 4, "ربيع الثاني": 4, "ربيع آخر": 4,
    "جمادى الأولى": 5, "جمادى الاولى": 5, "جمادى الأول": 5,
    "جمادى الآخرة": 6, "جمادى الاخرة": 6, "جمادى الثانية": 6, "جمادى الآخر": 6,
    "رجب": 7,
    "شعبان": 8,
    "رمضان": 9,
    "شوال": 10,
    "ذو القعدة": 11, "ذي القعدة": 11, "ذو قعدة": 11,
    "ذو الحجة": 12, "ذي الحجة": 12, "ذو حجة": 12,
}

GREGORIAN_MONTHS: dict[str, int] = {
    "يناير": 1, "كانون الثاني": 1,
    "فبراير": 2, "شباط": 2,
    "مارس": 3, "آذار": 3, "اذار": 3,
    "أبريل": 4, "ابريل": 4, "نيسان": 4,
    "مايو": 5, "أيار": 5, "ايار": 5,
    "يونيو": 6, "يونية": 6, "حزيران": 6,
    "يوليو": 7, "يولية": 7, "تموز": 7,
    "أغسطس": 8, "اغسطس": 8, "آب": 8,
    "سبتمبر": 9, "أيلول": 9, "ايلول": 9,
    "أكتوبر": 10, "اكتوبر": 10, "تشرين الأول": 10,
    "نوفمبر": 11, "تشرين الثاني": 11,
    "ديسمبر": 12, "كانون الأول": 12,
}

# أسماء الشهور مرتّبة بالأطول أولًا حتى يفوز "ربيع الأول" على "ربيع"
_HIJRI_MONTH_RE = "|".join(sorted(map(re.escape, HIJRI_MONTHS), key=len, reverse=True))
_GREGORIAN_MONTH_RE = "|".join(sorted(map(re.escape, GREGORIAN_MONTHS), key=len, reverse=True))

# «٤ من شوال ١٤٤٣هـ» / «٤ شوال ١٤٤٣ هـ»
_HIJRI_NAMED_RE = re.compile(rf"(\d{{1,2}})\s*(?:من\s+)?({_HIJRI_MONTH_RE})\s+(\d{{4}})")
# «١٤٤٢/٨/١٠هـ» أو «٨ / ٢ / ١٤٤٤هـ» — الترتيب يُحسم من موضع السنة (٤ خانات)
_NUMERIC_DATE_RE = re.compile(r"(\d{1,4})\s*[/\-]\s*(\d{1,2})\s*[/\-]\s*(\d{1,4})")
_GREGORIAN_NAMED_RE = re.compile(rf"(\d{{1,2}})\s*(?:من\s+)?({_GREGORIAN_MONTH_RE})\s+(\d{{4}})")
# «١٤٤٣هـ» وحدها (سنة بلا يوم/شهر)
_HIJRI_YEAR_ONLY_RE = re.compile(r"(\d{4})\s*هـ")

# فاصل «الموافق» يقسم النصّ إلى شطر هجري (قبله) وشطر ميلادي (بعده)
_EQUIV_SPLIT_RE = re.compile(r"الموافق")


def to_latin_digits(text: str) -> str:
    """يحوّل الأرقام العربية-الهندية إلى لاتينية (بلا مسّ بقية النصّ)."""
    return text.translate(ARABIC_INDIC_DIGITS)


def _iso(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}"


def _valid(year: int, month: int, day: int, years: range) -> bool:
    return year in years and 1 <= month <= 12 and 1 <= day <= 31


def _hijri_part(text: str) -> str:
    """الشطر الهجري: ما قبل «الموافق» إن وُجدت، وإلا النصّ كله."""
    return _EQUIV_SPLIT_RE.split(text, maxsplit=1)[0]


def _gregorian_part(text: str) -> str:
    """الشطر الميلادي: ما بعد «الموافق» إن وُجدت، وإلا النصّ كله."""
    parts = _EQUIV_SPLIT_RE.split(text, maxsplit=1)
    return parts[1] if len(parts) > 1 else text


def _from_numeric(text: str, years: range) -> str | None:
    """يقرأ «س/ش/ي» أو «ي/ش/س» — يُحسم الترتيب من الطرف الذي يقع في نطاق السنة."""
    for a, m, b in _NUMERIC_DATE_RE.findall(text):
        first, month, last = int(a), int(m), int(b)
        if _valid(first, month, last, years):     # سنة/شهر/يوم
            return _iso(first, month, last)
        if _valid(last, month, first, years):     # يوم/شهر/سنة
            return _iso(last, month, first)
    return None


def parse_hijri(text: str | None) -> str | None:
    """يستخرج تاريخًا هجريًا بصيغة ``YYYY-MM-DD`` من نصّ عربي حرّ.

    يعيد None إن لم يُعثر على تاريخ هجري كامل موثوق. السنة وحدها لا تكفي
    (لا نخترع يومًا وشهرًا) — لذلك ``hijri_year`` دالة منفصلة.
    """
    if not text:
        return None
    body = to_latin_digits(_hijri_part(text))
    m = _HIJRI_NAMED_RE.search(body)
    if m:
        day, month_name, year = int(m.group(1)), m.group(2), int(m.group(3))
        month = HIJRI_MONTHS[month_name]
        if _valid(year, month, day, _HIJRI_YEAR_RANGE):
            return _iso(year, month, day)
    return _from_numeric(body, _HIJRI_YEAR_RANGE)


def parse_gregorian(text: str | None) -> str | None:
    """يستخرج تاريخًا ميلاديًا بصيغة ``YYYY-MM-DD`` من نصّ عربي حرّ."""
    if not text:
        return None
    body = to_latin_digits(_gregorian_part(text))
    m = _GREGORIAN_NAMED_RE.search(body)
    if m:
        day, month_name, year = int(m.group(1)), m.group(2), int(m.group(3))
        month = GREGORIAN_MONTHS[month_name]
        if _valid(year, month, day, _GREGORIAN_YEAR_RANGE):
            return _iso(year, month, day)
    return _from_numeric(body, _GREGORIAN_YEAR_RANGE)


def hijri_year(*texts: str | None) -> str | None:
    """أول سنة هجرية معقولة في أي من النصوص الممرَّرة (بالترتيب).

    أوسع من ``parse_hijri``: يكفيها «١٤٤٣هـ» بلا يوم ولا شهر، لأن الغرض
    تقسيم المجلدات لا تأريخ الوثيقة.
    """
    for text in texts:
        if not text:
            continue
        body = to_latin_digits(_hijri_part(text))
        full = parse_hijri(text)
        if full:
            return full[:4]
        for candidate in _HIJRI_YEAR_ONLY_RE.findall(body):
            if int(candidate) in _HIJRI_YEAR_RANGE:
                return candidate
    return None
