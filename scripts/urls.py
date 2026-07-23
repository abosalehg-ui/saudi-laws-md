"""تطبيع هوية الروابط: صيغة قانونية واحدة تُستخدم في كل نقاط الدخول.

المشكلة: نفس الوثيقة قد يرد رابطها مُرمَّزًا (``%d9%86…``) أو غير مُرمَّز
(عربي مقروء) حسب خريطة الموقع ودفعة الاستيراد. بلا تطبيع تنقسم كل آليات
الهوية (``--resume``، الجلب الشرطي، كشف التكرار، حقل ``also_available_from``)
على نفس الوثيقة، فيُعاد استيرادها كنُسخ ويُفقد ETag المحفوظ.

الصيغة القانونية المعتمدة: فكّ ترميز المسار (الصيغة المقروءة، وهي الأغلبية
في المستودع)، تصغير المضيف، توحيد المخطّط، وإسقاط المقطع (fragment). لا
تُلمس الشرطة الأخيرة (قد تكون ذات دلالة على الخادم عند إعادة الجلب).
"""

from __future__ import annotations

from urllib.parse import unquote, urlsplit, urlunsplit


def canonical_url(url: str) -> str:
    """يعيد الصيغة القانونية لرابط لأغراض الهوية والتخزين. عملية idempotent."""
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    host = (parts.hostname or "").lower()
    if parts.port:
        host = f"{host}:{parts.port}"
    path = unquote(parts.path)
    return urlunsplit((scheme, host, path, parts.query, ""))
