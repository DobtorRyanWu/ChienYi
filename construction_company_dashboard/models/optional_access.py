# -*- coding: utf-8 -*-
"""營造廠主管與後台角色帳號對「選裝模組」裡白名單模型的讀取 ACL（合約 §0b-10、§3.2）。

security/ir.model.access.csv 只能引用本模組依賴範圍內的模型；白名單裡有模型落在本模組沒依賴、
各租戶不一定裝的模組（日誌人機明細在 construction_equipment、成本分析在 construction_cost_analysis）。
這種模型改在每次安裝／升級本模組時（data 的 security/optional_access.xml 呼叫），依 registry 有沒有這個模型建立 ACL：
帶本模組的 xmlid → 升級時保留、移除本模組時一併刪除；那個模組沒裝就不建。

已知限制：那個模組比本模組晚裝時，要再升級本模組一次才會補上
（沒補時該帳號讀那張表＝ACL 拒，畫面會報無權限，不會靜默變空）。
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
