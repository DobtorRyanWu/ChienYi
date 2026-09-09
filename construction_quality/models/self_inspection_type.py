# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


# 檢查時機的預設選項（＝ 18.0.4.9.0 以前 inspection_timing Selection 的值域）。
# 第三欄是 legacy_code，**只給資料遷移用**（把舊 Selection 的值對到新記錄）。
# 匯入與日常操作一律以 name 為準 —— 與 self.inspection.type.stage 的
# legacy_code(stage1/2/3) 同一個角色，手動新增的時機請留空。
DEFAULT_TIMINGS = [
    ('hold_point', '查驗停留點', 10),
    ('random', '隨機抽查', 20),
    ('before', '施工前檢查', 30),
    ('during', '施工中檢查', 40),
    ('after', '施工完成檢查', 50),
]
DEFAULT_TIMING_CODES = [c for c, _n, _s in DEFAULT_TIMINGS]


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

    # === 檢查時機 ===
    # 掛在檢查類型底下而非做成全域主檔，因為各家紙本表格的選項組本來就不同，
    # 連文字都不一樣：逸峰「施工完成檢查」vs 川易「施工後檢查」，
    # 監造抽查類則整組換成「查驗停留點／隨機抽查」。
    # 檢查類型本身已有 project_id，故「不同工程選項不同」自然成立。
    timing_ids = fields.One2many(
        'self.inspection.type.timing', 'type_id',
        string='檢查時機',
        copy=True,  # 複製檢查類型時一併複製（One2many 預設不複製）
        default=lambda self: self._default_timing_ids(),
        help='此檢查類型表頭「檢查時機」那一列可勾選的項目，紙本上可以同時勾多個'
             '（例如施工中＋施工完成）。名稱請原樣照紙本印的字填，'
             '匯入與列印都以名稱為準')

    @api.model
    def _default_timing_ids(self):
        """新類型預設帶原本 Selection 的那 5 個選項。

        與 _default_stage_ids 同樣只在 vals 未給 timing_ids 時生效，
        所以匯入時傳了自訂時機不會多出這 5 筆。
        """
        return [
            Command.create({'name': name, 'sequence': seq, 'legacy_code': code})
            for code, name, seq in DEFAULT_TIMINGS
        ]

    # === 量測區塊（表尾「丈量___位置…□合格□不合格」那一段）===
    # 定義見 self_inspection_measure.py。掛在類型底下、可以有多個，
    # 與查驗段落／檢查時機同一個形狀。沒有這一段的檢查類型就不要建列。
    measure_ids = fields.One2many(
        'self.inspection.type.measure', 'type_id',
        string='量測區塊',
        copy=True,  # 複製檢查類型時一併複製（One2many 預設不複製）
        help='紙本檢查項目表格「外面、下方」的那一段。'
             '27 種檢查表裡只有鋼筋有，其他類型不必建')

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


class SelfInspectionTypeTiming(models.Model):
    """
    自主檢查類型檢查時機

    設計說明：
    - 對應紙本表頭「檢查時機」那一列的勾選框，實測會同時勾多個
      （111年度西區水利 逸峰營造裂縫修補表：施工中＋施工完成）
    - 每個檢查類型有自己的一組，各類型不共用 —— 各家表格的選項組不同，
      連用字都不同（「施工完成檢查」vs「施工後檢查」）
    - 注意與「查驗段落」self.inspection.type.stage 區分：
      時機是整張檢查表的表頭屬性，段落是逐項的分組，兩者不同維度
    """
    _name = 'self.inspection.type.timing'
    _description = '自主檢查類型檢查時機'
    _order = 'sequence, id'

    type_id = fields.Many2one(
        'self.inspection.type',
        string='檢查類型',
        required=True,
        ondelete='cascade',
        index=True)

    name = fields.Char(
        string='時機名稱',
        required=True,
        help='原樣照紙本表頭印的字，例如：施工完成檢查／施工後檢查')

    sequence = fields.Integer(
        string='排序',
        default=10)

    legacy_code = fields.Char(
        string='舊代碼',
        copy=False,
        index=True,
        help='資料遷移用：hold_point/random/before/during/after（18.0.4.9.0 以前的'
             'inspection_timing 值域）。手動新增的時機請留空 —— 匯入是用「時機名稱」'
             '對應的，不需要代碼')

    # === SQL 約束 ===
    _sql_constraints = [
        ('name_type_uniq', 'UNIQUE(type_id, name)',
         '同一檢查類型內的時機名稱不可重複！'),
        ('legacy_code_type_uniq', 'UNIQUE(type_id, legacy_code)',
         '同一檢查類型內的舊代碼不可重複！'),
    ]

    @api.ondelete(at_uninstall=False)
    def _unlink_except_in_use(self):
        """時機已被檢查記錄勾選時不可刪除。

        與 stage 同樣用 @api.ondelete 而非 FK restrict：刪整個檢查類型時
        DB 會 cascade 掉本表，不走 ORM unlink，故此守門不會誤觸發。
        """
        for model in ('general.self.inspection',
                      'reservation.self.inspection'):
            Model = self.env.get(model)
            if Model is None:
                continue
            count = Model.sudo().search_count([
                ('inspection_timing_ids', 'in', self.ids)
            ])
            if count:
                raise UserError(
                    '此檢查時機已被 %s 筆「%s」勾選，請先取消勾選再刪除。'
                    % (count, Model._description))


class SelfInspectionTypeStage(models.Model):
    """
    自主檢查類型查驗段落

    設計說明：
    - 對應抽查紀錄表表格內的段落標題（一 廠商自主檢查／二 施工中／三 銑刨作業…）
    - 每個檢查類型有自己的一組段落，各類型不共用
      （瀝青混凝土 6 段、模板 4 段、測量放樣 3 段）
    - 注意與「檢查時機」self.inspection.type.timing 區分：後者是整張檢查表
      表頭的屬性（查驗停留點／施工前後檢查），段落是逐項的分組，兩者不同維度
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

    # === 本段落底下的檢查項目 ===
    # 這是 self.inspection.type.item.stage_id 的反向關聯（不新增資料表、不新增欄位）。
    # 存在的理由是「新建的檢查類型尚未儲存時也要能設定項目」：
    # 項目的 stage_id 是 Many2one，下拉走伺服器 name_search，未儲存的段落只是
    # 虛擬 NewId、DB 查不到，所以永遠選不到。改成從段落底下直接新增項目，
    # 走的是純巢狀 One2many（父→子的包含關係），Odoo 前端本來就支援未儲存狀態。
    item_ids = fields.One2many(
        'self.inspection.type.item', 'stage_id',
        string='檢查項目',
        copy=False,  # 複製檢查類型時，項目由 SelfInspectionType.copy() 統一重建
        help='屬於本段落的預設檢查項目')

    item_count = fields.Integer(
        string='項目數',
        compute='_compute_item_count')

    @api.depends('item_ids')
    def _compute_item_count(self):
        for stage in self:
            stage.item_count = len(stage.item_ids)

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

    @api.model_create_multi
    def create(self, vals_list):
        """從段落底下新增項目時，自動補上 type_id。

        走 stage.item_ids 建立時，ORM 只會帶 stage_id（那是 One2many 的反向欄位），
        不會帶 type_id，而 type_id 是 required —— 沒補就會直接建不起來。
        巢狀儲存的順序是「先建類型 → 再建段落 → 最後建項目」，所以走到這裡時
        stage_id 已經是真實 id，browse 得到。

        呼叫端明確給的 type_id 優先（例如 type.default_item_ids 那條路徑，
        以及 SelfInspectionType.copy() 重建項目時）。
        """
        Stage = self.env['self.inspection.type.stage']
        for vals in vals_list:
            if not vals.get('type_id') and vals.get('stage_id'):
                vals['type_id'] = Stage.browse(vals['stage_id']).type_id.id
        return super().create(vals_list)

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
