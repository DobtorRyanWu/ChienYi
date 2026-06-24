# -*- coding: utf-8 -*-
"""post-migration:把舊的業主關聯欄位(authority_id / authority_contact_id, Many2one)
對應的 partner 名稱,回填到新的純文字欄位(authority_name / authority_contact_name)。

背景:18.0.4.x 起 supervision.project 的「業主/主辦機關、機關承辦人」由 res.partner
關聯(Many2one)改為純文字(Char)。Odoo 移除欄位時不會自動刪除舊 DB 欄位,因此升級後舊的
authority_id / authority_contact_id(孤兒欄位)資料仍在,可在此階段搬移到新欄位,避免既有
業主資料遺失。

放在 post-migrate 而非 pre-migrate 的原因:pre 階段新欄位(authority_name)尚未由 ORM
建立,無法寫入;post 階段新欄位已建好(空值)、舊孤兒欄位資料仍在,兩者並存正好可搬移。

全新安裝不會跑 migration(無既有資料),故僅影響既有 DB 升級。
"""

import logging

_logger = logging.getLogger(__name__)

TABLE = 'supervision_project'
# (舊 Many2one 欄位, 新 Char 欄位) 對照
FIELD_PAIRS = [
    ('authority_id', 'authority_name'),
    ('authority_contact_id', 'authority_contact_name'),
]


def _column_exists(cr, table, column):
    cr.execute(
        """SELECT 1 FROM information_schema.columns
           WHERE table_name = %s AND column_name = %s""",
        (table, column),
    )
    return cr.fetchone() is not None


def migrate(cr, version):
    # version 為 None 代表全新安裝,無既有資料需搬移
    if not version:
        return

    for old_col, new_col in FIELD_PAIRS:
        # 不同升級路徑下舊孤兒欄位或新欄位可能不存在,任一缺少即跳過(防禦)
        if not _column_exists(cr, TABLE, old_col):
            _logger.info("跳過 %s:舊欄位不存在", old_col)
            continue
        if not _column_exists(cr, TABLE, new_col):
            _logger.warning("跳過 %s:新欄位 %s 不存在", old_col, new_col)
            continue

        # 僅在新欄位為空且舊關聯有值時回填,避免覆蓋使用者已輸入的文字。
        # 欄位名稱皆為本檔具名常數,非外部輸入,無 SQL injection 疑慮。
        cr.execute(
            """
            UPDATE {table} sp
               SET {new_col} = rp.name
              FROM res_partner rp
             WHERE sp.{old_col} = rp.id
               AND COALESCE(sp.{new_col}, '') = ''
            """.format(table=TABLE, old_col=old_col, new_col=new_col)
        )
        _logger.info("回填 %s → %s:%s 筆", old_col, new_col, cr.rowcount)
