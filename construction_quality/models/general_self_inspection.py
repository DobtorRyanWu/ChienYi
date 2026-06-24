# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class GeneralSelfInspection(models.Model):
    """
    一般式自主檢查

    設計說明：
    - 獨立於通報單的自主檢查記錄
    - 用於一般式工程的品質自主檢查
    - 支援多階段查驗與缺失追蹤
    """
    _name = 'general.self.inspection'
    _description = '一般式自主檢查'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'photo.sync.mixin']
    _order = 'inspection_date desc, id desc'
    _rec_name = 'sub_project_name'   # 以分項工程名稱顯示，較易辨識是哪張檢查單

    # === 基本資料 ===
    name = fields.Char(
        string='檢查編號',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('general.self.inspection') or '/')

    # === 工程關聯 ===
    project_id = fields.Many2one(
        'supervision.project',
        string='所屬工程',
        required=True,
        tracking=True,
        domain="[('project_type', '=', 'general')]")

    task_id = fields.Many2one(
        'project.task',
        string='關聯工項',
        domain="[('project_id', '=', project_id)]",
        help='此檢查關聯的契約工項')

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='project_id.company_id',
        store=True)

    # === 檢查資訊 ===
    inspection_type_id = fields.Many2one(
        'self.inspection.type',
        string='自主檢查類型',
        required=True,
        tracking=True)

    sub_project_name = fields.Char(
        string='分項工程名稱',
        required=True,
        help='施作項目名稱')

    inspection_date = fields.Date(
        string='檢查日期',
        required=True,
        default=fields.Date.today,
        tracking=True)

    inspection_location = fields.Char(
        string='檢查位置',
        help='具體施工位置')

    # === 廠商資訊 ===
    contractor_company_id = fields.Many2one(
        'res.company',
        string='承攬廠商',
        domain="[('company_type', '=', 'contractor')]")

    contractor_name = fields.Char(
        string='承攬廠商名稱',
        compute='_compute_contractor_name',
        store=True)

    subcontractor_name = fields.Char(
        string='協力廠商')

    @api.depends('contractor_company_id')
    def _compute_contractor_name(self):
        for record in self:
            record.contractor_name = record.contractor_company_id.name if record.contractor_company_id else ''

    # === 檢查時機 ===
    inspection_timing = fields.Selection([
        ('hold_point', '查驗停留點'),
        ('before', '施工前檢查'),
        ('during', '施工中檢查'),
        ('after', '施工完成檢查'),
    ], string='檢查時機', default='during', tracking=True)

    # === 檢查人員 ===
    inspector_id = fields.Many2one(
        'res.users',
        string='填表人',
        default=lambda self: self.env.uid,
        tracking=True)

    supervisor_id = fields.Many2one(
        'res.users',
        string='監造人員',
        help='監造確認人員')

    responsible_user_id = fields.Many2one(
        'res.users',
        string='自主檢查負責人',
        tracking=True,
        help='本檢查的負責人；預設繼承工程案件的「自主檢查負責人」，可於本筆覆寫')

    # === 檢查項目 ===
    checklist_ids = fields.One2many(
        'general.self.inspection.item', 'inspection_id',
        string='檢查項目')

    # === 檢查結果 ===
    has_defect = fields.Boolean(
        string='是否有缺失',
        compute='_compute_has_defect',
        store=True,
        tracking=True)

    defect_count = fields.Integer(
        string='缺失項數',
        compute='_compute_has_defect',
        store=True)

    overall_result = fields.Selection([
        ('pass', '合格'),
        ('conditional_pass', '條件合格'),
        ('fail', '不合格'),
    ], string='整體結果', compute='_compute_overall_result', store=True)

    @api.depends('checklist_ids.check_result')
    def _compute_has_defect(self):
        for record in self:
            defect_items = record.checklist_ids.filtered(
                lambda x: x.check_result == 'defect')
            record.defect_count = len(defect_items)
            record.has_defect = record.defect_count > 0

    @api.depends('checklist_ids.check_result')
    def _compute_overall_result(self):
        for record in self:
            if not record.checklist_ids:
                record.overall_result = False
            elif any(item.check_result == 'defect' for item in record.checklist_ids):
                record.overall_result = 'fail'
            elif all(item.check_result in ('pass', 'na') for item in record.checklist_ids):
                record.overall_result = 'pass'
            else:
                record.overall_result = 'conditional_pass'

    # === 附件 ===
    photo_ids = fields.Many2many(
        'ir.attachment',
        'general_inspection_photo_rel',
        'inspection_id', 'attachment_id',
        string='檢查照片')

    attachment_ids = fields.Many2many(
        'ir.attachment',
        'general_inspection_attachment_rel',
        'inspection_id', 'attachment_id',
        string='相關附件')

    # === 備註 ===
    note = fields.Text(string='備註說明')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('inspected', '已檢查'),
        ('confirmed', '已確認'),
        ('closed', '結案'),
    ], string='狀態', default='draft', tracking=True)

    # === 動作方法 ===
    def action_inspect(self):
        """完成檢查"""
        for record in self:
            if not record.checklist_ids:
                raise UserError('請先填寫檢查項目')
            record.state = 'inspected'

    def action_confirm(self):
        """監造確認"""
        for record in self:
            if record.state != 'inspected':
                raise UserError('只有已檢查狀態可以確認')
            record.write({
                'state': 'confirmed',
                'supervisor_id': self.env.uid,
            })

    def action_close(self):
        """結案"""
        for record in self:
            if record.state != 'confirmed':
                raise UserError('只有已確認狀態可以結案')
            if record.has_defect:
                raise UserError('尚有缺失未改善，無法結案')
            record.state = 'closed'

    def action_reset_draft(self):
        """重設為草稿"""
        for record in self:
            if record.state not in ('draft', 'inspected'):
                raise UserError('只有草稿或已檢查狀態可以重設')
            record.state = 'draft'

    @api.onchange('inspection_type_id')
    def _onchange_inspection_type_id(self):
        """自動帶入分項工程名稱"""
        if self.inspection_type_id:
            self.sub_project_name = self.inspection_type_id.name

    def action_load_default_items(self):
        """載入預設檢查項目"""
        self.ensure_one()
        if not self.inspection_type_id:
            raise UserError('請先選擇自主檢查類型')

        if self.checklist_ids:
            raise UserError('已有檢查項目，如需重新載入請先清除')

        items_vals = []
        for item in self.inspection_type_id.default_item_ids:
            items_vals.append(Command.create({
                'sequence': item.sequence,
                'type_item_id': item.id,
                'check_item': item.name,
                'design_standard': item.check_standard,
                'stage': item.stage,
                'note': item.note,
            }))

        if items_vals:
            self.checklist_ids = items_vals

        return True

    @api.onchange('project_id')
    def _onchange_project_id_responsible(self):
        """選工程案件時，由工程案件帶入預設「自主檢查負責人」（可手動覆寫）"""
        if self.project_id:
            self.responsible_user_id = self.project_id._get_activity_user('inspection')

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('general.self.inspection') or '/'
            # 未指定負責人時，由工程案件的「自主檢查負責人」帶入
            if not vals.get('responsible_user_id') and vals.get('project_id'):
                user = self.env['supervision.project'].browse(
                    vals['project_id'])._get_activity_user('inspection')
                if user:
                    vals['responsible_user_id'] = user.id
        return super().create(vals_list)
    
    # === 照片自動同步配置 ===
    def _get_photo_sync_config(self):
        """配置照片同步規則"""
        return {
            'photo_ids': {
                'source_model': 'inspection',
                'name_prefix': '檢查照片',
                'description_template': '檢查類型：{record.inspection_type_id.name}\n檢查地點：{record.inspection_location}',
                'location_field': 'inspection_location',
                'auto_tag': '自主檢查',
            },
        }

    # === 關聯照片（反向 from supervision.photo.source_id） ===
    related_photo_ids = fields.Many2many(
        'supervision.photo',
        compute='_compute_related_photo_ids',
        string='關聯照片',
        help='來源為此自主檢查的照片（透過 supervision.photo.source_id 反查）')

    related_photo_count = fields.Integer(
        string='照片數',
        compute='_compute_related_photo_ids')

    @api.depends()
    def _compute_related_photo_ids(self):
        Photo = self.env['supervision.photo']
        for rec in self:
            if not rec.id:
                rec.related_photo_ids = False
                rec.related_photo_count = 0
                continue
            photos = Photo.search([
                ('source_model', '=', 'inspection'),
                ('source_id', '=', rec.id),
            ])
            rec.related_photo_ids = photos
            rec.related_photo_count = len(photos)


class GeneralSelfInspectionItem(models.Model):
    """
    一般式自主檢查項目

    設計說明：
    - 記錄每個檢查項目的詳細結果
    - 支援多階段查驗
    """
    _name = 'general.self.inspection.item'
    _description = '一般式自主檢查項目'
    _order = 'sequence, id'
    _rec_name = 'check_item'   # 顯示檢查項目文字，避免 M2O 顯示成 model,id

    # === 關聯 ===
    inspection_id = fields.Many2one(
        'general.self.inspection',
        string='自主檢查',
        required=True,
        ondelete='cascade')

    # === 階段 ===
    stage = fields.Selection([
        ('stage1', '施工前'),
        ('stage2', '施工中'),
        ('stage3', '施工後'),
    ], string='查驗階段', default='stage1')

    sequence = fields.Integer(
        string='序號',
        default=10)

    # === 檢查內容 ===
    type_item_id = fields.Many2one(
        'self.inspection.type.item',
        string='檢查項目',
        domain="[('type_id', '=', parent.inspection_type_id), ('stage', '=', stage)]",
        help='從自主檢查類型的對應查驗階段中選擇')

    check_item = fields.Char(
        string='檢查項目',
        required=True)

    design_standard = fields.Text(
        string='設計圖說、規範之管理標準(定性定量)')

    actual_result = fields.Text(
        string='實際檢查情形')

    # === 檢查結果 ===
    check_result = fields.Selection([
        ('pass', '檢查合格'),
        ('defect', '有缺失需改正'),
        ('na', '無此項目'),
    ], string='檢查成果', default='pass')

    # === 缺失關聯 ===
    defect_id = fields.Many2one(
        'supervision.defect',
        string='關聯缺失單',
        help='若有缺失，可關聯 NCR 缺失單')

    # === 備註 ===
    note = fields.Text(string='備註')

    @api.onchange('type_item_id')
    def _onchange_type_item_id(self):
        """選擇檢查項目後自動帶入項目名稱與設計圖說"""
        if self.type_item_id:
            self.check_item = self.type_item_id.name
            self.design_standard = self.type_item_id.check_standard

    @api.onchange('stage')
    def _onchange_stage(self):
        """查驗階段變更時，若已選的項目不屬於新階段則清除"""
        if self.type_item_id and self.type_item_id.stage != self.stage:
            self.type_item_id = False
