# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import xml.etree.ElementTree as ET
import base64


class CostAnalysisImportXMLWizard(models.TransientModel):
    """
    從 XML 匯入成本分析精靈

    流程：
    1. 上傳政府採購標單 XML 檔案
    2. 自動解析 PayItem
    3. 生成預覽 + 計算估算金額
    4. 輸入預算總價
    5. 確認匯入 → 建立 cost.analysis + cost.analysis.line
    """
    _name = 'cost.analysis.import.xml.wizard'
    _description = '從 XML 匯入成本分析精靈'

    # === 上傳檔案 ===
    xml_file = fields.Binary(
        string='標單 XML 檔案',
        required=True,
        attachment=False,
        help='請上傳政府採購標單 XML 檔案 (ETenderSheet 格式)')

    xml_filename = fields.Char(
        string='檔案名稱')

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        required=True,
        default=lambda self: self.env.company)

    # === 解析狀態 ===
    state = fields.Selection([
        ('upload', '上傳檔案'),
        ('preview', '預覽資料'),
    ], string='狀態', default='upload', readonly=True)

    # === 成本分析資訊 ===
    planning_name = fields.Char(
        string='成本分析名稱',
        required=True,
        help='新建成本分析的名稱')

    total_budget = fields.Monetary(
        string='預算總價',
        required=True,
        currency_field='currency_id',
        help='契約預算總價')

    currency_id = fields.Many2one(
        'res.currency',
        string='幣別',
        default=lambda self: self.env.company.currency_id,
        required=True)

    # === 預覽資訊 ===
    total_items = fields.Integer(
        string='工項總數',
        readonly=True,
        help='解析到的工項總數（不含彙總項）')

    estimated_amount = fields.Float(
        string='估算金額',
        readonly=True,
        digits=(16, 2),
        help='所有工項的金額總計')

    preview_html = fields.Html(
        string='預覽',
        readonly=True,
        compute='_compute_preview_html',
        help='顯示解析後的工項預覽（前 20 筆）')

    # === 解析結果暫存 ===
    parsed_data = fields.Text(
        string='解析資料',
        help='JSON 格式的解析結果，用於最終匯入')

    # === 解析 XML ===
    @api.onchange('xml_file')
    def _onchange_xml_file(self):
        """當上傳檔案時，自動解析"""
        if self.xml_file and self.state == 'upload':
            self.action_parse_xml()

    def action_parse_xml(self):
        """解析 XML 並顯示預覽"""
        self.ensure_one()

        if not self.xml_file:
            raise UserError(_('請先上傳 XML 檔案'))

        try:
            # 解碼 base64
            xml_data = base64.b64decode(self.xml_file)

            # 解析 XML
            root = ET.fromstring(xml_data)

            # 檢查是否為 ETenderSheet 格式
            if 'ETenderSheet' not in root.tag:
                raise UserError(_('檔案格式錯誤：必須是 ETenderSheet 格式的 XML 檔案'))

            # 解析工項資料（複用 tender_import_wizard 的邏輯）
            items_data = self._parse_pay_items(root)

            # 計算統計資訊
            total_items = len([item for item in items_data if not item.get('has_children', False)])
            estimated_amount = sum(item.get('amount', 0) for item in items_data if not item.get('has_children', False))

            # 暫存解析結果（轉為 JSON）
            import json
            parsed_data_json = json.dumps(items_data, ensure_ascii=False)

            # 自動填入成本分析名稱（從 XML 或檔名）
            if not self.planning_name:
                self.planning_name = self.xml_filename or _('標單匯入')

            # 自動填入預算總價
            if not self.total_budget:
                self.total_budget = estimated_amount

            # 更新欄位
            self.write({
                'state': 'preview',
                'total_items': total_items,
                'estimated_amount': estimated_amount,
                'parsed_data': parsed_data_json,
            })

        except ET.ParseError as e:
            raise UserError(_('XML 解析失敗：%s') % str(e))
        except Exception as e:
            raise UserError(_('處理檔案時發生錯誤：%s') % str(e))

    def _parse_pay_items(self, root, parent_item_no='', level=0):
        """
        遞迴解析 PayItem（複用 tender_import_wizard 邏輯）

        返回格式：
        [
            {
                'item_no': '壹',
                'name': '發包工程費',
                'unit': '式',
                'quantity': 1,
                'unit_price': 0,
                'amount': 0,
                'level': 0,
                'parent_item_no': '',
                'ref_item_code': '',
                'has_children': True,
            },
            ...
        ]
        """
        items = []

        # 找出所有 PayItem
        pay_items = root.findall('.//PayItem')

        # 建立 itemKey 索引（用於查找父項）
        item_key_map = {}

        for pay_item in pay_items:
            item_key = pay_item.get('itemKey', '')
            item_no = pay_item.get('itemNo', '')
            ref_item_code = pay_item.get('refItemCode', '')

            # 解析欄位
            name = self._get_xml_text(pay_item, 'Description')
            unit = self._get_xml_text(pay_item, 'Unit')
            quantity = self._parse_float(self._get_xml_text(pay_item, 'Quantity'))
            unit_price = self._parse_float(self._get_xml_text(pay_item, 'Price'))
            amount = self._parse_float(self._get_xml_text(pay_item, 'TotalAmount'))

            # 決定父項目編號
            parent_key = item_key.rsplit('.', 1)[0] if '.' in item_key else ''
            parent_item_no_value = item_key_map.get(parent_key, '')

            # 記錄此項目
            item_key_map[item_key] = item_no

            # 判斷是否為彙總項（單價為 0 或數量為 0）
            has_children = (unit_price == 0 and amount > 0)

            items.append({
                'item_key': item_key,
                'item_no': item_no,
                'name': name,
                'unit': unit,
                'quantity': quantity,
                'unit_price': unit_price,
                'amount': amount,
                'level': item_key.count('.'),
                'parent_item_no': parent_item_no_value,
                'ref_item_code': ref_item_code,
                'has_children': has_children,
            })

        return items

    def _get_xml_text(self, element, tag_name):
        """取得 XML 元素的文字內容"""
        child = element.find(tag_name)
        return child.text if child is not None and child.text else ''

    def _parse_float(self, value_str):
        """將字串轉為浮點數"""
        try:
            return float(value_str.replace(',', '')) if value_str else 0.0
        except ValueError:
            return 0.0

    @api.depends('parsed_data', 'state')
    def _compute_preview_html(self):
        """生成預覽 HTML（前 20 筆）"""
        for wizard in self:
            if wizard.state == 'preview' and wizard.parsed_data:
                try:
                    import json
                    items = json.loads(wizard.parsed_data)[:20]  # 只顯示前 20 筆

                    html = '<table class="table table-sm table-striped">'
                    html += '<thead><tr><th>項目編號</th><th>項目名稱</th><th>單位</th><th>數量</th><th>單價</th><th>金額</th></tr></thead>'
                    html += '<tbody>'

                    for item in items:
                        indent = '&nbsp;' * (item['level'] * 4)
                        html += f'''<tr>
                            <td>{indent}{item['item_no']}</td>
                            <td>{item['name']}</td>
                            <td>{item['unit']}</td>
                            <td style="text-align:right">{item['quantity']:,.2f}</td>
                            <td style="text-align:right">{item['unit_price']:,.2f}</td>
                            <td style="text-align:right">{item['amount']:,.2f}</td>
                        </tr>'''

                    html += '</tbody></table>'
                    wizard.preview_html = html
                except:
                    wizard.preview_html = '<p>預覽生成失敗</p>'
            else:
                wizard.preview_html = '<p>請先上傳並解析 XML 檔案</p>'

    # === 執行匯入 ===
    def action_import(self):
        """執行匯入"""
        self.ensure_one()

        if not self.parsed_data:
            raise UserError(_('請先解析 XML 檔案'))

        import json
        items_data = json.loads(self.parsed_data)

        # 1. 建立 cost.analysis
        planning = self.env['cost.analysis'].create({
            'name': self.planning_name,
            'company_id': self.company_id.id,
            'import_mode': 'xml',
            'xml_file': self.xml_file,
            'xml_filename': self.xml_filename,
            'total_budget': self.total_budget,
            'state': 'draft',
        })

        # 2. 建立 item_no 到 line 的映射（用於建立父子關係）
        item_no_to_line = {}

        # 3. 遍歷所有工項並建立 cost.analysis.line
        for item in items_data:
            # 決定 parent_id
            parent_line_id = False
            if item['parent_item_no'] and item['parent_item_no'] in item_no_to_line:
                parent_line_id = item_no_to_line[item['parent_item_no']].id

            # 建立 cost.analysis.line
            line = self.env['cost.analysis.line'].create({
                'planning_id': planning.id,
                'parent_id': parent_line_id,
                'item_no': item['item_no'],
                'name': item['name'],
                'unit': item['unit'],
                'ref_item_code': item['ref_item_code'] or False,
                'quantity': item['quantity'],
                'contract_unit_price': item['unit_price'],
            })

            # 記錄映射
            item_no_to_line[item['item_no']] = line

        # 4. 返回新建的成本分析
        return {
            'type': 'ir.actions.act_window',
            'name': _('成本分析'),
            'res_model': 'cost.analysis',
            'res_id': planning.id,
            'view_mode': 'form',
            'target': 'current',
        }
