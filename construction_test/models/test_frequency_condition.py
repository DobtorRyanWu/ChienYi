# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TestFrequencyCondition(models.Model):
    """檢驗頻率條件明細"""
    _name = 'supervision.test.frequency.condition'
    _description = '檢驗頻率條件'
    _order = 'sequence, id'
    
    # ===================================================================
    # 基本欄位
    # ===================================================================
    
    standard_id = fields.Many2one(
        'supervision.test.standard',
        string='檢試驗項目',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    sequence = fields.Integer(
        string='排序',
        default=10
    )
    
    active = fields.Boolean(
        string='啟用',
        default=True,
        help='停用此條件將不會納入計算'
    )
    
    # ===================================================================
    # 條件類型與參數
    # ===================================================================
    
    condition_type = fields.Selection([
        ('exempt_below', '未達數量免檢'),        # (1) 未達a數量時免檢驗
        ('range_once', '數量區間檢驗1次'),      # (2) 數量達b~c時，檢驗1次
        ('exceed_interval', '超過數量每N加驗'),  # (3) 數量超過d時，每e加驗1次
        ('every_n', '每N數量檢驗1次'),          # (4) 每f數量，檢驗1次
        ('every_batch', '每批檢驗1次'),         # (5) 每批1次
    ], string='條件類型', required=True)

    # 彈性欄位，根據條件類型使用不同欄位
    threshold_qty = fields.Float(
        string='門檻數量',
        digits=(16, 4),
        help='用於「未達數量免檢」：未達此數量時免檢驗'
    )
    
    range_start = fields.Float(
        string='起始數量',
        digits=(16, 4),
        help='用於「數量區間檢驗1次」：區間起始數量'
    )
    
    range_end = fields.Float(
        string='結束數量',
        digits=(16, 4),
        help='用於「數量區間檢驗1次」：區間結束數量'
    )
    
    exceed_qty = fields.Float(
        string='超過數量',
        digits=(16, 4),
        help='用於「超過數量每N加驗」：超過此數量後開始加驗'
    )
    
    interval_qty = fields.Float(
        string='間隔數量',
        digits=(16, 4),
        help='用於「超過數量每N加驗」或「每N數量檢驗1次」：每隔此數量檢驗一次'
    )

    # ===================================================================
    # 計算欄位
    # ===================================================================
    
    condition_summary = fields.Char(
        string='條件摘要',
        compute='_compute_condition_summary',
        store=True,
        help='條件的文字描述'
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='standard_id.company_id',
        store=True,
        index=True
    )
    
    # ===================================================================
    # 計算方法
    # ===================================================================
    
    @api.depends(
        'condition_type', 'threshold_qty', 'range_start', 'range_end',
        'exceed_qty', 'interval_qty'
    )
    def _compute_condition_summary(self):
        """計算條件摘要文字"""
        for cond in self:
            if cond.condition_type == 'exempt_below':
                cond.condition_summary = f'未達 {cond.threshold_qty} 免檢'

            elif cond.condition_type == 'range_once':
                cond.condition_summary = f'數量 {cond.range_start}~{cond.range_end} 檢驗1次'

            elif cond.condition_type == 'exceed_interval':
                cond.condition_summary = f'超過 {cond.exceed_qty} 後每 {cond.interval_qty} 加驗1次'

            elif cond.condition_type == 'every_n':
                cond.condition_summary = f'每 {cond.interval_qty} 檢驗1次'

            elif cond.condition_type == 'every_batch':
                cond.condition_summary = '每批檢驗1次'

            else:
                cond.condition_summary = ''
    
    # ===================================================================
    # 約束條件
    # ===================================================================
    
    @api.constrains('condition_type', 'threshold_qty', 'range_start', 'range_end',
                    'exceed_qty', 'interval_qty')
    def _check_condition_values(self):
        """檢查條件參數是否合理"""
        for cond in self:
            if cond.condition_type == 'exempt_below':
                if not cond.threshold_qty or cond.threshold_qty <= 0:
                    raise ValidationError('「未達數量免檢」必須設定正數的門檻數量')
                    
            elif cond.condition_type == 'range_once':
                if cond.range_start is False or (not cond.range_end and cond.range_end != 0):
                    raise ValidationError('「數量區間檢驗1次」必須設定起始與結束數量')
                if cond.range_start >= cond.range_end:
                    raise ValidationError('起始數量必須小於結束數量')
                if cond.range_start < 0 or cond.range_end < 0:
                    raise ValidationError('數量不可為負數')
                    
            elif cond.condition_type == 'exceed_interval':
                if not cond.exceed_qty or not cond.interval_qty:
                    raise ValidationError('「超過數量每N加驗」必須設定超過數量與間隔數量')
                if cond.exceed_qty <= 0 or cond.interval_qty <= 0:
                    raise ValidationError('數量必須為正數')
                    
            elif cond.condition_type == 'every_n':
                if not cond.interval_qty or cond.interval_qty <= 0:
                    raise ValidationError('「每N數量檢驗1次」必須設定正數的間隔數量')
    
    # ===================================================================
    # 核心計算方法
    # ===================================================================
    
    def calculate_total_required_tests(self, cumulative_qty):
        """
        根據一組條件（recordset）計算總共需要的檢驗次數

        注意：exempt_below 條件會使整個計算回傳 0（免檢），
        所以必須將所有條件一起處理，不能各自獨立計算後相加。

        :param cumulative_qty: 累計完成數量
        :return: int, 總共需要的檢驗次數
        """
        if cumulative_qty <= 0:
            return 0

        total_required = 0
        conditions = self.filtered('active').sorted('sequence')

        for cond in conditions:
            if cond.condition_type == 'exempt_below':
                if cumulative_qty < cond.threshold_qty:
                    return 0  # 免檢，直接返回 0

            elif cond.condition_type == 'range_once':
                if cond.range_start <= cumulative_qty:
                    total_required += 1

            elif cond.condition_type == 'exceed_interval':
                if cond.interval_qty > 0:
                    total = int(cumulative_qty / cond.interval_qty)
                    exempt = int(cond.exceed_qty / cond.interval_qty)
                    total_required += max(0, total - exempt)

            elif cond.condition_type == 'every_n':
                if cond.interval_qty > 0:
                    total_required += int(cumulative_qty / cond.interval_qty)

            # every_batch: 與累計數量無關，跳過

        return total_required

    def calculate_required_tests(self, cumulative_qty):
        """
        根據條件計算需要的檢驗次數
        
        :param cumulative_qty: 累計完成數量
        :return: 需要的檢驗次數
        """
        self.ensure_one()
        
        if not self.active:
            return 0
        
        if cumulative_qty <= 0:
            return 0
        
        if self.condition_type == 'exempt_below':
            # (1) 未達數量免檢
            if cumulative_qty < self.threshold_qty:
                return 0
            # 達到門檻，但此條件本身不產生檢驗需求
            # （通常會搭配其他條件使用）
            return 0
            
        elif self.condition_type == 'range_once':
            # (2) 數量區間檢驗1次
            if self.range_start <= cumulative_qty <= self.range_end:
                return 1
            return 0
            
        elif self.condition_type == 'exceed_interval':
            # (3) 超過數量每N加驗：每 interval 檢驗一次，但未超過 exceed 免驗
            if self.interval_qty > 0:
                total = int(cumulative_qty / self.interval_qty)
                exempt = int(self.exceed_qty / self.interval_qty)
                return max(0, total - exempt)
            return 0
            
        elif self.condition_type == 'every_n':
            # (4) 每N數量檢驗1次
            return int(cumulative_qty / self.interval_qty)
            
        elif self.condition_type == 'every_batch':
            # (5) 每批1次
            return 0

        return 0
