# -*- coding: utf-8 -*-
"""完整性稽核紀錄。

這張表就是「我們有守住 DM 上那些承諾」的舉證憑據。客戶問「你怎麼證明資料沒被改過」、
「你怎麼證明兩年都在」，答案不是嘴巴講，是把這張表的紀錄調出來。

三種稽核：
* chain —— 雜湊鏈驗證（進階等級承諾的「竄改可偵測」）
* seq   —— 序號連續性
* retention —— 保存期間與每日筆數（基本等級承諾的「每分鐘一筆、保存兩年」）

稽核紀錄本身也不該被隨手改，但它不是量測資料，所以只用權限控管，
不上 append-only trigger——不然連修個備註都要開維護視窗。
"""

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

RESULT_OK = 'ok'
RESULT_GAP = 'gap'
RESULT_BROKEN = 'broken'


class WaterLevelIntegrityCheck(models.Model):
    _name = 'water.level.integrity.check'
    _description = '完整性稽核紀錄'
    _order = 'run_at desc, id desc'

    check_type = fields.Selection(
        [('chain', '雜湊鏈'),
         ('seq', '序號連續性'),
         ('retention', '保存期間'),
         ('maintenance', '維護視窗開啟')],
        string='稽核類型', required=True, index=True)
    device_id = fields.Many2one(
        'water.level.device', string='監測站',
        ondelete='cascade', index=True)
    site_id = fields.Many2one(
        related='device_id.site_id', string='監測場域', store=True, index=True)

    range_from_ts = fields.Datetime(string='起')
    range_to_ts = fields.Datetime(string='迄')
    range_from_seq = fields.Integer(string='起始序號')
    range_to_seq = fields.Integer(string='結束序號')
    checked_count = fields.Integer(string='檢查筆數')

    result = fields.Selection(
        [(RESULT_OK, '通過'),
         (RESULT_GAP, '有缺口'),
         (RESULT_BROKEN, '驗證失敗')],
        string='結果', required=True, index=True)
    first_bad_id = fields.Integer(
        string='第一筆有問題的紀錄 id',
        help='驗證失敗時指出從哪一筆開始對不上，方便直接查。')
    run_at = fields.Datetime(string='執行時間', default=fields.Datetime.now, readonly=True)
    note = fields.Text(string='說明')

    @api.depends('check_type', 'device_id.name', 'run_at')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '%s / %s / %s' % (
                dict(self._fields['check_type'].selection).get(rec.check_type, ''),
                rec.device_id.name or '全部',
                rec.run_at or '')

    # ==================== 雜湊鏈驗證 ====================

    @api.model
    def verify_chain(self, device, from_seq=None, limit=None):
        """驗證一台設備的雜湊鏈，回傳建立的稽核紀錄。

        兩種「斷」要分清楚，混在一起會天天噴假警報：
        * **合法的斷**：序號不連續（資料還沒補回來）。跨過缺口的那一筆，它的 prev
          本來就對不上，這不是竄改，記成 gap。
        * **真的斷**：序號連續但重算出來的雜湊與存的不一樣 → 資料被改過，記成 broken。

        只驗有 chain_hash 的紀錄。沒有雜湊的設備（基本等級或舊資料）不在此列。
        """
        device.ensure_one()
        domain = [('device_id', '=', device.id), ('chain_hash', '!=', False)]
        if from_seq:
            domain.append(('seq_no', '>=', from_seq))
        readings = self.env['water.level.reading'].search(
            domain, order='seq_no asc', limit=limit)
        if not readings:
            return self.create({
                'check_type': 'chain', 'device_id': device.id,
                'checked_count': 0, 'result': RESULT_OK,
                'note': _('沒有帶雜湊的紀錄可驗。'),
            })

        prev_seq = None
        prev_hash = ''
        broken_id = None
        gap_count = 0
        for reading in readings:
            if prev_seq is not None and reading.seq_no != prev_seq + 1:
                # 跨缺口：鏈在這裡合法地斷掉，改用本筆自己的雜湊當新起點
                gap_count += 1
                prev_hash = reading.chain_hash
                prev_seq = reading.seq_no
                continue
            expected = device.chain_hash(
                device.device_uid, reading.seq_no, reading.ts,
                reading.raw_value, prev_hash if prev_seq is not None else '')
            if expected != reading.chain_hash:
                broken_id = reading.id
                break
            prev_hash = reading.chain_hash
            prev_seq = reading.seq_no

        if broken_id:
            result, note = RESULT_BROKEN, _('第 %s 筆起雜湊對不上，資料在寫入後被更動過。') % broken_id
        elif gap_count:
            result, note = RESULT_GAP, _('鏈在 %s 處因序號缺口合法中斷，其餘皆通過。') % gap_count
        else:
            result, note = RESULT_OK, _('全部通過。')

        check = self.create({
            'check_type': 'chain',
            'device_id': device.id,
            'range_from_seq': readings[0].seq_no,
            'range_to_seq': readings[-1].seq_no,
            'range_from_ts': readings[0].ts,
            'range_to_ts': readings[-1].ts,
            'checked_count': len(readings),
            'result': result,
            'first_bad_id': broken_id or 0,
            'note': note,
        })
        if result == RESULT_BROKEN:
            _logger.error('水位雜湊鏈驗證失敗：%s 第 %s 筆', device.device_uid, broken_id)
            device.sudo().message_post(
                body=_('雜湊鏈驗證失敗：從紀錄 %s 起對不上，請立刻查。') % broken_id)
        return check

    @api.model
    def _cron_chain_verify(self):
        """每日驗增量。全量重驗會愈跑愈久，最後變成沒人敢開的 cron。"""
        devices = self.env['water.level.device'].search([
            ('active', '=', True), ('service_level', 'in', ['advanced', 'flagship']),
        ])
        for device in devices:
            start = (device.chain_verified_seq or 0) + 1
            check = self.verify_chain(device, from_seq=start)
            if check.result != RESULT_BROKEN and check.range_to_seq:
                device.sudo().write({'chain_verified_seq': check.range_to_seq})
