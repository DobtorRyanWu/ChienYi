# -*- coding: utf-8 -*-
"""S3 全域公司規則的寫入面（S3 fix1，2026-11-11）。

為什麼要有
----------
18 條全域公司規則（rule_company_global_<模型>，在 construction_payment／construction_contract_change／
construction_progress／construction_general／construction_supervision_base 的 security/company_rules.xml）
讀、刪、建都擋得住，**寫入只擋一半**：核心 write 只在寫入**前**用舊值檢查 ir.rule（odoo/models.py write 開頭的
``self.check_access('write')``），寫完不再檢查（只有 create 有寫後檢查）。於是讀得到、寫得了自己公司紀錄的人，
可以把它的工程或父單改成別家公司的——請款、計量驗收（＋明細）、非契約工項、進度報告明細、工項版本實測寫得進去
（S3 審查 skeptic F1；估驗、變更單的 project_id 另有 relational_input_guard 擋）。

這裡補兩件事，只對**非 sudo** 的 write、而且只在 vals 改到下表的欄位時（效能）：

1. **寫後再檢查**：寫完以寫入者身分 ``check_access('write')``；不符合規則就 AccessError（例外讓整個請求的交易回滾，
   與核心 create 的寫後檢查同一種語意）。
2. **有工程的單不能變成沒有工程**（UserError）：估驗、變更單、變更明細的規則對「工程空白」放行建立者
   （先存空單再「匯入工程案件」），所以把有工程的單清空工程、或把明細改掛到自己的空工程變更單上，
   第 1 點照樣會過，但同事從此看不到它（S3 審查 red-team F1）。建立者自己清也一樣擋。

sudo（系統內部流程）不檢查。正當的非 sudo 改寫（grep 全 repo，S3_fix1_report.md W-3）只有「匯入工程案件」
（estimate.import.wizard 替工程空白的估驗設工程）與契約變更精靈（contract.change.wizard 替變更單設工程），
都是「空白 → 自己公司的工程」，兩道檢查都會過。
測試：construction_company_dashboard/tests/test_company_isolation.py（TestCompanyIsolation 的 test_reparent_*、
test_blank_project_*、test_legit_*）。
"""
from odoo import _, models
from odoo.exceptions import UserError

# 模型 → 全域公司規則用得到、而且寫得進去的欄位。規則用 stored related company_id 的，同時列來源欄位與
# company_id 本身（related 欄位的 readonly 只是畫面屬性，ORM write 照樣把值寫進欄位）。
# report.project.task.user 是核心 SQL 檢視（寫不了），不在表上。
COMPANY_RULE_FIELDS = {
    'payment.claim': frozenset({'project_id'}),
    'payment.estimate': frozenset({'project_id'}),
    'payment.estimate.line': frozenset({'estimate_id'}),
    'payment.estimate.extra.item': frozenset({'project_id'}),
    'payment.estimate.extra.line': frozenset({'estimate_id', 'project_id'}),
    'work.acceptance': frozenset({'project_id'}),
    'work.acceptance.line': frozenset({'acceptance_id'}),
    'contract.change.order': frozenset({'project_id', 'company_id'}),
    'contract.change.order.line': frozenset({'change_order_id', 'company_id'}),
    'progress.schedule': frozenset({'project_id', 'company_id'}),
    'progress.schedule.line': frozenset({'schedule_id', 'company_id'}),
    'general.progress.report': frozenset({'project_id', 'company_id'}),
    'general.progress.report.line': frozenset({'report_id'}),
    'general.realtime.profit': frozenset({'project_id', 'company_id'}),
    'general.realtime.profit.cost': frozenset({'profit_id'}),
    'profit.loss.entry': frozenset({'project_id', 'company_id'}),
    'project.task.version': frozenset({'task_id'}),
}
# 模型 → 「這筆有沒有工程」的路徑：規則對工程空白放行建立者的那三個模型（#2 估驗、#8 變更單、#9 變更明細）
PROJECT_PATHS = {
    'payment.estimate': 'project_id',
    'contract.change.order': 'project_id',
    'contract.change.order.line': 'change_order_id.project_id',
}


class Base(models.AbstractModel):
    _inherit = 'base'

    def write(self, vals):
        watched = COMPANY_RULE_FIELDS.get(self._name)
        if not self or not watched or self.env.su or watched.isdisjoint(vals):
            return super().write(vals)
        path = PROJECT_PATHS.get(self._name)
        # 以寫入者身分讀（讀不到的紀錄在這裡就 AccessError，與 write 本身的寫前檢查同結果）
        had_project = self.filtered(path) if path else self.browse()
        result = super().write(vals)
        # 寫完以 sudo 讀：清空工程之後，非建立者已經讀不到這筆（讀它會先丟 AccessError，蓋掉下面要給的說明）
        lost = had_project.sudo().filtered(lambda record: not record.mapped(path))
        if lost:
            raise UserError(_(
                '%(model)s：已經有工程的紀錄不能改成沒有工程（清空工程、或改掛到沒有工程的單）——'
                '工程空白的單只有建立者看得到，改了同事就看不到。要換工程請直接選另一個工程。（%(names)s）',
                model=self._description, names='、'.join(lost.mapped('display_name'))))
        self.check_access('write')
        return result
