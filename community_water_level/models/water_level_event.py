# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import _, api, fields, models

# 簽收說明的長度上限（前台 textarea 的 maxlength 用同一個值）
ACK_NOTE_MAX = 500


class WaterLevelEvent(models.Model):
    _inherit = 'water.level.event'

    tank_id = fields.Many2one(
        'water.level.tank', string='蓄水池', ondelete='set null', index=True)

    # 簽收＝管委會「已處理」（2026-10-21 使用者定案）：記誰、何時、說明，**不結束事件**——
    # 結束事件會重算保全區段 protected_to_ts，而且越線事件的結束規則由 core 管。
    ack_user_id = fields.Many2one('res.users', string='簽收人', readonly=True, copy=False, index=True)
    ack_at = fields.Datetime(string='簽收時間', readonly=True, copy=False)
    ack_note = fields.Text(string='簽收說明', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        """事件記下當時設備裝在哪個池（拆模組前由核心的兩個建立點各自帶入）。

        設備日後換池，舊事件仍指向發生當時的池——所以是建立時抄一次，不做 related。
        """
        devices = self.env['water.level.device'].browse(
            {vals['device_id'] for vals in vals_list if vals.get('device_id')})
        tank_by_device = {device.id: device.tank_id.id for device in devices}
        for vals in vals_list:
            if 'tank_id' not in vals and vals.get('device_id'):
                vals['tank_id'] = tank_by_device.get(vals['device_id']) or False
        return super().create(vals_list)

    def _community_ack(self, user, note=''):
        """簽收。已經有人簽過就不覆寫、回 False。

        呼叫端（前台 controller）負責先確認 user 是這個社區的成員；這裡用 sudo 寫，所以方法名帶 `_`——
        不帶底線的話 portal 帳號可以經 /web/dataset/call_kw 直接呼叫、繞過 controller 的門。
        兩個人同時按：REPEATABLE READ 下第二筆寫入會序列化失敗，Odoo 重試整個請求時就讀到已簽收。
        """
        self.ensure_one()
        if self.ack_user_id:
            return False
        note = (note or '').strip()[:ACK_NOTE_MAX]
        event = self.sudo()
        event.write({'ack_user_id': user.id, 'ack_at': fields.Datetime.now(), 'ack_note': note or False})
        # Markup % 會把參數 escape（說明是前台輸入），不可以改成 f-string
        body = Markup('<p>%s</p>') % _('%(name)s 簽收了這個事件。', name=user.name)
        if note:
            body += Markup('<p>%s</p>') % _('說明：%(note)s', note=note)
        event.message_post(body=body, author_id=user.partner_id.id,
                           message_type='comment', subtype_xmlid='mail.mt_note')
        return True
