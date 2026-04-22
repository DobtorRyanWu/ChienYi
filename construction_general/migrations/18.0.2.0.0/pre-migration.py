# -*- coding: utf-8 -*-

def migrate(cr, version):
    """遷移前準備"""
    # 1. 備份現有編號
    cr.execute("""
        ALTER TABLE general_defect_improvement
        ADD COLUMN IF NOT EXISTS name_backup VARCHAR;
    """)
    cr.execute("""
        UPDATE general_defect_improvement
        SET name_backup = name;
    """)

    # 2. 備份 check_type
    cr.execute("""
        ALTER TABLE general_defect_improvement
        ADD COLUMN IF NOT EXISTS check_type_backup VARCHAR;
    """)
    cr.execute("""
        UPDATE general_defect_improvement
        SET check_type_backup = check_type;
    """)
