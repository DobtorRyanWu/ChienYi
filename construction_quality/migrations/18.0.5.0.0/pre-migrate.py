# -*- coding: utf-8 -*-
"""檢查時機：單選 Selection → 複選（掛在檢查類型底下的 self.inspection.type.timing）。

pre 階段只做一件事：把兩張表舊的 inspection_timing 字元欄整份抄進暫存表。

為什麼要抄而不是直接在 post 讀原欄：欄位已從 Python 模型移除，
Odoo 在升級收尾（_process_end）會清掉對應的 ir.model.fields，
不同版本對「要不要順手 DROP COLUMN」的行為不一致。抄一份是唯一可靠的作法，
真的被 drop 了資料也還在。
"""

TABLES = (
    ('general_self_inspection', '_mig_5000_gsi_timing'),
    ('reservation_self_inspection', '_mig_5000_rsi_timing'),
)


def migrate(cr, version):
    if not version:
        return

    for table, tmp in TABLES:
        cr.execute("""
            SELECT 1 FROM information_schema.columns
             WHERE table_name = %s AND column_name = 'inspection_timing'
        """, (table,))
        if not cr.fetchone():
            # 欄位不在（重跑或早已改過）→ 不建暫存表，post 端會自行略過
            continue

        cr.execute('DROP TABLE IF EXISTS %s' % tmp)
        cr.execute("""
            CREATE TABLE {tmp} AS
            SELECT id, inspection_timing AS timing_code
              FROM {table}
             WHERE inspection_timing IS NOT NULL
               AND inspection_timing != ''
        """.format(tmp=tmp, table=table))
