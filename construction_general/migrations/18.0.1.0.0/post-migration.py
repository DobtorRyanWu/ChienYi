# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """遷移舊的 Many2many 照片到新的 One2many 結構"""
    env = api.Environment(cr, SUPERUSER_ID, {})

    _logger.info('開始遷移缺失改善照片數據...')

    # 檢查舊欄位是否存在
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'general_defect_photo_rel'
        );
    """)
    if not cr.fetchone()[0]:
        _logger.info('未發現舊照片數據表，跳過遷移')
        return

    defects = env['general.defect.improvement'].search([
        '|',
        ('defect_photo_ids_legacy', '!=', False),
        ('improvement_photo_ids_legacy', '!=', False),
    ])

    migrated_count = 0

    for defect in defects:
        try:
            # 遷移缺失照片（矯正前）
            for attachment in defect.defect_photo_ids_legacy:
                existing = env['general.defect.improvement.photo'].search([
                    ('defect_improvement_id', '=', defect.id),
                    ('attachment_id', '=', attachment.id),
                ], limit=1)

                if not existing:
                    env['general.defect.improvement.photo'].create({
                        'defect_improvement_id': defect.id,
                        'attachment_id': attachment.id,
                        'photo_stage': 'before',
                        'upload_time': defect.found_date or defect.create_date,
                        'description': '自動遷移：缺失照片',
                    })
                    migrated_count += 1

            # 遷移改善照片（矯正後）
            for attachment in defect.improvement_photo_ids_legacy:
                existing = env['general.defect.improvement.photo'].search([
                    ('defect_improvement_id', '=', defect.id),
                    ('attachment_id', '=', attachment.id),
                ], limit=1)

                if not existing:
                    env['general.defect.improvement.photo'].create({
                        'defect_improvement_id': defect.id,
                        'attachment_id': attachment.id,
                        'photo_stage': 'after',
                        'upload_time': defect.improvement_date or defect.write_date,
                        'description': '自動遷移：改善照片',
                    })
                    migrated_count += 1

        except Exception as e:
            _logger.error(f'遷移缺失 {defect.name} 的照片時發生錯誤: {str(e)}')
            continue

    _logger.info(f'照片遷移完成！共遷移 {migrated_count} 張照片')
