# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class TestRecord(models.Model):
    """
    檢(試)驗管制記錄

    對應舊系統: testRecord

    記錄材料進場、取樣、試驗結果的詳細資料：
    - 進場日期與數量
    - 取樣日期與數量
    - 累計進場與取樣統計
    - 抽驗人員記錄
    - 試驗結果判定
    - 歸檔編號與附件
    """
    _name = 'supervision.test.record'
    _description = '檢(試)驗管制記錄'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'in_site_date desc, id desc'

    # === 基本資料 ===
    name = fields.Char(
        string='編號',
        copy=False,
        readonly=True,
        default=lambda self: '/',
        help='自動編號')

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

    standard_id = fields.Many2one(
        'supervision.test.standard',
        string='檢試驗項目',
        required=True,
        ondelete='restrict',
        index=True,
        tracking=True,
        domain="[('project_id', '=', project_id)]",
        help='舊系統欄位: standard')

    # === 材料關聯 ===
    material_name = fields.Char(
        string='材料名稱',
        related='standard_id.material',
        store=True,
        readonly=True)

    # 契約工項關聯（可選）
    task_id = fields.Many2one(
        'project.task',
        string='契約工項',
        domain="[('supervision_project_id', '=', project_id)]",
        help='舊系統欄位: payItem，此次檢驗對應的契約工項')

    # === 進場記錄 (舊系統欄位) ===
    in_site_date = fields.Date(
        string='進場日期',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
        index=True,
        help='舊系統欄位: inSiteDate')

    in_site_quantity = fields.Float(
        string='進場數量',
        digits=(16, 4),
        tracking=True,
        help='舊系統欄位: inSiteQuantity')

    in_site_sum_quantity = fields.Float(
        string='累計進場',
        digits=(16, 4),
        compute='_compute_cumulative',
        store=True,
        help='舊系統欄位: inSiteSumQuantity')

    # === 取樣記錄 (舊系統欄位) ===
    sample_date = fields.Date(
        string='取樣日期',
        tracking=True,
        help='舊系統欄位: sampleDate')

    sample_quantity = fields.Float(
        string='取樣數量',
        digits=(16, 4),
        tracking=True,
        help='舊系統欄位: sampleQuantity')

    sample_sum_quantity = fields.Float(
        string='累計取樣',
        digits=(16, 4),
        compute='_compute_cumulative',
        store=True,
        help='舊系統欄位: sampleSumQuantity')

    sample_rate = fields.Float(
        string='取樣率 (%)',
        digits=(5, 2),
        compute='_compute_sample_rate',
        store=True,
        help='舊系統欄位: sampleRate，累計取樣/累計進場 x 100')

    # === 抽驗人員 ===
    member_ids = fields.Many2many(
        'res.users',
        'test_record_member_rel',
        'record_id',
        'user_id',
        string='抽驗及會同人員',
        help='舊系統欄位: member')

    inspector_id = fields.Many2one(
        'res.users',
        string='主辦抽驗人員',
        default=lambda self: self.env.user,
        tracking=True)

    # === 檢驗結果 ===
    result = fields.Selection([
        ('pass', '合格'),
        ('fail', '不合格'),
        ('pending', '待判定'),
    ], string='抽試驗結果',
       default='pending',
       tracking=True,
       help='舊系統欄位: result')

    result_date = fields.Date(
        string='結果判定日期',
        tracking=True)

    result_description = fields.Text(
        string='結果說明',
        help='檢驗結果的詳細說明')

    # === 歸檔編號 ===
    archive_number = fields.Char(
        string='歸檔編號',
        tracking=True,
        help='舊系統欄位: archiveNumber')

    # === 附件 ===
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'test_record_attachment_rel',
        'record_id',
        'attachment_id',
        string='檢驗報告',
        help='上傳檢驗報告文件')

    attachment_count = fields.Integer(
        string='附件數',
        compute='_compute_attachment_count')

    # === 狀態管理 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('sampled', '已取樣'),
        ('tested', '已檢驗'),
        ('archived', '已歸檔'),
    ], string='狀態',
       default='draft',
       tracking=True,
       index=True)

    # === 備註 ===
    note = fields.Text(string='備註')

    # === 計算欄位 ===
    @api.depends('in_site_quantity', 'sample_quantity', 'in_site_date', 'standard_id')
    def _compute_cumulative(self):
        """
        計算累計數量

        查詢同專案同標準的所有記錄，按進場日期排序計算累計值
        """
        for rec in self:
            if not rec.project_id or not rec.standard_id or not rec.in_site_date:
                rec.in_site_sum_quantity = rec.in_site_quantity
                rec.sample_sum_quantity = rec.sample_quantity
                continue

            # 查詢同專案同標準、日期早於或等於本記錄的所有記錄
            domain = [
                ('project_id', '=', rec.project_id.id),
                ('standard_id', '=', rec.standard_id.id),
                ('in_site_date', '<=', rec.in_site_date),
            ]

            # 排除自己（如果已有 ID）
            if rec.id:
                domain.append(('id', '!=', rec.id))

            prev_records = self.search(domain)

            # 計算累計值
            prev_in_site = sum(prev_records.mapped('in_site_quantity'))
            prev_sample = sum(prev_records.mapped('sample_quantity'))

            rec.in_site_sum_quantity = prev_in_site + (rec.in_site_quantity or 0.0)
            rec.sample_sum_quantity = prev_sample + (rec.sample_quantity or 0.0)

    @api.depends('sample_sum_quantity', 'in_site_sum_quantity')
    def _compute_sample_rate(self):
        """計算取樣率"""
        for rec in self:
            if rec.in_site_sum_quantity:
                rec.sample_rate = (rec.sample_sum_quantity / rec.in_site_sum_quantity) * 100
            else:
                rec.sample_rate = 0.0

    @api.depends('attachment_ids')
    def _compute_attachment_count(self):
        """計算附件數量"""
        for rec in self:
            rec.attachment_count = len(rec.attachment_ids)

    # === 約束檢查 ===
    @api.constrains('in_site_quantity')
    def _check_in_site_quantity(self):
        """進場數量不可為負"""
        for rec in self:
            if rec.in_site_quantity < 0:
                raise ValidationError('進場數量不可為負數')

    @api.constrains('sample_quantity')
    def _check_sample_quantity(self):
        """取樣數量不可為負"""
        for rec in self:
            if rec.sample_quantity < 0:
                raise ValidationError('取樣數量不可為負數')

    @api.constrains('sample_date', 'in_site_date')
    def _check_sample_date(self):
        """取樣日期不可早於進場日期"""
        for rec in self:
            if rec.sample_date and rec.in_site_date:
                if rec.sample_date < rec.in_site_date:
                    raise ValidationError('取樣日期不可早於進場日期')

    # === 狀態動作 ===
    def action_sample(self):
        """標記為已取樣"""
        for rec in self:
            if rec.state != 'draft':
                raise UserError('只有草稿狀態可以標記為已取樣')
            if not rec.sample_date:
                rec.sample_date = fields.Date.today()
            rec.state = 'sampled'

    def action_test(self):
        """標記為已檢驗"""
        for rec in self:
            if rec.state != 'sampled':
                raise UserError('只有已取樣狀態可以標記為已檢驗')
            if rec.result == 'pending':
                raise UserError('請先填寫檢驗結果')
            if not rec.result_date:
                rec.result_date = fields.Date.today()
            rec.state = 'tested'

    def action_archive(self):
        """歸檔"""
        for rec in self:
            if rec.state != 'tested':
                raise UserError('只有已檢驗狀態可以歸檔')
            if not rec.archive_number:
                raise UserError('請先填寫歸檔編號')
            rec.state = 'archived'

    def action_reset_draft(self):
        """重設為草稿"""
        for rec in self:
            if rec.state == 'archived':
                raise UserError('已歸檔的記錄無法重設')
            rec.state = 'draft'

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        """建立時自動產生編號"""
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('supervision.test.record') or '/'
        records = super().create(vals_list)
        # 觸發同專案同標準其他記錄的累計重算
        records._trigger_cumulative_recompute()
        return records

    def write(self, vals):
        """更新時觸發累計重算"""
        result = super().write(vals)
        # 如果修改了影響累計計算的欄位，觸發重算
        if any(f in vals for f in ['in_site_quantity', 'sample_quantity', 'in_site_date', 'standard_id', 'project_id']):
            self._trigger_cumulative_recompute()
        return result

    def _trigger_cumulative_recompute(self):
        """觸發同專案同標準所有記錄的累計重算"""
        for rec in self:
            if rec.project_id and rec.standard_id:
                # 找出所有需要重算的記錄
                related_records = self.search([
                    ('project_id', '=', rec.project_id.id),
                    ('standard_id', '=', rec.standard_id.id),
                    ('in_site_date', '>=', rec.in_site_date),
                    ('id', '!=', rec.id),
                ])
                # 觸發重算（Odoo 會自動處理 compute 欄位）
                if related_records:
                    related_records._compute_cumulative()

    def unlink(self):
        """刪除前檢查"""
        for rec in self:
            if rec.state == 'archived':
                raise UserError('已歸檔的記錄無法刪除')
        return super().unlink()

    def name_get(self):
        """自訂顯示名稱"""
        result = []
        for rec in self:
            name = rec.name or '/'
            if rec.material_name:
                name = f'{name} - {rec.material_name}'
            if rec.in_site_date:
                name = f'{name} ({rec.in_site_date})'
            result.append((rec.id, name))
        return result

    @api.onchange('standard_id')
    def _onchange_standard_id(self):
        """當選擇檢試驗項目時，自動設定專案"""
        if self.standard_id and self.standard_id.project_id:
            self.project_id = self.standard_id.project_id

    @api.onchange('project_id')
    def _onchange_project_id(self):
        """當專案變更時，清空檢試驗項目"""
        if self.project_id:
            if self.standard_id and self.standard_id.project_id != self.project_id:
                self.standard_id = False
            return {
                'domain': {
                    'standard_id': [('project_id', '=', self.project_id.id)],
                    'task_id': [('supervision_project_id', '=', self.project_id.id)],
                }
            }

    def action_view_attachments(self):
        """查看附件"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '檢驗報告附件',
            'res_model': 'ir.attachment',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.attachment_ids.ids)],
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
            },
        }
