# -*- coding: utf-8 -*-
"""營造廠主管與後台角色帳號對「選裝模組」裡白名單模型的讀取 ACL（合約 §0b-10、§3.2）。

security/ir.model.access.csv 只能引用本模組依賴範圍內的模型；白名單裡有模型落在本模組沒依賴、
各租戶不一定裝的模組（日誌人機明細在 construction_equipment、成本分析在 construction_cost_analysis）。
這種模型改在每次安裝／升級本模組時（data 的 security/optional_access.xml 呼叫），依 registry 有沒有這個模型建立 ACL：
帶本模組的 xmlid → 升級時保留、移除本模組時一併刪除；那個模組沒裝就不建。

那個模組比本模組晚裝時：靠下面 ir.model.data._process_end 的覆寫補上——核心在每次模組安裝／升級流程的最後
呼叫它，這時所有模組都載入完了。2026-11-25 以前沒有這一段，要等下次升級本模組才補；示範站與正式站都是
公文模組（construction_office）後裝，營造廠主管與後台角色帳號的公文、行事曆因此整個無權限。
"""
from odoo import api, models

MODULE = 'construction_company_dashboard'
MANAGER_GROUP_XMLID = f'{MODULE}.group_contractor_manager'
ROLE_MANAGER_GROUP_XMLID = f'{MODULE}.group_role_manager'
# 群組 → 標籤前綴（ACL 名稱用）
GROUP_LABELS = {
    MANAGER_GROUP_XMLID: '營造廠主管',
    ROLE_MANAGER_GROUP_XMLID: '後台角色帳號',
}

# (模型, ACL 的 xmlid 名稱, 群組)；xmlid 名稱與 ir.model.access.csv 同一命名
OPTIONAL_READ_ACCESS = (
    ('daily.log.man.machine.detail', 'access_cm_daily_log_man_machine_detail', MANAGER_GROUP_XMLID),
    ('daily.log.man.machine.detail', 'access_role_daily_log_man_machine_detail', ROLE_MANAGER_GROUP_XMLID),
    # 成本分析（S1，2026-11-10）：只給角色帳號；營造廠主管照舊沒有（rule_scope 對它也拒）
    ('cost.analysis', 'access_role_cost_analysis', ROLE_MANAGER_GROUP_XMLID),
    ('cost.analysis.line', 'access_role_cost_analysis_line', ROLE_MANAGER_GROUP_XMLID),
    # 送審管制（construction_review，選裝；淞源 C5，2026-11-12）：期限待辦要讀它的限定提送日
    ('supervision.plan.control', 'access_cm_plan_control', MANAGER_GROUP_XMLID),
    ('supervision.plan.control', 'access_role_plan_control', ROLE_MANAGER_GROUP_XMLID),
    # 公文（construction_office，選裝；淞源 C10，2026-11-12）：營造廠主管用手機查、角色帳號後台也查；
    # 讀得到哪些由 rule_scope.COMPANY_OWNED_LEVEL 決定（所屬公司＝自己的公司）
    ('construction.official.doc', 'access_cm_official_doc', MANAGER_GROUP_XMLID),
    ('construction.official.doc', 'access_role_official_doc', ROLE_MANAGER_GROUP_XMLID),
    # 行事曆事項（construction_office；淞源 C7）：同公文
    ('construction.calendar.event', 'access_cm_calendar_event', MANAGER_GROUP_XMLID),
    ('construction.calendar.event', 'access_role_calendar_event', ROLE_MANAGER_GROUP_XMLID),
)


class IrModelAccess(models.Model):
    _inherit = 'ir.model.access'

    @api.model
    def _dash_sync_optional_manager_access(self):
        """建立（或更新）選裝模組模型的 1,0,0,0 讀取 ACL；回傳建好的 ACL。"""
        data_list = []
        for model_name, xml_name, group_xmlid in OPTIONAL_READ_ACCESS:
            model = self.env['ir.model']._get(model_name)
            if not model:
                continue
            group = self.env.ref(group_xmlid)
            data_list.append({
                'xml_id': f'{MODULE}.{xml_name}',
                'noupdate': False,
                'values': {
                    'name': f'{GROUP_LABELS[group_xmlid]} 讀 {model.name}',
                    'model_id': model.id,
                    'group_id': group.id,
                    'perm_read': True,
                    'perm_write': False,
                    'perm_create': False,
                    'perm_unlink': False,
                },
            })
        if not data_list:
            return self.browse()
        return self.sudo()._load_records(data_list, update=True)


class IrModelData(models.Model):
    _inherit = 'ir.model.data'

    @api.model
    def _process_end(self, modules):
        """任何模組安裝／升級完都把選裝模組的讀取 ACL 補齊（見檔頭）。可重跑：已經有的只會照同樣的值再寫一次。"""
        result = super()._process_end(modules)
        if modules:
            self.env['ir.model.access']._dash_sync_optional_manager_access()
        return result
