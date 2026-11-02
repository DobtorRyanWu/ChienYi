# -*- coding: utf-8 -*-
"""材料試驗報告（送審函）—— docx 對照表。

樣板原本的主旨整段是特定案件內容：「檢附植筋拉拔測試報告一份，
報告編號：22RT153」，2026-08-05 改成 {{ testName }} / {{ reportNo }}。

公文抬頭原本寫死任泰自己的「負責人」與 email，每一家客戶的送審函都印任泰的人與信箱
（2026-11-02 改）：email 改接案件監造公司（res.company）的 email，沒填就留白；
負責人系統裡沒有對應欄位（res.company 沒有負責人、project_leader_id 是契約變更審核人），
樣板只留「負責人：」讓人手填。地址／電話／傳真本來就是空白，不動。
"""

MODEL = 'supervision.test.record'
MODE = 'docx'


def build_context(record):
    standard = record.standard_id
    return {
        # 試驗名稱：優先用檢試驗項目的名稱，沒有就用記錄本身的名稱
        'testName': (standard.display_name if standard else '') or record.name or '',
        # 報告編號：優先用 construction_test 2.7.0 新增的「試驗報告編號」。舊資料沒有，
        # 退回歸檔編號（那欄實際上多半存簽核紀錄，見 test_record.test_report_no 的說明）
        'reportNo': record.test_report_no or record.archive_number or record.name or '',
        # 發文單位（監造公司）的 email：案件的「管理公司（系統）」
        'supervisorEmail': record.project_id.company_id.email or '',
    }


def FILENAME(record):
    return '材料試驗報告_%s_%s.docx' % (
        record.project_id.name or '', record.archive_number or record.name or record.id)
