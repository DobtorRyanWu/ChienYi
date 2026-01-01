# -*- coding: utf-8 -*-

from odoo import models, fields, api


class TestStandard(models.Model):
    """
    檢試驗項目管理

    對應舊系統: testStandard

    管理工程的檢試驗項目，包含：
    - 試驗工項/材料設定
    - 依據方法與規範要求
    - 頻率與下限設定
    - 取樣規則與條件
    - 關聯契約工項
    """
    _name = 'supervision.test.standard'
    _description = '檢試驗項目'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id'

    # === 基本資料 ===
    name = fields.Char(
        string='項目名稱',
        required=True,
        tracking=True,
        help='檢試驗項目名稱')

    sequence = fields.Integer(
        string='排序',
        default=10,
        help='排序順序')

    active = fields.Boolean(
        string='啟用',
        default=True)

    project_id = fields.Many2one(
        'supervision.project',
        string='所屬工程',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True)

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='project_id.company_id',
        store=True,
        readonly=True)

    # === 檢驗項目資訊 (舊系統欄位對應) ===
    material = fields.Char(
        string='試驗工項/材料',
        required=True,
        tracking=True,
        help='舊系統欄位: material')

    describe = fields.Text(
        string='依據之方法',
        help='舊系統欄位: describe，說明檢驗依據的標準方法')

    norm = fields.Text(
        string='規範之要求',
        help='舊系統欄位: norm，規範要求的標準值或範圍')

    standard = fields.Text(
        string='頻率及下限',
        help='舊系統欄位: standard，取樣頻率和最低要求')

    unit = fields.Char(
        string='檢查單位',
        help='舊系統欄位: unit，檢驗數量的計量單位')

    # === 取樣規則 ===
    sampling_size = fields.Char(
        string='取樣大小',
        help='每次取樣的數量或規格')

    sampling_conditions = fields.Text(
        string='檢驗頻率條件',
        help='舊系統欄位: conditions (a~f 參數規則)，定義取樣頻率的各項條件')

    # === 契約工項關聯 ===
    # 注意：規格書中的 project.contract.item 對應現有系統的 project.task
    task_ids = fields.Many2many(
        'project.task',
        'test_standard_task_rel',
        'standard_id',
        'task_id',
        string='關聯契約工項',
        domain="[('supervision_project_id', '=', project_id)]",
        help='舊系統欄位: payItems，此檢試驗項目適用的契約工項')

    # === 檢驗記錄 ===
    test_record_ids = fields.One2many(
        'supervision.test.record',
        'standard_id',
        string='檢驗記錄')

    test_record_count = fields.Integer(
        string='檢驗次數',
        compute='_compute_test_record_count',
        store=True)

    # === 統計欄位 ===
    total_in_site_quantity = fields.Float(
        string='累計進場數量',
        compute='_compute_statistics',
        store=True,
        digits=(16, 4))

    total_sample_quantity = fields.Float(
        string='累計取樣數量',
        compute='_compute_statistics',
        store=True,
        digits=(16, 4))

    overall_sample_rate = fields.Float(
        string='整體取樣率 (%)',
        compute='_compute_statistics',
        store=True,
        digits=(5, 2))

    pass_count = fields.Integer(
        string='合格次數',
        compute='_compute_statistics',
        store=True)

    fail_count = fields.Integer(
        string='不合格次數',
        compute='_compute_statistics',
        store=True)

    pass_rate = fields.Float(
        string='合格率 (%)',
        compute='_compute_statistics',
        store=True,
        digits=(5, 2))

    # === 備註 ===
    note = fields.Text(string='備註')

    @api.depends('test_record_ids')
    def _compute_test_record_count(self):
        """計算檢驗記錄數量"""
        for rec in self:
            rec.test_record_count = len(rec.test_record_ids)

    @api.depends(
        'test_record_ids',
        'test_record_ids.in_site_quantity',
        'test_record_ids.sample_quantity',
        'test_record_ids.result'
    )
    def _compute_statistics(self):
        """計算統計數據"""
        for rec in self:
            records = rec.test_record_ids
            rec.total_in_site_quantity = sum(records.mapped('in_site_quantity'))
            rec.total_sample_quantity = sum(records.mapped('sample_quantity'))

            if rec.total_in_site_quantity:
                rec.overall_sample_rate = (rec.total_sample_quantity / rec.total_in_site_quantity) * 100
            else:
                rec.overall_sample_rate = 0.0

            rec.pass_count = len(records.filtered(lambda r: r.result == 'pass'))
            rec.fail_count = len(records.filtered(lambda r: r.result == 'fail'))

            total_judged = rec.pass_count + rec.fail_count
            if total_judged:
                rec.pass_rate = (rec.pass_count / total_judged) * 100
            else:
                rec.pass_rate = 0.0

    def name_get(self):
        """自訂顯示名稱"""
        result = []
        for rec in self:
            name = f'{rec.name}'
            if rec.material and rec.material != rec.name:
                name = f'{rec.name} ({rec.material})'
            result.append((rec.id, name))
        return result

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        """支援依名稱和材料搜尋"""
        domain = domain or []
        if name:
            domain = [
                '|',
                ('name', operator, name),
                ('material', operator, name)
            ] + domain
        return self._search(domain, limit=limit, order=order)

    def action_view_test_records(self):
        """查看檢驗記錄"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '檢驗記錄',
            'res_model': 'supervision.test.record',
            'view_mode': 'tree,form',
            'domain': [('standard_id', '=', self.id)],
            'context': {
                'default_standard_id': self.id,
                'default_project_id': self.project_id.id,
            },
        }
