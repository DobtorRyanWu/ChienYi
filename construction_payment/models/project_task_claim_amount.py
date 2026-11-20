# -*- coding: utf-8 -*-
"""契約工項「實際請款金額」改用估驗計價（2026-11-20）。

- 沒有子工項的（一般、整包、比例項）＝這個工項所有**已核定、已歸檔**估驗明細的「本次估驗金額」
  （estimate_amount，存資料庫、手動金額照手動值）加總。
  🔴 不讀最後一張的「累計估驗金額」（cumulative_estimate_amount）：那是非儲存欄位，拿它當來源，
     估驗變動後工項上不會自動更新。
- 彙總項＝子工項加總（排除不計入契約金額的預備單價項目），**不讀它自己在估驗單上的彙總列**：
  pg18 已核定／已歸檔的 71 張裡有 5 張沒有彙總列，讀自己那一列會少算。
- 非契約工項（payment.estimate.extra.line）不在契約工項樹裡，不算。
- 「完成率」公式不變（實際請款金額 ÷ 契約金額），意思變成請款比例 → 名稱改「累計估驗比例 (%)」，欄位代碼不改。
- 沒安裝本模組時，construction_supervision_base 的舊公式（依施工日誌推算）照舊；裝了就被這裡蓋掉。
"""
from odoo import api, fields, models

CLAIM_STATES = ('approved', 'archived')


class ProjectTaskClaimAmount(models.Model):
    _inherit = 'project.task'

    # 只給 depends 用的反查（不存資料庫、不新增資料表）
    estimate_line_ids = fields.One2many(
        'payment.estimate.line', 'task_id', string='估驗明細', readonly=True)

    actual_amount = fields.Float(
        help='已核定、已歸檔估驗計價的累計估驗金額：\n'
             '・彙總項（有子工項）：子工項實際請款金額總和（不含預備單價項目）\n'
             '・其他工項（一般、整包、比例項）：已核定／已歸檔估驗單明細的「本次估驗金額」加總\n'
             '草稿、待核定的估驗不算。施工做了多少請看「實際完成數量」（施工日誌）。')

    completion_rate = fields.Float(
        string='累計估驗比例 (%)',
        help='實際請款金額（已核定累計估驗金額）÷ 契約金額 × 100')

    @api.depends('child_ids', 'child_ids.actual_amount', 'child_ids.exclude_from_contract_amount',
                 'estimate_line_ids.estimate_amount', 'estimate_line_ids.estimate_id.state')
    def _compute_actual_amount(self):
        for task in self:
            if task.child_ids:
                task.actual_amount = sum(
                    child.actual_amount for child in task.child_ids
                    if not child.exclude_from_contract_amount)
            else:
                task.actual_amount = round(sum(
                    line.estimate_amount for line in task.sudo().estimate_line_ids
                    if line.estimate_id.state in CLAIM_STATES), 2)
