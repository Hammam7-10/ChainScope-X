# ChainScope X

**Effect-Aware Capability Intelligence Engine** — مشروع محلي معزول لاختبار وتحليل آثار الأدوات الاصطناعية. حالة المستودع هي R4: R0–R3 محفوظة، وR4 تضيف استرجاع سياسات محليًا، وسير LangGraph واحد، وربط سجلات R2 بمحرك R3 الحتمي. هذا مختبر تطوير واختبار، وليس منصة أمن إنتاجية.

## نطاق R4

- ChromaDB محلي دائم في `data/chroma/` افتراضيًا، مع إمكانية تغييره عبر `CHAIN_SCOPE_CHROMA_DIR`.
- ملفات سياسات Markdown/TXT ذات TOML front matter في `data/policies/`، قابلة للتغيير عبر `CHAIN_SCOPE_POLICY_DIR`.
- تمثيلات embedding حقيقية محلية عبر FastEmbed/ONNX؛ لا يوجد embedding API بعيد.
- StateGraph أساسي واحد: التحقق من الطلب ← استرجاع RAG ← فحص سجل الأدوات والسياسات ← تخطيط محدود ← تحقق حتمي ← تنفيذ أدوات R2 الست المسموحة ← تحليل R3 ← تقرير منظم.
- خطة الأداة وحدها يمكن أن تأتي من Groq في live mode. R2 هو مصدر الأحداث والأدلة الفعلية، و`AnalysisService` في R3 هو مصدر القرار الأمني النهائي. لا تستطيع نتائج LLM استبدال تحليل R3.
- يخزن Chroma معرفة السياسات عبر إعادة تشغيل العملية؛ أما حالة تشغيل LangGraph وسجلات المختبر والأدلة فتبقى مؤقتة داخل العملية. لا توجد PostgreSQL أو Supabase أو واجهات أعمال إنتاجية أو معالجة علاجية آلية.

## التثبيت والتشغيل

Python 3.12+ موصى به. ثبّت اعتمادات التشغيل والاختبار المثبتة بالإصدارات داخل بيئة افتراضية:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
export FASTEMBED_CACHE_PATH="${FASTEMBED_CACHE_PATH:-$HOME/.cache/fastembed}"
export CHAIN_SCOPE_CHROMA_DIR="${CHAIN_SCOPE_CHROMA_DIR:-$PWD/data/chroma}"
export CHAIN_SCOPE_POLICY_DIR="${CHAIN_SCOPE_POLICY_DIR:-$PWD/data/policies}"
python -m pytest -q
```

في أول تشغيل قد يُحمّل FastEmbed أوزان `paraphrase-multilingual-MiniLM-L12-v2` المحلية (ملف الأوزان الفعلي نحو 235 MB، ومجلد cache نحو 241 MiB في التشغيل المتحقق). تُحفظ الملفات افتراضيًا خارج المستودع تحت `~/.cache/fastembed/`، ويمكن تبديل المسار بمتغير البيئة. يستخدم النموذج vectors حقيقية لاستعلامات عربية وإنجليزية؛ جودة الترتيب العملي تُراجع ضمن اختبارات R4.

لتنفيذ حالة مختبر اصطناعية حقيقية عبر LangGraph (الوضع الافتراضي deterministic/mock):

```sh
python -m app.agent.cli --scenario A --query "نفّذ تحويلًا داخليًا آمنًا واحفظ التقرير في مساحة العمل." --mode mock
python -m app.agent.cli --scenario C --query "اختبر مسار البيانات السرية إلى الوجهة الخارجية المحاكاة المحظورة." --mode mock
```

السيناريوهات المتاحة هي A–D فقط. لا ينفّذ المختبر شبكات حقيقية أو وجهات خارجية فعلية. تستعمل السيناريوهات موارد ثابتة اصطناعية في adapters R2، ومرجع `$ref` لاختيار خرج أداة سابقة معتمدة. المخرجات JSON تتضمن سياق الاسترجاع ومصادره، وسجلات التنفيذ الفعلية، والتغطية، وتحليل R3 دون إعادة صياغة نتيجته.

## وضع Groq الحي

يستخدم `--mode live` محول Groq مرة واحدة لاقتراح خطة JSON فقط. معرف النموذج الافتراضي القابل للتغيير هو `openai/gpt-oss-20b` عبر `GROQ_MODEL_ID`. يجب إتاحة `GROQ_API_KEY` من مخزن أسرار أو متغير بيئة محلي؛ لا تضع المفتاح في Git أو ملف إعداد متعقب. يرفض validator الخطة قبل التنفيذ إذا خالفت allowlist. الوضع mock لا يستخدم مفتاحًا ولا يمثل تحققًا من تكامل LLM حي. لم يُضبط Groq secret في بيئة التحقق الحالية، لذلك تكامل الاستدلال الحي **غير متحقق**.

## تشغيل واجهة R0

واجهة FastAPI الأصلية محفوظة ويمكن تشغيلها منفصلة:

```sh
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

افتح `http://127.0.0.1:8000/`، وتتوفر الصحة عبر `/health`. هذا ليس API أعمال R4 ولا يعرّض LangGraph للعامة.

## الاستعادة وحالة المشروع

راجع `docs/PROJECT_STATE.md` و`docs/IMPLEMENTATION_PLAN.md` و`docs/RAG_SPEC.md` و`docs/AGENT_WORKFLOW_SPEC.md` و`docs/RESTORE_GUIDE.md`. لا يحتوي Git على قاعدة Chroma أو cache النموذج. تعاد فهرسة وثائق السياسات المحلية عند إنشاء workflow؛ السجلات التنفيذية والأدلة في R2 غير دائمة.
