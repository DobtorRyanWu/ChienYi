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
        'supervision.project',
        string='所屬工程',
        help='將此檢查類型設定綁定於特定工程案件')

    # === 關聯契約工項 ===
    task_ids = fields.Many2many(
        'project.task',
        'inspection_type_task_rel',
        'type_id',
        'task_id',
        string='關聯契約工項',
        domain="[('supervision_project_id', '=', project_id), ('is_summary_item', '=', False)]",
        help='此檢查類型適用的契約工項')

    # === 說明 ===
    description = fields.Text(string='類型說明')

    # === 預設檢查項目 ===
    default_item_ids = fields.One2many(
        'self.inspection.type.item', 'type_id',
        string='預設檢查項目',
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
        ('code_unique', 'UNIQUE(code)',
         '類型代碼必須唯一！'),
    ]

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


class SelfInspectionTypeItem(models.Model):
    """
    自主檢查類型預設項目

    設計說明：
    - 作為自主檢查的預設樣板項目
    - 新增檢查時可快速帶入
    """
    _name = 'self.inspection.type.item'
    _description = '自主檢查類型預設項目'
    _order = 'sequence, id'

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

    stage = fields.Selection([
        ('stage1', '施工前'),
        ('stage2', '施工中'),
        ('stage3', '施工後'),
    ], string='查驗階段', default='stage1')

    # === 備註 ===
    note = fields.Text(string='備註')


class SelfInspectionTypeCopyWizard(models.TransientModel):
    """
    複製自主檢查類型到其他工程

    設計說明：
    - 將選擇的檢查類型複製到指定工程
    - 複製時清空類型代碼以避免唯一約束冲突
    - 預設檢查項目隨主記錄一起複製
    """
    _name = 'self.inspection.type.copy.wizard'
    _description = '複製自主檢查類型到其他工程'

    project_id = fields.Many2one(
        'supervision.project',
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
            # 複製主記錄，清空 code 避免唯一約束冲突
            # default_item_ids (One2many) 由 copy() 自動複製
            type_record.copy({
                'code': False,
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
