# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError

# 只對這些模型的訊息生效，不改成全域行為
LOCKED_MESSAGE_MODELS = ('construction.service.ticket',)

# 會改到「內容」的欄位。標星號、表情、已讀等不在此列，照常可寫。
CONTENT_FIELDS = ('body', 'attachment_ids', 'subject', 'author_id', 'date',
                  'model', 'res_id', 'message_type')


class MailMessage(models.Model):
    _inherit = 'mail.message'

    def _locked_helpdesk_messages(self):
        return self.filtered(lambda m: m.model in LOCKED_MESSAGE_MODELS)

    def write(self, vals):
        # env.su：系統自身的處理（例如刪除整張服務單時連帶清訊息）放行；
        # 使用者從畫面「編輯留言」走的是 _message_update_content，已在服務單上擋掉。
        if not self.env.su and any(f in vals for f in CONTENT_FIELDS) \
                and self._locked_helpdesk_messages():
            raise UserError(_('服務單上的留言送出後不能修改。要更正請再留一則新的留言。'))
        return super().write(vals)

    def unlink(self):
        if not self.env.su and self._locked_helpdesk_messages():
            raise UserError(_('服務單上的留言送出後不能刪除。'))
        return super().unlink()
