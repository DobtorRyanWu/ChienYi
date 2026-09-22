# -*- coding: utf-8 -*-
# 18.0.6.2.0：新增「工程管理者」群組後，把既有的工程師帳號遷過去。
#
# 條件：內部帳號、有「設定」(base.group_system)、有 group_supervisor_admin
#       （原本下拉的「系統管理者」）、而且不是代操作員。
#   → 原本「系統管理者＋設定」的組合就是工程師，改成「工程管理者」。
#   → 代操作員不動；__system__（id 1）沒有 group_supervisor_admin，自然排除。
#
# 登入後的首頁：工程管理者維持原本的畫面（使用者裁示）。
# _apply_operator_home_action 已排除工程管理者；這裡再把 action_id 還原成
# 遷移前的值，確保不會因為加入群組而被改掉。
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    manager = env.ref('construction_supervision_base.group_engineering_manager')
    operator = env.ref('construction_supervision_base.group_operator')
    backend = env.ref('construction_supervision_base.group_supervisor_admin')
    system = env.ref('base.group_system')

    users = env['res.users'].with_context(active_test=False).search([
        ('share', '=', False),
        ('groups_id', 'in', system.id),
        ('groups_id', 'in', backend.id),
        ('groups_id', 'not in', operator.id),
        ('groups_id', 'not in', manager.id),
    ])
    for user in users:
        old_action = user.action_id.id
        user.write({'groups_id': [(4, manager.id)]})
        if user.action_id.id != old_action:
            user.action_id = old_action
        _logger.info('工程管理者遷移：%s (id=%s)', user.login, user.id)
    _logger.info('工程管理者遷移完成，共 %s 個帳號', len(users))
