# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError
import xml.etree.ElementTree as ET
import base64
import re


class TenderImportWizard(models.TransientModel):
    """
    契約標單匯入精靈

    用於匯入政府採購標單 XML (ETenderSheet 格式)
    將 PayItem 轉換為契約工項 (project.task)
    """
    _name = 'tender.import.wizard'
    _description = '契約標單匯入精靈'

    # === 關聯工程案件 ===
    project_id = fields.Many2one(
        'project.project',
        string='工程案件',
        required=True,
        readonly=True,
        help='將標單匯入此工程案件')

    project_name = fields.Char(
        string='工程名稱',
        related='project_id.name',
        readonly=True)

    # === 上傳檔案 ===
    xml_file = fields.Binary(
        string='標單 XML 檔案',
        required=True,
        attachment=False,
        help='請上傳政府採購標單 XML 檔案 (ETenderSheet 格式)')

    xml_filename = fields.Char(string='檔案名稱')

    # === 狀態 ===
    state = fields.Selection([
        ('upload', '上傳檔案'),
        ('previewing', '確認中'),
        ('done', '匯入完成'),
    ], string='狀態', default='upload', readonly=True)

    # === 匯入結果 ===
    imported_count = fields.Integer(
        string='已匯入工項數',
        readonly=True)

    preview_count = fields.Integer(
        string='預計匯入工項數',
        readonly=True)

    # === 金額核對報告 ===
    validation_report = fields.Text(
        string='金額核對報告',
        readonly=True)
    has_validation_warning = fields.Boolean(
        string='有差異',
        default=False)

    # === 金額核對（不建立 task）===

    def _compute_reconciliation_from_items(self, items_data):
        """
        從 items_data（parse 結果，尚未建立 task）計算金額核對報告。
        遞迴模擬 planned_amount，與 xml_amount 比較。
        回傳 (report_text, has_warning)。
        """
        def compute_item_amount(item):
            children = [i for i in items_data if i['parent_item_key'] == item['item_key']]
            if children:
                return round(sum(compute_item_amount(c) for c in children), 2)
            elif item.get('unit_price'):
                return round((item.get('quantity') or 0) * item['unit_price'], 2)
            else:
                # 稅什費等無單價項，以 xml_amount 為準（不需比對）
                return item.get('amount') or 0.0

        warn_rows = []
        ok_count = 0
        for item in items_data:
            xml_amt = item.get('amount') or 0.0
            if item.get('has_children'):
                if not xml_amt:
                    continue
                computed = compute_item_amount(item)
                label = f'[分類] {item["name"]}'
            elif item.get('unit_price'):
                computed = round((item.get('quantity') or 0) * item['unit_price'], 2)
                label = item.get('name', '')
            else:
                ok_count += 1
                continue

            diff = round(computed - xml_amt, 2)
            if abs(diff) > 0.01:
                warn_rows.append(
                    f'⚠ {label}：計算 {computed:,.2f} / XML {xml_amt:,.2f} / 差異 {diff:+,.2f}')
            else:
                ok_count += 1

        if warn_rows:
            report = '\n'.join(warn_rows)
            if ok_count:
                report += f'\n（其餘 {ok_count} 個工項金額吻合）'
            return report, True
        else:
            return f'全部 {ok_count} 個工項金額核對無誤。', False

    def _parse_xml_and_validate(self):
        """解析 XML 並做前置驗證，回傳 items_data。共用於 preview 與 confirm。"""
        if not self.xml_file:
            raise UserError('請先上傳 XML 檔案')
        if not self.project_id:
            raise UserError('工程案件未關聯專案，無法建立工項')
        try:
            xml_data = base64.b64decode(self.xml_file)
            root = ET.fromstring(xml_data)
        except ET.ParseError as e:
            raise UserError(f'XML 解析失敗：{str(e)}')
        except Exception as e:
            raise UserError(f'處理檔案時發生錯誤：{str(e)}')
        if 'ETenderSheet' not in root.tag:
            raise UserError('檔案格式錯誤：必須是 ETenderSheet 格式的 XML 檔案')
        items_data = self._parse_pay_items(root)
        if not items_data:
            raise UserError('未解析到任何工項資料')
        leaf_items = [item for item in items_data if not item.get('has_children')]
        if leaf_items and all(item.get('unit_price', 0) == 0 for item in leaf_items):
            raise UserError(
                '此為空白標單（所有末端工項的單價皆為 0），無法匯入。\n'
                '請上傳含有單價的標單檔案。'
            )
        return items_data

    # === 解析 XML ===
    def _parse_pay_items(self, root, parent_item_key='', level=0):
        """
        遞迴解析 PayItem

        返回格式：
        [
            {
                'item_key': '1',          # XML itemKey（唯一整數，用於父子關係追蹤）
                'item_no': '壹',           # XML itemNo（完整項次編號）
                'name': '發包工程費',
                'unit': '式',
                'quantity': 1,
                'unit_price': 0,
                'amount': 0,
                'remark': '[發包]',
                'level': 0,
                'parent_item_key': '',    # 父節點的 itemKey
                'ref_item_code': '',
                'has_children': True,
            },
            ...
        ]
        """
        items = []

        # 找到 DetailList
        ns = {'ns': 'http://pcstd.pcc.gov.tw/2003/eTender'}
        detail_list = root.find('.//ns:DetailList', ns)

        if detail_list is None:
            return items

        # 解析所有 PayItem
        items = self._parse_pay_item_recursive(detail_list, ns, parent_item_key, level)

        return items

    def _parse_pay_item_recursive(self, element, ns, parent_item_key='', level=0):
        """遞迴解析 PayItem，以 itemKey 作為父子關係的唯一識別"""
        items = []

        for pay_item in element.findall('ns:PayItem', ns):
            # 取得基本資訊
            item_key = pay_item.get('itemKey', '')      # 唯一識別（用於 task_map）
            item_no = pay_item.get('itemNo', '')         # 完整項次編號
            ref_item_code = pay_item.get('refItemCode', '').strip()

            # 取得中文描述
            desc_elem = pay_item.find('ns:Description[@language="zh-TW"]', ns)
            name = desc_elem.text if desc_elem is not None else ''

            # 取得單位
            unit_elem = pay_item.find('ns:Unit[@language="zh-TW"]', ns)
            unit = unit_elem.text if unit_elem is not None else ''

            # 取得數量
            qty_elem = pay_item.find('ns:Quantity', ns)
            quantity = float(qty_elem.text) if qty_elem is not None and qty_elem.text else 0

            # 取得單價
            price_elem = pay_item.find('ns:Price', ns)
            unit_price = float(price_elem.text) if price_elem is not None and price_elem.text else 0

            # 取得複價
            amount_elem = pay_item.find('ns:Amount', ns)
            amount = float(amount_elem.text) if amount_elem is not None and amount_elem.text else 0

            # 取得備註
            remark_elem = pay_item.find('ns:Remark', ns)
            remark = remark_elem.text if remark_elem is not None else ''

            # 取得稅什費比例（官方電子標單專屬欄位）
            percent_elem = pay_item.find('ns:Percent', ns)
            percent = float(percent_elem.text) if percent_elem is not None and percent_elem.text else 0.0

            # 檢查是否有子項目
            child_pay_items = pay_item.findall('ns:PayItem', ns)
            has_children = len(child_pay_items) > 0

            # 建立項目資料
            item_data = {
                'item_key': item_key,
                'item_no': item_no,
                'name': name,
                'unit': unit,
                'quantity': quantity,
                'unit_price': unit_price,
                'amount': amount,
                'remark': remark,
                'percent': percent,
                'level': level,
                'parent_item_key': parent_item_key,
                'ref_item_code': ref_item_code,
                'has_children': has_children,
            }

            items.append(item_data)

            # 遞迴解析子項目，傳遞本節點的 itemKey 作為子節點的父參考
            if has_children:
                child_items = self._parse_pay_item_recursive(
                    pay_item, ns, item_key, level + 1
                )
                items.extend(child_items)

        return items

    def action_preview(self):
        """預覽金額核對報告（不建立任何工項）"""
        self.ensure_one()
        items_data = self._parse_xml_and_validate()
        report, has_warning = self._compute_reconciliation_from_items(items_data)
        self.write({
            'state': 'previewing',
            'preview_count': len(items_data),
            'validation_report': report,
            'has_validation_warning': has_warning,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_reset_upload(self):
        """清除預覽結果，回到上傳狀態"""
        self.write({
            'state': 'upload',
            'validation_report': False,
            'has_validation_warning': False,
            'preview_count': 0,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirm_import(self):
        """確認匯入：建立工項並顯示結果"""
        self.ensure_one()
        items_data = self._parse_xml_and_validate()

        # 建立工項
        created_tasks = self._create_tasks(items_data)

        # 儲存原始 XML 供後續契約變更 XLSX 匯入使用
        if self.xml_file:
            self.project_id.write({
                'tender_xml_data': self.xml_file,
                'tender_xml_filename': self.xml_filename or 'tender.xml',
            })

        # 更新統計，使用 previewing 階段已計算好的核對報告
        self.write({
            'state': 'done',
            'imported_count': len(created_tasks),
        })

        # 無差異 → 導航到工項列表；有差異 → 留在 wizard done 頁顯示報告
        if not self.has_validation_warning:
            tree_view_id = self.env.ref(
                'construction_supervision_base.view_task_tree_project_specific').id
            return {
                'type': 'ir.actions.act_window',
                'name': f'{self.project_id.name} - 契約工項',
                'res_model': 'project.task',
                'view_mode': 'list,form',
                'views': [(tree_view_id, 'list'), (False, 'form')],
                'domain': [('id', 'in', created_tasks.ids)],
                'context': {'default_project_id': self.project_id.id},
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_task_list(self):
        """從 done 頁導航至剛匯入的工項列表"""
        self.ensure_one()
        tree_view_id = self.env.ref(
            'construction_supervision_base.view_task_tree_project_specific').id
        tasks = self.env['project.task'].search([
            ('project_id', '=', self.project_id.id),
            ('active', '=', True),
        ])
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.project_id.name} - 契約工項',
            'res_model': 'project.task',
            'view_mode': 'list,form',
            'views': [(tree_view_id, 'list'), (False, 'form')],
            'domain': [('id', 'in', tasks.ids)],
            'context': {
                'default_project_id': self.project_id.id,
            },
            'target': 'current',
        }

    def _create_tasks(self, items_data):
        """建立工項記錄"""
        Task = self.env['project.task']
        created_tasks = Task.browse()

        # 以 itemKey（XML 唯一整數）作為 key，避免 itemNo 重複導致父子關係錯亂
        task_map = {}

        # 單位標準化與 uom 解析改用共用方法（project.task._normalize_unit_display /
        # _resolve_uom_id），與契約變更、成本分析共用同一份，確保全系統一致。

        # 預建立 product cache：批次查詢已存在的 product（以 default_code 為鍵）
        all_ref_codes = {
            item.get('ref_item_code', '').strip()
            for item in items_data
            if item.get('ref_item_code', '').strip()
        }
        product_cache = {}
        if all_ref_codes:
            existing_products = self.env['product.product'].search_read(
                [('default_code', 'in', list(all_ref_codes))],
                ['id', 'default_code', 'uom_id']
            )
            for p in existing_products:
                product_cache[p['default_code']] = p
            # 批次確保已存在的 product 都標記為標準工項
            if existing_products:
                existing_ids = [p['id'] for p in existing_products]
                self.env['product.product'].browse(existing_ids).mapped(
                    'product_tmpl_id').write({'is_standard_work_item': True})

        # 按順序賦予 sequence 值，從 10 開始，每次遞增 10
        for index, item in enumerate(items_data, start=1):
            item_key = item.get('item_key', '')
            parent_item_key = item.get('parent_item_key', '')
            unit_name = item.get('unit', '')
            ref_code = item.get('ref_item_code', '').strip()

            # 標準化顯示單位 + 解析 uom_id（共用方法：精確→別名→模糊→自動建立）
            display_unit = Task._normalize_unit_display(unit_name)
            uom_id = Task._resolve_uom_id(display_unit)

            # 對應或建立 product.product（僅有 ref_item_code 時處理）
            product_id = False
            if ref_code:
                if ref_code not in product_cache:
                    # 找不到則自動建立服務型 product
                    new_product = self.env['product.product'].create({
                        'name': item.get('name', ''),
                        'default_code': ref_code,
                        'type': 'service',
                        'uom_id': uom_id or False,
                        'uom_po_id': uom_id or False,
                        'is_standard_work_item': True,
                    })
                    product_cache[ref_code] = {
                        'id': new_product.id,
                        'default_code': ref_code,
                        'uom_id': (uom_id, unit_name) if uom_id else False,
                    }
                cached = product_cache[ref_code]
                product_id = cached['id']
                # ⚠️ 不再「以 product 的 uom 為準」：unit_id 一律由標單單位解析，
                #    避免 ref_item_code 不可靠時把錯 product 的單位帶進 unit_id。

            # 準備工項資料（item_level 由 compute 自動計算，無需傳入）
            task_vals = {
                'project_id': self.project_id.id,
                'name': item.get('name', ''),
                'item_no': item.get('item_no', ''),
                'sequence': index * 10,
                'unit': display_unit,
                'unit_id': uom_id,
                'product_id': product_id,
                'planned_qty': item.get('quantity', 0),
                'unit_price': item.get('unit_price', 0),
                'xml_amount': item.get('amount', 0),
                'construction_notes': item.get('remark', ''),
                'tax_misc_rate': item.get('percent', 0) or 0.0,
                'ref_item_code': ref_code or item.get('ref_item_code', ''),
            }

            # 以 itemKey 查找父節點，保留階層結構
            if parent_item_key:
                parent_task = task_map.get(parent_item_key)
                if parent_task:
                    task_vals['parent_id'] = parent_task.id

            # 建立任務
            task = Task.create(task_vals)
            created_tasks |= task

            # 以 itemKey 記錄，確保唯一性
            if item_key:
                task_map[item_key] = task

        # ── 稅什費比例計算 ────────────────────────────────────────
        # 找到名稱含「稅什費」的工項，計算其佔同層前置項目的比例 N%
        # N = 稅什費.xml_amount ÷ sum(同層 sequence 較小的項目 xml_amount) × 100
        self._compute_tax_misc_rate(created_tasks)

        return created_tasks

    def _compute_tax_misc_rate(self, tasks):
        """
        計算並儲存稅什費比例（N%）。

        三段優先：
        1. XML <Percent> 欄位 > 0（官方電子標單）→ 建立 task 時已寫入，此處跳過
        2. 備註含 N% 格式（自行轉檔但備註完整）→ regex 解析
        3. 反推算（自行轉檔且備註遺失）→ xml_amount ÷ 同層前置加總
        """
        import re as _re
        tax_tasks = tasks.filtered(lambda t: '稅什費' in (t.name or '') or '稅雜費' in (t.name or ''))
        for tax_task in tax_tasks:
            # 優先 1：<Percent> 已在建立 task 時寫入 tax_misc_rate，直接跳過
            if tax_task.tax_misc_rate:
                continue

            # 優先 2：備註含 N% 格式（如 "(一~八*約10.95%)" 或 "(一)~(七) × 3.5%"）
            remark = tax_task.construction_notes or ''
            m = _re.search(r'([\d.]+)\s*%', remark)
            if m:
                n_pct = float(m.group(1))
                tax_task.write({'tax_misc_rate': n_pct})
                continue

            # 優先 3：反推算（備註遺失時的 fallback）
            domain = [
                ('id', 'in', tasks.ids),
                ('sequence', '<', tax_task.sequence),
            ]
            if tax_task.parent_id:
                domain.append(('parent_id', '=', tax_task.parent_id.id))
            else:
                domain.append(('parent_id', '=', False))

            preceding = self.env['project.task'].search(domain)
            base_sum = sum(t.xml_amount for t in preceding)

            if not base_sum:
                continue  # 分母為 0，無法計算

            n_pct = (tax_task.xml_amount / base_sum) * 100.0
            tax_task.write({'tax_misc_rate': n_pct})
