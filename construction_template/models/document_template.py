# -*- coding: utf-8 -*-

import base64
import io
import json
import logging
from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError

from ..utils import template_render

_logger = logging.getLogger(__name__)

# 常見紙張的短邊×長邊（twips，1cm = 567）。用來由 docx 的 sectPr 反推紙張格式。
PAGE_TWIPS = {
    'A4': (11906, 16838),
    'A3': (16838, 23811),
    'A5': (8391, 11906),
    'letter': (12240, 15840),
    'legal': (12240, 20160),
}
PAGE_TOLERANCE = 400          # twips（約 0.7cm）；不同工具產生的尺寸會有零頭


def _docx_page_setup(file_bytes):
    """由 docx 的 sectPr 判斷 (紙張格式, 方向)；判不出來回 (None, None)。

    檢試驗管制表是橫向 A4，但編輯器一律以直向 A4 開啟、右半邊被切掉——
    因為以前沒有任何地方把 docx 的版面帶進 doc.document。
    """
    try:
        from docx import Document
        from docx.oxml.ns import qn
    except ImportError:
        return None, None
    try:
        sect = Document(io.BytesIO(file_bytes)).element.body.find(qn('w:sectPr'))
        if sect is None:
            return None, None
        pg = sect.find(qn('w:pgSz'))
        if pg is None:
            return None, None
        w = int(pg.get(qn('w:w')))
        h = int(pg.get(qn('w:h')))
    except Exception:
        return None, None

    landscape = (pg.get(qn('w:orient')) == 'landscape') or w > h
    short, long_ = min(w, h), max(w, h)
    fmt = None
    for name, (s, l) in PAGE_TWIPS.items():
        if abs(short - s) <= PAGE_TOLERANCE and abs(long_ - l) <= PAGE_TOLERANCE:
            fmt = name
            break
    return fmt, ('landscape' if landscape else 'portrait')

# 上傳時依副檔名決定 mimetype。這裡的值必須與 _check_attachment_type()
# 的 allowed_mimetypes 一致，否則合法檔案會被自己的約束擋下來。
TEMPLATE_MIMETYPES = {
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'xls': 'application/vnd.ms-excel',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'doc': 'application/msword',
    'pdf': 'application/pdf',
}
# 允許的樣板格式。以 TEMPLATE_MIMETYPES 為單一來源，避免兩份清單漂移。
ALLOWED_MIMETYPES = set(TEMPLATE_MIMETYPES.values())
# 副檔名不在上表時給的值——刻意不在 ALLOWED_MIMETYPES 裡，讓格式檢查擋下來。
FALLBACK_MIMETYPE = 'application/octet-stream'
DEFAULT_TEMPLATE_FILENAME = '樣板檔案'
UNSUPPORTED_FORMAT_MSG = (
    '樣板檔案格式不支援！請上傳 Excel (.xls/.xlsx)、'
    'Word (.doc/.docx) 或 PDF 格式的檔案。'
)


def _mimetype_from_filename(filename):
    """由檔名副檔名推斷 mimetype"""
    ext = (filename or '').rsplit('.', 1)[-1].lower() if '.' in (filename or '') else ''
    return TEMPLATE_MIMETYPES.get(ext, FALLBACK_MIMETYPE)


def _required_extension(template_type):
    """這個樣板類型必須用什麼副檔名。

    以對照表的 MODE 為唯一依據——docx 模式的樣板餵 xlsx（或反過來）套印一定
    失敗，而且底層丟出的是「is not a Word file, content type is …」這種看不懂
    的訊息。更麻煩的是專案專屬樣板優先序最高，掛錯一份就會蓋掉正確的系統預設
    樣板，整個專案的該張報表都出不來。所以在上傳當下就擋。

    沒有對照表的類型（還沒做自動套印）不限制，回 None。
    """
    mapping = template_render.get_mapping(template_type)
    if mapping is None:
        return None
    return '.docx' if getattr(mapping, 'MODE', 'cells') == 'docx' else '.xlsx'


def _format_mismatch_msg(type_label, filename, required):
    return (
        '「%s」這類樣板必須是 %s 檔，但你上傳的是「%s」。\n\n'
        '每種報表的版面格式是固定的（Word 或 Excel），上傳錯格式會讓該報表'
        '完全無法匯出。\n'
        '請確認檔案是否拿錯，或到「所有樣板」下載該類型的空白範本作為基礎。'
        % (type_label, required, filename or '（未命名）'))


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
        ('plan_control', '計畫書送審管制表'),
        ('test_control', '檢(試)驗管制表'),
        ('progress_report', '進度報告'),
        ('progress_schedule', '工程預定進度表'),
        ('estimate_report', '估驗計價表'),
        # EAGLE 的全域估驗樣板：原系統把兩份打包成 zip 一起下載，
        # 這裡拆成兩個獨立類型，各自一個按鈕。
        ('invoice_detail', '估驗詳細表'),
        ('invoice_photo', '估驗照片'),
        ('acceptance_report', '驗收報告'),
        ('notification_slip', '通報單'),
        ('material_test', '材料試驗報告'),
        # 營造版（施工廠商填寫的「公共工程施工日誌」）。
        # 上面的 daily_log_1/2 是監造版「公共工程監造日報表」，兩者並存：
        # 同一張日誌可依需要匯出監造版或營造版。
        ('daily_log_c1', '施工日誌-第一聯（營造版）'),
        ('daily_log_c2', '施工日誌-第二聯（營造版）'),
    ], string='樣板類型', required=True, index=True, tracking=True,
       help='選擇此樣板適用的報表類型')

    # === 樣板檔案 ===
    # 實際儲存位置。使用者不直接操作它，改由 file_data 的上傳元件間接維護，
    # 但仍需保留（action_open_in_editor / action_download_template 都讀它，
    # 且 view 的 invisible="not attachment_id" 修飾語需要它）。
    attachment_id = fields.Many2one(
        'ir.attachment',
        string='樣板附件（內部）',
        help='樣板檔案實際存放的附件記錄，由上方「樣板檔案」欄位自動維護')

    file_name = fields.Char(
        string='檔案名稱',
        compute='_compute_file_name',
        store=True,
        readonly=False,
        help='上傳檔案時自動帶入，可自行修改')

    # 上傳入口。附件仍以 attachment_id 為單一儲存位置，這裡只是把
    # 標準 binary 上傳元件接上去（原本 view 用的 many2one_binary widget
    # 在 Odoo 18 不存在，會靜默降級成 ir.attachment 下拉選單）。
    file_data = fields.Binary(
        string='樣板檔案',
        compute='_compute_file_data',
        inverse='_inverse_file_data',
        help='上傳樣板檔案（支援 .xlsx / .xls / .docx / .doc / .pdf）')

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
    @api.depends('attachment_id.name')
    def _compute_file_name(self):
        """檔名跟著附件走。store + readonly=False 是為了兩件事：
        ①模組升級時自動從既有附件回填，不必手寫 migration
        ②上傳元件的 filename= 仍可直接寫入
        """
        for record in self:
            # stored compute 必須對每一筆賦值，不能有沒走到的分支
            record.file_name = record.attachment_id.name or False

    @api.depends('attachment_id.datas')
    def _compute_file_data(self):
        for record in self:
            record.file_data = record.attachment_id.datas if record.attachment_id else False

    def _inverse_file_data(self):
        """把上傳的內容寫進 ir.attachment（沒有就建一個）。

        附件是唯一儲存位置，attachment_id 之外的欄位（file_size / mimetype）
        都是 related，會自動跟上。
        """
        for record in self:
            if not record.file_data:
                # 清空 = 移除附件
                if record.attachment_id:
                    record.attachment_id.unlink()
                    record.attachment_id = False
                continue

            # 上傳時 Odoo 會連同 filename= 指定的 file_name 一起寫入，
            # 但不保證先後順序，取不到就退回附件原名、再退回預設名。
            fname = record.file_name or (record.attachment_id.name if record.attachment_id else False) \
                or DEFAULT_TEMPLATE_FILENAME
            mimetype = _mimetype_from_filename(fname)
            # 這裡必須自己擋格式：_check_attachment_type() 只 constrains
            # attachment_id，換檔案時 attachment_id 沒變、約束不會觸發，
            # 於是覆蓋上傳可以塞進任何格式。
            if mimetype not in ALLOWED_MIMETYPES:
                raise ValidationError(UNSUPPORTED_FORMAT_MSG)
            # 格式合法還不夠，還要跟樣板類型相符（docx 類型不能傳 xlsx）
            required = _required_extension(record.template_type)
            if required and not fname.lower().endswith(required):
                raise ValidationError(_format_mismatch_msg(
                    dict(record._fields['template_type'].selection).get(
                        record.template_type, record.template_type),
                    fname, required))
            vals = {
                'name': fname,
                'datas': record.file_data,
                'mimetype': mimetype,
            }
            if record.attachment_id:
                record.attachment_id.write(vals)
            else:
                record.attachment_id = self.env['ir.attachment'].create(dict(
                    vals,
                    res_model=record._name,
                    res_id=record.id,
                ))

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
        """驗證附件檔案類型。

        注意：這條只在 attachment_id 本身變動時觸發，覆蓋既有附件的內容
        不會走到這裡——那條路徑由 _inverse_file_data() 自己擋。
        """
        for record in self:
            if record.attachment_id and record.mimetype:
                if record.mimetype not in ALLOWED_MIMETYPES:
                    raise ValidationError(UNSUPPORTED_FORMAT_MSG)

    @api.constrains('template_type', 'attachment_id')
    def _check_template_type_format(self):
        """樣板類型與檔案格式必須相符。

        涵蓋 _inverse_file_data() 擋不到的路徑——先傳好 docx 再把類型改成
        xlsx 類的、或用 ORM／匯入直接建記錄。
        """
        for record in self:
            if not record.attachment_id:
                continue
            required = _required_extension(record.template_type)
            filename = record.attachment_id.name or ''
            if required and not filename.lower().endswith(required):
                raise ValidationError(_format_mismatch_msg(
                    dict(record._fields['template_type'].selection).get(
                        record.template_type, record.template_type),
                    filename, required))

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
        """下載系統內建預設樣板。

        改指向資料庫裡同類型的 is_default 記錄，不再組 static/ 路徑——
        原本的寫法指向 construction_template/static/templates/，那個目錄
        並不存在（實測回 404），而且把 13 種類型全寫死成 .xlsx，
        但實際有 3 個是 .docx。改讀 DB 後副檔名自動正確，
        範本更新時也不會有兩份檔案不同步的問題。
        """
        self.ensure_one()
        default = self.sudo().search([
            ('template_type', '=', self.template_type),
            ('is_default', '=', True),
        ], limit=1)
        if not default or not default.attachment_id:
            raise UserError('此類型尚無系統內建預設樣板！')
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{default.attachment_id.id}?download=true',
            'target': 'self',
        }

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

        # 把 docx 的版面（紙張格式／方向）一起帶進編輯器，否則橫向樣板會被切掉
        vals = {'content_json': content_json}
        fmt, orientation = _docx_page_setup(file_bytes)
        if fmt:
            vals['page_format'] = fmt
        if orientation:
            vals['page_orientation'] = orientation

        Doc = self.env['doc.document'].sudo()
        doc = Doc.browse(self.editor_doc_id) if self.editor_doc_id else Doc
        if doc and doc.exists():
            doc.write(vals)
        else:
            doc = Doc.create(dict(vals, name=self.name or (self.file_name or '範本')))
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
