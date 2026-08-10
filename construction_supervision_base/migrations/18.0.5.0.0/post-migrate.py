# -*- coding: utf-8 -*-
# 回填既有代操作員的首頁動作 → 工程管理 > 工程總覽 > 工程案件。
#
# 新的 _apply_operator_home_action() 只在 create / 群組異動時觸發，既有帳號
# 不會自己套用，所以這裡補一次。與 helper 同樣的規則：只填空的，不覆蓋
# 使用者自己設過的首頁動作。
#
# 用純 SQL 是因為 res.users.action_id 有 _check_action_id constrains，
# 走 ORM 會為了每個帳號重跑一次檢查；這裡寫入的 action 是固定同一支
# （project.project 的 act_window、context 為 {} 不含 active_id），
# 已確認通過該 constrains。

def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        SELECT res_id FROM ir_model_data
         WHERE model = 'ir.actions.act_window'
           AND module = 'construction_supervision_base'
           AND name = 'action_supervision_project'
    """)
    row = cr.fetchone()
    if not row:
        return
    action_id = row[0]

    cr.execute("""
        SELECT res_id FROM ir_model_data
         WHERE model = 'res.groups'
           AND module = 'construction_supervision_base'
           AND name = 'group_operator'
    """)
    row = cr.fetchone()
    if not row:
        return
    group_id = row[0]

    cr.execute("""
        UPDATE res_users u
           SET action_id = %s
          FROM res_groups_users_rel r
         WHERE r.uid = u.id
           AND r.gid = %s
           AND u.action_id IS NULL
    """, (action_id, group_id))
