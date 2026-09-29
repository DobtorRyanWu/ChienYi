# -*- coding: utf-8 -*-
# ======================================================================
# 【停用】登記客戶確認（2026-09-29）
#
# 使用者判斷目前沒有電話、LINE 客服，客戶一律在前台按「問題已解決」，
# 這個對話框很可能用不到，先停用（本檔保留、不載入）。
#
# 要恢復，四個地方取消註解／加回：
#   1. wizards/__init__.py：取消註解 `from . import ticket_confirm_wizard`
#   2. security/ir.model.access.csv：加回下面這一行（CSV 不能寫註解，所以只能記在這裡）
#      access_ticket_confirm_wizard_agent,construction.service.ticket.confirm.wizard 客服,model_construction_service_ticket_confirm_wizard,group_helpdesk_agent,1,1,1,1
#   3. models/service_ticket.py：取消註解 action_open_confirm_wizard
#   4. views/service_ticket_views.xml：取消註解「登記客戶確認」按鈕與 view_ticket_confirm_wizard_form
# 然後升級模組。實際寫入的 _register_confirmation() 一直都在（前台按鈕也用它），不必動。
# ======================================================================
from odoo import _, fields, models
from odoo.exceptions import UserError

from ..models.service_ticket import CONFIRM_METHOD_SELECTION


class ConstructionServiceTicketConfirmWizard(models.TransientModel):
    """登記客戶確認：客戶用電話、LINE 等方式說「問題已解決」時，由客服代為登記。

    佐證依方式而定：LINE、Email 要附截圖；電話、當面不可能有圖，改為必須寫下對方怎麼說。
    客戶沒回應不等於確認。客戶自己在前台按「問題已解決」不走這裡。
    """
    _name = 'construction.service.ticket.confirm.wizard'
    _description = '登記客戶確認'

    ticket_id = fields.Many2one('construction.service.ticket', string='服務單', required=True, readonly=True)
    confirm_method = fields.Selection(
        [m for m in CONFIRM_METHOD_SELECTION if m[0] != 'portal'],
        string='確認方式', required=True)
    confirm_contact = fields.Char(string='確認的人', required=True, help='客戶那邊是誰說問題解決了。')
    confirm_note = fields.Text(
        string='說明', help='客戶怎麼說的。電話、當面確認時必填（時間與對方原話）。')
    attachment_ids = fields.Many2many(
        'ir.attachment', 'construction_ticket_confirm_wizard_att_rel', 'wizard_id', 'attachment_id',
        string='佐證', help='LINE、Email 確認時必附截圖。')

    def action_confirm(self):
        self.ensure_one()
        if not (self.confirm_contact or '').strip():
            raise UserError(_('請填寫確認的人。'))
        # 依方式檢查佐證的規則在 _register_confirmation()，前台與這裡共用
        self.ticket_id._register_confirmation(
            self.confirm_method, self.confirm_contact.strip(), self.confirm_note,
            self.env.user, attachments=self.attachment_ids)
        return {'type': 'ir.actions.act_window_close'}
