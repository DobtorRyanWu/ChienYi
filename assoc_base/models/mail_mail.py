"""郵件暫停寄送（計畫 §5）：信件照常產生、留在佇列可檢視，但不寄出。

兩層，缺一不可：
1. `mail.mail.send()`：force_send 與排程 cron 都經這裡，攔在這層信件會停在 outgoing。
2. `ir.mail_server.send_email()`：擋直呼旁路（例：event/models/event_mail.py:407
   在範本出錯時直接寄信給主辦人）。

**參數不存在時視為 hold**：乾淨的新資料庫沒有這個參數，也不能把信寄出去。
上線順序見 README：先清掉佇列裡的舊信 → 設 SMTP → 參數改 0 → 重啟。
"""

import logging

from odoo import _, api, models
from odoo.addons.base.models.ir_mail_server import MailDeliveryException

_logger = logging.getLogger(__name__)

HOLD_PARAM = 'assoc.mail.hold'


def mail_on_hold(env):
    return env['ir.config_parameter'].sudo().get_param(HOLD_PARAM, '1') != '0'


class MailMail(models.Model):
    _inherit = 'mail.mail'

    def send(self, auto_commit=False, raise_exception=False, post_send_callback=None):
        if mail_on_hold(self.env):
            # 只記筆數：收件人是個資
            _logger.info('assoc mail hold: %s 封信保留在佇列，未寄出', len(self))
            return True
        return super().send(
            auto_commit=auto_commit, raise_exception=raise_exception,
            post_send_callback=post_send_callback)


class IrMailServer(models.Model):
    _inherit = 'ir.mail_server'

    @api.model
    def send_email(self, message, *args, **kwargs):
        if mail_on_hold(self.env):
            _logger.warning('assoc mail hold: 已攔下一封直接呼叫 send_email 的信')
            raise MailDeliveryException(_('系統目前暫停寄送郵件（assoc.mail.hold）。'))
        return super().send_email(message, *args, **kwargs)
