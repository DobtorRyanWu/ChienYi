# -*- coding: utf-8 -*-
"""預設範本的「說明」改成使用者看得懂的字（拿掉 doc.linked.mixin 等內部名稱）。

data/doc_template_data.xml 在 <data noupdate="1"> 裡，既有 DB 升級不會吃到新文字，
所以這裡就地更新。只動「說明仍含內部名稱」的範本：被人改過說明的不覆蓋。
idempotent：換過一次後不再含內部名稱，重跑不動。
"""
from odoo import api, SUPERUSER_ID

# 內部名稱特徵：說明含任一個就視為還是出貨時的舊文字
_TECH_MARKERS = ('doc.linked.mixin', 'doc.template.field')

_NEW_DESCRIPTIONS = {
    'template_meeting_record': '用於監造會議記錄的文件範本，含會議資訊、出席者、議題、結論等段落。可由會議記錄自動建立並填入內容。',
    'template_self_inspection': '承包商自主檢查表，可由一般式或預約式的自主檢查自動建立並填入內容。',
    'template_defect_improvement': '缺失改善通知書，可由一般式或預約式的缺失改善自動建立並填入內容。',
    'template_payment_estimate': (
        '估驗計價單線上協作版本（補充既有報表，供協商階段使用）。範本內的 {{ var }} 預先建為文字填寫欄位；'
        '要綁實際資料，請在後台把這份範本的適用模型設為估驗計價（需已安裝估驗計價模組），'
        '再把對應欄位的類型改為「系統欄位」並填入欄位名稱（如 estimate_no / project_id.name / subtotal）。'
        '可由估驗計價單自動建立並填入內容。'),
    'template_review_control': '材料／設備送審文件審核表，可由送審申請自動建立並填入內容。',
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, text in _NEW_DESCRIPTIONS.items():
        rec = env.ref('dobtor_doc_editor.' + xmlid, raise_if_not_found=False)
        if not rec or not any(m in (rec.description or '') for m in _TECH_MARKERS):
            continue  # 找不到、已換過或被人改過 → 不動
        rec.write({'description': text})
