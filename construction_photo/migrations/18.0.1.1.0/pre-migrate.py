# -*- coding: utf-8 -*-
"""
Pre-migration: source_model 代碼遷移
舊值（英文全名）→ 新值（三字母代碼）
"""
import logging

_logger = logging.getLogger(__name__)

# 舊值 → 新值 對照表
SOURCE_MAPPING = {
    'daily_log': 'DLG',
    'inspection': 'INS',
    'defect': 'DEF',
    'test': 'TST',
    'acceptance': 'ACP',
    'notification': 'NTF',
    'other': 'MAN',
}


def migrate(cr, version):
    """遷移 source_model 欄位值"""
    if not version:
        return

    _logger.info("開始遷移 supervision_photo.source_model 代碼...")

    for old_val, new_val in SOURCE_MAPPING.items():
        cr.execute(
            "UPDATE supervision_photo SET source_model = %s WHERE source_model = %s",
            (new_val, old_val)
        )
        count = cr.rowcount
        if count:
            _logger.info("  %s → %s: %d 筆", old_val, new_val, count)

    _logger.info("source_model 代碼遷移完成")
