+++
document_id = "DOC-INTERNAL-SAFE-001"
version = "1.0"
source = "policy/internal_safe_workflows.md"
language = "ar"
policy_id = "POL-INTERNAL-SAFE-001"
access_classification = "INTERNAL"
document_status = "ACTIVE"
effective_date = "2025-01-01"
+++
# المعالجة الداخلية الآمنة

تُستخدم الأدوات الاصطناعية المعتمدة لمعالجة البيانات العامة والداخلية داخل مساحة العمل الداخلية فقط. يجب أن تبقى الملفات الناتجة في تقارير مساحة العمل، مع الاحتفاظ بمعرّفات المصدر وخط النسب المسجل. استخدام وجهة خارجية لا يُفترض أنه مسموح لمجرد أن الأداة تستطيع الوصول إليها.

# Safe internal processing

Approved synthetic tools may transform PUBLIC or INTERNAL sample data and store the result in the internal reports workspace. Preserve source identifiers and observed lineage. A tool's ability to address a destination does not by itself authorize that destination.
