# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class ReservationSelfInspection(models.Model):
    """
    預約式自主檢查 (通報單內)

    設計說明：
    - 綁定於通報單的自主檢查記錄
    - 用於預約式工程的品質自主檢查
    - 與 reservation.notification.slip 關聯
    """
    _name = 'reservation.self.inspection'
    _description = '預約式自主檢查 (通報單內)'
    # photo.sync.mixin 已隨照片資料表收斂退場
    _inherit = ['mail.thread', 'supervision.attachment.mixin']
    _order = 'inspection_date desc, id desc'
    _rec_name = 'sub_project_name'   # 以分項工程名稱顯示，較易辨識是哪張檢查單

    # === 通報單關聯 ===
    slip_id = fields.Many2one(
        'reservation.notification.slip',
        string='所屬通報單',
        required=True,
        ondelete='cascade',
        tracking=True)

    project_id = fields.Many2one(
        'project.project',
        string='所屬工程',
        related='slip_id.project_id',
        store=True)

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='project_id.company_id',
        store=True)

    # === 基本資料 ===
    inspection_no = fields.Char(
        string='編號',
        copy=False,
        default=lambda self: self.env['ir.sequence'].next_by_code('reservation.self.inspection') or '/')

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
    # 與一般式同構，見 general_self_inspection.py 的說明。
    # project_id 是 related slip_id.project_id（store=True），所以 depends 掛 project_id 即可。
    contractor_name = fields.Char(
        string='承攬廠商',
        compute='_compute_contractor_name',
        store=True, readonly=False,
        help='留空自動帶入工程案件的營造廠商；本次確實由其他廠商承攬時才填，填了即覆蓋')

    @api.depends('project_id')
    def _compute_contractor_name(self):
        for record in self:
            record.contractor_name = record.project_id.contractor_company_name or ''

    # === 檢查時機 ===
    # 紙本表單的「檢查時機」其實是兩個度：
    #   ① 檢驗停留點 vs 隨機抽查（抽查方式）
    #   ② 施工前 / 施工中 / 施工完成（時點）
    # 模型合成一個 Selection。廠商自主檢查表只有①（只勾停留點或隨機），
    # 舊值域沒有 random 時，這類表單從紙本搬進來會被 ValueError 擋下。
    inspection_timing = fields.Selection([
        ('hold_point', '查驗停留點'),
        ('random', '隨機抽查'),
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

    responsible_user_id = fields.Many2one(
        'res.users',
        string='自主檢查負責人',
        tracking=True,
        help='本檢查的負責人；預設繼承工程案件的「自主檢查負責人」，可於本筆覆寫')

    # === 檢查項目 ===
    checklist_ids = fields.One2many(
        'reservation.self.inspection.item', 'inspection_id',
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

    # 與一般式同構（general_self_inspection.py）。自主檢查總表的「試驗結果」
    # 合格／不合格就是讀這欄；預約式原本缺這個欄位，導致該表整欄空白。
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
                # 沒有檢查項目＝尚未檢查，不判合格也不判不合格
                record.overall_result = False
            elif any(item.check_result == 'defect' for item in record.checklist_ids):
                record.overall_result = 'fail'
            elif all(item.check_result in ('pass', 'na') for item in record.checklist_ids):
                # na（無此項目）＝本次不需檢查，視為合格
                record.overall_result = 'pass'
            else:
                record.overall_result = 'conditional_pass'

    # === 附件 ===
    # 照片資料表收斂：見 models/supervision_photo.py
    photo_ids = fields.One2many(
        'supervision.photo',
        'reservation_inspection_id',
        string='檢查照片')

    # 2026-08-20 補：本模型原本完全沒有附件欄位，表單卻有「照片與附件」頁籤，
    # 等於只有照片、附件無處可放（一般式自主檢查一直都有）。比照一般式補上。
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'reservation_inspection_attachment_rel',
        'inspection_id', 'attachment_id',
        string='相關附件')

    def _attachment_default_category(self):
        """自主檢查附件 → 12-文書資料 / 07-施工抽查"""
        return self.env.ref(
            'construction_supervision_base.cat_12_07',
            raise_if_not_found=False) or super()._attachment_default_category()

    def _attachment_folder_label(self):
        """資料夾**依自主檢查類型**分，與一般式一致。

        現場是把同一種檢查表（inspection_type_id）的歷次檢查放在一起。
        """
        self.ensure_one()
        return ((self.inspection_type_id.name or '').strip()
                or (self.sub_project_name or '').strip()
                or f'檢查單 {self.id}')

    def _attachment_default_folder(self):
        """自主檢查附件 → 12-文書資料 / 07-施工抽查 / <自主檢查類型>

        末層是同類型歷次檢查共用的資料夾，所以 bind_source 要關掉。
        """
        return self._attachment_category_folder(bind_source=False)

    # === 備註 ===
    note = fields.Text(string='備註說明')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('inspected', '已檢查'),
        ('confirmed', '已確認'),
    ], string='狀態', default='draft', tracking=True)

    # === 動作方法 ===
    def action_inspect(self):
        """完成檢查"""
        for record in self:
            if not record.checklist_ids:
                raise UserError('請先填寫檢查項目')
            record.state = 'inspected'

    def action_confirm(self):
        """確認檢查"""
        for record in self:
            if record.state != 'inspected':
                raise UserError('只有已檢查狀態可以確認')
            record.state = 'confirmed'

    def action_reset_draft(self):
        """重設為草稿"""
        for record in self:
            if record.state not in ('draft', 'inspected'):
                raise UserError('只有草稿或已檢查狀態可以重設')
            record.state = 'draft'

    first_stage_id = fields.Many2one(
        'self.inspection.type.stage',
        string='預設段落',
        compute='_compute_first_stage_id',
        help='供檢查項目內嵌清單的新列帶入預設段落')

    @api.depends('inspection_type_id')
    def _compute_first_stage_id(self):
        for record in self:
            record.first_stage_id = record.inspection_type_id.stage_ids[:1]

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
                'stage_id': item.stage_id.id,
                'note': item.note,
            }))

        if items_vals:
            self.checklist_ids = items_vals

        return True

    @api.onchange('slip_id')
    def _onchange_slip_responsible(self):
        """選通報單(帶出工程案件)時，由工程案件帶入預設「自主檢查負責人」（可覆寫）"""
        project = self.slip_id.project_id
        if project:
            self.responsible_user_id = project._get_activity_user('inspection')

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('inspection_no') or vals.get('inspection_no') == '/':
                vals['inspection_no'] = self.env['ir.sequence'].next_by_code('reservation.self.inspection') or '/'
            # 未指定負責人時，由工程案件(經通報單)的「自主檢查負責人」帶入
            if not vals.get('responsible_user_id') and vals.get('slip_id'):
                project = self.env['reservation.notification.slip'].browse(
                    vals['slip_id']).project_id
                user = project._get_activity_user('inspection') if project else False
                if user:
                    vals['responsible_user_id'] = user.id
        return super().create(vals_list)
    
    # 照片收斂後不再需要 _get_photo_sync_config()


class ReservationSelfInspectionItem(models.Model):
    """
    預約式自主檢查項目

    設計說明：
    - 記錄每個檢查項目的詳細結果
    - 支援多階段查驗
    """
    _name = 'reservation.self.inspection.item'
    _description = '預約式自主檢查項目'
    # stage_sequence 排前面，項目自然依段落分群排好
    _order = 'stage_sequence, sequence, id'
    _rec_name = 'check_item'   # 顯示檢查項目文字，避免 M2O 顯示成 model,id

    # === 關聯 ===
    inspection_id = fields.Many2one(
        'reservation.self.inspection',
        string='自主檢查',
        required=True,
        ondelete='cascade')

    # 段落與樣板項目的 domain 來源。用 stored related 而非 parent.inspection_type_id，
    # 因為本模型有一張獨立 form view（construction_reservation），那裡沒有 parent。
    # ⚠️ 凡是 domain 引用了此欄位的 view，都必須把它放進 view 裡（可 invisible）。
    inspection_type_id = fields.Many2one(
        'self.inspection.type',
        string='自主檢查類型',
        related='inspection_id.inspection_type_id',
        store=True,
        readonly=True,
        index=True)

    # === 查驗段落 ===
    stage_id = fields.Many2one(
        'self.inspection.type.stage',
        string='查驗段落',
        ondelete='set null',
        index=True,
        domain="[('type_id', '=', inspection_type_id)]")

    # 供 _order 使用
    stage_sequence = fields.Integer(
        related='stage_id.sequence',
        store=True,
        index=True,
        string='段落排序')

    sequence = fields.Integer(
        string='序號',
        default=10)

    # === 檢查內容 ===
    type_item_id = fields.Many2one(
        'self.inspection.type.item',
        string='檢查項目',
        domain="[('type_id', '=', inspection_type_id), ('stage_id', '=', stage_id)]",
        help='從自主檢查類型的對應查驗段落中選擇')

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

    # === 備註 ===
    note = fields.Text(string='備註')

    @api.onchange('type_item_id')
    def _onchange_type_item_id(self):
        """選擇檢查項目後自動帶入項目名稱、設計圖說與段落"""
        if self.type_item_id:
            self.check_item = self.type_item_id.name
            self.design_standard = self.type_item_id.check_standard
            if not self.stage_id:
                self.stage_id = self.type_item_id.stage_id

    @api.onchange('stage_id')
    def _onchange_stage_id(self):
        """查驗段落變更時，若已選的項目不屬於新段落則清除"""
        if self.type_item_id and self.type_item_id.stage_id != self.stage_id:
            self.type_item_id = False
