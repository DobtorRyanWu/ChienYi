# -*- coding: utf-8 -*-
"""檢查時機：單選 Selection → 複選，選項掛在檢查類型底下。

背景：
  紙本表頭的「檢查時機」那一列本來就可以同時勾多個（實測 111 年度西區水利
  逸峰營造裂縫修補表：施工中＋施工完成），舊模型是單選 Selection，
  第二個勾選直接掉。
  而且各家表格的選項組不同、連用字都不同 —— 逸峰印「施工完成檢查」、
  川易印「施工後檢查」、監造抽查類則整組換成「查驗停留點／隨機抽查」。
  故選項不再寫死在欄位上，改成每個檢查類型自己一組
  （self.inspection.type.timing），檢查類型本身已有 project_id，
  「不同工程選項不同」自然成立。

本 script 做的事：
  1. 既有檢查類型補上 5 個預設時機
     （欄位上的 default= 只對「之後新建」的類型生效，既有 74 筆不會自己長出來）
  2. 把 pre 階段抄下來的舊值，依 code 對到「該筆自己的檢查類型」底下那一筆時機，
     寫進新的 Many2many
  3. 舊值的檢查類型是空的（沒得掛）→ 記進 log，不硬塞

刻意不做的事：
  不替「檢查類型為空」的記錄造一個孤兒時機。那會讓資料看起來完整、
  實際上指向一個沒人管的類型，之後再也沒人會發現。
"""
import logging

_logger = logging.getLogger(__name__)

# 與 models/self_inspection_type.py 的 DEFAULT_TIMINGS 一致。
# 這裡刻意複製一份而非 import：migration 要能對「當時的」值域負責，
# 日後模型改了預設值，已經跑過的遷移結果不該跟著漂移。
DEFAULT_TIMINGS = [
    ('hold_point', '查驗停留點', 10),
    ('random', '隨機抽查', 20),
    ('before', '施工前檢查', 30),
    ('during', '施工中檢查', 40),
    ('after', '施工完成檢查', 50),
]

SOURCES = (
    ('general_self_inspection', '_mig_5000_gsi_timing',
     'general_self_inspection_timing_rel'),
    ('reservation_self_inspection', '_mig_5000_rsi_timing',
     'reservation_self_inspection_timing_rel'),
)


def _table_exists(cr, name):
    cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = %s",
               (name,))
    return bool(cr.fetchone())


def migrate(cr, version):
    if not version:
        return

    # ── 1. 既有檢查類型補預設時機 ──────────────────────────────────────────
    cr.execute("SELECT id FROM self_inspection_type")
    type_ids = [r[0] for r in cr.fetchall()]

    cr.execute("SELECT type_id, code FROM self_inspection_type_timing "
               "WHERE code IS NOT NULL")
    existing = {(r[0], r[1]) for r in cr.fetchall()}

    created = 0
    for type_id in type_ids:
        for code, name, seq in DEFAULT_TIMINGS:
            if (type_id, code) in existing:
                continue
            cr.execute("""
                INSERT INTO self_inspection_type_timing
                       (type_id, name, sequence, code, create_uid, create_date,
                        write_uid, write_date)
                VALUES (%s, %s, %s, %s, 1, now() AT TIME ZONE 'UTC',
                        1, now() AT TIME ZONE 'UTC')
            """, (type_id, name, seq, code))
            created += 1
    _logger.info('檢查時機遷移：%s 個檢查類型，補建預設時機 %s 筆',
                 len(type_ids), created)

    # ── 2. 舊單選值 → 新複選關聯 ──────────────────────────────────────────
    for table, tmp, rel in SOURCES:
        if not _table_exists(cr, tmp):
            _logger.info('檢查時機遷移：%s 沒有暫存表，略過（欄位本來就不在）', table)
            continue

        # 該筆自己的檢查類型底下、code 相同的那一筆時機
        cr.execute("""
            INSERT INTO {rel} (inspection_id, timing_id)
            SELECT t.id, tm.id
              FROM {tmp} t
              JOIN {table} i ON i.id = t.id
              JOIN self_inspection_type_timing tm
                ON tm.type_id = i.inspection_type_id
               AND tm.code = t.timing_code
             ON CONFLICT DO NOTHING
        """.format(rel=rel, tmp=tmp, table=table))
        moved = cr.rowcount

        # 掛不上的：檢查類型為空，或該類型底下找不到這個 code
        cr.execute("""
            SELECT t.timing_code, count(*)
              FROM {tmp} t
              JOIN {table} i ON i.id = t.id
             WHERE NOT EXISTS (
                   SELECT 1 FROM {rel} r WHERE r.inspection_id = t.id)
             GROUP BY t.timing_code
        """.format(tmp=tmp, table=table, rel=rel))
        orphans = cr.fetchall()

        cr.execute("SELECT count(*) FROM %s" % tmp)
        total = cr.fetchone()[0]
        _logger.info('檢查時機遷移：%s 舊值 %s 筆 → 遷入 %s 筆%s',
                     table, total, moved,
                     ('，掛不上 %s' % dict(orphans)) if orphans else '')

        cr.execute('DROP TABLE IF EXISTS %s' % tmp)

    # ── 3. 讓 stored compute 的顯示文字重算 ────────────────────────────────
    # 新增的 stored 欄位 Odoo 會在建欄時算一次，但那時 M2M 還是空的
    # （本 script 才剛寫進去），必須明確再戳一次。
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    for model in ('general.self.inspection', 'reservation.self.inspection'):
        records = env[model].search([('inspection_timing_ids', '!=', False)])
        records.modified(['inspection_timing_ids'])
        records._compute_inspection_timing_display()
        records.flush_recordset(['inspection_timing_display'])
        _logger.info('檢查時機遷移：%s 重算顯示文字 %s 筆', model, len(records))
