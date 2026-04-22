# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """
    模組安裝後的資料遷移

    將現有無 company_id 的記錄分配給預設公司
    """
    _logger.info('=== 開始價格庫資料遷移 ===')

    # 取得預設公司（通常是第一個公司）
    default_company = env['res.company'].search([], limit=1)
    if not default_company:
        _logger.warning('無法找到預設公司，跳過資料遷移')
        return

    _logger.info(f'預設公司：{default_company.name} (ID: {default_company.id})')

    # 遷移價格庫分類
    categories_without_company = env['price.library.category'].search([
        ('company_id', '=', False)
    ])
    if categories_without_company:
        _logger.info(f'找到 {len(categories_without_company)} 筆無公司的價格庫分類')
        categories_without_company.write({'company_id': default_company.id})
        _logger.info('價格庫分類遷移完成')
    else:
        _logger.info('無需遷移價格庫分類')

    # 遷移價格庫項目
    items_without_company = env['price.library.item'].search([
        ('company_id', '=', False)
    ])
    if items_without_company:
        _logger.info(f'找到 {len(items_without_company)} 筆無公司的價格庫項目')
        items_without_company.write({'company_id': default_company.id})
        _logger.info('價格庫項目遷移完成')
    else:
        _logger.info('無需遷移價格庫項目')

    _logger.info('=== 價格庫資料遷移完成 ===')
