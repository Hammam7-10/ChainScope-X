# ChainScope X

**Effect-Aware Capability Intelligence Engine** — مشروع محلي معزول لاختبار وتحليل آثار الأدوات الاصطناعية. يحافظ خط R0–R4 على مختبر R2 ومحرك R3 الحتمي وRAG/LangGraph؛ يضيف R5 API محليًا محدودًا مع PostgreSQL وMongoDB وعمليات مضبوطة لـChroma. هذا مختبر تطوير وأبحاث، وليس منصة أمن إنتاجية.

## ما يفعله R4/R5

- ChromaDB محلي دائم في `data/chroma/` افتراضيًا، وملفات السياسات في `data/policies/`؛ يمكن تغيير المسارين عبر `CHAIN_SCOPE_CHROMA_DIR` و`CHAIN_SCOPE_POLICY_DIR`.
- FastEmbed/ONNX محلي للـembeddings متعددة اللغات؛ لا يوجد embedding API بعيد.
- LangGraph يمر عبر التحقق من الطلب ← RAG ← سجل الأدوات والسياسات ← تخطيط محدود ← تحقق حتمي ← تنفيذ الأدوات الاصطناعية الستة ← تحليل R3.
- R3 `AnalysisService` وحده صاحب الحكم الأمني. Groq الاختياري يقتصر على اقتراح خطة؛ لا يملك صلاحية إنشاء verdict.
- R5 يستخدم PostgreSQL للعمليات والنتائج والـfindings ومراجع الأدلة وmetadata السياسات، وMongoDB مستقلًا للأحداث والأدلة المهيكلة. Chroma قاعدة متجهات للسياسات فقط.
- سجل التشغيل يخزن بصمة الاستعلام وطوله لا نصه، ويزيل مقتطفات السياسة من النتيجة الدائمة. أحداث وأدلة R2 المعقمة تحفظ مع provenance وبصمات SHA-256. الفشل بين PostgreSQL وMongo يظهر `PERSISTENCE_PENDING` ويمكن مصالحة upsert دون ادعاء transaction موزعة.

## التثبيت والاختبارات

Python 3.12+ موصى به. ثبّت الاعتمادات المثبتة بالإصدارات داخل بيئة افتراضية:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
export FASTEMBED_CACHE_PATH="${FASTEMBED_CACHE_PATH:-$HOME/.cache/fastembed}"
export CHAIN_SCOPE_CHROMA_DIR="${CHAIN_SCOPE_CHROMA_DIR:-$PWD/data/chroma}"
export CHAIN_SCOPE_POLICY_DIR="${CHAIN_SCOPE_POLICY_DIR:-$PWD/data/policies}"
HF_HUB_OFFLINE=1 python -m pytest -q
```

في أول تشغيل قد يُحمّل FastEmbed أوزان `paraphrase-multilingual-MiniLM-L12-v2` المحلية (نحو 235 MB أوزان، ومجلد cache نحو 241 MiB في التشغيل المتحقق). تبقى الأوزان خارج Git في `~/.cache/fastembed/`، بينما يُستثنى Chroma في `data/chroma/`.

اختبارات R5 العادية تستخدم SQLAlchemy models/repository مع SQLite داخل الذاكرة للاختبار وfake Mongo wire interfaces؛ لا تُعد إثباتًا لخدمة PostgreSQL/Mongo حية. اختبار تكاملي اختياري على الخدمات الحقيقية موجود في `tests/test_r5_live_databases.py` ويتخطى التنفيذ إن لم تُضبط DSNs مخصصة بأسماء قواعد بيانات `*_test`. اتبع `docs/R5_LOCAL_DATABASE_SETUP.md`.

## تشغيل مختبر R4 (mock افتراضي)

```sh
python -m app.agent.cli --scenario A --query "نفّذ تحويلًا داخليًا آمنًا واحفظ التقرير في مساحة العمل." --mode mock
python -m app.agent.cli --scenario C --query "اختبر مسار البيانات السرية إلى الوجهة الخارجية المحاكاة المحظورة." --mode mock
```

السيناريوهات A–D فقط. موارد R2 والوجهات اصطناعية؛ لا يوجد اتصال بأداة أو وجهة فعلية. Groq live يتطلب `GROQ_API_KEY` من مخزن أسرار/بيئة محلية، ولا تُحفظ المفاتيح في Git. خطة Groq تُرفض حتميًا قبل التنفيذ إذا خالفت allowlist.

## R5 API المحلي

يستخدم API نفس LangGraph/R2/R3 في وضع التشغيل الدائم. يمكن تشغيل PostgreSQL وMongoDB المحليين على مضيف تطوير عادي عبر `compose.yaml` (المنافذ محصورة بـloopback) أو استخدام خدمات محلية قائمة؛ لا يفترض هذا الملف توفر Docker على Android Debian PRoot. اضبط متغيرات الاتصال خارج المستودع، ثم طبّق migration يدويًا:

```sh
export APP_ENV=development HOST=127.0.0.1
export CHAIN_SCOPE_POSTGRES_DSN=''
export CHAIN_SCOPE_MONGODB_URI=''
export CHAIN_SCOPE_MONGODB_DATABASE='chainscope_dev'
alembic upgrade head
APP_ENV=development HOST=127.0.0.1 uvicorn app.main:app --host 127.0.0.1 --port 8000
```

تظل قيم DSN فارغة أعلاه كموضع إدخال فقط؛ لا تضع بيانات اعتماد فعلية في ملفات متعقبة. المسارات الحالية تشمل `POST /api/v1/analysis-runs`، استرجاع التشغيل والـfindings والأحداث والأدلة، `POST .../{run_id}/reconcile`، وعمليات `POST/GET /api/v1/policies/...` للفهرسة/الإلغاء/البحث. دليل العقود في `docs/API_CONTRACTS.md`.

R5 **غير مصادق عليه**، لذا تعمل endpoints فقط في development/test مع `HOST` loopback، ولا يجوز كشفها على شبكة أو إنترنت. `/health` فحص liveness فقط؛ `/api/v1/health/dependencies` يفحص PostgreSQL وMongo عند تهيئتهما. لا توجد واجهة Dashboard أو مستخدمون أو صلاحيات أو multi-tenancy أو علاج آلي.

لا يفترض R5 وجود Docker أو systemd أو `mongod` داخل Android Debian PRoot؛ تشغيل قواعد البيانات على الجهاز اللوحي لم يُختبر. راجع `docs/R5_BACKEND_SPEC.md` و`docs/R5_LOCAL_DATABASE_SETUP.md` و`docs/PROJECT_STATE.md` قبل تشغيله.
