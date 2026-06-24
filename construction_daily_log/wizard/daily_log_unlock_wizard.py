# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import timedelta


class DailyLogUnlockWizard(models.TransientModel):
    """施工日誌解鎖精靈"""
    _name = 'daily.log.unlock.wizard'
    _description = '施工日誌解鎖精靈'

    _DURATION_LABELS = {'24': '1天', '72': '3天', '120': '5天', '168': '7天'}

    sheet_id = fields.Many2one(
        'daily.log.sheet',
        string='日誌',
        required=True,
        readonly=True,
    )
    
    log_date = fields.Date(
        related='sheet_id.log_date',
        string='日誌日期',
        readonly=True,
    )
    
    days_since_log = fields.Integer(
        related='sheet_id.days_since_log',
        string='距今天數',
        readonly=True,
    )
    
    unlock_reason = fields.Text(
        string='解鎖原因',
        required=True,
        help='請說明為何需要解鎖此日誌',
    )
    
    unlock_duration = fields.Selection([
        ('24', '1天'),
        ('72', '3天'),
        ('120', '5天'),
        ('168', '7天'),
    ], string='解鎖時長', default='120', required=True,
       help='解鎖後在指定時間內可以修改，時間到後自動重新鎖定')

    can_unlock = fields.Boolean(related='sheet_id.can_unlock')

    def action_confirm_unlock(self):
        """確認解鎖"""
        self.ensure_one()
        
        if not self.sheet_id.can_unlock:
            raise UserError('您沒有解鎖權限！')
        
        # 計算失效時間
        hours = int(self.unlock_duration)
        expires_at = fields.Datetime.now() + timedelta(hours=hours)
        
        # 執行解鎖
        unlock_vals = {
            'is_unlocked': True,
            'unlocked_by_id': self.env.uid,
            'unlock_date': fields.Datetime.now(),
            'unlock_reason': self.unlock_reason,
            'unlock_expires_at': expires_at,
        }
        # 自動鎖定的日誌解鎖後恢復為編輯中
        if self.sheet_id.state == 'auto_locked':
            unlock_vals['state'] = 'draft'
        self.sheet_id.write(unlock_vals)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '解鎖成功',
                'message': f'日誌已解鎖，將於 {expires_at.strftime("%Y-%m-%d %H:%M")} 自動重新鎖定',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_request_unlock(self):
        """提出解鎖申請（無權限使用者）"""
        self.ensure_one()
        sheet = self.sheet_id
        user = self.env.user
        duration_label = self._DURATION_LABELS.get(self.unlock_duration, self.unlock_duration)

        sheet.write({
            'unlock_request_state': 'pending',
            'unlock_requested_by_id': user.id,
            'unlock_request_duration': self.unlock_duration,
            'unlock_request_reason': self.unlock_reason,
        })

        # 取得監造工程師通知
        engineer = sheet.supervision_project_id.supervision_engineer_id
        partner_ids = engineer.partner_id.ids if engineer and engineer.partner_id else []

        sheet.message_post(
            body=(f'🔓 {user.name} 針對【{sheet.supervision_project_id.name}】'
                  f' {sheet.log_date} 的施工日誌提出解鎖申請。\n'
                  f'申請解鎖時長：{duration_label}\n'
                  f'原因：{self.unlock_reason}'),
            partner_ids=partner_ids,
            message_type='notification',
            subtype_xmlid='mail.mt_comment',
        )
        return {'type': 'ir.actions.act_window_close'}
