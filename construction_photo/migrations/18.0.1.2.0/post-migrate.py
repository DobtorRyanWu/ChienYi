# -*- coding: utf-8 -*-
"""
照片管理模組 18.0.1.1.0 → 18.0.1.2.0 升級

- 新增 supervision.photo.category 模型 + 19 筆預設分類
- supervision.photo 新增 category_id Many2one
- 遷移：把舊 category Selection 值對應到新 category_id（同代碼）
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """把既有 supervision.photo.category Selection 值遷移到 category_id"""

    # 對照表：Selection code → 新 category 的 xml_id
    code_to_xmlid = {
        'STL': 'construction_photo.cat_stl',
        'CON': 'construction_photo.cat_con',
        'FRM': 'construction_photo.cat_frm',
        'PIP': 'construction_photo.cat_pip',
        'ELC': 'construction_photo.cat_elc',
        'EXC': 'construction_photo.cat_exc',
        'BKF': 'construction_photo.cat_bkf',
        'PAV': 'construction_photo.cat_pav',
        'DRN': 'construction_photo.cat_drn',
        'DEF': 'construction_photo.cat_def',
        'OTH': 'construction_photo.cat_oth',
    }

    # 一次取出所有 xml_id 對應的 res_id
    cr.execute("""
        SELECT module || '.' || name AS xmlid, res_id
        FROM ir_model_data
        WHERE module = 'construction_photo'
          AND name LIKE 'cat_%'
    """)
    xmlid_to_id = {row[0]: row[1] for row in cr.fetchall()}

    migrated = 0
    skipped = 0
    for code, xmlid in code_to_xmlid.items():
        cat_id = xmlid_to_id.get(xmlid)
        if not cat_id:
            _logger.warning(f'  分類 xmlid {xmlid} 找不到對應 record，跳過 {code}')
            skipped += 1
            continue
        cr.execute("""
            UPDATE supervision_photo
            SET category_id = %s
            WHERE category = %s AND category_id IS NULL
        """, (cat_id, code))
        n = cr.rowcount
        if n:
            _logger.info(f'  遷移 {n} 張 {code} 照片到 category_id={cat_id}')
            migrated += n

    _logger.info(
        f'supervision.photo.category 遷移完成：'
        f'已轉 {migrated} 張，無對應 {skipped} 類'
    )
