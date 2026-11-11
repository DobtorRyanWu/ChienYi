# -*- coding: utf-8 -*-
"""估驗計價 → 工程估驗計價單樣板匯出。"""

from odoo import _, models
from odoo.exceptions import AccessError

TEMPLATE_TYPE = 'estimate_report'
# 估驗表單上的四顆匯出按鈕（views/payment_estimate_export_views.xml，差在 context 的 template_type）。
# 唯讀帳號（後台角色帳號，S1 fix2-X）只准這四種：RPC 直接帶別的樣板類型（例：同一個方法也套得出進度報告、施工日誌）一律拒。
ESTIMATE_EXPORT_TEMPLATE_TYPES = ('estimate_report', 'invoice_detail', 'invoice_photo', 'estimate_progress_report')


class PaymentEstimate(models.Model):
    _name = 'payment.estimate'
    _inherit = ['payment.estimate', 'document.template.export.mixin']

    def action_export_estimate_template(self):
        """把本張估驗的資料填進「工程估驗計價單」樣板並下載。

        唯讀帳號（res.users._dash_is_restricted_internal()：公司儀表板的方法閘門只放後台角色帳號進來）：
        1. 只能匯出自己讀得到的估驗：先 check_access('read')，範圍外的 id（RPC 直接帶）在任何套印、寫入之前就拒；
        2. template_type 只准 ESTIMATE_EXPORT_TEMPLATE_TYPES 四種；
        3、4（以本人身分套印、不刪別人的檔）見 document.template.export.mixin（template_export_mixin.py）。
        """
        self.ensure_one()
        template_type = self.env.context.get('template_type', TEMPLATE_TYPE)
        if self.env.user._dash_is_restricted_internal():
            if template_type not in ESTIMATE_EXPORT_TEMPLATE_TYPES:
                raise AccessError(_('唯讀帳號只能匯出估驗表單上的四份文件（計價單、估驗詳細表、估驗照片、進度報告表）。'))
            if not self._filtered_access('read'):
                raise AccessError(_('唯讀帳號只能匯出自己讀得到的估驗。'))
        return self._export_document_template(template_type)
