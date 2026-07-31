# -*- coding: utf-8 -*-
"""照片資料表收斂的共用 migration 工具。

為什麼拆成共用工具而不是一支大 migration
----------------------------------------
收斂涉及 6 個模組的表，而 `construction_photo` 是其他模組的**依賴**，
它的 migration 執行時，下游模組（construction_general 等）宣告的來源欄位
（general_defect_id…）根本還不存在。上一輪就踩過同樣的坑：
缺失照片回填寫在 construction_photo 的 migration 裡，log 顯示
「模型 general.defect.improvement 未安裝，略過」。

所以改成**每個模組遷移自己的表與自己的欄位**，載入順序天然正確，
共用邏輯放在這裡避免抄六份。

⚠️ 附件脫鉤必須在刪表之前
-------------------------
缺失照片行的附件是 Odoo core 為 `image = Binary(attachment=True)` 建的
欄位附件（res_model=照片行模型 / res_field='image'）。直接刪照片行，
core 會**連帶刪掉附件**，照片就真的消失了。
`migrate_defect_lines()` 一定會先脫鉤再讓呼叫端刪表；而 `drop_tables()`
只在 `verify()` 通過時才由呼叫端執行 —— 驗證沒過就保留舊表，資料還在、
可以修正後重跑（本工具全部以 attachment_id 去重，重跑安全）。
"""

import logging

_logger = logging.getLogger(__name__)


def table_exists(cr, table):
    cr.execute("select to_regclass(%s)", (f'public.{table}',))
    return cr.fetchone()[0] is not None


def count(cr, table):
    if not table_exists(cr, table):
        return 0
    cr.execute(f'select count(*) from {table}')
    return cr.fetchone()[0]


def snapshot(cr):
    """遷移前基準，交給 verify() 比對。"""
    return {
        'photos': count(cr, 'supervision_photo'),
        'attachments': count(cr, 'ir_attachment'),
    }


def migrate_defect_lines(cr, line_table, defect_table, source_col, line_model):
    """缺失照片行 → supervision_photo（含 photo_stage 與**附件脫鉤**）。"""
    if not table_exists(cr, line_table):
        return 0

    # (1) 還沒有對應 supervision_photo 的照片行 → 補建
    cr.execute(f"""
        insert into supervision_photo
            (attachment_id, project_id, {source_col}, photo_stage,
             description, shot_at, upload_date, source_model, source_id,
             active, create_uid, write_uid, create_date, write_date)
        select l.attachment_id, d.project_id, l.defect_improvement_id,
               l.photo_stage,
               coalesce(nullif(l.description, ''), a.name),
               coalesce(l.upload_time, now() at time zone 'utc'),
               coalesce(l.upload_time, now() at time zone 'utc'),
               'defect', l.defect_improvement_id,
               true, 1, 1,
               now() at time zone 'utc', now() at time zone 'utc'
          from {line_table} l
          join ir_attachment a on a.id = l.attachment_id
          join {defect_table} d on d.id = l.defect_improvement_id
         where l.attachment_id is not null
           and not exists (select 1 from supervision_photo p
                            where p.attachment_id = l.attachment_id)
    """)
    created = cr.rowcount

    # (2) 收斂前由「同步」建出來的照片 → 回填來源欄位與階段
    cr.execute(f"""
        update supervision_photo p
           set {source_col} = l.defect_improvement_id,
               photo_stage  = l.photo_stage
          from {line_table} l
         where p.attachment_id = l.attachment_id
           and p.{source_col} is null
    """)
    linked = cr.rowcount

    # (3) ⚠️ 附件脫鉤 —— 沒有這步，刪表時 core 會把照片檔案一起帶走
    cr.execute("""
        update ir_attachment a
           set res_model = 'supervision.photo', res_field = null, res_id = p.id
          from supervision_photo p
         where p.attachment_id = a.id
           and a.res_model = %s
           and a.res_field = 'image'
    """, (line_model,))
    detached = cr.rowcount

    _logger.info('照片收斂 %s：新建 %s、回填 %s、附件脫鉤 %s',
                 line_table, created, linked, detached)
    return created


def migrate_m2m(cr, rel_table, rec_col, source_col, project_sql=None):
    """M2M 中間表 → supervision_photo 的來源欄位。

    project_sql：用來取得所屬工程的 SQL 片段（以 r.<rec_col> 為輸入），
    留空表示來源記錄本身就是工程案件（告示牌）。
    """
    if not table_exists(cr, rel_table):
        return 0

    project_expr = project_sql or f'r.{rec_col}'
    cr.execute(f"""
        insert into supervision_photo
            (attachment_id, project_id, {source_col}, description,
             shot_at, upload_date, active,
             create_uid, write_uid, create_date, write_date)
        select r.attachment_id, {project_expr}, r.{rec_col}, a.name,
               now() at time zone 'utc', now() at time zone 'utc', true,
               1, 1, now() at time zone 'utc', now() at time zone 'utc'
          from {rel_table} r
          join ir_attachment a on a.id = r.attachment_id
         where not exists (select 1 from supervision_photo p
                            where p.attachment_id = r.attachment_id)
    """)
    created = cr.rowcount

    cr.execute(f"""
        update supervision_photo p
           set {source_col} = r.{rec_col}
          from {rel_table} r
         where p.attachment_id = r.attachment_id
           and p.{source_col} is null
    """)
    _logger.info('照片收斂 %s：新建 %s、回填 %s', rel_table, created, cr.rowcount)
    return created


def backfill_from_source_ref(cr, source_model_code, source_col, source_table):
    """已經是 supervision_photo、但只用舊的 source_model/source_id 標記來源的照片，
    回填成真正的 Many2one。

    檢試驗與通報單的照片本來就直接建在 supervision_photo（沒有中間表），
    只是靠字串+整數的假關聯掛著，所以只需要這一步。
    """
    cr.execute(f"""
        update supervision_photo p
           set {source_col} = p.source_id
          from {source_table} s
         where p.source_model = %s
           and p.source_id = s.id
           and p.{source_col} is null
    """, (source_model_code,))
    _logger.info('照片收斂 %s：回填 %s 筆', source_col, cr.rowcount)
    return cr.rowcount


def verify(cr, before, line_tables=(), rel_tables=()):
    """驗證。任何一項不過就回 False —— 呼叫端不可刪表。"""
    ok = True

    after = snapshot(cr)
    if after['photos'] < before['photos']:
        _logger.error('照片收斂驗證失敗：照片總數變少 %s → %s',
                      before['photos'], after['photos'])
        ok = False
    if after['attachments'] < before['attachments']:
        _logger.error(
            '照片收斂驗證失敗：ir_attachment 少了 %s 張（%s → %s）——'
            '附件脫鉤沒做對，照片檔案會遺失，中止刪表',
            before['attachments'] - after['attachments'],
            before['attachments'], after['attachments'])
        ok = False

    for table in list(line_tables) + list(rel_tables):
        if not table_exists(cr, table):
            continue
        cr.execute(f"""
            select count(*) from {table} t
             where t.attachment_id is not null
               and not exists (select 1 from supervision_photo p
                                where p.attachment_id = t.attachment_id)
        """)
        missing = cr.fetchone()[0]
        if missing:
            _logger.error('照片收斂驗證失敗：%s 有 %s 筆沒有對應照片', table, missing)
            ok = False

    cr.execute("""
        select count(*) from supervision_photo p
         where p.attachment_id is not null
           and not exists (select 1 from ir_attachment a
                            where a.id = p.attachment_id)
    """)
    broken = cr.fetchone()[0]
    if broken:
        _logger.error('照片收斂驗證失敗：%s 筆照片的附件不存在', broken)
        ok = False

    return ok


def drop_tables(cr, tables, models=()):
    """驗證通過後才刪。Odoo 不會自動 drop 被移除模型的表。"""
    dropped = []
    for table in tables:
        if table_exists(cr, table):
            cr.execute(f'drop table {table} cascade')
            dropped.append(table)
    for model in models:
        cr.execute("""
            delete from ir_model_data
             where model = 'ir.model'
               and res_id in (select id from ir_model where model = %s)
        """, (model,))
        cr.execute("delete from ir_model where model = %s", (model,))
    _logger.info('照片收斂：已刪除舊表 %s', dropped)
    return dropped
