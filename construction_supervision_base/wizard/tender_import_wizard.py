# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError
import xml.etree.ElementTree as ET
import base64


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
        'supervision.project',
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
        ('done', '匯入完成'),
    ], string='狀態', default='upload', readonly=True)

    # === 匯入結果 ===
    imported_count = fields.Integer(
        string='已匯入工項數',
        readonly=True)

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

    def action_import(self):
        """執行匯入"""
        self.ensure_one()

        if not self.xml_file:
            raise UserError('請先上傳 XML 檔案')

        if not self.project_id.project_id:
            raise UserError('工程案件未關聯專案，無法建立工項')

        try:
            # 解析 XML
            xml_data = base64.b64decode(self.xml_file)
            root = ET.fromstring(xml_data)

            # 檢查是否為 ETenderSheet 格式
            if 'ETenderSheet' not in root.tag:
                raise UserError('檔案格式錯誤：必須是 ETenderSheet 格式的 XML 檔案')

            items_data = self._parse_pay_items(root)
        except ET.ParseError as e:
            raise UserError(f'XML 解析失敗：{str(e)}')
        except UserError:
            raise
        except Exception as e:
            raise UserError(f'處理檔案時發生錯誤：{str(e)}')

        if not items_data:
            raise UserError('未解析到任何工項資料')

        # 檢查空白標單（所有末端工項單價皆為 0）
        leaf_items = [item for item in items_data if not item.get('has_children')]
        if leaf_items and all(item.get('unit_price', 0) == 0 for item in leaf_items):
            raise UserError(
                '此為空白標單（所有末端工項的單價皆為 0），無法匯入。\n'
                '請上傳含有單價的標單檔案。'
            )

        # 建立工項
        created_tasks = self._create_tasks(items_data)

        # 更新統計
        self.write({
            'state': 'done',
            'imported_count': len(created_tasks),
        })

        # 返回工項列表視圖
        tree_view_id = self.env.ref('construction_supervision_base.view_task_tree_project_specific').id

        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.project_id.name} - 契約工項',
            'res_model': 'project.task',
            'view_mode': 'list,form',
            'views': [(tree_view_id, 'list'), (False, 'form')],
            'domain': [('id', 'in', created_tasks.ids)],
            'context': {
                'default_project_id': self.project_id.project_id.id,
            },
            'target': 'current',
        }

    def _create_tasks(self, items_data):
        """建立工項記錄"""
        Task = self.env['project.task']
        created_tasks = Task.browse()

        # 以 itemKey（XML 唯一整數）作為 key，避免 itemNo 重複導致父子關係錯亂
        task_map = {}

        # 按順序賦予 sequence 值，從 10 開始，每次遞增 10
        for index, item in enumerate(items_data, start=1):
            item_key = item.get('item_key', '')
            parent_item_key = item.get('parent_item_key', '')

            # 準備工項資料
            task_vals = {
                'project_id': self.project_id.project_id.id,
                'name': item.get('name', ''),
                'item_no': item.get('item_no', ''),
                'sequence': index * 10,
                'unit': item.get('unit', ''),
                'planned_qty': item.get('quantity', 0),
                'unit_price': item.get('unit_price', 0),
                'construction_notes': item.get('remark', ''),
                'item_level': item.get('level', 0),
                'ref_item_code': item.get('ref_item_code', ''),
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

        return created_tasks
