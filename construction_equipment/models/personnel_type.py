# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PersonnelType(models.Model):
    """
    人員機具設定

    用於定義工地常用的人員類型（技工、大工、小工等）與機具類型
    使用者可以新增自訂類型
    """
    _name = 'personnel.type'
    _description = '人員機具設定'
    _order = 'record_type, sequence, name'

    # === 基本資料 ===
    name = fields.Char(
        string='人員/機具名稱',
        required=True,
        index=True)

    record_type = fields.Selection([
        ('personnel', '人員'),
        ('equipment', '機具'),
    ], string='類型', required=True, default='personnel')

    sequence = fields.Integer(
        string='排序',
        default=10,
        help='控制下拉選單中的顯示順序')

    active = fields.Boolean(
        string='啟用',
        default=True,
        help='停用後將不會出現在下拉選單中')

    code = fields.Char(
        string='代碼',
        help='選填，用於系統整合或報表識別')

    description = fields.Text(
        string='說明',
        help='此人員類型的詳細說明')

    # 預設共用（空白）：日誌下拉依「工程所屬公司」過濾（18.0.1.4.0），若預設帶建立者當下的公司，
    # 在別家公司的工程下建的工種會從那個工程的下拉消失（jt 有 56/58 筆就是這樣建出來的）。
    # 要只給某家公司用時才明確選公司（匯入工具 import_resources.py 一律明寫）。
    company_id = fields.Many2one(
        'res.company',
        string='公司',
        index=True,
        help='空白＝所有公司共用；選了公司＝只出現在該公司工程的人機下拉')

    # === 使用統計 ===
    usage_count = fields.Integer(
        string='使用次數',
        compute='_compute_usage_count',
        help='被引用的人機項目數量')

    # -------------------------------------------------------------------------
    # Compute Methods
    # -------------------------------------------------------------------------

    def _compute_usage_count(self):
        """計算使用次數"""
        ManMachine = self.env['daily.log.man.machine']
        for record in self:
            record.usage_count = ManMachine.search_count([
                ('personnel_type_id', '=', record.id)
            ])

    # -------------------------------------------------------------------------
    # Constraint Methods
    # -------------------------------------------------------------------------

    @api.constrains('name', 'record_type', 'company_id')
    def _check_name_unique(self):
        """確保同一公司內同類型名稱不重複"""
        for record in self:
            domain = [
                ('name', '=', record.name),
                ('record_type', '=', record.record_type),
                ('company_id', '=', record.company_id.id),
                ('id', '!=', record.id)
            ]
            if self.search_count(domain) > 0:
                raise ValidationError(
                    f'「{record.name}」已存在，請勿重複建立。'
                )

    # -------------------------------------------------------------------------
    # CRUD Methods
    # -------------------------------------------------------------------------

    def unlink(self):
        """刪除前檢查是否有使用中的人機項目"""
        for record in self:
            if record.usage_count > 0:
                raise ValidationError(
                    f'「{record.name}」已被 {record.usage_count} 個人機項目使用，'
                    f'無法刪除。建議改為「停用」。'
                )
        return super().unlink()

    # -------------------------------------------------------------------------
    # SQL Constraints
    # -------------------------------------------------------------------------

    _sql_constraints = [
        ('name_type_company_unique',
         'UNIQUE(name, record_type, company_id)',
         '同一公司內同類型名稱不可重複！'),
    ]
