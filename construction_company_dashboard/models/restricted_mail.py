# -*- coding: utf-8 -*-
"""受限帳號不在公開頻道裡（合約 §0b-25；使用者 11-06 決定：討論是千溢／監造方內部在用，營造方不用）。

受限帳號＝營造方（後台營造廠主管、前台營造帳號）與控台讀取帳號（res.users._dash_is_restricted()）。
讀取與寫入的收窄在 rule_scope.py（公開頻道 channel_type='channel' 與其成員紀錄讀不到、改不了）；這裡管「成員資格」：

* 不自動加入：核心在建帳號、改群組、頻道改「自動加入群組」時，把群組裡的人全部加進頻道
  （mail/models/discuss/res_users.py:13-27、res_groups.py:12、discuss_channel.py:344-365 _subscribe_users_automatically）。
  營造廠主管與控台讀取帳號隱含 base.group_user，所以一建帳號就被加進 #general。覆寫
  _subscribe_users_automatically_get_members 把受限帳號剔掉（一個程式點涵蓋上面三條路）。
* 既有成員資格移除：升級本模組時（data/restricted_channels.xml 的 function）與帳號的群組／營造標記改變時
  （res_users_guard.py write）移除受限帳號在公開頻道的成員紀錄。私訊（chat）、群組對話（group）不動。

另：訊息搜尋不因「讀不到的來源單據」而整個出錯（11-06 抗辯 red-team F10）。核心 mail.message._search 對每張
來源單據呼叫該模型的 _get_mail_message_access；有些核心模型在裡面以使用者身分讀單據欄位（例 calendar.event 讀
privacy，calendar/models/calendar_event.py:892），受限帳號讀不到那張單據（範圍規則「其他」類）就丟 AccessError，
整個搜尋失敗（`search_count([])` 實測）。對受限帳號先把來源單據濾成讀得到的再交給核心——讀不到的本來就會被判為
不可見，結果不變，只是不再丟錯。其他帳號照核心。
"""
import logging

from odoo import api, models

from .rule_scope import CHANNEL_TYPE_PUBLIC

_logger = logging.getLogger(__name__)


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    def _subscribe_users_automatically_get_members(self):
        new_members = super()._subscribe_users_automatically_get_members()
        partner_ids = {pid for pids in new_members.values() for pid in pids}
        if not partner_ids:
            return new_members
        restricted = self.env['res.partner'].sudo().browse(partner_ids).with_context(
            active_test=False).user_ids.filtered(lambda user: user._dash_is_restricted()).partner_id
        if not restricted:
            return new_members
        blocked = set(restricted.ids)
        return {channel_id: [pid for pid in pids if pid not in blocked] for channel_id, pids in new_members.items()}


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _dash_leave_public_channels(self):
        """self 之中的受限帳號：移除它們在公開頻道的成員紀錄（sudo；回傳移除筆數）。"""
        restricted = self.sudo().with_context(active_test=False).filtered(lambda user: user._dash_is_restricted())
        if not restricted:
            return 0
        members = self.env['discuss.channel.member'].sudo().search([
            ('partner_id', 'in', restricted.partner_id.ids),
            ('channel_id.channel_type', '=', CHANNEL_TYPE_PUBLIC),
        ])
        if members:
            _logger.info('受限帳號移出公開頻道：%s',
                         ', '.join(f'{m.partner_id.display_name}@{m.channel_id.name}' for m in members))
            members.unlink()
        return len(members)

    @api.model
    def _dash_remove_restricted_channel_memberships(self):
        """升級時呼叫（data/restricted_channels.xml）：全部受限帳號移出公開頻道。可重跑。"""
        partners = self.env['discuss.channel.member'].sudo().search([
            ('channel_id.channel_type', '=', CHANNEL_TYPE_PUBLIC), ('partner_id', '!=', False),
        ]).partner_id
        users = partners.with_context(active_test=False).user_ids
        return users._dash_leave_public_channels()


class MailMessage(models.Model):
    _inherit = 'mail.message'

    def _filter_records_for_message_operation(self, doc_model, doc_res_ids, operation):
        if self.env.su or not self.env['ir.rule']._dash_scope_kind():
            return super()._filter_records_for_message_operation(doc_model, doc_res_ids, operation)
        # 受限帳號：讀不到（或已刪除）的來源單據先拿掉——核心對它們的判定本來就是「不可見」（見檔頭）
        documents = self.env[doc_model].with_context(active_test=False).browse(doc_res_ids).exists()
        readable = set(documents._filtered_access('read').ids)
        return super()._filter_records_for_message_operation(
            doc_model, [doc_id for doc_id in doc_res_ids if doc_id in readable], operation)
