# -*- coding: utf-8 -*-

import base64
import json
import logging
from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class DocumentTemplate(models.Model):
    """
    文件樣板

    對應舊系統：樣板設定
    業務說明：
    - 管理各類報表輸出樣板 (Excel/Word)
    - 支援系統預設樣板與專案自訂樣板
    - 可上傳、下載、測試樣板
    - 樣板優先順序：專案專屬 > 公司預設 > 系統預設
    """
    _name = 'document.template'
    _description = '文件樣板'
    _order = 'template_type, sequence, id'
    _inherit = ['mail.thread']

    # === 基本資料 ===
    name = fields.Char(
        string='樣板名稱',
        required=True,
        tracking=True,
        help='樣板的顯示名稱')

    sequence = fields.Integer(
        string='排序',
        default=10,
        help='同類型樣板的顯示順序')

    active = fields.Boolean(
        string='啟用',
        default=True,
        tracking=True,
        help='停用後此樣板將不會被使用')

    # === 樣板類型 ===
    template_type = fields.Selection([
        ('daily_log_1', '施工日誌-第一聯'),
        ('daily_log_2', '施工日誌-第二聯'),
        ('self_inspection', '自主檢查表'),
        ('defect_improvement', '缺失改善'),
        ('defect_control', '缺失改善管制表'),
        ('review_control', '送審管制表'),
        ('test_control', '檢(試)驗管制表'),
        ('progress_report', '進度報告'),
        ('progress_schedule', '工程預定進度表'),
        ('estimate_report', '估驗計價表'),
        ('acceptance_report', '驗收報告'),
        ('notification_slip', '通報單'),
        ('material_test', '材料試驗報告'),
    ], string='樣板類型', required=True, index=True, tracking=True,
       help='選擇此樣板適用的報表類型')

    # === 樣板檔案 ===
    attachment_id = fields.Many2one(
        'ir.attachment',
        string='樣板檔案',
        help='上傳的樣板檔案 (支援 Excel/Word 格式)')

    file_name = fields.Char(
        string='檔案名稱',
        related='attachment_id.name',
        readonly=True)

    file_data = fields.Binary(
        string='檔案內容',
        related='attachment_id.datas',
        readonly=True)

    file_size = fields.Integer(
        string='檔案大小',
        related='attachment_id.file_size',
        readonly=True)

    mimetype = fields.Char(
        string='檔案類型',
        related='attachment_id.mimetype',
        readonly=True)

    # === 適用範圍 ===
    is_default = fields.Boolean(
        string='系統預設',
        default=False,
        tracking=True,
        help='勾選後此樣板為系統預設，所有專案可用')

    scope_type = fields.Selection([
        ('system', '系統層級'),
        ('company', '公司層級'),
        ('project', '專案層級'),
    ], string='適用範圍', default='company', required=True, tracking=True,
       compute='_compute_scope_type', store=True, readonly=False,
       help='系統層級：所有公司可用；公司層級：僅該公司可用；專案層級：僅該專案可用')

    project_id = fields.Many2one(
        'project.project',
        string='專屬專案',
        tracking=True,
        help='若指定專案，則僅該專案使用此樣板；留空則為通用樣板')

    company_id = fields.Many2one(
        'res.company',
        string='適用公司',
        default=lambda self: self.env.company,
        tracking=True,
        help='此樣板適用的公司')

    # === 欄位對照 ===
    field_mapping = fields.Text(
        string='欄位對照表',
        help='樣板欄位與系統欄位的對照，JSON 格式。例如：{"A1": "project_id.name", "B2": "date"}')

    field_mapping_display = fields.Text(
        string='欄位對照說明',
        compute='_compute_field_mapping_display',
        help='以易讀格式顯示欄位對照')

    # === 說明與備註 ===
    description = fields.Text(
        string='樣板說明',
        help='描述此樣板的用途與特點')

    notes = fields.Html(
        string='備註')

    # === 使用統計 ===
    usage_count = fields.Integer(
        string='使用次數',
        default=0,
        readonly=True,
        help='此樣板被使用的次數')

    last_used_date = fields.Datetime(
        string='最後使用時間',
        readonly=True)

    # === 版本管理 ===
    version = fields.Char(
        string='版本',
        default='1.0',
        help='樣板版本號')

    version_notes = fields.Text(
        string='版本說明',
        help='此版本的更新說明')

    # 線上編輯器文件 id（dobtor_doc_editor 的 doc.document）。
    # 用 Integer 軟關聯，避免 construction_template 硬依賴 dobtor_doc_editor。
    editor_doc_id = fields.Integer(
        string='編輯器文件 id', readonly=True, copy=False,
        help='此範本以文件編輯器開啟時對應的 doc.document 記錄 id')

    # 線上試算表 id（dobtor_spreadsheet_editor / spreadsheet.spreadsheet）。同樣用 Integer 軟關聯。
    editor_spreadsheet_id = fields.Integer(
        string='編輯器試算表 id', readonly=True, copy=False,
        help='此範本以試算表編輯器開啟時對應的 spreadsheet.spreadsheet 記錄 id')

    # === SQL 約束 ===
    _sql_constraints = [
        ('unique_default_type_company',
         'UNIQUE(template_type, is_default, company_id)',
         '每種樣板類型在同一公司只能有一個系統預設！'),
        ('unique_project_type',
         'UNIQUE(template_type, project_id)',
         '每個專案的同一樣板類型只能有一個樣板！'),
    ]

    # === 計算欄位 ===
    @api.depends('is_default', 'project_id')
    def _compute_scope_type(self):
        """根據設定自動判斷適用範圍"""
        for record in self:
            if record.is_default:
                record.scope_type = 'system'
            elif record.project_id:
                record.scope_type = 'project'
            else:
                record.scope_type = 'company'

    @api.depends('field_mapping')
    def _compute_field_mapping_display(self):
        """以易讀格式顯示欄位對照"""
        for record in self:
            if record.field_mapping:
                try:
                    mapping = json.loads(record.field_mapping)
                    lines = []
                    for key, value in mapping.items():
                        lines.append(f'{key} -> {value}')
                    record.field_mapping_display = '\n'.join(lines)
                except (json.JSONDecodeError, TypeError):
                    record.field_mapping_display = '格式錯誤，請檢查 JSON 語法'
            else:
                record.field_mapping_display = '尚未設定欄位對照'

    # === 約束驗證 ===
    @api.constrains('field_mapping')
    def _check_field_mapping(self):
        """驗證欄位對照表格式"""
        for record in self:
            if record.field_mapping:
                try:
                    mapping = json.loads(record.field_mapping)
                    if not isinstance(mapping, dict):
                        raise ValidationError('欄位對照表必須是 JSON 物件格式！')
                except json.JSONDecodeError as e:
                    raise ValidationError(f'欄位對照表 JSON 格式錯誤：{str(e)}')

    @api.constrains('is_default', 'project_id')
    def _check_default_no_project(self):
        """系統預設樣板不能指定專案"""
        for record in self:
            if record.is_default and record.project_id:
                raise ValidationError('系統預設樣板不能指定專屬專案！')

    @api.constrains('attachment_id')
    def _check_attachment_type(self):
        """驗證附件檔案類型"""
        allowed_mimetypes = [
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/pdf',
        ]
        for record in self:
            if record.attachment_id and record.mimetype:
                if record.mimetype not in allowed_mimetypes:
                    raise ValidationError(
                        '樣板檔案格式不支援！請上傳 Excel (.xls/.xlsx)、'
                        'Word (.doc/.docx) 或 PDF 格式的檔案。')

    # === Onchange ===
    @api.onchange('is_default')
    def _onchange_is_default(self):
        """設為系統預設時清除專案"""
        if self.is_default:
            self.project_id = False

    @api.onchange('project_id')
    def _onchange_project_id(self):
        """指定專案時取消系統預設"""
        if self.project_id:
            self.is_default = False
            # 自動設定公司為專案的管理公司
            if self.project_id.company_id:
                self.company_id = self.project_id.company_id

    @api.onchange('template_type')
    def _onchange_template_type(self):
        """根據類型自動設定名稱"""
        if self.template_type and not self.name:
            type_labels = dict(self._fields['template_type'].selection)
            self.name = type_labels.get(self.template_type, '')

    # === 動作方法 ===
    def action_download_template(self):
        """下載樣板檔案"""
        self.ensure_one()
        if not self.attachment_id:
            raise UserError('尚未上傳樣板檔案！')
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self.attachment_id.id}?download=true',
            'target': 'self',
        }

    def action_download_default_template(self):
        """下載系統內建預設樣板"""
        self.ensure_one()
        # 系統內建樣板路徑對照
        default_templates = {
            'daily_log_1': 'construction_template/static/templates/daily_log_1.xlsx',
            'daily_log_2': 'construction_template/static/templates/daily_log_2.xlsx',
            'self_inspection': 'construction_template/static/templates/self_inspection.xlsx',
            'defect_improvement': 'construction_template/static/templates/defect_improvement.xlsx',
            'defect_control': 'construction_template/static/templates/defect_control.xlsx',
            'review_control': 'construction_template/static/templates/review_control.xlsx',
            'test_control': 'construction_template/static/templates/test_control.xlsx',
            'progress_report': 'construction_template/static/templates/progress_report.xlsx',
            'progress_schedule': 'construction_template/static/templates/progress_schedule.xlsx',
            'estimate_report': 'construction_template/static/templates/estimate_report.xlsx',
            'acceptance_report': 'construction_template/static/templates/acceptance_report.xlsx',
            'notification_slip': 'construction_template/static/templates/notification_slip.xlsx',
            'material_test': 'construction_template/static/templates/material_test.xlsx',
        }
        template_path = default_templates.get(self.template_type)
        if template_path:
            return {
                'type': 'ir.actions.act_url',
                'url': f'/{template_path}',
                'target': 'self',
            }
        raise UserError('此類型尚無系統內建預設樣板！')

    def action_open_in_editor(self):
        """用系統內建編輯器開啟本範本。

        - .docx → dobtor_doc_editor 文件編輯器（解析成可編輯 canvas 內容）
        - .xlsx → 試算表編輯器（目前尚未支援 xlsx 二進位匯入，先擋下並提示）
        """
        self.ensure_one()
        if not self.attachment_id:
            raise UserError('尚未上傳樣板檔案，無法開啟編輯器！')
        fname = (self.file_name or self.attachment_id.name or '').lower()
        if fname.endswith('.docx'):
            doc = self._sync_editor_doc()
            return doc.action_open_editor()
        if fname.endswith('.xlsx'):
            ss = self._sync_editor_spreadsheet()
            return ss.open_spreadsheet()
        raise UserError('僅支援 .docx / .xlsx 範本以編輯器開啟。')

    def _sync_editor_doc(self):
        """建立或更新對應的 doc.document，並把目前的 docx 解析成可編輯內容。

        每次開啟都重新解析目前附件，確保範本更新後編輯器內容同步。
        """
        self.ensure_one()
        try:
            from odoo.addons.dobtor_doc_editor.controllers.doc_controller import (
                _ts_parse_docx_to_elements,
            )
        except ImportError:
            raise UserError('文件編輯器模組（dobtor_doc_editor）未安裝，無法開啟。')

        file_bytes = base64.b64decode(self.attachment_id.datas or b'')
        elements = _ts_parse_docx_to_elements(file_bytes)
        if not elements:
            raise UserError('DOCX 解析失敗，無法轉為可編輯內容（請確認檔案格式）。')
        content_json = json.dumps({'main': elements}, ensure_ascii=False)

        Doc = self.env['doc.document'].sudo()
        doc = Doc.browse(self.editor_doc_id) if self.editor_doc_id else Doc
        if doc and doc.exists():
            doc.write({'content_json': content_json})
        else:
            doc = Doc.create({
                'name': self.name or (self.file_name or '範本'),
                'content_json': content_json,
            })
            self.editor_doc_id = doc.id
        return doc

    def _sync_editor_spreadsheet(self):
        """建立或更新對應的 spreadsheet.spreadsheet，把目前的 xlsx 匯入為可編輯試算表。"""
        self.ensure_one()
        if 'spreadsheet.spreadsheet' not in self.env:
            raise UserError('試算表編輯器模組（dobtor_spreadsheet_editor）未安裝，無法開啟。')
        file_bytes = base64.b64decode(self.attachment_id.datas or b'')
        Sheet = self.env['spreadsheet.spreadsheet'].sudo()
        name = self.name or (self.file_name or '範本')

        existing = (
            Sheet.browse(self.editor_spreadsheet_id)
            if self.editor_spreadsheet_id else Sheet
        )
        if existing and existing.exists():
            existing.unlink()  # 重新匯入：直接以最新附件重建，避免殘留舊修訂
        ss = Sheet.create_from_xlsx(
            name, file_bytes,
            res_model='document.template', res_id=self.id,
            source_filename=self.file_name,
        )
        self.editor_spreadsheet_id = ss.id
        return ss

    def action_test_template(self):
        """測試樣板 (使用測試資料產生檔案)"""
        self.ensure_one()
        if not self.attachment_id:
            raise UserError('請先上傳樣板檔案！')
        # TODO: 實作樣板測試邏輯
        # 1. 讀取樣板
        # 2. 填入測試資料
        # 3. 產生並下載測試檔案
        raise UserError('樣板測試功能開發中，敬請期待！')

    def action_duplicate(self):
        """複製樣板"""
        self.ensure_one()
        new_template = self.copy({
            'name': f'{self.name} (複製)',
            'is_default': False,
            'project_id': False,
            'usage_count': 0,
            'last_used_date': False,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': '文件樣板',
            'res_model': 'document.template',
            'res_id': new_template.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_usage_log(self):
        """查看使用紀錄"""
        self.ensure_one()
        # TODO: 實作使用紀錄查看
        raise UserError('使用紀錄功能開發中！')

    # === 業務方法 ===
    def record_usage(self):
        """記錄樣板使用"""
        for record in self:
            record.sudo().write({
                'usage_count': record.usage_count + 1,
                'last_used_date': fields.Datetime.now(),
            })

    @api.model
    def get_template_for_report(self, template_type, project_id=None, company_id=None):
        """
        取得報表樣板 (依優先順序)

        優先順序：
        1. 專案專屬樣板
        2. 公司預設樣板
        3. 系統預設樣板

        Args:
            template_type: 樣板類型 (selection 值)
            project_id: 專案 ID (可選)
            company_id: 公司 ID (可選，預設為當前公司)

        Returns:
            document.template recordset (可能為空)
        """
        domain = [
            ('template_type', '=', template_type),
            ('active', '=', True),
        ]

        # 1. 優先找專案專屬樣板
        if project_id:
            template = self.search(
                domain + [('project_id', '=', project_id)],
                limit=1
            )
            if template:
                return template

        # 2. 找公司預設樣板
        target_company_id = company_id or self.env.company.id
        template = self.search(
            domain + [
                ('project_id', '=', False),
                ('company_id', '=', target_company_id),
                ('is_default', '=', False),
            ],
            limit=1
        )
        if template:
            return template

        # 3. 找系統預設樣板
        template = self.search(
            domain + [('is_default', '=', True)],
            limit=1
        )
        return template

    @api.model
    def get_available_templates(self, template_type, project_id=None):
        """
        取得可用樣板列表

        Args:
            template_type: 樣板類型
            project_id: 專案 ID (可選)

        Returns:
            document.template recordset
        """
        domain = [
            ('template_type', '=', template_type),
            ('active', '=', True),
        ]

        # 可用範圍：系統預設 + 當前公司 + 指定專案
        company_id = self.env.company.id
        scope_domain = [
            '|', '|',
            ('is_default', '=', True),
            '&', ('project_id', '=', False), ('company_id', '=', company_id),
        ]
        if project_id:
            scope_domain = ['|'] + scope_domain + [('project_id', '=', project_id)]

        return self.search(domain + scope_domain, order='is_default desc, sequence')

    def get_field_mapping_dict(self):
        """取得欄位對照字典"""
        self.ensure_one()
        if not self.field_mapping:
            return {}
        try:
            return json.loads(self.field_mapping)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_field_mapping_dict(self, mapping_dict):
        """設定欄位對照字典"""
        self.ensure_one()
        if not isinstance(mapping_dict, dict):
            raise ValidationError('欄位對照必須是字典格式！')
        self.field_mapping = json.dumps(mapping_dict, ensure_ascii=False, indent=2)

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        """建立記錄"""
        for vals in vals_list:
            # 自動設定名稱
            if not vals.get('name') and vals.get('template_type'):
                type_labels = dict(self._fields['template_type'].selection)
                vals['name'] = type_labels.get(vals['template_type'], '')
        return super().create(vals_list)

    def write(self, vals):
        """更新記錄"""
        # 如果更新了樣板檔案，自動更新版本說明
        if 'attachment_id' in vals and vals['attachment_id']:
            vals.setdefault('version_notes', f'檔案已於 {fields.Datetime.now()} 更新')
        return super().write(vals)

    def copy(self, default=None):
        """複製記錄"""
        default = default or {}
        default.setdefault('name', f'{self.name} (複製)')
        default.setdefault('is_default', False)
        default.setdefault('usage_count', 0)
        default.setdefault('last_used_date', False)
        return super().copy(default)

    def name_get(self):
        """顯示名稱"""
        result = []
        for record in self:
            type_labels = dict(self._fields['template_type'].selection)
            type_name = type_labels.get(record.template_type, '')
            scope = ''
            if record.is_default:
                scope = ' [系統預設]'
            elif record.project_id:
                scope = f' [{record.project_id.code}]'
            name = f'{record.name} ({type_name}){scope}'
            result.append((record.id, name))
        return result
