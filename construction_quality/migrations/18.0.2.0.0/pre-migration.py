# -*- coding: utf-8 -*-

def migrate(cr, version):
    """遷移前準備"""
    # 1. 備份現有編號
    cr.execute("""
        ALTER TABLE reservation_defect_improvement
        ADD COLUMN IF NOT EXISTS record_no_backup VARCHAR;
    """)
    cr.execute("""
        UPDATE reservation_defect_improvement
        SET record_no_backup = record_no;
    """)

    # 2. 備份 check_type（預約式已經是正確的選項，但仍備份）
    cr.execute("""
        ALTER TABLE reservation_defect_improvement
        ADD COLUMN IF NOT EXISTS check_type_backup VARCHAR;
    """)
    cr.execute("""
        UPDATE reservation_defect_improvement
        SET check_type_backup = check_type;
    """)
