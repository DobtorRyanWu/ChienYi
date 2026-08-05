# -*- coding: utf-8 -*-
"""材料試驗報告（送審函）—— docx 對照表。

樣板原本的主旨整段是特定案件內容：「檢附植筋拉拔測試報告一份，
報告編號：22RT153」，2026-08-05 改成 {{ testName }} / {{ reportNo }}。

公文抬頭的地址／電話／email／負責人是**任泰自己的公司資料**，不是專案殘料，
保留不動（要改成從公司資料帶入是另一個決定）。
"""

MODEL = 'supervision.test.record'
MODE = 'docx'


def build_context(record):
    standard = record.standard_id
    return {
        # 試驗名稱：優先用檢試驗項目的名稱，沒有就用記錄本身的名稱
        'testName': (standard.display_name if standard else '') or record.name or '',
        # 報告編號：歸檔編號就是報告上的編號
        'reportNo': record.archive_number or record.name or '',
    }


def FILENAME(record):
    return '材料試驗報告_%s_%s.docx' % (
        record.project_id.name or '', record.archive_number or record.name or record.id)
