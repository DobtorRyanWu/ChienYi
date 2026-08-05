# -*- coding: utf-8 -*-
"""預定進度表 —— 佔位符對照表（專案層級，只帶表頭）。

⚠️ 這份**刻意不做工作項目的動態套印**。

樣板的主體是「主要工作項目 + 日數 + 甘特長條」，但 Odoo 的 progress.schedule
是週期 S 曲線（date_start / planned_progress / cumulative_planned），
沒有工作項目與其工期；而且 F~AK 的長條是儲存格填色不是文字，
本引擎只能填文字。硬湊會產生假的工作項目清單。

2026-08-05 已把來源專案的 8 個工作項目（假設工程／材料訂製／固定樁工程／
浮筒組裝工程／迎星碼頭…）清掉，工項區留白供人工填寫，
這裡只自動帶入工程名稱與預定工期。
"""

MODEL = 'project.project'
MODE = 'placeholder'


def build_context(project):
    return {
        'project.name': project.name or '',
        'plannedDuration': project.contract_duration or '',
    }


def FILENAME(project):
    return '預定進度表_%s.xlsx' % (project.name or project.id)
