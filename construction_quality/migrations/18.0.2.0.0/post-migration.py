# -*- coding: utf-8 -*-
from datetime import datetime

def migrate(cr, version):
    """遷移後處理"""

    # 1. 設定預設 record_type
    cr.execute("""
        UPDATE reservation_defect_improvement
        SET record_type = 'supervision'
        WHERE record_type IS NULL;
    """)

    # 2. 為所有工程建立預設前綴配置（如果尚未建立）
    # 找出所有有缺失改善記錄的工程，為它們建立前綴配置
    cr.execute("""
        INSERT INTO defect_improvement_prefix_config (
            project_id,
            supervision_prefix,
            contractor_prefix,
            create_date,
            write_date,
            create_uid,
            write_uid
        )
        SELECT DISTINCT
            project_id,
            '監造' as supervision_prefix,
            '營造' as contractor_prefix,
            NOW() as create_date,
            NOW() as write_date,
            1 as create_uid,
            1 as write_uid
        FROM reservation_defect_improvement
        WHERE project_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM defect_improvement_prefix_config dipc
              WHERE dipc.project_id = reservation_defect_improvement.project_id
          );
    """)

    # 3. 計算並設定序號（按工程、日期、類型分組）
    cr.execute("""
        WITH numbered_records AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY project_id, found_date, check_type, record_type
                    ORDER BY id
                ) as seq_num
            FROM reservation_defect_improvement
        )
        UPDATE reservation_defect_improvement rdi
        SET sequence_number = nr.seq_num
        FROM numbered_records nr
        WHERE rdi.id = nr.id;
    """)

    # 4. 觸發編號重新計算（透過 compute 欄位）
    # 這會在模組更新後自動執行
