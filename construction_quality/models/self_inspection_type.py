# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class SelfInspectionType(models.Model):
    """
    自主檢查類型

    設計說明：
    - 管理自主檢查表的類型與樣板
    - 預設檢查項目可作為新增檢查時的範本
    - 支援一般式與預約式工程共用
    """
    _name = 'self.inspection.type'
    _description = '自主檢查類型'
    _order = 'sequence, name'

    # === 基本資料 ===
    name = fields.Char(
        string='類型名稱',
        required=True,
        help='例如：鋼筋綁紮、混凝土澆置、模板組立等')

    code = fields.Char(
        string='類型代碼',
        help='類型識別代碼')

    sequence = fields.Integer(
        string='排序',
        default=10)

    active = fields.Boolean(
        string='啟用',
        default=True)

    # === 分類 ===
    category = fields.Selection([
        ('structure', '結構工程'),
        ('civil', '土木工程'),
        ('electrical', '電氣工程'),
        ('mechanical', '機械工程'),
        ('plumbing', '給排水工程'),
        ('fire_protection', '消防工程'),
        ('landscape', '景觀工程'),
        ('finishing', '裝修工程'),
        ('other', '其他'),
    ], string='工程類別', default='structure')

    # === 所屬工程 ===
    project_id = fields.Many2one(
        'project.project',
        string='所屬工程',
        help='將此檢查類型設定綁定於特定工程案件')

    # === 關聯契約工項 ===
    task_ids = fields.Many2many(
        'project.task',
        'inspection_type_task_rel',
        'type_id',
        'task_id',
        string='關聯契約工項',
        copy=False,  # 契約工項因專案而異，不可跨工程複製（Many2many 預設會複製）
        domain="[('supervision_project_id', '=', project_id), ('is_summary_item', '=', False)]",
        help='此檢查類型適用的契約工項')

    # === 說明 ===
    description = fields.Text(string='類型說明')

    # === 原始樣板檔 ===
    template_file = fields.Binary(
        string='檢查表樣板檔',
        attachment=True,  # 存成 ir.attachment，不佔 model row
        help='此檢查類型的原始 docx 樣板檔，供下載參考')
    template_filename = fields.Char(
        string='樣板檔名')

    # === 查驗段落 ===
    stage_ids = fields.One2many(
        'self.inspection.type.stage', 'type_id',
        string='查驗段落',
        copy=True,  # 複製檢查類型時一併複製段落（One2many 預設不複製）
        default=lambda self: self._default_stage_ids(),
        help='此檢查類型的表格分段，例如：廠商自主檢查／施工中／銑刨作業。'
             '對應抽查紀錄表中的「一、二、三…」段落標題')

    @api.model
    def _default_stage_ids(self):
        """新類型預設帶標準三段，確保逐項的段落下拉永不空白。

        注意：default 只在 vals 未給 stage_ids 時生效，
        所以匯入時傳了自訂段落不會多出這三段。
        """
        return [
            Command.create({'name': '施工前', 'sequence': 10, 'legacy_code': 'stage1'}),
            Command.create({'name': '施工中', 'sequence': 20, 'legacy_code': 'stage2'}),
            Command.create({'name': '施工後', 'sequence': 30, 'legacy_code': 'stage3'}),
        ]

    # === 預設檢查項目 ===
    default_item_ids = fields.One2many(
        'self.inspection.type.item', 'type_id',
        string='預設檢查項目',
        copy=True,  # 複製檢查類型時一併複製預設項目（One2many 預設不複製）
        help='新增檢查時可自動帶入的預設項目')

    # === 統計 ===
    inspection_count = fields.Integer(
        string='檢查次數',
        compute='_compute_inspection_count')

    @api.depends()
    def _compute_inspection_count(self):
        """計算使用此類型的檢查次數"""
        GeneralInspection = self.env.get('general.self.inspection')
        ReservationInspection = self.env.get('reservation.self.inspection')

        for record in self:
            count = 0
            if GeneralInspection:
                count += GeneralInspection.search_count([
                    ('inspection_type_id', '=', record.id)
                ])
            if ReservationInspection:
                count += ReservationInspection.search_count([
                    ('inspection_type_id', '=', record.id)
                ])
            record.inspection_count = count

    @api.onchange('project_id')
    def _onchange_project_id(self):
        """所屬工程變更時，清空已關聯的契約工項"""
        if self.task_ids:
            self.task_ids = [(5, 0, 0)]
            return {
                'warning': {
                    'title': '注意',
                    'message': '所屬工程已變更，關聯契約工項已清空，請重新選擇。',
                }
            }

    # === SQL 約束 ===
    _sql_constraints = [
        ('code_project_unique', 'UNIQUE(code, project_id)',
         '同一工程內的類型代碼必須唯一！'),
    ]

    # === CRUD 覆寫 ===
    def copy(self, default=None):
        """複製檢查類型時，讓新項目的段落指向「新類型」的段落。

        問題：stage_ids 與 default_item_ids 都是 copy=True，Odoo 會各自複製，
        但複製出來的項目其 stage_id 仍指向「來源類型」的段落。畫面上看起來
        完全正常（段落名一樣），只有 domain 篩不到、前台掉「未分段」才會露餡。

        解法：先不複製項目（否則 _check_stage_belongs_to_type 會在 flush 時就炸），
        等新段落建好後，用「段落名稱」建立 舊 → 新 的對照再建項目。
        名稱在同一類型內由 UNIQUE(type_id, name) 保證唯一，故可安全當 key。
        """
        default = dict(default or {})
        default.setdefault('default_item_ids', [])
        new_records = super().copy(default)

        Item = self.env['self.inspection.type.item']
        for src, dst in zip(self, new_records):
            stage_map = {s.name: s.id for s in dst.stage_ids}
            vals_list = [{
                'type_id': dst.id,
                'sequence': it.sequence,
                'name': it.name,
                'check_standard': it.check_standard,
                'note': it.note,
                'stage_id': stage_map.get(it.stage_id.name, False),
            } for it in src.default_item_ids]
            if vals_list:
                Item.create(vals_list)
        return new_records

    # === 動作方法 ===
    def action_view_inspections(self):
        """檢視使用此類型的檢查紀錄"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - 檢查紀錄',
            'res_model': 'general.self.inspection',
            'view_mode': 'list,form',
            'domain': [('inspection_type_id', '=', self.id)],
            'context': {'default_inspection_type_id': self.id},
        }


class SelfInspectionTypeStage(models.Model):
    """
    自主檢查類型查驗段落

    設計說明：
    - 對應抽查紀錄表表格內的段落標題（一 廠商自主檢查／二 施工中／三 銑刨作業…）
    - 每個檢查類型有自己的一組段落，各類型不共用
      （瀝青混凝土 6 段、模板 4 段、測量放樣 3 段）
    - 注意與「檢查時機」inspection_timing 區分：後者是整張檢查表的屬性
      （查驗停留點／施工前後檢查），段落是逐項的分組，兩者不同維度
    """
    _name = 'self.inspection.type.stage'
    _description = '自主檢查類型查驗段落'
    _order = 'sequence, id'

    type_id = fields.Many2one(
        'self.inspection.type',
        string='檢查類型',
        required=True,
        ondelete='cascade',
        index=True)

    name = fields.Char(
        string='段落名稱',
        required=True,
        help='例如：廠商自主檢查、材料、儀器、設備機具、銑刨作業、鋪築前置作業')

    sequence = fields.Integer(
        string='排序',
        default=10)

    legacy_code = fields.Char(
        string='舊代碼',
        copy=False,
        index=True,
        help='資料遷移用：stage1/stage2/stage3。手動新增的段落請留空')

    # === SQL 約束 ===
    _sql_constraints = [
        ('name_type_uniq', 'UNIQUE(type_id, name)',
         '同一檢查類型內的段落名稱不可重複！'),
    ]

    @api.ondelete(at_uninstall=False)
    def _unlink_except_in_use(self):
        """段落已被檢查項目引用時不可刪除。

        用 @api.ondelete 而非 FK ondelete='restrict'：刪整個檢查類型時，
        PG 會同時 cascade 刪 item 與 stage 兩張子表，兩條 cascade 的觸發順序
        未定義；若 stage 先被刪，RESTRICT 會炸掉一個本來合法的操作。
        刪類型時 stage 是被 DB cascade 掉的、不走 ORM unlink，故此守門
        正確地不會誤觸發。
        """
        for model in ('self.inspection.type.item',
                      'general.self.inspection.item',
                      'reservation.self.inspection.item'):
            Model = self.env.get(model)
            if Model is None:
                continue
            count = Model.sudo().search_count([('stage_id', 'in', self.ids)])
            if count:
                raise UserError(
                    '此段落已被 %s 筆「%s」引用，請先將那些項目改掛其他段落。'
                    % (count, Model._description))


class SelfInspectionTypeItem(models.Model):
    """
    自主檢查類型預設項目

    設計說明：
    - 作為自主檢查的預設樣板項目
    - 新增檢查時可快速帶入
    """
    _name = 'self.inspection.type.item'
    _description = '自主檢查類型預設項目'
    # stage_sequence 排前面，項目自然依段落分群排好（報表分節、前台分群都不必再排序）
    _order = 'stage_sequence, sequence, id'

    # === 關聯 ===
    type_id = fields.Many2one(
        'self.inspection.type',
        string='檢查類型',
        required=True,
        ondelete='cascade')

    # === 項目資料 ===
    sequence = fields.Integer(
        string='序號',
        default=10)

    name = fields.Char(
        string='檢查項目',
        required=True)

    check_standard = fields.Text(
        string='設計圖說、規範之管理標準(定性/定量)',
        help='設計圖說、規範之管理標準(定性/定量)')

    stage_id = fields.Many2one(
        'self.inspection.type.stage',
        string='查驗段落',
        ondelete='set null',
        index=True,
        domain="[('type_id', '=', type_id)]",
        help='此項目屬於檢查表的哪一段落')

    # 供 _order 使用，讓項目依段落順序自然分群
    stage_sequence = fields.Integer(
        related='stage_id.sequence',
        store=True,
        index=True,
        string='段落排序')

    # === 備註 ===
    note = fields.Text(string='備註')

    @api.constrains('stage_id', 'type_id')
    def _check_stage_belongs_to_type(self):
        """段落必須屬於本項目所屬的檢查類型。

        這是複製檢查類型時「段落沒重指」的最終安全網（見 SelfInspectionType.copy）。
        """
        for rec in self:
            if rec.stage_id and rec.stage_id.type_id != rec.type_id:
                raise ValidationError(
                    '段落「%s」不屬於檢查類型「%s」。'
                    % (rec.stage_id.name, rec.type_id.name))


class SelfInspectionTypeCopyWizard(models.TransientModel):
    """
    複製自主檢查類型到其他工程

    設計說明：
    - 將選擇的檢查類型複製到指定工程
    - 類型代碼一併複製（唯一性已改為「同工程內唯一」，跨工程不衝突）
    - 預設檢查項目 (default_item_ids) 隨主記錄一起複製
    - 關聯契約工項 (task_ids) 因各工程契約不一致，不複製
    """
    _name = 'self.inspection.type.copy.wizard'
    _description = '複製自主檢查類型到其他工程'

    project_id = fields.Many2one(
        'project.project',
        string='目標工程',
        required=True,
        help='將選擇的檢查類型複製到此工程')

    type_ids = fields.Many2many(
        'self.inspection.type',
        string='複製項目',
        readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'type_ids' in fields_list:
            active_ids = self.env.context.get('active_ids', [])
            res['type_ids'] = [(6, 0, active_ids)]
        return res

    def action_copy(self):
        """執行複製操作"""
        if not self.type_ids:
            raise UserError('請先選擇要複製的檢查類型')

        for type_record in self.type_ids:
            # 複製到目標工程：
            # - default_item_ids（預設檢查項目）由欄位 copy=True 一併複製
            # - task_ids（關聯契約工項）由欄位 copy=False 不複製
            # - code 一併保留，因唯一性已改為「同工程內唯一」，跨工程不衝突
            type_record.copy({
                'project_id': self.project_id.id,
            })

        # 跳轉至目標工程的檢查類型列表
        return {
            'type': 'ir.actions.act_window',
            'name': '自主檢查類型',
            'res_model': 'self.inspection.type',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.project_id.id)],
            'context': {'search_default_group_project': 1},
        }
