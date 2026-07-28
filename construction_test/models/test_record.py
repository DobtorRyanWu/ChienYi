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
        'project.project',
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

    # === 需求2: 調整欄位名稱 ===
    standard_id = fields.Many2one(
        'supervision.test.standard',
        string='試驗工項',
        required=True,
        ondelete='restrict',
        index=True,
        tracking=True,
        domain="[('project_id', '=', project_id)]",
        help='舊系統欄位: standard')

    # === 需求2+4: 契約工項關聯改為只能選擇已關聯的工項 ===
    task_id = fields.Many2one(
        'project.task',
        string='材料名稱',
        domain="[('id', 'in', available_task_ids)]",
        help='關聯的契約工項（舊系統欄位: payItem）')
    
    available_task_ids = fields.Many2many(
        'project.task',
        compute='_compute_available_task_ids',
        help='可選擇的契約工項清單（來自試驗工項設定的關聯）')
    
    # === 需求3+5: 新增欄位用於 list view 和顯示檢試驗設定資料 ===
    # 不使用 store=True，避免佔用資料庫空間
    contract_qty = fields.Float(
        string='契約數量',
        related='task_id.planned_qty',
        readonly=True,
        digits=(16, 4),
        help='契約工項的預定數量')
    
    test_standard_name = fields.Char(
        string='檢試驗名稱',
        related='standard_id.name',
        readonly=True,
        help='檢試驗項目的名稱')
    
    standard_describe = fields.Text(
        string='依據之方法',
        related='standard_id.describe',
        readonly=True,
        help='檢驗依據的標準方法')
    
    standard_norm = fields.Text(
        string='規範之要求',
        related='standard_id.norm',
        readonly=True,
        help='規範要求的標準值或範圍')
    
    standard_frequency = fields.Text(
        string='規定抽樣頻率',
        related='standard_id.standard',
        readonly=True,
        help='抽樣頻率和最低要求')
    
    standard_unit = fields.Char(
        string='檢查單位',
        related='standard_id.unit',
        readonly=True,
        help='檢驗數量的計量單位')

    # === 進場記錄 (舊系統欄位) ===
    in_site_date = fields.Date(
        string='進場日期',
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

    # === 需求6: 抽樣記錄 (舊系統欄位) - 取樣改為抽樣 ===
    sample_date = fields.Date(
        string='抽樣日期',
        tracking=True,
        help='舊系統欄位: sampleDate')

    sample_quantity = fields.Float(
        string='抽樣數量',
        digits=(16, 4),
        tracking=True,
        help='舊系統欄位: sampleQuantity')

    sample_sum_quantity = fields.Float(
        string='累計抽樣',
        digits=(16, 4),
        compute='_compute_cumulative',
        store=True,
        help='舊系統欄位: sampleSumQuantity')

    sample_rate = fields.Float(
        string='抽樣率 (%)',
        digits=(5, 2),
        compute='_compute_sample_rate',
        store=True,
        help='舊系統欄位: sampleRate，累計抽樣/累計進場 x 100')

    # === 抽驗及會同人員 ===
    owner_member = fields.Char(
        string='業主方人員',
        help='業主方會同人員（手動輸入文字；業主方人員多非系統使用者）')

    supervision_member_ids = fields.Many2many(
        'res.users',
        'test_record_supervision_member_rel',
        'record_id', 'user_id',
        string='監造方人員')

    contractor_member_ids = fields.Many2many(
        'res.users',
        'test_record_contractor_member_rel',
        'record_id', 'user_id',
        string='營造方人員')

    responsible_user_id = fields.Many2one(
        'res.users',
        string='檢試驗負責人',
        tracking=True,
        help='接收檢試驗通知的負責人員')

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

    # === 需求7: 狀態管理改為自動判定的處理狀態 ===
    processing_status = fields.Selection([
        ('not_started', '尚未檢驗'),
        ('in_progress', '已開始檢驗'),
        ('completed', '檢驗完成'),
    ], string='處理狀態',
       compute='_compute_processing_status',
       store=True,
       index=True,
       help='根據進場、抽樣、檢驗結果自動判定')

    # === 系統自動建立相關欄位 ===
    auto_created = fields.Boolean(
        string='系統自動建立',
        default=False,
        readonly=True,
        help='由檢驗需求檢查功能自動建立')
    
    trigger_log_line_id = fields.Many2one(
        'daily.log.line',
        string='觸發日誌',
        readonly=True,
        help='觸發此檢驗的施工日誌明細')
    
    trigger_cumulative_qty = fields.Float(
        string='觸發時累計數量',
        digits=(16, 4),
        readonly=True,
        help='觸發時的累計完成數量')

    # === 備註 ===
    note = fields.Text(string='備註')

    # === 關聯照片（反向 from supervision.photo.source_id） ===
    # supervision.photo 是用 source_model='test' + source_id=<this id> 單向關聯，
    # 不是 ORM Many2one，所以這裡用 computed One2many 反查。
    related_photo_ids = fields.Many2many(
        'supervision.photo',
        compute='_compute_related_photo_ids',
        string='關聯照片',
        help='來源為此檢試驗記錄的照片（透過 supervision.photo.source_id 反查）')

    related_photo_count = fields.Integer(
        string='照片數',
        compute='_compute_related_photo_ids')

    # === 計算欄位 ===

    @api.depends()
    def _compute_related_photo_ids(self):
        """反查 supervision.photo 中 source_model='test' AND source_id=self.id 的照片"""
        Photo = self.env['supervision.photo']
        for rec in self:
            if not rec.id:
                rec.related_photo_ids = False
                rec.related_photo_count = 0
                continue
            photos = Photo.search([
                ('source_model', '=', 'test'),
                ('source_id', '=', rec.id),
            ])
            rec.related_photo_ids = photos
            rec.related_photo_count = len(photos)
    
    @api.depends('standard_id', 'standard_id.task_ids')
    def _compute_available_task_ids(self):
        """需求4: 計算可選擇的工項（來自試驗工項設定的關聯）"""
        for record in self:
            if record.standard_id and record.standard_id.task_ids:
                record.available_task_ids = record.standard_id.task_ids
            else:
                record.available_task_ids = False
    
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
        """計算抽樣率"""
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

    @api.depends(
        'in_site_date', 'in_site_quantity',
        'sample_date', 'sample_quantity',
        'result', 'result_date'
    )
    def _compute_processing_status(self):
        """
        需求7: 自動判定處理狀態
        
        判定標準：
        - 檢驗完成：有檢驗結果（合格或不合格）
        - 已開始檢驗：進場和抽樣資料都完整
        - 尚未檢驗：其他情況
        """
        for record in self:
            # 判定邏輯
            if record.result and record.result != 'pending':
                # 有檢驗結果 = 檢驗完成
                record.processing_status = 'completed'
            elif (record.in_site_date and record.in_site_quantity and
                  record.sample_date and record.sample_quantity):
                # 進場和抽樣資料都完整 = 已開始檢驗
                record.processing_status = 'in_progress'
            else:
                # 其他情況 = 尚未檢驗
                record.processing_status = 'not_started'

    # === 約束檢查 ===
    @api.constrains('in_site_quantity')
    def _check_in_site_quantity(self):
        """進場數量不可為負"""
        for rec in self:
            if rec.in_site_quantity < 0:
                raise ValidationError('進場數量不可為負數')

    @api.constrains('sample_quantity')
    def _check_sample_quantity(self):
        """抽樣數量不可為負"""
        for rec in self:
            if rec.sample_quantity < 0:
                raise ValidationError('抽樣數量不可為負數')

    # 【已移除】原本有一條 _check_sample_date：抽樣日期不可早於進場日期。
    # 移除原因：該規則對「工地抽樣」成立，但對「廠驗（出廠前查驗）」不成立，而廠驗是
    # 台灣公共工程的常規流程 —— 預鑄構件、預拌混凝土等在工廠/拌合廠抽樣檢驗合格後才運抵工地，
    # 抽樣日必然早於進場日；同一批抽樣分多次進場也很常見。
    # 實例：P11001「預力混凝土版樁廠驗」2021-08-26 抽樣，分別於 09-13、09-23 進場（皆合格）。
    # 模型中沒有任何欄位可區分「廠驗」與「工地抽樣」，因此無法寫成正確的條件式約束；
    # 硬性阻擋會讓合法的歷史資料無法建檔。若日後要恢復檢查，必須先新增
    # 「出廠前抽樣」旗標欄位並僅在未勾選時檢查，不要直接把這條加回來。

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        """建立時自動產生編號"""
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('supervision.test.record') or '/'
            # 未指定負責人時，由工程案件的「檢試驗負責人」帶入（程式/Portal 建立也適用）
            if not vals.get('responsible_user_id') and vals.get('project_id'):
                project = self.env['project.project'].browse(vals['project_id'])
                user = project._get_activity_user('test')
                if user:
                    vals['responsible_user_id'] = user.id
        records = super().create(vals_list)
        # 觸發同專案同標準其他記錄的累計重算
        records._trigger_cumulative_recompute()
        # 自動解決相關的 pending 預警
        records._auto_resolve_warnings()
        # 發送建立通知
        records._notify_record_created()
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

    def _notify_record_created(self):
        """建立檢試驗紀錄時發送通知提醒"""
        activity_type = self.env.ref(
            'construction_test.activity_type_test_record_created',
            raise_if_not_found=False,
        )
        if not activity_type:
            return

        # TODO: 權限設計完成後改回 sup_project._get_activity_user('test')
        user = self.env.ref('base.user_admin')

        for rec in self:
            standard_name = rec.standard_id.name or ''
            task_name = rec.task_id.name or ''
            note = (
                f'<p>已建立檢試驗紀錄 <strong>{rec.name}</strong></p>'
                f'<ul>'
                f'<li>試驗工項：{standard_name}</li>'
                f'<li>材料名稱：{task_name}</li>'
                f'</ul>'
            )

            rec.activity_schedule(
                activity_type_id=activity_type.id,
                summary=f'檢試驗紀錄已建立 - {rec.name}',
                note=note,
                user_id=user.id,
            )

            rec.message_post(
                body=note,
                subject=f'檢試驗紀錄已建立 - {rec.name}',
                partner_ids=user.partner_id.ids,
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

    def _auto_resolve_warnings(self):
        """當檢驗記錄建立後，自動解決相關的 pending 預警"""
        TestWarning = self.env['supervision.test.warning']
        for rec in self:
            if not rec.project_id or not rec.standard_id or not rec.task_id:
                continue
            domain = [
                ('project_id', '=', rec.project_id.id),
                ('standard_id', '=', rec.standard_id.id),
                ('task_id', '=', rec.task_id.id),
                ('state', '=', 'pending'),
            ]
            # 自動建立的記錄有 trigger_cumulative_qty，只解決門檻 <= 該值的預警
            # 手動建立的記錄沒有此值，解決所有 pending 預警
            if rec.trigger_cumulative_qty:
                domain.append(('next_threshold_qty', '<=', rec.trigger_cumulative_qty))
            pending_warnings = TestWarning.search(domain)
            if pending_warnings:
                pending_warnings.write({
                    'state': 'done',
                    'handled_by_id': self.env.user.id,
                    'handled_date': fields.Datetime.now(),
                    'note': f'系統自動解決：檢驗記錄 {rec.name} 已建立',
                })

    def unlink(self):
        """刪除記錄"""
        return super().unlink()

    def name_get(self):
        """自訂顯示名稱"""
        result = []
        for rec in self:
            name = rec.name or '/'
            if rec.standard_id:
                name = f'{name} - {rec.standard_id.material}'
            if rec.in_site_date:
                name = f'{name} ({rec.in_site_date})'
            result.append((rec.id, name))
        return result

    @api.onchange('standard_id')
    def _onchange_standard_id(self):
        """當選擇試驗工項時，自動設定專案並清空材料名稱"""
        if self.standard_id:
            if self.standard_id.project_id:
                self.project_id = self.standard_id.project_id
            # 清空材料名稱（task_id），強制使用者重新選擇
            self.task_id = False

    @api.onchange('task_id')
    def _onchange_task_id_check_relation(self):
        """需求4: 檢查選擇的工項是否在關聯清單中"""
        if self.task_id and self.standard_id:
            if self.task_id not in self.standard_id.task_ids:
                self.task_id = False
                return {
                    'warning': {
                        'title': '工項未關聯',
                        'message': (
                            f'選擇的工項未在試驗工項設定中建立關聯！\n\n'
                            f'請先到「檢試驗項目設定」中的「關聯契約工項」頁籤\n'
                            f'建立試驗工項「{self.standard_id.material}」與契約工項的關聯。'
                        ),
                    }
                }

    @api.onchange('project_id')
    def _onchange_project_id(self):
        """當專案變更時，清空試驗工項/材料，並由工程案件帶入預設檢試驗負責人（可手動覆寫）"""
        if self.project_id:
            if self.standard_id and self.standard_id.project_id != self.project_id:
                self.standard_id = False
            self.task_id = False
            # 預設負責人繼承自工程案件的「檢試驗負責人」設定；使用者仍可在本筆改成他人
            self.responsible_user_id = self.project_id._get_activity_user('test')
            return {
                'domain': {
                    'standard_id': [('project_id', '=', self.project_id.id)],
                }
            }

    def action_view_attachments(self):
        """查看附件"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '檢驗報告附件',
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.attachment_ids.ids)],
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
            },
        }
