# -*- coding: utf-8 -*-
"""驗收紀錄 —— docx 對照表。

樣板原本把來源案的「訂約總價／結算金額 5,520,048元」寫死在表格裡，
2026-08-05 清掉並改成 {{ }} 佔位符（docxtpl 直接吃 Jinja2，
不需要經過 +++INS+++ 轉換——那是舊 EAGLE 樣板才有的語法）。

⚠️ 本機 DB 的 acceptance.final 是 0 筆，套印路徑以臨時記錄驗證過，
但沒有真實資料可對照。實際使用前建議先用一筆真的驗收紀錄確認欄位對得上。
"""

from ..utils.formatters import money, roc_date

MODEL = 'acceptance.final'
MODE = 'docx'


def build_context(acceptance):
    project = acceptance.project_id
    return {
        'contractNo': project.contract_no or '',
        'contractorName': acceptance.contractor_company_id.display_name or '',
        'subjectName': project.name or '',
        'batch': acceptance.name or '',
        'completionDate': roc_date(acceptance.acceptance_date),
        'contractAmount': money(project.contract_amount),
        # 結算金額：acceptance.final 沒有這個欄位，改讀結案紀錄的 final_amount，
        # 沒有結案紀錄就留白（不要拿契約金額頂替，那是不同的數字）
        'settlementAmount': money(acceptance.closure_id.final_amount
                                  if acceptance.closure_id else None),
    }


def FILENAME(acceptance):
    return '驗收紀錄_%s_%s.docx' % (
        acceptance.project_id.name or '', acceptance.name or acceptance.id)
