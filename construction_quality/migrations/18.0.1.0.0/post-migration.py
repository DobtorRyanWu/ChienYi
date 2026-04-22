# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """遷移預約式缺失改善的舊照片到新結構"""
    env = api.Environment(cr, SUPERUSER_ID, {})

    _logger.info('開始遷移預約式缺失改善照片數據...')

    # 檢查舊欄位是否存在
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'reservation_defect_photo_rel'
        );
    """)
    if not cr.fetchone()[0]:
        _logger.info('未發現舊照片數據表，跳過遷移')
        return

    defects = env['reservation.defect.improvement'].search([
        '|',
        ('defect_photo_ids_legacy', '!=', False),
        ('improvement_photo_ids_legacy', '!=', False),
    ])

    migrated_count = 0

    for defect in defects:
        try:
            # 遷移缺失照片（矯正前）
            for attachment in defect.defect_photo_ids_legacy:
                existing = env['reservation.defect.improvement.photo'].search([
                    ('defect_improvement_id', '=', defect.id),
                    ('attachment_id', '=', attachment.id),
                ], limit=1)

                if not existing:
                    env['reservation.defect.improvement.photo'].create({
                        'defect_improvement_id': defect.id,
                        'attachment_id': attachment.id,
                        'photo_stage': 'before',
                        'upload_time': defect.found_date or defect.create_date,
                        'description': '自動遷移：缺失照片',
                    })
                    migrated_count += 1

            # 遷移改善照片（矯正後）
            for attachment in defect.improvement_photo_ids_legacy:
                existing = env['reservation.defect.improvement.photo'].search([
                    ('defect_improvement_id', '=', defect.id),
                    ('attachment_id', '=', attachment.id),
                ], limit=1)

                if not existing:
                    env['reservation.defect.improvement.photo'].create({
                        'defect_improvement_id': defect.id,
                        'attachment_id': attachment.id,
                        'photo_stage': 'after',
                        'upload_time': defect.improvement_date or defect.write_date,
                        'description': '自動遷移：改善照片',
                    })
                    migrated_count += 1

        except Exception as e:
            _logger.error(f'遷移預約式缺失 {defect.record_no} 的照片時發生錯誤: {str(e)}')
            continue

    _logger.info(f'預約式缺失改善照片遷移完成！共遷移 {migrated_count} 張照片')
