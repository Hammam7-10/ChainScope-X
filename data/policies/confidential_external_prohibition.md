+++
document_id = "DOC-CONFIDENTIAL-EXTERNAL-001"
version = "1.0"
source = "policy/confidential_external_prohibition.md"
language = "en"
policy_id = "POL-CONFIDENTIAL-SHARE-001"
access_classification = "INTERNAL"
document_status = "ACTIVE"
effective_date = "2025-01-01"
policy_rule_json = '''
{"rule_id":"POL-CONFIDENTIAL-SHARE-001","version":"1.0","kind":"PROHIBIT_DESTINATION","scope":{"tool_ids":["file-sharing"],"destination_ids":["destination:external:simulated"],"classifications":["CONFIDENTIAL"]},"conditions":{"prohibited_destinations":["destination:external:simulated"]},"outcome":"DENY","effective_from":"2025-01-01T00:00:00+00:00","effective_to":null,"evidence_requirements":["event_path","observed_event","coverage"],"active":true}
'''
+++
# Confidential sharing restriction

CONFIDENTIAL synthetic files must not be sent by the File Sharing tool to the simulated external destination. A violation can be confirmed only when the actual successful transmission is connected to the confidential source by recorded graph edges and resolvable evidence, the active rule applies, and monitoring coverage is complete.

# قيد مشاركة البيانات السرية

يُمنع إرسال الملفات الاصطناعية المصنفة CONFIDENTIAL بواسطة أداة مشاركة الملفات إلى الوجهة الخارجية المحاكاة. لا تُثبت المخالفة إلا إذا رُبط حدث الإرسال الناجح بالمصدر السري عبر حواف وأدلة فعلية، وكانت القاعدة النشطة منطبقة والتغطية كاملة.
