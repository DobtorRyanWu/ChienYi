# -*- coding: utf-8 -*-
{
    'name': 'ChienYi × dobtor_doc_editor 整合橋接',
    'version': '18.0.1.0.0',
    'category': 'Construction/Integration',
    'summary': '把 doc.linked.mixin 真實植入 ChienYi 模型（Sprint 21）',
    'description': """
ChienYi × dobtor_doc_editor Bridge
====================================

Sprint 21 P1-2 second leg：讓 ChienYi 模組能透過 dobtor_doc_editor 的
``doc.linked.mixin`` 開啟線上協作文件，補上原規劃唯一剩下的 P 級缺口。

設計原則
--------
* **Bridge 模組**：本身不修改 construction_quality 或 dobtor_doc_editor 任一個原始檔，
  只在 ``_inherit`` 鏈上插入 mixin；兩邊單獨安裝皆不受影響。
* **Pull-on-demand**：用戶在後台點「開啟線上文件」按鈕才建立 doc.document，
  避免一堆空白文件污染 DB。
* **Hook overrides**：依 docs/chienyi_integration_examples.md §3 的模式覆寫
  ``_doc_default_template_xml_id`` / ``_doc_initial_name`` / ``_doc_collaborators``
  / ``_doc_render_context``。

植入範圍
--------
* general.self.inspection — 一般式自主檢查（Sprint 21）
* reservation.self.inspection — 預約式自主檢查（Sprint 22）
* supervision.defect — 缺失改善（Sprint 22）
* payment.estimate — 估驗計價（Sprint 22）
* construction.meeting.record — 監造會議記錄（Sprint 24，搭配 construction_meeting_record 模組）

Sprint 24 後 4 個 dobtor 預設樣板（self_inspection / defect_improvement /
payment_estimate / meeting_record）全部有 host model 引用，引用率達 100%。
    """,
    'author': 'ChienYi × dobtor_doc_editor',
    'license': 'LGPL-3',
    'depends': [
        'dobtor_doc_editor',
        'construction_quality',
        'construction_payment',
        'construction_meeting_record',
        'construction_review',
    ],
    'data': [
        'security/doc_role_bridge.xml',
        'views/general_self_inspection_views.xml',
        'views/reservation_self_inspection_views.xml',
        'views/supervision_defect_views.xml',
        'views/payment_estimate_views.xml',
        'views/meeting_record_views.xml',
        'views/review_application_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
