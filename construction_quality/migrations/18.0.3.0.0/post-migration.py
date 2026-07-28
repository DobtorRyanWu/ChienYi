# -*- coding: utf-8 -*-
"""查驗階段改為段落主檔：把舊 stage 值搬進新的 stage_id。

搭配 pre-migration.py 使用，背景見該檔說明。

為什麼全用 SQL 而不用 ORM：
  - 避開 stage_ids 的 default（會對每個既有類型再塞一次三段）
  - 避開 _check_stage_belongs_to_type 在中途半成品狀態下誤炸
  - 避開 mail tracking 對一千多列逐筆寫 message
  - 1600 多列一個 statement 完事，且完全確定性

⚠️ 刻意不 DROP 舊 stage 欄位。留到下一個版本確認生產穩定後才清，
   在那之前舊 varchar 欄位是唯一的無痛回滾路徑。

冪等：建段落有 NOT EXISTS 守衛，回填有 IS NULL 守衛，重跑無副作用。
"""

import logging

_logger = logging.getLogger(__name__)

# (legacy_code, 段落名稱, sequence)
_LEGACY_STAGES = (
    ('stage1', '施工前', 10),
    ('stage2', '施工中', 20),
    ('stage3', '施工後', 30),
)

# (item 表, 主檔表 or None)；None 代表該表自己就有 type_id
_ITEM_TABLES = (
    ('self_inspection_type_item', None),
    ('general_self_inspection_item', 'general_self_inspection'),
    ('reservation_self_inspection_item', 'reservation_self_inspection'),
)


def migrate(cr, version):
    if not version:
        return

    # ── 1. 為每個既有類型建立三個標準段落 ─────────────────────
    for code, name, seq in _LEGACY_STAGES:
        cr.execute("""
            INSERT INTO self_inspection_type_stage
                   (type_id, name, sequence, legacy_code,
                    create_uid, create_date, write_uid, write_date)
            SELECT t.id, %s, %s, %s, 1, now(), 1, now()
              FROM self_inspection_type t
             WHERE NOT EXISTS (
                   SELECT 1 FROM self_inspection_type_stage s
                    WHERE s.type_id = t.id AND s.legacy_code = %s)
        """, (name, seq, code, code))
        _logger.info('[段落遷移] 建立「%s」段落 %s 筆', name, cr.rowcount)

    # ── 2. 樣板預設項目：自己就有 type_id ─────────────────────
    cr.execute("""
        UPDATE self_inspection_type_item i
           SET stage_id = s.id
          FROM self_inspection_type_stage s
         WHERE s.type_id = i.type_id
           AND s.legacy_code = i.stage
           AND i.stage_id IS NULL
    """)
    _logger.info('[段落遷移] self_inspection_type_item 回填 %s 列', cr.rowcount)

    # ── 3&4. 兩張逐項表：經主檔取得 inspection_type_id ────────
    for item_table, parent_table in _ITEM_TABLES[1:]:
        cr.execute("""
            UPDATE {item} i
               SET stage_id = s.id
              FROM {parent} p
              JOIN self_inspection_type_stage s
                ON s.type_id = p.inspection_type_id
             WHERE i.inspection_id = p.id
               AND s.legacy_code = i.stage
               AND i.stage_id IS NULL
        """.format(item=item_table, parent=parent_table))
        _logger.info('[段落遷移] %s 回填 %s 列', item_table, cr.rowcount)

        # stored related，順手補上讓 domain 立刻可用（Odoo 也會自行重算，重複無害）
        cr.execute("""
            UPDATE {item} i
               SET inspection_type_id = p.inspection_type_id
              FROM {parent} p
             WHERE i.inspection_id = p.id
               AND i.inspection_type_id IS DISTINCT FROM p.inspection_type_id
        """.format(item=item_table, parent=parent_table))
        _logger.info('[段落遷移] %s 補 inspection_type_id %s 列',
                     item_table, cr.rowcount)

    # ── 5. stage_sequence（stored related，_order 用）──────────
    # 新增 stored related 時 stage_id 還是空的，Odoo 那次重算填不到值，
    # 這裡在 stage_id 填好之後補算。
    for item_table, _parent in _ITEM_TABLES:
        cr.execute("""
            UPDATE {item} i
               SET stage_sequence = s.sequence
              FROM self_inspection_type_stage s
             WHERE i.stage_id = s.id
               AND i.stage_sequence IS DISTINCT FROM s.sequence
        """.format(item=item_table))
        _logger.info('[段落遷移] %s 補 stage_sequence %s 列', item_table, cr.rowcount)

    # ── 6. 驗證：舊值非空但新值仍空 = 資料遺失，中止整個升級 ──
    for item_table, _parent in _ITEM_TABLES:
        cr.execute("""
            SELECT count(*) FROM {item}
             WHERE stage IS NOT NULL AND stage <> '' AND stage_id IS NULL
        """.format(item=item_table))
        lost = cr.fetchone()[0]
        if lost:
            cr.execute("""
                SELECT stage, count(*) FROM {item}
                 WHERE stage IS NOT NULL AND stage <> '' AND stage_id IS NULL
                 GROUP BY 1 ORDER BY 1
            """.format(item=item_table))
            raise Exception(
                '[段落遷移] %s 有 %s 列的 stage 對不到任何段落：%s。'
                '整個升級已中止，資料未被更動。'
                % (item_table, lost, cr.fetchall()))

        cr.execute("""
            SELECT s.name, count(*) FROM {item} i
              LEFT JOIN self_inspection_type_stage s ON s.id = i.stage_id
             GROUP BY 1 ORDER BY 1
        """.format(item=item_table))
        _logger.info('[段落遷移] 升級後 %s 的段落分佈：%s', item_table, cr.fetchall())
