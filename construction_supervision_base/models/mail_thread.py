# -*- coding: utf-8 -*-
from odoo import models


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _message_compute_author(self, author_id=None, email_from=None, raise_on_email=True):
        """通知不因「作者(操作者)無 email」而中斷。

        本系統允許使用非 email 的登入帳號，且通知很重要（缺失派工、解鎖申請、進度…）。
        Odoo 核心 mail.thread._message_compute_author 在「作者無 email 且非 sudo」時會 raise
        「Unable to send message, please configure the sender's email address」，
        導致後台申請解鎖等通知類動作被擋。此處改為不 raise，並盡量退回用公司 email 當寄件人
        （有設才用、不偽造）；作者有 email 時完全走原生。email_from 最終仍空時，訊息照 post、
        通知信進佇列（不寄、不崩潰）。
        """
        author_id, email_from = super()._message_compute_author(
            author_id=author_id, email_from=email_from, raise_on_email=False)
        if not email_from:
            company = self.env.company
            email_from = company.email_formatted or company.email or email_from
        return author_id, email_from
