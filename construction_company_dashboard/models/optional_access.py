# -*- coding: utf-8 -*-
"""營造廠主管對「選裝模組」裡白名單模型的讀取 ACL（合約 §0b-10、§3.2）。

security/ir.model.access.csv 只能引用本模組依賴範圍內的模型；白名單裡有模型落在本模組沒依賴、
各租戶不一定裝的模組（日誌人機明細在 construction_equipment）。這種模型改在每次安裝／升級本模組時
（data 的 security/optional_access.xml 呼叫），依 registry 有沒有這個模型建立 ACL：
帶本模組的 xmlid → 升級時保留、移除本模組時一併刪除；那個模組沒裝就不建。

已知限制：那個模組比本模組晚裝時，要再升級本模組一次才會補上
（沒補時營造廠主管讀那張子表＝ACL 拒，畫面會報無權限，不會靜默變空）。
"""
from odoo import api, models

MODULE = 'construction_company_dashboard'
MANAGER_GROUP_XMLID = f'{MODULE}.group_contractor_manager'

# 模型 → ACL 的 xmlid 名稱（與 ir.model.access.csv 同一命名）
OPTIONAL_MANAGER_READ = {
    'daily.log.man.machine.detail': 'access_cm_daily_log_man_machine_detail',
}


class IrModelAccess(models.Model):
    _inherit = 'ir.model.access'

    @api.model
    def _dash_sync_optional_manager_access(self):
        """建立（或更新）選裝模組模型的營造廠主管 1,0,0,0 讀取 ACL；回傳建好的 ACL。"""
        group = self.env.ref(MANAGER_GROUP_XMLID)
        data_list = []
        for model_name, xml_name in OPTIONAL_MANAGER_READ.items():
            model = self.env['ir.model']._get(model_name)
            if not model:
                continue
            data_list.append({
                'xml_id': f'{MODULE}.{xml_name}',
                'noupdate': False,
                'values': {
                    'name': f'營造廠主管 讀 {model.name}',
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
