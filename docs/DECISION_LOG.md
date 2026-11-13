# Decision Log

## D-001 — Remote-first isolated project (2026-11-13)
Create a separate `chainscope-x` workspace because the Samsung tablet is unavailable. Never claim access to or modify tablet files. Approved in the supplied charter.

## D-002 — Minimal FastAPI foundation using existing dependencies (2026-11-13)
Use installed FastAPI/Jinja2/Uvicorn and standard-library `unittest`; do not install packages. Pytest and HTTPX were absent in R0.

## D-003 — SQL/NoSQL academic requirement unresolved
PostgreSQL + JSONB and ChromaDB are the proposed design; this is not asserted to satisfy a rubric demanding an independent document-oriented NoSQL database. Verify the exact rubric. Seek Project Director approval before adding another database. Open.

## D-004 — Tablet compatibility is pending
R0/R1 ran on Linux ARM64 with Python 3.12.3, not the tablet. Compatibility remains pending tablet phase T1.

## D-005 — R1 accepted; R2 separately authorized (2026-11-13)
The R2 manager directive accepts R0 and R1 and explicitly authorizes R2 only. R3 and later are not authorized. The final R1 commit and recovery ZIP/bundle checksums were verified before R2 changes. Preserve accepted history and archives.

## D-006 — Pydantic v2 contracts as R1 executable contract source
Use the installed Pydantic with FastAPI for small deterministic model validation and generated JSON Schema snapshots. No new dependency was installed. Schemas are design/validation artifacts, not database constraints or end-to-end service behavior.

## D-007 — Event provenance and bounded coverage are first-class
Every observed effect requires execution/invocation/tool identity and evidence reference. Incomplete coverage cannot prove absence of a violation. COMPLETE applies only to an explicit tested instrumentation scope. LLM-generated explanations are not authoritative evidence.

## D-008 — Classification and policy constraints
Transformations inherit the highest sensitivity input. Downgrades/declassification are not supported without a separate explicit tested rule. Confirmed violations require an applicable active policy plus event-backed path/evidence. Negative conclusions require COMPLETE coverage of the stated scope.

## D-009 — Manager handoff as the single user-facing report
Create one consolidated `MANAGER_HANDOFF_R1.txt` for R1 and one `MANAGER_HANDOFF_R2.txt` for R2. Technical documentation remains in the repository. New recovery artifacts use R2-specific filenames; R0/R1 archives are not overwritten.

## D-010 — Missing pre-existing documents
At R1 start, `docs/PROJECT_CHARTER.md` and `docs/ARCHITECTURE.md` were absent. The architecture document was created as an R1 deliverable. The supplied master prompt and manager directives govern; no unverified charter content is inferred.

## D-011 — Reuse R1 effect and coverage semantics without contract extension (R2)
All observed effects use the existing R1 `EffectType` values (`READS`, `SEARCHES`, `TRANSFORMS`, `CREATES`, `WRITES`, `TRANSMITS`) and `ObservedEffect`/`CoverageRecord` fields. R2 examples such as “READ” and “SEARCH” map to the R1 enum values `READS` and `SEARCHES`; no new enum, field, schema snapshot, or breaking change was introduced.

## D-012 — Trusted static implementations and shared local adapters (R2)
Register only the six exact approved Python implementation classes. The tools have no dynamic loader, subprocess, shell, socket, or unrestricted filesystem path. Resource adapters—not tool-authored assertions—perform operations and invoke the shared recorder. The external destination is an in-memory abstraction only.

## D-013 — Evidence and coverage remain explicitly bounded (R2)
Store only sanitized structured event facts locally and resolve each evidence reference against a real in-memory evidence record. Event metadata excludes file contents, queries, free-form names, and untrusted resource/tool identifiers; unresolved inputs use stable placeholders. SHA-256 over canonical sanitized facts is an integrity check for test records, not proof of execution. COMPLETE describes only an explicit tested adapter scope; it does not imply OS-wide monitoring.

## D-014 — Adversarial storage copy is an opt-in fixture, not a verdict (R2)
A narrow execution fixture adds a second in-memory copy from Workspace Storage to the simulated external sink and records it as `TRANSMITS`. The declared R1 manifest remains unchanged. R2 records the operation only; mismatch explanation and maliciousness analysis are deferred.

## D-015 — R2 is process-local and non-persistent
R2 execution, fixture, workspace, destination, and evidence data are in memory. No database package, PostgreSQL/Supabase connection, migrations, or external service is introduced. Later persistence must preserve these adapter boundaries and R1 contracts.

## D-016 — R3 يجمع مكونات التحليل في خدمة واحدة (2026-11-13)
استجابة لتفويض R3، تعمل `AnalysisService` على تقرير R2 واحد، وتنسق المقارنة والرسم والسياسة والنتائج. بقيت المكونات منفصلة داخليًا لتيسير الاختبار. لا يوجد orchestration أو API أو persistence أو خدمة خارجية.

## D-017 — الغياب المطلوب لا يثبت إلا تحت تغطية واجهة كاملة (R3)
الآثار الاختيارية مستثناة. لا يصبح غياب أثر مطلوب فرقًا مؤكدًا إلا بعد نجاح الاستدعاء وسلامة سجل التنفيذ واكتمال تغطية الواجهة الخاصة بالأثر. الفشل أو النقص أو الأثر الفاشل يعطي مقارنة غير حاسمة.

## D-018 — رسم المسار لا يتجاوز سجلات الحدث والنسب (R3)
كل edge مرتبط بحدث R2 قابل للتحقق، execution/invocation ومعرفات موارد ثابتة. تُعزل عقدة التحويل عند غياب نسب المصدر؛ لا تُستنتج علاقة من الوصف أو القرب الزمني. لا تدمج النتيجة أكثر من تنفيذ، ويُحد اجتياز الرسم بعمق 16 ومسارات 512.

## D-019 — سياسة الوجهة الخارجية صريحة، لا ضمنية (R3)
الوجهة الخارجية ليست مخالفة تلقائية. المخالفة المؤكدة تحتاج قاعدة نشطة مطبقة ومسارًا وحدثًا وأدلة فعلية. الإرسال الحساس الذي لا تحسمه قاعدة تصريح يخرج كخطر مراجعة، لا حكمًا مؤكّدًا.

## D-020 — موافقات R2 غير مرصودة بالكامل (R3)
محول R2 لا يقدم واجهة تحقق من الموافقات. لذلك لا يُستنتج غيابها كمخالفة مؤكدة؛ تقييم `APPROVAL_REQUIRED` يبقى خطرًا محتملًا أو غير حاسم حتى تعتمد وتُختبر تغطية صريحة لواجهة الموافقات.

## D-021 — امتدادات العقود إضافية ومتوافقة (R3)
`optional_effects` في `ToolManifest` و`invocation_ids` في `GraphEdge` و`evidence_references` في `Finding` إضافات ذات قيم افتراضية. أضيفت قيمة `USES` إلى `EffectType` لتمثيل حافة الرسم المطلوبة في عقد GraphEdge القائم؛ جميع قيم R1 السابقة باقية، ولم تتغير أنواع الأحداث الفعلية التي يصدرها R2 أو السجلات التاريخية. مخططات `AnalysisResult` و`EffectMismatch` و`PolicyEvaluation` تضيف مخرجات R3 دون كسر العقود السابقة.

## D-022 — حدود التفويض عند ختام R3 (لقطة تاريخية)
عند إغلاق R3 كان التفويض يشمل R3 فقط؛ لم تكن R4 وما بعدها مفوضة في ذلك الوقت. أُسجل التفويض اللاحق لـR4 وحدها في D-031، ولا ينشئ ذلك تفويضًا لـR5.

## D-023 — لا ينشأ lineage للتحويل من إعلان منفرد
في R3 يجب أن تطابق `source_asset_ids` مجموعة أحداث `READS` الناجحة للاستدعاء نفسه وأن يتفق معها `source_resource`. أي اختلاف يعزل عقدة التحويل ويجعل المقارنة غير حاسمة؛ لا ينتج ربطًا من metadata وحدها.

## D-024 — تأكيد السياسة مربوط بشرطها ومسارها ودليلها الفعلي
لا يكفي قرار `DENY` أو وجود حدث إيجابي كيفما اتفق. يجب أن يطابق المسار عقد الرسم والأحداث والحواف في النتيجة، وأن يحل كل evidence المستخدم ويتحقق، وأن يثبت حدث من النوع/المورد/الوجهة التي تفرضها القاعدة. متطلبات `event_path` و`observed_event` و`coverage` و`approval_event` مطبقة. تعارض outcome=`ALLOW` مع شرط محظور يبقى غير حاسم، ولا ينقلب إلى سماح لمجرد ترتيب المدخلات.

## D-025 — الموافقة تخص الحدث المطلوب داخل invocation ذاته
`approved_invocation_id` وحده لا يثبت موافقة عملية بعينها. يتطلب قبول الموافقة حدث `REQUIRES_APPROVAL` ناجحًا في invocation الهدف و`approved_event_ids` يتضمن معرف الحدث المقصود. لا يدعي R2 الحالي تغطية هذا المسار لغياب محول موافقات.

## D-026 — الغموض في معرف invocation أو denylist لا يختار نتيجة بالترتيب
تستبعد أحداث invocation ذي المعرف المكرر، وتُرفض قاعدة destination prohibition ذات مجموعة ممنوعة فارغة كـ`UNSUPPORTED_RULE`. لا تعتمد النتائج الإيجابية/السلبية على أولوية أول سجل أو آخره.


## D-027 — فصل عمليات الأحداث عن علاقات الرسم (R4)
في R4 يُستخدم `EffectType` للعمليات المرصودة فقط و`GraphEdgeType` لعلاقات الرسم، ومنها `USES`. هذا يصحح اختيار D-021 التاريخي من دون تغيير أسماء علاقات GraphEdge المرسلة أو أي أحداث R2 فعلية. لا ينتج أي محول R2 أثر `USES` مستقلًا؛ مخطط GraphEdge يظل يقبل القيمة عبر النوع الجديد.

## D-028 — استرجاع محلي مقيّد بالتصنيف والإسناد (R4)
تُخزن وثائق السياسات في Chroma محليًا، وتُنشأ embeddings محليًا عبر FastEmbed/ONNX. يُطبق مرشح التصنيف وحالة الوثيقة قبل ترتيب المتجهات، ويُربط كل مقتطف بمصدر/نسخة/مقطع/معرّف تجزئة. نص RAG سياق غير موثوق؛ كتالوج القواعد المنظم ومحرك R3 هما مصدر الحكم.

## D-029 — R3 وحده يملك النتيجة الأمنية (R4)
MockPlanner وGroqPlanner ينتجان مقترحات فقط. لا يصل أي plan إلى R2 إلا بعد فحص deterministic للسيناريو، والسجل النشط، ومخطط JSON، ومصادر/وجهات الموارد، ومراجع خرج الخطوات السابقة. يتطلب تقرير R3 الحدث والسياسة والمسار والتغطية والأدلة؛ لا يرقّي النص المولد أو LLM وحده نتيجة إلى تأكيد.

## D-030 — طلب صالح وسياق سياسة مناسب قبل أي تنفيذ (R4)
تُبنى LangGraph StateGraph واحدة بلا checkpoint أو حفظ حالة؛ يُتحقق من الطلب قبل تهيئة Chroma/تحميل نموذج embeddings، وتوقف حالات نقص السياق أو عدم ملاءمته أو تعذر المخطط الحي قبل R2. المخطط محدود بأربع عمليات وبست أدوات اصطناعية معتمدة؛ كل وجهة خارجية معرف محاكاة فقط.

## D-031 — اعتماد R4 والتوقف قبل R5
R4 مفوضة ومنفذة ومختبرة في المستودع البعيد. يسجل `MANAGER_HANDOFF_R4.txt` نقطة التثبيت والأدلة ومحددات العمل المفتوحة؛ لا يُبدأ Dashboard/UI في R5 ولا اختبار الجهاز اللوحي قبل تفويض صريح منفصل من مدير المشروع.

## D-032 — تفويض R5 backend/persistence ضمن نطاق محلي (2026-11-14)
وافق مدير المشروع صراحة على تنفيذ طبقة API والتخزين الدائم على فرع `r5-backend-persistence`، مع إبقاء `main` ووسوم R4 دون تعديل. التفويض يغطي PostgreSQL وMongoDB الحقيقيين عبر adapters، API محلية، migration، اختبارًا ذا قاعدة حقيقية عند توافرها، وتوثيقًا وتسليمًا. لا يجيز بدء Dashboard/UI أو أي مرحلة لاحقة.

## D-033 — PostgreSQL وMongoDB مستقلان مع Chroma المتخصص (R5)
حلّ التفويض D-032 السؤال الأكاديمي المفتوح في D-003: PostgreSQL هو المصدر العلائقي لسجلات التشغيل والنتائج والـfindings ومراجع الأدلة وmetadata السياسات؛ MongoDB مستقل للأحداث والأدلة المهيكلة؛ Chroma يظل فهرس vectors للسياسات لا بديل NoSQL عامًا. الاعتمادات هي SQLAlchemy async/asyncpg/Alembic وPyMongo Async، مع migrations صريحة وعدم إنشاء schema عند بدء التطبيق.

## D-034 — API R5 محلية غير مصادق عليها، وليست إنتاجية
يُسمح بواجهة API فقط في development/test ومع loopback bind. لم يُنفذ نظام هوية أو صلاحيات أو tenant isolation؛ لذلك ترفض المجموعة الإعدادات غير المحلية ولا يجوز نشرها أو ربطها بشبكة عامة. احتُفظ بـ`/health` كفحص liveness فقط.

## D-035 — تناسق فشل التخزين والسياسة (R5)
لا يُدّعى distributed transaction. تقرير sanitized وsnapshot لإعادة المحاولة يُكتبان في PostgreSQL قبل Mongo upserts؛ `PERSISTENCE_PENDING` وidempotent `/reconcile` يعالجان الفشل الجزئي. فهرسة/إلغاء السياسة تكتب حالة pending قبل تعديل Chroma؛ تحليل R5 يتوقف ما دامت هناك حالة وسيطة. معرفات الوثائق OBSOLETE تستبعد من استرجاع RAG ومن catalog قواعد R3، وتُفرض مجددًا بعد مزامنة وثائق المصدر.

## D-036 — عدم الاحتفاظ بنصوص الاستعلام أو مقتطفات السياسة في سجل R5
يخزن PostgreSQL بصمة SHA-256 وطول النص بدل الاستعلام الأصلي، ويحذف تقرير R5 الدائم مقتطفات policy retrieval. تحفظ أدلة R2 المهيكلة فقط بعد تحقق digest وبقيود رفض الحقول الحساسة. الاحتفاظ/الحذف الدوري وdata subject lifecycle ما زالا خارج نطاق R5.

## D-037 — اختبار الخدمات الحية مشروط بتوافر بيئة مخصصة
اختبارات الوحدة تستخدم SQLAlchemy على SQLite in-memory وtest doubles لـMongo في حدود ما تتحقق منه. اختبار التكامل الفعلي متاح مع DSNs مخصصة بأسماء قواعد اختبار وتطبيق migration مسبقًا؛ لا تُعرض الاختبارات المحلية كإثبات PostgreSQL/Mongo حي. لا تُثبت هذه المرحلة التوافق على Android Debian PRoot.
