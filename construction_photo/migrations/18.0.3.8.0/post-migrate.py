# -*- coding: utf-8 -*-
"""照片管理模組 18.0.3.7.4 → 18.0.3.8.0：shot_date 改台灣日期，既有資料重算（公司儀表板合約 §5.3）。

原本 shot_date 取 shot_at.date()（shot_at 存 naive UTC → UTC 日期），台灣 00:00–07:59 上傳的照片
日期落到前一天；另有照片 shot_at 有值、shot_date 卻是空的，永遠算不進「今日照片」。
dev 實查（升級前）：前者 52 張、後者 121 張。

只動兩種值，不動可能是人填的日期：
1. shot_at 有值、shot_date 空 → 補台灣日期。
2. shot_date ＝ shot_at 的 UTC 日期、且不等於台灣日期（＝舊公式算出來的）→ 改台灣日期。
   **例外：前台上傳的照片（is_portal_uploaded）不改、只記數**——前台上傳表單有「照片日期」欄位，
   會直接寫 shot_date；台灣 00:00–07:59 上傳、而使用者選的剛好是前一天（＝UTC 日期）時，
   從資料分不出是舊公式還是人選的，保守不動（dev 這種照片 0 張）。
shot_date 與兩個日期都不同（人填的）、shot_at 空的，都不動。

日期換算用模型同一支 to_local_date()（不用 SQL 的 AT TIME ZONE），結果與之後新建照片的 compute 一致。
寫完以同一套分類再掃一次，還有應補／應改的就丟例外讓升級失敗（不信 UPDATE 的 rowcount）。
"""

import logging

from odoo.addons.construction_supervision_base.utils.local_date import to_local_date

_logger = logging.getLogger(__name__)

# 一次 UPDATE 的筆數上限（VALUES 清單）
UPDATE_BATCH = 1000


def _has_column(cr, table, column):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table, column))
    return bool(cr.fetchone())


def classify_shot_dates(cr):
    """回傳 (應補 [(id, 日期)], 應改 [(id, 日期)], 前台上傳而跳過的 id 清單)。"""
    portal_col = 'is_portal_uploaded' if _has_column(cr, 'supervision_photo', 'is_portal_uploaded') else 'FALSE'
    cr.execute(f"""
        SELECT id, shot_at, shot_date, COALESCE({portal_col}, FALSE)
        FROM supervision_photo
        WHERE shot_at IS NOT NULL
        ORDER BY id
    """)
    fill, change, skipped_portal = [], [], []
    for photo_id, shot_at, shot_date, portal in cr.fetchall():
        local = to_local_date(shot_at)
        if shot_date is None:
            fill.append((photo_id, local))
        elif shot_date == local:
            continue
        elif shot_date == shot_at.date():
            if portal:
                skipped_portal.append(photo_id)
            else:
                change.append((photo_id, local))
        # 其他：與 UTC、台灣日期都不同＝人填的，不動
    return fill, change, skipped_portal


def _write(cr, pairs):
    for start in range(0, len(pairs), UPDATE_BATCH):
        chunk = pairs[start:start + UPDATE_BATCH]
        values = ', '.join(['(%s, %s::date)'] * len(chunk))
        params = [v for pair in chunk for v in pair]
        cr.execute(f"""
            UPDATE supervision_photo AS p SET shot_date = v.d
            FROM (VALUES {values}) AS v(id, d)
            WHERE p.id = v.id
        """, params)


def recompute_shot_dates(cr):
    """重算並驗算；回傳筆數 {'filled', 'changed', 'skipped_portal'}。驗算不過丟 RuntimeError。"""
    fill, change, skipped_portal = classify_shot_dates(cr)
    _write(cr, fill + change)
    left_fill, left_change, _skipped = classify_shot_dates(cr)
    if left_fill or left_change:
        raise RuntimeError(
            f'照片日期重算後驗算不一致：仍有 {len(left_fill)} 張應補、{len(left_change)} 張應改'
            f'（例 id {[p for p, _d in (left_fill + left_change)[:10]]}）')
    stats = {'filled': len(fill), 'changed': len(change), 'skipped_portal': len(skipped_portal)}
    _logger.info('照片 shot_date 改台灣日期：補 %(filled)s 張、改日 %(changed)s 張、'
                 '前台上傳不確定是否人填而跳過 %(skipped_portal)s 張', stats)
    if skipped_portal:
        _logger.warning('前台上傳、shot_date 等於 UTC 日期的照片未改（可能是人選的日期），id 前 50 筆：%s',
                        skipped_portal[:50])
    return stats


def migrate(cr, version):
    if not version:
        return
    recompute_shot_dates(cr)
