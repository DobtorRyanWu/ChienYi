# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class SupervisionReviewApplication(models.Model):
    """
    送審管制

    對應舊系統: reviewApplication
    業務說明:
    - 管理工程材料送審流程
    - 追蹤型錄、樣品、測試報告、協力廠商資料的送審進度
    - 記錄審查結果、廠驗、取樣試驗等資訊
    """
    _name = 'supervision.review.application'
    _description = '送審管制'
    _inherit = ['mail.thread', 'mail.activity.mixin',
                'supervision.attachment.mixin']
    _order = 'expected_review_date asc, id desc'
    _rec_name = 'display_name'

    # === 基本資料 ===
    name = fields.Char(
        string='材料名稱',
        required=True,
        tracking=True,
        help='舊系統欄位: name')

    display_name = fields.Char(
        string='顯示名稱',
        compute='_compute_display_name',
        store=True)

    sequence_code = fields.Char(
        string='送審編號',
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: '/')

    project_id = fields.Many2one(
        'project.project',
        string='所屬工程',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
        domain="[('state', 'not in', ['closed', 'terminated'])]")

    company_id = fields.Many2one(
        'res.company',
        string='管理公司',
        related='project_id.company_id',
        store=True,
        readonly=True)

    # === 契約資訊 (舊系統欄位) ===
    no = fields.Char(
        string='契約詳細表項次',
        tracking=True,
        help='舊系統欄位: no')

    number = fields.Float(
        string='契約數量',
        digits='Product Unit of Measure',
        help='舊系統欄位: number')

    # === 送審日期 (舊系統欄位) ===
    expected_review_date = fields.Date(
        string='送審-預定日期',
        tracking=True,
        help='舊系統欄位: expectedReviewDate')

    final_review_date = fields.Date(
        string='送審-實際日期',
        tracking=True,
        help='舊系統欄位: finalReviewDate')

    review_delay_days = fields.Integer(
        string='送審延遲天數',
        compute='_compute_review_delay_days',
        store=True,
        help='實際送審日期與預定日期的差異天數，正數表示延遲')

    @api.depends('expected_review_date', 'final_review_date')
    def _compute_review_delay_days(self):
        for record in self:
            if record.expected_review_date and record.final_review_date:
                delta = record.final_review_date - record.expected_review_date
                record.review_delay_days = delta.days
            else:
                record.review_delay_days = 0

    # === 送審資料 (舊系統欄位) ===
    has_catalog = fields.Boolean(
        string='型錄',
        default=False,
        tracking=True,
        help='舊系統欄位: hasCatalog')

    has_demo = fields.Boolean(
        string='樣品',
        default=False,
        tracking=True,
        help='舊系統欄位: hasDemo')

    has_related_test_report = fields.Boolean(
        string='相關測試報告',
        default=False,
        tracking=True,
        help='舊系統欄位: hasRelatedTestReport')

    has_subcontractor = fields.Boolean(
        string='協力廠商資料',
        default=False,
        tracking=True,
        help='舊系統欄位: hasSubcontractor')

    has_others = fields.Boolean(
        string='其他',
        default=False,
        tracking=True)

    others = fields.Text(
        string='其他資料說明',
        help='當選擇其他送審資料時，請填寫說明')

    # === 送審資料摘要 ===
    review_materials_summary = fields.Char(
        string='送審資料摘要',
        compute='_compute_review_materials_summary',
        store=True)

    @api.depends('has_catalog', 'has_demo', 'has_related_test_report', 'has_subcontractor', 'has_others')
    def _compute_review_materials_summary(self):
        for record in self:
            materials = []
            if record.has_catalog:
                materials.append('型錄')
            if record.has_demo:
                materials.append('樣品')
            if record.has_related_test_report:
                materials.append('測試報告')
            if record.has_subcontractor:
                materials.append('協力廠商')
            if record.has_others:
                materials.append('其他')
            record.review_materials_summary = ', '.join(materials) if materials else '-'

    # === 審查 (舊系統欄位) ===
    review_date = fields.Date(
        string='審查日期',
        tracking=True,
        help='舊系統欄位: reviewDate')

    final_review_result = fields.Selection([
        ('pass', '合格'),
        ('conditional', '條件式通過'),
        ('fail', '不合格'),
    ], string='審查結果',
       tracking=True,
       help='舊系統欄位: finalReviewResult')

    review_comment = fields.Text(
        string='審查意見',
        help='審查人員的意見與備註')

    # 來源管制表的「審查日期」格子常常是「日期＋監造審查發文字號」兩行，
    # 舊版只接得住日期，文號只能塞進審查意見或丟掉。另立一欄存放，
    # 與歸檔紀錄的 archive_number（機關核准文號）對稱。
    review_document_no = fields.Char(
        string='審查函號',
        tracking=True,
        help='監造單位審查完發文的公文字號（例：110任泰顧字第0601051501號）')

    # === 廠驗 (舊系統欄位) ===
    is_factory_inspection = fields.Boolean(
        string='是否廠驗',
        default=False,
        tracking=True,
        help='舊系統欄位: isFactoryInspection')

    factory_inspection_date = fields.Date(
        string='廠驗日期',
        tracking=True,
        help='舊系統欄位: factoryInspectionDate')

    factory_inspection_note = fields.Text(
        string='廠驗備註')

    # === 取樣試驗 (舊系統欄位) ===
    is_test = fields.Boolean(
        string='是否取樣試驗',
        default=False,
        tracking=True,
        help='舊系統欄位: isTest')

    test_unit = fields.Char(
        string='預定試驗單位',
        tracking=True,
        help='舊系統欄位: testUnit')

    # === 歸檔 (舊系統欄位) ===
    archive_number = fields.Char(
        string='歸檔編號',
        tracking=True,
        help='舊系統欄位: archiveNumber')

    archive_note = fields.Text(
        string='備註',
        help='備註')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '編輯中'),
        ('done', '已完成'),
    ], string='狀態',
       default='draft',
       required=True,
       tracking=True,
       index=True)

    # === 附件 ===
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'review_application_attachment_rel',
        'review_id',
        'attachment_id',
        string='送審文件')

    def _attachment_default_category(self):
        """送審文件 → 12-文書資料 / 08-送審管制 / 02-材料

        2026-08-11 從父分類 08-送審管制 下移一層，與計畫書管制表
        （supervision.plan.control → 01-計畫書）分開歸檔。既有附件的分類不受
        影響（mixin 只在分類空白時才填），只有之後上傳的會歸到 02-材料。
        """
        return self.env.ref(
            'construction_supervision_base.cat_12_08_02',
            raise_if_not_found=False) or super()._attachment_default_category()

    def _attachment_folder_label(self):
        """資料夾名稱＝「送審日期 材料名稱」，例如「20260815 預拌混凝土」。

        2026-08-20 依實際歸檔習慣：一筆送審一個自己的資料夾，名稱是日期＋材料名。
        日期優先取實際送審日，沒有就取預定日；都沒有就只用材料名稱
        （之後補了日期也不會自動改名，避免下次上傳又生一個新資料夾）。

        ⚠️ 這是依「看到的一種做法」訂的，公司內部尚無統一習慣。
        要改只需改這個方法。
        """
        self.ensure_one()
        date = self.final_review_date or self.expected_review_date
        parts = [date.strftime('%Y%m%d') if date else '', (self.name or '').strip()]
        return ' '.join(p for p in parts if p) or f'送審 {self.id}'

    def _attachment_default_folder(self):
        """送審文件 → 12-文書資料 / 08-送審管制 / 02-材料 / <日期 材料名稱>

        路徑由分類的祖先鏈推出，不寫死中文字串（分類改名會自動跟著改）。
        """
        return self._attachment_category_folder()

    attachment_count = fields.Integer(
        string='附件數',
        compute='_compute_attachment_count')

    @api.depends('attachment_ids')
    def _compute_attachment_count(self):
        for record in self:
            record.attachment_count = len(record.attachment_ids)

    # === 追蹤欄位 ===
    done_date = fields.Datetime(
        string='完成時間',
        readonly=True)

    done_by = fields.Many2one(
        'res.users',
        string='完成人',
        readonly=True)

    # === 計算欄位 ===
    @api.depends('sequence_code', 'name')
    def _compute_display_name(self):
        for record in self:
            if record.sequence_code and record.sequence_code != '/':
                record.display_name = f'[{record.sequence_code}] {record.name}'
            else:
                record.display_name = record.name or ''

    # === 約束 ===
    @api.constrains('expected_review_date', 'final_review_date')
    def _check_review_dates(self):
        for record in self:
            if record.expected_review_date and record.final_review_date:
                if record.final_review_date < record.expected_review_date:
                    # 允許提前送審，只做提醒
                    pass



    # === 狀態動作 ===
    def action_done(self):
        """完成記錄"""
        for record in self:
            if record.state != 'draft':
                raise UserError('只有編輯中的記錄可以完成')

            # 產生送審編號
            if record.sequence_code == '/':
                record.sequence_code = self.env['ir.sequence'].next_by_code(
                    'supervision.review.application') or '/'

            record.write({
                'state': 'done',
                'done_date': fields.Datetime.now(),
                'done_by': self.env.uid,
            })

    def action_reset_draft(self):
        """重設為編輯中"""
        for record in self:
            if record.state != 'done':
                raise UserError('只有已完成的記錄可以重設為編輯中')
            record.write({
                'state': 'draft',
                'done_date': False,
                'done_by': False,
            })

    # === 檢視動作 ===
    def action_view_attachments(self):
        """查看附件"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '送審文件',
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.attachment_ids.ids)],
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
            },
        }

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('sequence_code', '/') == '/':
                # 送審編號在送審時產生，建立時先保持 /
                pass
        return super().create(vals_list)

    def unlink(self):
        for record in self:
            if record.state == 'done':
                raise UserError('已完成的送審記錄不可刪除，請先重設為編輯中')
        return super().unlink()

    def copy(self, default=None):
        default = dict(default or {})
        default.update({
            'sequence_code': '/',
            'state': 'draft',
            'done_date': False,
            'done_by': False,
            'final_review_date': False,
            'review_date': False,
            'final_review_result': False,
            'review_comment': False,
        })
        return super().copy(default)

    # === 名稱搜尋 ===
    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        if name:
            domain = [
                '|', '|',
                ('sequence_code', operator, name),
                ('name', operator, name),
                ('no', operator, name)
            ] + domain
        return self._search(domain, limit=limit, order=order)
