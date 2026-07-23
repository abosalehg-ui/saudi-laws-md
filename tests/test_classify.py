from scripts.classify import (
    VALID_TYPES,
    classify_doc_type,
    resolve_category,
    simplify_category,
)


def test_law_and_regulation_titles():
    assert classify_doc_type("نظام العمل") == "نظام"
    assert classify_doc_type("تنظيم المؤسسة العامة للري") == "نظام"
    assert classify_doc_type("اللائحة التنفيذية لنظام الجمعيات") == "لائحة"
    assert classify_doc_type("قواعد تنظيم لوحات الدعاية") == "لائحة"
    assert classify_doc_type("دليل تنظيم اعتماد المشاتل") == "لائحة"


def test_decrees_orders_decisions():
    assert classify_doc_type("مرسوم ملكي رقم (م/١٧٠) الموافقة على اتفاقية") == "مرسوم ملكي"
    assert classify_doc_type("أمر ملكي رقم (أ/٢٥٩) تعيين نائب عام") == "أمر ملكي"
    assert classify_doc_type("قرار مجلس الوزراء رقم (٨٩٣)") == "قرار"


def test_decision_after_issuer_prefix():
    # الصيغة الغالبة لعناوين قرارات qanoonsa: "الجهة: قرار رقم (...)"
    assert (
        classify_doc_type("وزارة الطاقة: قرار رقم (٣٩٢٢) نزع ملكية من أجل تعزيز موثوقية الشبكة")
        == "قرار"
    )
    # لا يُطابق عناوين لا تحوي "قرار" بعد نقطتين
    assert classify_doc_type("نظام العمل: أحكام عامة") == "نظام"


def test_agreements_and_standards():
    assert classify_doc_type("اتفاقية عامة للتعاون") == "اتفاقية"
    assert classify_doc_type("معايير احتساب سعر بيع التجزئة المرجعي") == "معايير"
    assert classify_doc_type("جدول تصنيف المخالفات والعقوبات") == "معايير"


def test_update_url_wins_over_title():
    url = "https://nezams.com/تحديثات-الأنظمة/تعديل-المادة-الرابعة/"
    assert classify_doc_type("تعديل المادة الرابعة من نظام العمل", url) == "تعديل"


def test_decision_fallback_and_other():
    # عنوان لا يطابق أي نمط لكن البنية قرار → قرار
    assert classify_doc_type("الموافقة على مشروع", is_decision=True) == "قرار"
    # لا نمط ولا قرار → أخرى
    assert classify_doc_type("إعلان عام للجمهور") == "أخرى"


def test_simplify_category_strips_generic_prefix():
    assert (
        simplify_category("الأنظمة السعودية – أنظمة العمل والرعاية الاجتماعية")
        == "أنظمة العمل والرعاية الاجتماعية"
    )
    assert simplify_category("عمل") == "عمل"
    assert simplify_category(None) is None
    assert simplify_category("") is None
    # التصنيف العام وحده (بلا مجال بعد الشرطة) يُعامل كغياب تصنيف
    assert simplify_category("الأنظمة السعودية") is None


def test_simplify_category_merges_known_aliases():
    # صيغ بديلة (خطأ إملائي/همزة/ترتيب) لنفس تصنيف الموقع المصدر تُوحَّد
    assert simplify_category("أنظمة الزراعة والمياة والثروات الحية") == "أنظمة الزراعة والمياه والثروات الحية"
    assert simplify_category("أنظمة المواصلات والإتصالات") == "أنظمة المواصلات والاتصالات"
    assert (
        simplify_category("الأنظمة السعودية – أنظمة الأمن الداخلي")
        == "أنظمة الأمن الداخلي والأحوال المدنية والأنظمة الجنائية"
    )


def test_resolve_category_falls_back_to_doc_type():
    # لا تصنيف من الصفحة → يُستخدم نوع الوثيقة بدل "غير-مصنف"
    assert resolve_category(None, "لائحة") == "لائحة"
    # تصنيف موجود → يُبسَّط ويُستخدم
    assert resolve_category("الأنظمة السعودية – تجاري", "نظام") == "تجاري"
    # لا تصنيف ونوع "أخرى" → None (يبقى غير-مصنف)
    assert resolve_category(None, "أخرى") is None
    # نوع "نظام" كمجلد يُوحَّد مع "التنظيمات" (قرار المالك: تصنيف واحد)
    assert resolve_category(None, "نظام") == "التنظيمات"
    assert resolve_category("نظام", "نظام") == "التنظيمات"


def test_all_outputs_are_valid_types():
    samples = [
        "نظام العمل", "اللائحة التنفيذية", "مرسوم ملكي رقم", "أمر ملكي رقم",
        "قرار مجلس", "اتفاقية", "معايير", "شيء غريب",
    ]
    for title in samples:
        assert classify_doc_type(title) in VALID_TYPES
