# حالة المشروع — ChainScope X

**المرحلة الحالية:** R5 — طبقة التخزين الدائم وواجهة API المحلية
**الحالة:** R0–R4 محفوظة ومقبولة. R5 نُفذت على الفرع المنفصل `r5-backend-persistence` المبني من `main` المطابق لخط R4 (`d54c4f820ccb6fa8b0de1742fa2dfb717893922f`). commit التنفيذ `523da9abe445b79bde2e605a00b57e2e1a5fe060`. اختبارات R5 كاملة محليًا ناجحة؛ بانتظار مراجعة مدير المشروع قبل أي دمج أو مرحلة جديدة.
**آخر تحديث:** 2026-11-14

## الأساس والفروع

المشروع في `/home/ubuntu/chainscope-x` على المستودع الخاص `Hammam7-10/ChainScope-X`. `main` والوسم `r4-checkpoint` محفوظان كما هما؛ لا تعديلات أو دمج لخط الأساس. فرع العمل `r5-backend-persistence` مخصص لتنفيذ R5 فقط. تقرير مدير R5: `MANAGER_HANDOFF_R5.txt`؛ تقرير المرحلة الفني: `docs/PHASE_REPORTS/R5.md`.

## بنية R5

PostgreSQL عبر SQLAlchemy async هو المخزن العلائقي لجلسات التحليل والنتائج والـfindings ومراجع الأدلة وmetadata السياسات؛ يديره migration صريح في `alembic/versions/20261114_01_r5_persistence.py`. MongoDB Async يحفظ أحداث R2 وأدلة R2 المهيكلة ذات provenance بهويات ثابتة وعمليات upsert قابلة لإعادة المحاولة. Chroma يظل فهرس vectors محليًا للسياسات.

أضيفت API تطويرية محلية إلى FastAPI؛ تنفذ R4 workflow نفسه ولا تستبدل R3. `AnalysisService` هو مصدر verdict الوحيد. تزامن الحالة عبر PostgreSQL/Mongo لا يدعي distributed transaction؛ `PERSISTENCE_PENDING` ولقطة retry تسمحان بالمصالحة. تغييرات السياسة تسجل pending قبل تغيير Chroma، وتحجب التشغيل حتى حالة مستقرة. تُستبعد وثائق `OBSOLETE` من retrieval وقواعد R3.

## الخصوصية وحدود الخدمة

لا يُحفظ نص query؛ يخزن digest بطول/بصمة فقط، وتزال مقتطفات سياسة RAG من التقرير الدائم. يُتحقق من بصمة evidence قبل التخزين. أسرار الاتصال لا توجد في `.env.example`، و`.gitignore` يستبعد ملفات `.env` وقواعد Chroma وبيئة `.venv`.

API R5 غير مصادق عليها؛ لا هوية أو أدوار أو multi-tenancy أو Dashboard أو rate limiting. المجموعة محصورة بـ`APP_ENV=development|test` و`HOST` loopback وpeer loopback مباشر، ولا تدعم reverse proxy أو النشر العام. `/health` liveness فقط.

## أدلة التحقق

التشغيل الكامل الأخير: `HF_HUB_OFFLINE=1 .venv/bin/python -m pytest -q` — **98 passed, 1 skipped**. الاختبار الوحيد المتخطى هو اختبار PostgreSQL/Mongo الحي، لأنه لا تتوفر خوادم فعلية أو DSNs لقواعد اختبار مخصصة؛ اختبار التكامل الحقيقي جاهز اختياريًا عبر `tests/test_r5_live_databases.py`. اختبارات local SQL تستخدم SQLite in-memory واختبارات Mongo adapter doubles؛ كما اختُبر مسار LangGraph/R2/R3 الحقيقي في mock.

نجح `python -m compileall -q app tests alembic` و`pip check` بلا تعارض. أُنشئ SQL من migration R5 في وضع Alembic offline فقط دون اتصال بالخدمة. لم يُشغّل PostgreSQL/Mongo server ولم تُثبت حزم نظام. البيئة الحالية ARM64/Linux وPython 3.12.3؛ حزم asyncpg وPyMongo كانت متاحة في بيئة ARM64. توافق الجهاز Samsung Galaxy Tab S7+ / Debian PRoot وPython 3.13.5 لم يُختبر.

## التشغيل

اقرأ `docs/R5_LOCAL_DATABASE_SETUP.md` لإنشاء قواعد تطوير معزولة على مضيف موثوق. المتغيرات التشغيلية هي `CHAIN_SCOPE_POSTGRES_DSN`, `CHAIN_SCOPE_MONGODB_URI`, `CHAIN_SCOPE_MONGODB_DATABASE`; تُطبق migration يدويًا بـ`alembic upgrade head`. شغّل FastAPI فقط على `127.0.0.1`. لا يفترض المشروع Docker أو systemd أو خادم قواعد بيانات داخل Android PRoot.

## بوابة المرحلة

R5 فقط مفوضة، وقد انتهى نطاق الكود والاختبار والتوثيق. سلّم `MANAGER_HANDOFF_R5.txt` إلى مدير المشروع وانتظر اعتمادها. **لا تدمج إلى `main`، ولا تبدأ R6–R11 أو UI/Dashboard أو T1–T3، ولا تنفذ نشرًا، قبل تفويض صريح جديد.**
