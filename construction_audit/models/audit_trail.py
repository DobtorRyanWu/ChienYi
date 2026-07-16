# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
import json


class AuditTrail(models.Model):
    """
    操作軌跡記錄

    設計特點：
    - 記錄系統中重要操作的完整軌跡
    - 支援多種操作類型：建立、修改、狀態變更、刪除
    - 記錄變更前後的值
    - 不可修改或刪除，確保稽核完整性
    """
    _name = 'audit.trail'
    _description = '操作軌跡'
    _order = 'create_date desc, id desc'
    _rec_name = 'display_name'

    # === 操作類型 ===
    operation_type = fields.Selection([
        ('create', '建立'),
        ('write', '修改'),
        ('state_change', '狀態變更'),
        ('unlink', '刪除'),
    ], string='操作類型', required=True, readonly=True, index=True)

    # === 來源資訊 ===
    model_id = fields.Many2one(
        'ir.model', string='模型',
        required=True, readonly=True, ondelete='cascade', index=True)

    model_name = fields.Char(
        string='模型名稱', related='model_id.model',
        store=True, readonly=True)

    model_description = fields.Char(
        string='模型說明', related='model_id.name',
        store=True, readonly=True)

    res_id = fields.Integer(
        string='記錄 ID', required=True, readonly=True, index=True)

    res_name = fields.Char(
        string='記錄名稱', readonly=True,
        help='操作時的記錄名稱')

    # === 操作者資訊 ===
    user_id = fields.Many2one(
        'res.users', string='操作者',
        required=True, readonly=True, index=True,
        default=lambda self: self.env.user)

    company_id = fields.Many2one(
        'res.company', string='公司',
        required=True, readonly=True,
        default=lambda self: self.env.company)

    # === 變更內容 ===
    old_values = fields.Text(
        string='變更前', readonly=True,
        help='JSON 格式的變更前值')

    new_values = fields.Text(
        string='變更後', readonly=True,
        help='JSON 格式的變更後值')

    changed_fields = fields.Char(
        string='變更欄位', readonly=True,
        help='逗號分隔的變更欄位列表')

    # === 狀態變更專用 ===
    old_state = fields.Char(
        string='原狀態', readonly=True)

    new_state = fields.Char(
        string='新狀態', readonly=True)

    # === 備註 ===
    note = fields.Text(
        string='備註', readonly=True)

    # === 顯示名稱 ===
    display_name = fields.Char(
        string='顯示名稱', compute='_compute_display_name', store=True)

    @api.depends('operation_type', 'model_description', 'res_name', 'create_date')
    def _compute_display_name(self):
        operation_labels = {
            'create': '建立',
            'write': '修改',
            'state_change': '狀態變更',
            'unlink': '刪除',
        }
        for record in self:
            operation = operation_labels.get(record.operation_type, record.operation_type)
            model_desc = record.model_description or record.model_name
            res_name = record.res_name or f'ID: {record.res_id}'
            date_str = record.create_date.strftime('%Y-%m-%d %H:%M') if record.create_date else ''
            record.display_name = f'[{operation}] {model_desc} - {res_name} ({date_str})'

    # === 格式化顯示 ===
    old_values_display = fields.Text(
        string='變更前 (格式化)', compute='_compute_values_display')

    new_values_display = fields.Text(
        string='變更後 (格式化)', compute='_compute_values_display')

    @api.depends('old_values', 'new_values')
    def _compute_values_display(self):
        for record in self:
            record.old_values_display = record._format_values(record.old_values)
            record.new_values_display = record._format_values(record.new_values)

    def _format_values(self, values_json):
        """將 JSON 值格式化為可讀的文字"""
        if not values_json:
            return ''
        try:
            values = json.loads(values_json)
            lines = []
            for field_name, value in values.items():
                if isinstance(value, dict):
                    # Many2one 欄位
                    display_value = value.get('display_name', value.get('id', str(value)))
                elif isinstance(value, list):
                    # Many2many/One2many 欄位
                    display_value = ', '.join([str(v) for v in value])
                elif isinstance(value, bool):
                    display_value = '是' if value else '否'
                elif value is None:
                    display_value = '(空)'
                else:
                    display_value = str(value)
                lines.append(f'{field_name}: {display_value}')
            return '\n'.join(lines)
        except (json.JSONDecodeError, TypeError):
            return values_json

    # === 防止修改和刪除 ===
    def write(self, vals):
        raise UserError('操作軌跡記錄不可修改')

    def unlink(self):
        raise UserError('操作軌跡記錄不可刪除')

    # === 建立方法 ===
    @api.model
    def log_operation(self, model_name, res_id, operation_type,
                      old_values=None, new_values=None,
                      old_state=None, new_state=None,
                      res_name=None, note=None, changed_fields=None):
        """
        記錄操作軌跡

        Args:
            model_name: 模型技術名稱 (如 'project.project')
            res_id: 記錄 ID
            operation_type: 操作類型 (create/write/state_change/unlink)
            old_values: 變更前的值 (dict)
            new_values: 變更後的值 (dict)
            old_state: 原狀態
            new_state: 新狀態
            res_name: 記錄名稱
            note: 備註
            changed_fields: 變更的欄位列表

        Returns:
            audit.trail 記錄
        """
        # 取得模型 ID
        model = self.env['ir.model'].sudo().search([('model', '=', model_name)], limit=1)
        if not model:
            return self.env['audit.trail']

        # 準備變更值 JSON
        old_values_json = json.dumps(old_values, ensure_ascii=False, default=str) if old_values else None
        new_values_json = json.dumps(new_values, ensure_ascii=False, default=str) if new_values else None

        # 準備變更欄位字串
        changed_fields_str = ', '.join(changed_fields) if changed_fields else None

        # 使用 sudo 建立記錄，繞過 write 限制
        vals = {
            'model_id': model.id,
            'res_id': res_id,
            'res_name': res_name,
            'operation_type': operation_type,
            'user_id': self.env.user.id,
            'company_id': self.env.company.id,
            'old_values': old_values_json,
            'new_values': new_values_json,
            'changed_fields': changed_fields_str,
            'old_state': old_state,
            'new_state': new_state,
            'note': note,
        }

        # 直接使用 SQL 插入，繞過 ORM 限制
        return self.sudo().with_context(audit_trail_create=True).create(vals)

    @api.model_create_multi
    def create(self, vals_list):
        """覆寫建立方法，只允許內部建立"""
        if not self.env.context.get('audit_trail_create'):
            raise UserError('請使用 log_operation 方法記錄操作軌跡')
        # 繞過 write 限制
        return super(AuditTrail, self.sudo()).create(vals_list)
