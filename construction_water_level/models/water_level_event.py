# -*- coding: utf-8 -*-
"""事件與事件影像關鍵幀（DM 進階等級：事件保全）。

**誠實條款，寫在最前面**：DM 承諾的「事件前緩衝保全（事件前資料落盤保存）」，
真正的落盤是**現場設備**的責任——資料要在事件發生前就已經寫進設備的儲存體，
Odoo 收到的時候事情早就過去了。Odoo 這一側能做的是：把事件區間標成永久保留，
讓任何清理／封存程序都不准碰它，並且把設備送上來的關鍵幀存好。
把這句寫進客戶文件，不要讓業務講成「Odoo 會幫你保全事件前的資料」。

事件可以由兩邊產生：
* 設備端偵測（隨上報的 events 區塊帶上來），帶自己的 event_uid
* Odoo 端偵測（門檻越線、斷線、時鐘偏移、鏈斷掉）
"""

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# 事件前要保護多久的資料（分鐘）。DM 的「事件前緩衝」在 Odoo 這側就是這段保護區間。
PRE_EVENT_BUFFER_MINUTES = 15
# 事件後保護多久
POST_EVENT_BUFFER_MINUTES = 15


class WaterLevelEvent(models.Model):
    _name = 'water.level.event'
    _description = '水位事件'
    _inherit = ['mail.thread']
    _order = 'start_ts desc, id desc'

    name = fields.Char(string='事件編號', readonly=True, copy=False, default='新事件')
    event_uid = fields.Char(
        string='設備端事件碼', index=True, copy=False,
        help='設備自己給的事件識別碼。關鍵幀靠 (設備, 事件碼) 掛回來。')

    device_id = fields.Many2one(
        'water.level.device', string='監測站',
        required=True, ondelete='restrict', index=True)
    site_id = fields.Many2one(
        related='device_id.site_id', string='監測場域', store=True, index=True)
    tank_id = fields.Many2one(
        'water.level.tank', string='蓄水池', ondelete='set null', index=True)

    event_type = fields.Selection(
        [('level_high', '水位過高'),
         ('level_low', '水位過低'),
         ('offline', '斷線'),
         ('power_loss', '失電'),
         ('comm_switch', '通訊切換備援'),
         ('clock_drift', '時鐘偏移'),
         ('chain_break', '雜湊鏈異常'),
         ('manual', '人工標記')],
        string='事件類型', required=True, index=True)
    severity = fields.Selection(
        [('info', '資訊'), ('warning', '警告'), ('critical', '嚴重')],
        string='嚴重度', default='warning', required=True)

    start_ts = fields.Datetime(string='開始時間', required=True, index=True)
    end_ts = fields.Datetime(string='結束時間')
    peak_value = fields.Float(string='極值(m)', digits=(10, 3))
    trigger_state = fields.Char(string='觸發時狀態')

    state = fields.Selection(
        [('open', '進行中'), ('closed', '已結束'), ('reviewed', '已複核')],
        string='狀態', default='open', required=True, index=True, tracking=True)

    # 事件區間永久保留：清理與封存程序看這兩個欄位，落在區間內的紀錄一律不准動
    protected_from_ts = fields.Datetime(string='保護區間起', readonly=True)
    protected_to_ts = fields.Datetime(string='保護區間迄', readonly=True)

    frame_ids = fields.One2many(
        'water.level.event.frame', 'event_id', string='關鍵幀')
    frame_count = fields.Integer(string='影像數', compute='_compute_frame_count')
    note = fields.Text(string='說明')

    _sql_constraints = [
        ('device_event_uid_uniq', 'unique(device_id, event_uid)',
         '同一監測站的同一個設備端事件碼已存在。'),
    ]

    def _compute_frame_count(self):
        self.frame_count = 0
        saved = self.filtered(lambda e: isinstance(e.id, int))
        if not saved:
            return
        groups = self.env['water.level.event.frame']._read_group(
            [('event_id', 'in', saved.ids)], groupby=['event_id'], aggregates=['__count'])
        counts = {event.id: count for event, count in groups}
        for event in saved:
            event.frame_count = counts.get(event.id, 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '新事件') == '新事件':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'water.level.event') or '新事件'
            vals.setdefault('protected_from_ts', self._buffer_start(vals.get('start_ts')))
            vals.setdefault('protected_to_ts', self._buffer_end(vals.get('end_ts')
                                                                or vals.get('start_ts')))
        return super().create(vals_list)

    @staticmethod
    def _buffer_start(start_ts):
        from datetime import timedelta
        if not start_ts:
            return False
        start = fields.Datetime.to_datetime(start_ts)
        return start - timedelta(minutes=PRE_EVENT_BUFFER_MINUTES)

    @staticmethod
    def _buffer_end(end_ts):
        from datetime import timedelta
        if not end_ts:
            return False
        end = fields.Datetime.to_datetime(end_ts)
        return end + timedelta(minutes=POST_EVENT_BUFFER_MINUTES)

    def action_close(self):
        for event in self:
            event.write({
                'state': 'closed',
                'end_ts': event.end_ts or fields.Datetime.now(),
            })
            event.protected_to_ts = event._buffer_end(event.end_ts)

    def action_review(self):
        self.write({'state': 'reviewed'})

    def reading_ids_in_range(self):
        """事件區間內的水位紀錄（含前後緩衝），事件報表與保護判斷都用這個。"""
        self.ensure_one()
        return self.env['water.level.reading'].search([
            ('device_id', '=', self.device_id.id),
            ('ts', '>=', self.protected_from_ts or self.start_ts),
            ('ts', '<=', self.protected_to_ts or fields.Datetime.now()),
        ], order='ts asc')

    @api.model
    def is_protected(self, device, ts):
        """這個時間點是否落在任何事件的保護區間內。清理／封存前必問。"""
        return bool(self.search_count([
            ('device_id', '=', device.id),
            ('protected_from_ts', '<=', ts),
            ('protected_to_ts', '>=', ts),
        ]))

    @api.model
    def record_from_device(self, device, payload):
        """設備端送上來的事件。同一個 event_uid 重送只更新不重複開。"""
        event_uid = payload.get('uid')
        domain = [('device_id', '=', device.id)]
        existing = self.search(domain + [('event_uid', '=', event_uid)], limit=1) \
            if event_uid else self.browse()
        vals = {
            'device_id': device.id,
            'tank_id': device.tank_id.id or False,
            'event_uid': event_uid,
            'event_type': payload.get('type') or 'manual',
            'severity': payload.get('severity') or 'warning',
            'start_ts': payload.get('start_ts'),
            'end_ts': payload.get('end_ts'),
            'peak_value': payload.get('peak_value') or 0.0,
            'note': payload.get('note'),
        }
        vals = {k: v for k, v in vals.items() if v not in (None, False)} \
            if existing else vals
        if existing:
            existing.write(vals)
            return existing
        return self.create(vals)


class WaterLevelEventFrame(models.Model):
    _name = 'water.level.event.frame'
    _description = '事件影像關鍵幀'
    _order = 'event_id, sequence, ts'

    event_id = fields.Many2one(
        'water.level.event', string='事件',
        required=True, ondelete='cascade', index=True)
    device_id = fields.Many2one(
        related='event_id.device_id', string='監測站', store=True, index=True)
    ts = fields.Datetime(string='拍攝時間', required=True)
    kind = fields.Selection(
        [('pre', '事件前'), ('peak', '極值'), ('post', '事件後')],
        string='類型', default='peak', required=True)
    sequence = fields.Integer(string='序', default=10)

    # restrict：影像是舉證用的，不能因為有人清附件就無聲消失
    attachment_id = fields.Many2one(
        'ir.attachment', string='影像檔', required=True, ondelete='restrict')
    frame_hash = fields.Char(string='影像雜湊', size=64)
    byte_size = fields.Integer(string='檔案大小(bytes)')
    width = fields.Integer(string='寬')
    height = fields.Integer(string='高')

    @api.depends('event_id.name', 'kind', 'ts')
    def _compute_display_name(self):
        for frame in self:
            frame.display_name = '%s %s %s' % (
                frame.event_id.name or '', frame.kind or '', frame.ts or '')
