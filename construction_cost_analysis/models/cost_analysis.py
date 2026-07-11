# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import logging
import base64
import xml.etree.ElementTree as ET
import re

_logger = logging.getLogger(__name__)


class CostAnalysis(models.Model):
    """成本分析"""
    _name = 'cost.analysis'
    _description = '成本分析'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    # ========================================
    # 基本資訊
    # ========================================
    name = fields.Char(
        string='名稱',
        required=True,
        tracking=True,
        help='成本分析名稱'
    )

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        required=True,
        default=lambda self: self.env.company,
        tracking=True
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='幣別',
        related='company_id.currency_id',
        store=True,
        readonly=True
    )

    # ========================================
    # 匯入模式
    # ========================================
    import_mode = fields.Selection(
        [
            ('project', '從專案匯入'),
            ('xml', '從 XML 匯入'),
        ],
        string='匯入模式',
        required=True,
        default='project',
        tracking=True,
        help='選擇從既有專案或 XML 標單匯入工項'
    )

    source_project_id = fields.Many2one(
        'supervision.project',
        string='來源專案',
        tracking=True,
        help='從此專案匯入契約工項'
    )

    xml_file = fields.Binary(
        string='XML 檔案',
        attachment=False,
        help='上傳政府採購網 XML 標單'
    )

    xml_filename = fields.Char(
        string='檔案名稱'
    )

    # ========================================
    # 狀態
    # ========================================
    state = fields.Selection(
        [
            ('draft', '草稿'),
            ('confirmed', '已確認'),
            ('done', '完成'),
        ],
        string='狀態',
        default='draft',
        required=True,
        tracking=True
    )

    # ========================================
    # 預算明細
    # ========================================
    line_ids = fields.One2many(
        'cost.analysis.line',
        'planning_id',
        string='預算明細',
        copy=True
    )

    line_count = fields.Integer(
        string='明細數量',
        compute='_compute_line_statistics',
        store=True
    )

    # ========================================
    # 金額統計
    # ========================================
    total_budget = fields.Monetary(
        string='招標總價',
        compute='_compute_budget_totals',
        store=True,
        currency_field='currency_id',
        help='所有明細的契約金額總和'
    )

    suggested_total = fields.Monetary(
        string='建議總價',
        compute='_compute_budget_totals',
        store=True,
        currency_field='currency_id',
        help='所有有建議單價的明細，其建議金額總和'
    )

    variance_amount = fields.Monetary(
        string='差異金額',
        compute='_compute_variance',
        store=True,
        currency_field='currency_id',
        help='建議總價 - 預算總價'
    )

    variance_percent = fields.Float(
        string='差異百分比',
        compute='_compute_variance',
        store=True,
        digits=(16, 2),
        help='(差異金額 / 預算總價) × 100%'
    )

    # ========================================
    # 匹配統計
    # ========================================
    matched_line_count = fields.Integer(
        string='已匹配明細數',
        compute='_compute_line_statistics',
        store=True,
        help='有建議單價的明細數量'
    )

    match_rate = fields.Float(
        string='匹配率',
        compute='_compute_line_statistics',
        store=True,
        digits=(16, 2),
        help='(已匹配明細數 / 明細總數) × 100%'
    )

    # ========================================
    # Compute Methods
    # ========================================
    @api.depends('line_ids', 'line_ids.has_suggestion')
    def _compute_line_statistics(self):
        """計算明細統計"""
        for record in self:
            lines = record.line_ids.filtered(lambda l: not l.is_summary_item)
            record.line_count = len(lines)
            record.matched_line_count = len(lines.filtered(lambda l: l.has_suggestion))
            record.match_rate = (
                (record.matched_line_count / record.line_count * 100.0)
                if record.line_count > 0 else 0.0
            )

    @api.depends('line_ids', 'line_ids.contract_amount', 'line_ids.suggested_amount')
    def _compute_budget_totals(self):
        """計算預算總計"""
        for record in self:
            lines = record.line_ids.filtered(lambda l: not l.is_summary_item)
            record.total_budget = sum(lines.mapped('contract_amount'))
            # 只加總有建議單價的明細
            suggested_lines = lines.filtered(lambda l: l.has_suggestion)
            record.suggested_total = sum(suggested_lines.mapped('suggested_amount'))

    @api.depends('total_budget', 'suggested_total')
    def _compute_variance(self):
        """計算差異"""
        for record in self:
            record.variance_amount = record.suggested_total - record.total_budget
            record.variance_percent = (
                (record.variance_amount / record.total_budget * 100.0)
                if record.total_budget > 0 else 0.0
            )

    # ========================================
    # XML 解析工具方法
    # ========================================
    @staticmethod
    def _ca_parse_float(value_str):
        try:
            return float(value_str.replace(',', '')) if value_str else 0.0
        except ValueError:
            return 0.0

    def _ca_normalize_unit(self, s):
        """標準化 XML 單位（委派共用方法 project.task._normalize_unit_display，全系統一致）"""
        return self.env['project.task']._normalize_unit_display(s)

    def _ca_parse_pay_items_recursive(self, element, ns, parent_item_key='', level=0):
        """遞迴解析 PayItem，以 itemKey 作為父子關係唯一識別"""
        items = []
        for pay_item in element.findall('ns:PayItem', ns):
            item_key = pay_item.get('itemKey', '')
            item_no = pay_item.get('itemNo', '')
            ref_item_code = pay_item.get('refItemCode', '').strip()

            desc_elem = pay_item.find('ns:Description[@language="zh-TW"]', ns)
            name = desc_elem.text if desc_elem is not None else ''

            unit_elem = pay_item.find('ns:Unit[@language="zh-TW"]', ns)
            unit = unit_elem.text if unit_elem is not None else ''

            qty_elem = pay_item.find('ns:Quantity', ns)
            quantity = float(qty_elem.text) if qty_elem is not None and qty_elem.text else 0.0

            price_elem = pay_item.find('ns:Price', ns)
            unit_price = float(price_elem.text) if price_elem is not None and price_elem.text else 0.0

            child_pay_items = pay_item.findall('ns:PayItem', ns)
            has_children = len(child_pay_items) > 0

            items.append({
                'item_key': item_key,
                'item_no': item_no,
                'name': name,
                'unit': unit,
                'quantity': quantity,
                'unit_price': unit_price,
                'ref_item_code': ref_item_code,
                'level': level,
                'parent_item_key': parent_item_key,
                'has_children': has_children,
            })

            if has_children:
                items.extend(
                    self._ca_parse_pay_items_recursive(pay_item, ns, item_key, level + 1)
                )

        return items

    # ========================================
    # 匯入模式切換 onchange
    # ========================================
    @api.onchange('import_mode')
    def _onchange_import_mode(self):
        """切換匯入模式時清除現有明細，避免資料混雜"""
        if self.state == 'draft':
            self.line_ids = [(5, 0, 0)]

    # ========================================
    # 從 XML 解析並載入工項
    # ========================================
    def action_parse_xml(self):
        """解析 XML 檔案並建立預算明細（保留父子階層）"""
        self.ensure_one()
        if not self.xml_file:
            raise UserError('請先上傳 XML 檔案！')
        if self.state != 'draft':
            raise UserError('只有草稿狀態可以重新解析 XML！')

        try:
            xml_data = base64.b64decode(self.xml_file)
            root = ET.fromstring(xml_data)
            if 'ETenderSheet' not in root.tag:
                raise UserError('檔案格式錯誤：必須是 ETenderSheet 格式')
        except UserError:
            raise
        except Exception as e:
            raise UserError(f'XML 解析失敗：{e}')

        ns = {'ns': 'http://pcstd.pcc.gov.tw/2003/eTender'}
        detail_list = root.find('.//ns:DetailList', ns)
        if detail_list is None:
            raise UserError('未找到 DetailList 節點，請確認 XML 格式')

        items_data = self._ca_parse_pay_items_recursive(detail_list, ns)
        if not items_data:
            raise UserError('未解析到任何工項資料')

        # UoM 對應表
        all_uoms = self.env['uom.uom'].search_read([], ['name', 'id'])
        uom_cache = {u['name']: u['id'] for u in all_uoms}
        _ALIAS = {
            'b.m³': 'm³', 'c.m³': 'm³',
            'b.m3': 'm³', 'c.m3': 'm³',
            'm²/月': 'm²', 'm³/月': 'm³',
        }

        def _norm(s):
            return re.sub(r'\s+', '', (s or '').lower())

        uom_norm = {}
        for u in all_uoms:
            nk = _norm(u['name'])
            if nk not in uom_norm:
                uom_norm[nk] = u['id']

        def resolve_uom(raw):
            disp = self._ca_normalize_unit(raw)
            uom_id = uom_cache.get(disp)
            if not uom_id:
                nk = _norm(disp)
                std = _ALIAS.get(nk)
                if std:
                    uom_id = uom_cache.get(std)
                if not uom_id:
                    uom_id = uom_norm.get(nk, False)
            return disp, uom_id

        # 清除現有明細
        self.line_ids.unlink()

        item_key_map = {}  # itemKey → cost.analysis.line record

        for seq, item in enumerate(items_data, start=10):
            item_key = item['item_key']
            parent_item_key = item['parent_item_key']

            parent_line_id = False
            if parent_item_key:
                parent_line = item_key_map.get(parent_item_key)
                if parent_line:
                    parent_line_id = parent_line.id

            disp_unit, uom_id = resolve_uom(item['unit'])

            line = self.env['cost.analysis.line'].create({
                'planning_id': self.id,
                'parent_id': parent_line_id,
                'sequence': seq,
                'item_no': item['item_no'],
                'name': item['name'],
                'unit': disp_unit,
                'unit_id': uom_id,
                'ref_item_code': item['ref_item_code'] or False,
                'quantity': item['quantity'],
                'contract_unit_price': item['unit_price'],
            })
            if item_key:
                item_key_map[item_key] = line

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ========================================
    # 從專案載入工項
    # ========================================
    def action_load_from_project(self):
        """從來源專案載入契約工項（保留父子階層）"""
        self.ensure_one()
        if not self.source_project_id:
            raise UserError('請先選擇來源專案！')
        if self.state != 'draft':
            raise UserError('只有草稿狀態可以重新載入工項！')

        self.line_ids.unlink()

        tasks = self.source_project_id.task_ids.sorted(
            lambda t: (t.sequence, t.item_no or '', t.id)
        )
        if not tasks:
            raise UserError('來源專案沒有工項！')

        task_to_line = {}
        for task in tasks:
            parent_line_id = False
            if task.parent_id and task.parent_id.id in task_to_line:
                parent_line_id = task_to_line[task.parent_id.id].id

            line = self.env['cost.analysis.line'].create({
                'planning_id': self.id,
                'parent_id': parent_line_id,
                'sequence': task.sequence,
                'item_no': task.item_no,
                'name': task.name,
                'unit': task.unit,
                'unit_id': task.unit_id.id if task.unit_id else False,
                'ref_item_code': task.ref_item_code or False,
                'task_id': task.id,
                'quantity': task.planned_qty,
                'contract_unit_price': task.unit_price,
            })
            task_to_line[task.id] = line

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ========================================
    # 狀態切換方法
    # ========================================
    def action_confirm(self):
        """確認"""
        for record in self:
            if record.state != 'draft':
                raise UserError('只有草稿狀態可以確認！')
            record.state = 'confirmed'

    def action_done(self):
        """完成"""
        for record in self:
            if record.state != 'confirmed':
                raise UserError('只有已確認狀態可以完成！')
            record.state = 'done'

    def action_reset_to_draft(self):
        """重設為草稿"""
        for record in self:
            record.state = 'draft'

    # ========================================
    # 價格庫匯入方法
    # ========================================
    def action_import_suggested_prices(self):
        """從價格庫比對建議單價（正規化名稱 + 正規化單位，忽略公司）"""
        import unicodedata
        import re

        def normalize(s):
            s = unicodedata.normalize('NFKC', s or '')  # 全形→半形
            return re.sub(r'\s+', ' ', s).strip().lower()

        self.ensure_one()
        if not self.line_ids:
            raise UserError('沒有可比對的明細！')

        PriceItem = self.env['price.library.item']
        Task = self.env['project.task']
        # 單庫單公司：比對不以 company 過濾，僅限啟用中的項目
        base_domain = [('active', '=', True)]
        by_name = ambiguous = 0
        unmatched_no_name = []   # 找不到同名項目
        unmatched_unit = []      # 有同名但單位不符

        for line in self.line_ids.filtered(lambda l: not l.is_summary_item):
            # 以正規化名稱搜尋候選；單位改在 Python 端正規化後比對（較耐髒資料）
            norm = normalize(line.name)
            candidates = PriceItem.search(base_domain + [('name_normalized', '=', norm)])

            if not candidates:
                line.match_status = 'none'
                unmatched_no_name.append(f'  • {line.name}')
                continue

            line_unit = Task._normalize_unit_display(line.unit)
            unit_matched = candidates.filtered(
                lambda it: Task._normalize_unit_display(it.unit) == line_unit
            )
            if len(unit_matched) == 1:
                line.library_item_id = unit_matched
                line.match_status = 'matched'
                by_name += 1
            elif len(unit_matched) > 1:
                line.match_status = 'ambiguous'
                ambiguous += 1
            else:
                # 找得到同名，但無單位相符者
                line.match_status = 'none'
                unmatched_unit.append(f'  • {line.name}（單位 {line.unit}）')

        unmatched_count = len(unmatched_no_name) + len(unmatched_unit)
        msg = f'成功比對 {by_name} 筆'
        if ambiguous:
            msg += f'\n{ambiguous} 筆有多個候選，請手動確認'
        if unmatched_unit:
            msg += f'\n以下 {len(unmatched_unit)} 筆有同名項目但單位不符：\n' + '\n'.join(unmatched_unit)
        if unmatched_no_name:
            msg += f'\n以下 {len(unmatched_no_name)} 筆在價格庫找不到同名項目：\n' + '\n'.join(unmatched_no_name)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '價格庫比對完成',
                'message': msg,
                'type': 'success' if not (ambiguous or unmatched_count) else 'warning',
                'sticky': bool(unmatched_count),
                # 通知後軟重整當前表單，讓比對後的建議單價/金額/統計即時刷新（否則畫面停在舊值）
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    # ========================================
    # 統計分析方法
    # ========================================
    def action_view_statistics(self):
        """查看統計分析"""
        self.ensure_one()
        return {
            'name': f'{self.name} - 統計分析',
            'type': 'ir.actions.act_window',
            'res_model': 'cost.analysis',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
            'context': {'form_view_initial_mode': 'readonly'},
        }
