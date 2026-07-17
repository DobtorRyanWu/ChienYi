# -*- coding: utf-8 -*-
"""
Migration 18.0.4.3.0（pre）：前台四角色「往下合併」

背景：
  舊「權限等級」category 同時有兩套並列四階層——
    舊 4 階（viewer⊂user⊂leader⊂subscriber，扛 303 條 ACL）
    新 v11 4 角（observer/field/manager/boss，各 imply 一個舊群組）
  兩套並列導致 Odoo 無法把 category linearize 成單一繼承鏈，使用者表單退化成
  核取方塊、只有開發者模式看得到。

合併方向（搬遷量最小）：
  保留舊 4 群組的 xml_id（303 條 ACL 原地不動），改名為 老闆/主管/現場人員/
  定期閱覽者；把新 4 角的 record rule / guard / 12 條 ACL repoint 到對應舊群組
  （由 XML/CSV 檔完成），並刪除 4 個新群組。

為何必須放在 pre-migrate（而非 post）：
  新群組（observer 等）目前的 name 就是「定期閱覽者/現場人員/主管/老闆」。
  資料載入階段會把舊群組改成同名，若此時新群組仍存在，會撞 res.groups 的
  (category_id, name) 唯一約束（res_groups_name_uniq）。故必須在「資料載入之前」
  先刪掉 4 個新群組。

刪除順序（避開 RESTRICT 外鍵）：
  res.groups 的外鍵中，ir_model_access.group_id 與 rule_group_rel.group_id 為
  RESTRICT（會擋刪除），而此刻 ACL/rule 仍指向新群組（CSV/XML 的 repoint 在資料
  階段、發生在 pre 之後）。因此本腳本先把這兩個關聯 repoint 到對應舊群組，才刪
  群組。res_groups_users_rel、res_groups_implied_rel 為 CASCADE，刪群組時自動清。

注意：portal_valid_until 是 res.users 實體欄位，群組刪除不影響；observer 既有
      到期日自動保留，改名後這些帳號變成 viewer-only，正好命中新的到期判斷
      （viewer and not user）。
"""

import logging

_logger = logging.getLogger(__name__)

# 新角色 xml_id → 對應（改名後）舊群組 xml_id
NEW_TO_OLD = {
    'group_portal_boss': 'group_portal_subscriber',
    'group_portal_manager': 'group_portal_leader',
    'group_portal_field': 'group_portal_user',
    'group_portal_observer': 'group_portal_viewer',
}
MODULE = 'construction_supervision_base'


def _group_id(cr, xmlid):
    cr.execute(
        "SELECT res_id FROM ir_model_data WHERE module=%s AND model='res.groups' AND name=%s",
        (MODULE, xmlid))
    row = cr.fetchone()
    return row[0] if row else None


def migrate(cr, version):
    # 全新安裝（version 為空）不需遷移
    if not version:
        return

    _logger.info("開始執行 18.0.4.3.0（pre）前台四角色往下合併遷移...")

    for new_xmlid, old_xmlid in NEW_TO_OLD.items():
        nid = _group_id(cr, new_xmlid)
        oid = _group_id(cr, old_xmlid)
        if not oid:
            _logger.warning("找不到目標舊群組 %s，跳過", old_xmlid)
            continue
        if not nid:
            _logger.info("新群組 %s 已不存在，跳過", new_xmlid)
            continue

        # 1) 兜底：把掛在新群組的帳號補進舊群組（新角色本就 imply 舊群組，通常已存在）
        cr.execute(
            "INSERT INTO res_groups_users_rel (gid, uid) "
            "SELECT %s, uid FROM res_groups_users_rel WHERE gid=%s "
            "ON CONFLICT DO NOTHING",
            (oid, nid))

        # 2) repoint ACL（RESTRICT 外鍵，必須先改指向舊群組）
        cr.execute("UPDATE ir_model_access SET group_id=%s WHERE group_id=%s", (oid, nid))

        # 3) repoint record rule 的 M2M（RESTRICT 外鍵），先刪會撞主鍵的列再 UPDATE
        cr.execute(
            "DELETE FROM rule_group_rel WHERE group_id=%s "
            "AND rule_group_id IN (SELECT rule_group_id FROM rule_group_rel WHERE group_id=%s)",
            (nid, oid))
        cr.execute("UPDATE rule_group_rel SET group_id=%s WHERE group_id=%s", (oid, nid))

        # 4) 刪新群組：先清 ir_model_data，再刪 res_groups（users/implied 關聯 CASCADE 自動清）
        cr.execute(
            "DELETE FROM ir_model_data WHERE module=%s AND model='res.groups' AND res_id=%s",
            (MODULE, nid))
        cr.execute("DELETE FROM res_groups WHERE id=%s", (nid,))
        _logger.info("已刪除新群組 %s（id=%s），關聯 repoint 至 %s（id=%s）",
                     new_xmlid, nid, old_xmlid, oid)

    _logger.info("18.0.4.3.0（pre）遷移完成。")
