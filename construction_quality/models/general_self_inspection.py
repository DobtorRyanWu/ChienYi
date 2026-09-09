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
    # photo.sync.mixin 已隨照片資料表收斂退場
    _inherit = ['mail.thread', 'mail.activity.mixin',
                'supervision.attachment.mixin']
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
        'project.project',
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
    # 承攬廠商＝工程案件的營造廠商（純文字）。建檔時帶入、允許就該筆覆寫。
    # 原本是 Many2one('res.company')，但本系統一庫一公司，那個下拉永遠只有一個選項。
    # depends 只掛 project_id、不掛 contractor_company_name 本身 ——
    # 否則工程案件日後改名，會回頭蓋掉已經逐筆填好／覆寫過的值。
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
    # 紙本表頭那一列本來就可以同時勾多個（實測：施工中＋施工完成），
    # 而且各家表格的選項組不同、連用字都不同（「施工完成檢查」vs「施工後檢查」），
    # 所以選項掛在檢查類型底下（self.inspection.type.timing）而非寫死 Selection。
    # 18.0.5.0.0 以前是單選 Selection，值域 hold_point/random/before/during/after。
    inspection_timing_ids = fields.Many2many(
        'self.inspection.type.timing',
        'general_self_inspection_timing_rel',
        'inspection_id',
        'timing_id',
        string='檢查時機',
        tracking=True,
        domain="[('type_id', '=', inspection_type_id)]",
        help='可複選；選項由所選「自主檢查類型」底下的檢查時機決定')

    # 供列印報表、前台顯示與文件樣板取用的文字（原本直接讀 Selection 的 label）
    inspection_timing_display = fields.Char(
        string='檢查時機（文字）',
        compute='_compute_inspection_timing_display',
        store=True)

    @api.depends('inspection_timing_ids', 'inspection_timing_ids.name')
    def _compute_inspection_timing_display(self):
        for record in self:
            record.inspection_timing_display = '、'.join(
                record.inspection_timing_ids.mapped('name'))

    @api.constrains('inspection_timing_ids', 'inspection_type_id')
    def _check_timing_belongs_to_type(self):
        """勾選的時機必須屬於本筆所選的檢查類型。

        沒有這道守門時，改掉檢查類型後舊的勾選會留著卻不再出現在畫面上
        （domain 篩掉了），變成「看不到但列印得出來」的幽靈值。
        """
        for record in self:
            bad = record.inspection_timing_ids.filtered(
                lambda t: t.type_id != record.inspection_type_id)
            if bad:
                raise ValidationError(
                    '檢查時機「%s」不屬於檢查類型「%s」，請重新勾選。'
                    % ('、'.join(bad.mapped('name')),
                       record.inspection_type_id.name or '（未選）'))

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

    # === 量測記錄（表尾「丈量___位置…□合格□不合格」那一段）===
    # 空列＝沒有記錄：紙本預印 4 列、實填 2 列就只建 2 列，不預建空列。
    measure_line_ids = fields.One2many(
        'general.self.inspection.measure.line', 'inspection_id',
        string='量測記錄')

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

    @api.depends('checklist_ids.check_result', 'measure_line_ids.result')
    def _compute_has_defect(self):
        # 量測列的「不合格」一併計入 —— 「這張表有沒有缺失」在語意上包含它。
        # ⚠️ 但缺失單精靈只從檢查項目建（量測列沒有項目名稱可當缺失描述），
        #    所以會有「has_defect 為真、精靈裡沒有可選項目」的情況，
        #    由 construction_general 的精靈給訊息說明，不要給空清單。
        for record in self:
            defect_items = record.checklist_ids.filtered(
                lambda x: x.check_result == 'defect')
            failed_measures = record.measure_line_ids.filtered(
                lambda x: x.result == 'fail')
            record.defect_count = len(defect_items) + len(failed_measures)
            record.has_defect = record.defect_count > 0

    @api.depends('checklist_ids.check_result', 'measure_line_ids.result')
    def _compute_overall_result(self):
        for record in self:
            if not record.checklist_ids and not record.measure_line_ids:
                record.overall_result = False
            elif (any(item.check_result == 'defect' for item in record.checklist_ids)
                  or any(m.result == 'fail' for m in record.measure_line_ids)):
                record.overall_result = 'fail'
            elif all(item.check_result in ('pass', 'na') for item in record.checklist_ids):
                record.overall_result = 'pass'
            else:
                record.overall_result = 'conditional_pass'

    # === 附件 ===
    # 照片資料表收斂：原為 M2M→ir.attachment + photo.sync.mixin 同步，
    # 現在照片就是 supervision.photo 本身（見 models/supervision_photo.py）。
    photo_ids = fields.One2many(
        'supervision.photo',
        'general_inspection_id',
        string='檢查照片')

    attachment_ids = fields.Many2many(
        'ir.attachment',
        'general_inspection_attachment_rel',
        'inspection_id', 'attachment_id',
        string='相關附件')

    def _attachment_default_category(self):
        """自主檢查附件 → 12-文書資料 / 07-施工抽查"""
        return self.env.ref(
            'construction_supervision_base.cat_12_07',
            raise_if_not_found=False) or super()._attachment_default_category()

    def _attachment_folder_label(self):
        """資料夾**依自主檢查類型**分，不是依這張檢查單的單號。

        2026-08-20 依實際歸檔習慣修正：現場是把同一種檢查表
        （inspection_type_id，例如「鋼筋組立自主檢查表」）的歷次檢查放在一起。
        一張單一個資料夾會把樹打碎，也跟紙本習慣對不上。
        """
        self.ensure_one()
        return ((self.inspection_type_id.name or '').strip()
                or (self.sub_project_name or '').strip()
                or f'檢查單 {self.id}')

    def _attachment_default_folder(self):
        """自主檢查附件 → 12-文書資料 / 07-施工抽查 / <自主檢查類型>

        路徑由分類的祖先鏈推出，不寫死中文字串（分類改名會自動跟著改）。
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
        """自動帶入分項工程名稱，並清掉不屬於新類型的檢查時機"""
        if self.inspection_type_id:
            self.sub_project_name = self.inspection_type_id.name
        # 時機是逐類型各一組，換了類型舊勾選必然失效（_check_timing_belongs_to_type
        # 會擋下）。這裡先清掉，讓使用者在畫面上就看到要重新勾。
        self.inspection_timing_ids = [Command.clear()]

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
                user = self.env['project.project'].browse(
                    vals['project_id'])._get_activity_user('inspection')
                if user:
                    vals['responsible_user_id'] = user.id
        return super().create(vals_list)
    
    # 照片收斂後不再需要 _get_photo_sync_config()（沒有「同步」這件事），
    # 也不再需要 related_photo_ids 反查 —— photo_ids 本身就是 supervision.photo。
    related_photo_count = fields.Integer(
        string='照片數',
        compute='_compute_related_photo_count')

    @api.depends('photo_ids')
    def _compute_related_photo_count(self):
        for rec in self:
            rec.related_photo_count = len(rec.photo_ids)


class GeneralSelfInspectionItem(models.Model):
    """
    一般式自主檢查項目

    設計說明：
    - 記錄每個檢查項目的詳細結果
    - 支援多階段查驗
    """
    _name = 'general.self.inspection.item'
    _description = '一般式自主檢查項目'
    # stage_sequence 排前面，項目自然依段落分群排好
    _order = 'stage_sequence, sequence, id'
    _rec_name = 'check_item'   # 顯示檢查項目文字，避免 M2O 顯示成 model,id

    # === 關聯 ===
    inspection_id = fields.Many2one(
        'general.self.inspection',
        string='自主檢查',
        required=True,
        ondelete='cascade')

    # 段落與樣板項目的 domain 來源。用 stored related 而非 parent.inspection_type_id，
    # 因為獨立 form view 沒有 parent（見 construction_reservation 那張 item form）。
    # ⚠️ 凡是 domain 引用了此欄位的 view，都必須把它放進 view 裡（可 invisible），
    #    否則 client 端求不出值、下拉會恆空。
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

    # 註：缺失關聯欄位是 defect_improvement_id（→ general.defect.improvement），
    #     定義在 construction_general/models/general_self_inspection.py，
    #     由「建立缺失」精靈 create.defect.improvement.wizard 寫入。

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


class GeneralSelfInspectionMeasureLine(models.Model):
    """一般式自主檢查量測列。

    句型與值都在 self.inspection.measure.line.mixin，這裡只多一個 inspection_id。
    """
    _name = 'general.self.inspection.measure.line'
    _description = '一般式自主檢查量測列'
    _inherit = ['self.inspection.measure.line.mixin']
    _rec_name = 'rendered'

    inspection_id = fields.Many2one(
        'general.self.inspection',
        string='自主檢查',
        required=True,
        ondelete='cascade',
        index=True)

    @api.constrains('block_id', 'inspection_id')
    def _check_block_belongs_to_type(self):
        """量測區塊必須屬於本筆所選的檢查類型。

        沒有這道守門時，改掉檢查類型後舊的量測列會留著卻不再屬於這張表，
        變成「看不到但列印得出來」的幽靈列 —— 與檢查時機那道守門同一個理由。
        """
        for line in self:
            if line.block_id.type_id != line.inspection_id.inspection_type_id:
                raise ValidationError(
                    '量測區塊「%s」不屬於檢查類型「%s」，請重新選擇。'
                    % (line.block_id.name or '',
                        line.inspection_id.inspection_type_id.name or '（未選）'))
