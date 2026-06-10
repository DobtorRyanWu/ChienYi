# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 監造會議記錄',
    'version': '18.0.1.0.0',
    'category': 'Construction',
    'summary': '監造會議記錄管理（Sprint 24 新增；可選 dobtor_doc_editor_chienyi 啟用線上協作）',
    'description': """
監造會議記錄
==============

此模組為 Sprint 24 新增，補上 ChienYi 系統缺的「會議記錄」核心模組。

主要功能
--------
* 會議基本資料（會議名稱 / 日期 / 地點 / 主席 / 紀錄人）
* 出席者管理（res.partner Many2many）
* 工程關聯（supervision.project Many2one，可選）
* mail.thread 整合（chatter / 跟蹤 / 通知）
* 狀態流（草稿 → 確認 → 結案）

整合
----
* 安裝 dobtor_doc_editor_chienyi 後，會議記錄會自動取得「開啟線上文件」按鈕，
  點擊建立 doc.document（從 dobtor_doc_editor.template_meeting_record 樣板複製）
  並把出席者中的 user 自動加為協作者；不裝 dobtor 模組仍可正常使用。
    """,
    'author': 'ChienYi',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/meeting_record_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
