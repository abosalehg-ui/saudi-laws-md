from scripts.classify import VALID_TYPES, classify_doc_type


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


def test_all_outputs_are_valid_types():
    samples = [
        "نظام العمل", "اللائحة التنفيذية", "مرسوم ملكي رقم", "أمر ملكي رقم",
        "قرار مجلس", "اتفاقية", "معايير", "شيء غريب",
    ]
    for title in samples:
        assert classify_doc_type(title) in VALID_TYPES
