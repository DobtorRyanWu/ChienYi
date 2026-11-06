# -*- coding: utf-8 -*-
"""工程的營造廠清單或監造公司變動時，相關營造廠的營造廠主管允許公司自動重算（合約 §2、§1-9）。
另提供工程上的「重新帶入營造廠歸屬」（合約 §3.5 後續：工程補了營造廠之後，底下歸屬空白的單據補一次）。
"""
from odoo import _, api, models
from odoo.exceptions import AccessError

from .contractor_attribution import ContractorAttributionMixin  # noqa: F401  確保 mixin 已載入

# 工程欄位變動要觸發同步的欄位
SYNC_TRIGGER_FIELDS = frozenset({'contractor_company_ids', 'company_id'})
# 營造廠層級的 8 個模型 → 所屬工程欄位（與 contractor_attribution.py 一致；日誌用 supervision_project_id）
ATTRIBUTION_PROJECT_FIELDS = {
    'daily.log.sheet': 'supervision_project_id',
    'supervision.photo': 'project_id',
    'general.defect.improvement': 'project_id',
    'reservation.defect.improvement': 'project_id',
    'supervision.test.record': 'project_id',
    'general.self.inspection': 'project_id',
    'reservation.self.inspection': 'project_id',
    'payment.estimate': 'project_id',
}


class ProjectProject(models.Model):
    _inherit = 'project.project'

    def _dash_contractors_snapshot(self):
        return self.sudo().with_context(active_test=False).mapped('contractor_company_ids')

    # 一定要帶裝飾器：call_kw 依方法的 _api 判斷「model 方法、不取 ids」，覆寫不會繼承父類別的 _api；
    # 少了它，任何 XML-RPC／JSON-RPC 的 create 都在權限檢查之前 TypeError（線 E 實證）
    @api.model_create_multi
    def create(self, vals_list):
        projects = super().create(vals_list)
        self.env['res.users']._dash_sync_managers_of(projects._dash_contractors_snapshot())
        return projects

    def write(self, vals):
        if not (SYNC_TRIGGER_FIELDS & vals.keys()):
            return super().write(vals)
        before = self._dash_contractors_snapshot()
        res = super().write(vals)
        self.env['res.users']._dash_sync_managers_of(before | self._dash_contractors_snapshot())
        return res

    def unlink(self):
        before = self._dash_contractors_snapshot()
        res = super().unlink()
        self.env['res.users']._dash_sync_managers_of(before)
        return res

    def action_dash_refill_attribution(self):
        """重新帶入營造廠歸屬：對本工程底下「營造廠」空白的單據重算一次（只限監造方）。

        已有值的不動；重算規則同欄位預設（工程只有一家營造廠 → 那家；建立者是營造方且範圍公司在內 → 範圍公司）。
        """
        if not self.env.user._is_supervision_side():
            raise AccessError(_('只有監造方帳號可以重新帶入營造廠歸屬。'))
        # 下面以 sudo 搜尋並重算：呼叫者必須能寫這些工程（11-06 抗辯 skeptic F5：jt 這種共用庫裡，
        # A 監造公司的人對讀不到的 B 公司工程照樣重算，還能從回傳訊息得知筆數）
        self.check_access('write')
        filled = 0
        for model_name, project_field in ATTRIBUTION_PROJECT_FIELDS.items():
            Model = self.env[model_name].sudo().with_context(active_test=False)
            blanks = Model.search([
                (project_field, 'in', self.ids), ('contractor_company_id', '=', False)])
            if not blanks:
                continue
            field = Model._fields['contractor_company_id']
            self.env.add_to_compute(field, blanks)
            blanks.flush_recordset(['contractor_company_id'])
            filled += len(blanks.filtered('contractor_company_id'))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success' if filled else 'warning',
                'message': _('已補上 %s 筆單據的營造廠歸屬。', filled) if filled else
                           _('沒有可補的單據（工程若有多家營造廠，需由監造方逐筆指定）。'),
                'sticky': False,
            },
        }
