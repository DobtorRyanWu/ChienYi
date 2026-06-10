# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class SupervisionProject(models.Model):
    """
    擴展監造專案模型

    新增價格庫自動提取功能：
    - 專案結案時自動提取契約工項到價格庫
    - 追蹤價格來源
    - 計算建議單價統計
    """
    _inherit = 'supervision.project'

    # === 價格庫提取狀態 ===
    price_library_extracted = fields.Boolean(
        string='已提取至價格庫',
        default=False,
        copy=False,
        help='標記此專案的工項是否已提取至價格庫')

    price_library_extracted_date = fields.Datetime(
        string='提取日期',
        copy=False,
        help='工項提取至價格庫的日期時間')

    price_library_extracted_count = fields.Integer(
        string='提取工項數',
        default=0,
        copy=False,
        help='已提取至價格庫的工項數量')

    # === 覆寫結案方法 ===
    def action_close(self):
        """
        結案

        覆寫基礎類別的方法，在結案後自動提取工項到價格庫
        """
        result = super().action_close()

        # 結案後自動提取工項到價格庫
        for project in self:
            if not project.price_library_extracted:
                try:
                    project._extract_tasks_to_price_library()
                except Exception as e:
                    _logger.error(f'專案 {project.code} 提取工項到價格庫失敗: {str(e)}')
                    # 不中斷結案流程，只記錄錯誤

        return result

    def _extract_tasks_to_price_library(self):
        """
        提取契約工項到價格庫

        邏輯：
        1. 取得所有有效工項（排除彙總項）
        2. 遍歷每個工項
        3. 使用 (company_id, name, unit) 作為唯一鍵匹配或建立 price.library.item
        4. 建立 price.library.item.source 記錄
        5. 更新統計資訊

        注意：
        - 使用 sudo() 以避免權限問題（自動化操作）
        - 批次處理提升效能（每 500 筆 commit）
        - SQL 約束會自動防止重複提取
        """
        self.ensure_one()

        _logger.info(f'=== 開始提取專案 {self.code} 的工項到價格庫 ===')

        # 1. 取得有效工項（排除彙總項）
        tasks = self.task_ids.filtered(
            lambda t: t.active and not t.is_summary_item and t.unit_price > 0
        )

        if not tasks:
            _logger.info(f'專案 {self.code} 無有效工項可提取')
            return

        _logger.info(f'找到 {len(tasks)} 筆有效工項')

        # 使用 sudo() 以系統管理員權限執行
        PriceLibraryItem = self.env['price.library.item'].sudo()
        PriceLibraryItemSource = self.env['price.library.item.source'].sudo()

        extracted_count = 0
        skipped_count = 0
        batch_size = 500  # 批次大小

        # 2. 遍歷每個工項
        for idx, task in enumerate(tasks, 1):
            try:
                # 3. 匹配或建立價格庫項目
                # 層 1：精確名稱 + 單位；層 2：正規化名稱 + 單位
                library_item = PriceLibraryItem.search([
                    ('company_id', '=', self.company_id.id),
                    ('name', '=', task.name),
                    ('unit', '=', task.unit),
                ], limit=1)
                if not library_item:
                    norm = PriceLibraryItem._do_normalize(task.name)
                    if norm:
                        library_item = PriceLibraryItem.search([
                            ('company_id', '=', self.company_id.id),
                            ('name_normalized', '=', norm),
                            ('unit', '=', task.unit),
                        ], limit=1)

                if not library_item:
                    # 建立新的價格庫項目
                    # 嘗試找到或建立預設分類
                    default_category = self.env['price.library.category'].sudo().search([
                        ('company_id', '=', self.company_id.id),
                        ('code', '=', 'AUTO'),
                    ], limit=1)

                    if not default_category:
                        default_category = self.env['price.library.category'].sudo().create({
                            'name': '自動匯入',
                            'code': 'AUTO',
                            'company_id': self.company_id.id,
                            'sequence': 999,
                        })

                    library_item = PriceLibraryItem.create({
                        'name': task.name,
                        'item_no': task.item_no,
                        'parent_item_no': task.parent_id.item_no if task.parent_id else False,
                        'unit': task.unit,
                        'unit_price': task.unit_price,
                        'company_id': self.company_id.id,
                        'category_id': default_category.id,
                        'is_auto_created': True,
                        'auto_created_date': fields.Date.today(),
                        'price_source': f'專案: {self.code}',
                    })
                    _logger.debug(f'建立新價格庫項目: {library_item.name}')
                else:
                    pass  # 現有項目：單價由 source_ids 統計，不覆寫主記錄

                # 4. 建立價格來源記錄
                # 檢查是否已經提取過（避免重複）
                existing_source = PriceLibraryItemSource.search([
                    ('library_item_id', '=', library_item.id),
                    ('task_id', '=', task.id),
                ], limit=1)

                if existing_source:
                    _logger.debug(f'工項 {task.item_no} {task.name} 已經提取過，跳過')
                    skipped_count += 1
                    continue

                PriceLibraryItemSource.create({
                    'library_item_id': library_item.id,
                    'project_id': self.id,
                    'task_id': task.id,
                    'unit_price': task.unit_price,
                    'planned_qty': task.planned_qty,
                    'planned_amount': task.planned_amount,
                })

                extracted_count += 1

                # 批次提交
                if idx % batch_size == 0:
                    self.env.cr.commit()
                    _logger.info(f'已處理 {idx}/{len(tasks)} 筆工項')

            except Exception as e:
                _logger.error(f'提取工項 {task.item_no} {task.name} 失敗: {str(e)}')
                skipped_count += 1
                continue

        # 5. 更新專案統計
        self.write({
            'price_library_extracted': True,
            'price_library_extracted_date': fields.Datetime.now(),
            'price_library_extracted_count': extracted_count,
        })

        # 最終提交
        self.env.cr.commit()

        _logger.info(f'=== 專案 {self.code} 提取完成：成功 {extracted_count} 筆，跳過 {skipped_count} 筆 ===')

    # === 手動提取動作 ===
    def action_extract_to_price_library(self):
        """手動提取工項到價格庫"""
        for project in self:
            if project.state != 'closed':
                from odoo.exceptions import UserError
                raise UserError('只有已結案的專案可以提取工項到價格庫')

            project._extract_tasks_to_price_library()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '提取成功',
                'message': f'已提取 {self.price_library_extracted_count} 筆工項到價格庫',
                'type': 'success',
                'sticky': False,
            }
        }
