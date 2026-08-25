# -*- coding: utf-8 -*-
"""序號缺口。

DM 基本等級承諾「連續序號核對，缺號自動索取補送」。缺口不是查詢時算出來的暫時值，
是一個有狀態的東西：偵測到 → 要求補送 → 補回來 → 關閉，中間可能要求很多次，
也可能永遠補不回來（設備本地緩衝已被覆蓋）。那些都要留紀錄，才有東西可以對客戶交代。

**缺口只由「向前跳號」產生**：本批最小序號 > 設備游標 + 1。
補送批次帶的是舊序號，只會關缺口、不會開新缺口——這條規則不寫死，
系統會把每一次補送都當成新的跳號，自己無限製造缺口。
"""

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# 同一個缺口最多主動要求幾次補送，超過就認賠並通知
MAX_RESEND_REQUESTS = 5


class WaterLevelGap(models.Model):
    _name = 'water.level.gap'
    _description = '序號缺口'
    _order = 'device_id, seq_from'

    device_id = fields.Many2one(
        'water.level.device', string='監測站',
        required=True, ondelete='cascade', index=True)
    site_id = fields.Many2one(
        related='device_id.site_id', string='監測場域', store=True, index=True)

    seq_from = fields.Integer(string='起始序號', required=True)
    seq_to = fields.Integer(string='結束序號', required=True)
    missing_count = fields.Integer(
        string='缺少筆數', compute='_compute_missing_count', store=True)
    filled_count = fields.Integer(string='已補回筆數', default=0)

    state = fields.Selection(
        [('open', '待補送'),
         ('requested', '已要求補送'),
         ('partial', '部分補回'),
         ('filled', '已補齊'),
         ('unrecoverable', '無法補回')],
        string='狀態', default='open', required=True, index=True)

    detected_at = fields.Datetime(
        string='偵測時間', default=fields.Datetime.now, readonly=True)
    last_request_at = fields.Datetime(string='最後要求時間', readonly=True)
    request_count = fields.Integer(string='要求次數', default=0, readonly=True)
    filled_at = fields.Datetime(string='補齊時間', readonly=True)
    note = fields.Char(string='備註')

    _sql_constraints = [
        ('device_range_uniq', 'unique(device_id, seq_from, seq_to)',
         '同一監測站的同一個缺口區間已存在。'),
    ]

    @api.depends('seq_from', 'seq_to')
    def _compute_missing_count(self):
        for gap in self:
            gap.missing_count = max(0, gap.seq_to - gap.seq_from + 1)

    @api.depends('device_id.name', 'seq_from', 'seq_to')
    def _compute_display_name(self):
        for gap in self:
            gap.display_name = '%s #%s-%s' % (
                gap.device_id.name or '', gap.seq_from, gap.seq_to)

    # ==================== 供 ingest 呼叫 ====================

    @api.model
    def _open_gap(self, device, seq_from, seq_to):
        """開一個缺口。同一區間已存在就不重複開。"""
        if seq_to < seq_from:
            return self.browse()
        existing = self.search([
            ('device_id', '=', device.id),
            ('seq_from', '=', seq_from),
            ('seq_to', '=', seq_to),
        ], limit=1)
        if existing:
            return existing
        return self.create({
            'device_id': device.id,
            'seq_from': seq_from,
            'seq_to': seq_to,
        })

    @api.model
    def _close_filled(self, device, received_seqs):
        """收到補送資料後，重算哪些缺口補齊了。

        不用「收到幾筆就減幾筆」這種累計法——補送可能重複、可能亂序，
        累計會失準。直接回資料表數這個區間現在有幾筆，是唯一不會騙人的算法。
        """
        if not received_seqs:
            return
        gaps = self.search([
            ('device_id', '=', device.id),
            ('state', 'in', ['open', 'requested', 'partial']),
            ('seq_from', '<=', max(received_seqs)),
            ('seq_to', '>=', min(received_seqs)),
        ])
        for gap in gaps:
            self.env.cr.execute("""
                SELECT count(*) FROM water_level_reading
                 WHERE device_id = %s AND seq_no BETWEEN %s AND %s
            """, (device.id, gap.seq_from, gap.seq_to))
            have = self.env.cr.fetchone()[0]
            vals = {'filled_count': have}
            if have >= gap.missing_count:
                vals.update(state='filled', filled_at=fields.Datetime.now())
            elif have:
                vals['state'] = 'partial'
            gap.write(vals)

    # ==================== 定期稽核 ====================

    @api.model
    def _cron_gap_scan(self):
        """把序號連續性從頭掃一次，不只依賴上報當下的偵測。

        為什麼需要：上報時的偵測只看得到「這批相對於游標」的跳號。資料若從別的路徑
        進來（補遷、匯入、設備重置後序號回頭），或某次上報的偵測被交易回滾掉，
        缺口就永遠不會被發現。這支是那個兜底。
        """
        devices = self.env['water.level.device'].search([('active', '=', True)])
        opened = closed = 0
        for device in devices:
            self.env.cr.execute("""
                SELECT seq_no + 1 AS gap_from, next_seq - 1 AS gap_to
                  FROM (SELECT seq_no,
                               lead(seq_no) OVER (ORDER BY seq_no) AS next_seq
                          FROM water_level_reading
                         WHERE device_id = %s AND seq_no IS NOT NULL) t
                 WHERE next_seq > seq_no + 1
                 ORDER BY 1
            """, (device.id,))
            for gap_from, gap_to in self.env.cr.fetchall():
                gap = self._open_gap(device, gap_from, gap_to)
                if gap.state == 'filled':
                    # 之前標成補齊、現在又缺了：資料被抽掉才會這樣，要重新開單
                    gap.write({'state': 'open', 'filled_at': False})
                opened += 1

            # 反向：資料庫裡已經連續了，但缺口還掛著未關
            stale = self.search([
                ('device_id', '=', device.id),
                ('state', 'in', ['open', 'requested', 'partial']),
            ])
            for gap in stale:
                self.env.cr.execute("""
                    SELECT count(*) FROM water_level_reading
                     WHERE device_id = %s AND seq_no BETWEEN %s AND %s
                """, (device.id, gap.seq_from, gap.seq_to))
                if self.env.cr.fetchone()[0] >= gap.missing_count:
                    gap.write({
                        'state': 'filled',
                        'filled_count': gap.missing_count,
                        'filled_at': fields.Datetime.now(),
                    })
                    closed += 1
        _logger.info('序號缺口稽核：掃到缺口 %s 個、關閉 %s 個', opened, closed)

    @api.model
    def _pending_ranges(self, device, limit=20):
        """要塞進 ingest 回應、請設備補送的區間清單。

        每回一次就記一次要求次數；超過上限就不再要，改標成無法補回並留紀錄——
        一直要一個設備已經沒有的資料，只是讓雙方每分鐘互相浪費。
        """
        gaps = self.search([
            ('device_id', '=', device.id),
            ('state', 'in', ['open', 'requested', 'partial']),
        ], order='seq_from', limit=limit)
        ranges = []
        for gap in gaps:
            if gap.request_count >= MAX_RESEND_REQUESTS:
                gap.write({
                    'state': 'unrecoverable',
                    'note': _('要求補送 %s 次仍未補齊，停止索取。') % gap.request_count,
                })
                continue
            gap.write({
                'state': 'requested',
                'request_count': gap.request_count + 1,
                'last_request_at': fields.Datetime.now(),
            })
            ranges.append({'from': gap.seq_from, 'to': gap.seq_to})
        return ranges
