# -*- coding: utf-8 -*-
"""
Migration script: 用戶群組架構重構
從舊的 8 個 Portal 群組遷移到新的 6 個群組（4 個權限等級 + 2 個組織類型）
"""

def migrate(cr, version):
    """遷移用戶群組：從舊架構到新架構"""

    from odoo import api, SUPERUSER_ID
    import logging

    _logger = logging.getLogger(__name__)
    _logger.info("開始執行群組架構遷移...")

    env = api.Environment(cr, SUPERUSER_ID, {})

    # 群組對應表：舊群組 → (新權限等級群組, 新組織類型群組)
    old_to_new = {
        'group_supervision_subscriber': ('group_portal_subscriber', 'group_supervision_org'),
        'group_supervision_project_leader': ('group_portal_leader', 'group_supervision_org'),
        'group_supervision_regular_user': ('group_portal_user', 'group_supervision_org'),
        'group_supervision_viewer': ('group_portal_viewer', 'group_supervision_org'),
        'group_contractor_subscriber': ('group_portal_subscriber', 'group_contractor_org'),
        'group_contractor_project_leader': ('group_portal_leader', 'group_contractor_org'),
        'group_contractor_regular_user': ('group_portal_user', 'group_contractor_org'),
        'group_contractor_viewer': ('group_portal_viewer', 'group_contractor_org'),
    }

    module_name = 'construction_supervision_base'
    total_migrated = 0

    for old_xmlid, (new_level_xmlid, new_org_xmlid) in old_to_new.items():
        try:
            # 取得舊群組
            old_group = env.ref(f'{module_name}.{old_xmlid}', raise_if_not_found=False)
            if not old_group:
                _logger.warning(f"找不到舊群組: {old_xmlid}，跳過")
                continue

            # 取得新群組
            new_level_group = env.ref(f'{module_name}.{new_level_xmlid}', raise_if_not_found=False)
            new_org_group = env.ref(f'{module_name}.{new_org_xmlid}', raise_if_not_found=False)

            if not new_level_group:
                _logger.error(f"找不到新權限等級群組: {new_level_xmlid}")
                continue

            if not new_org_group:
                _logger.error(f"找不到新組織類型群組: {new_org_xmlid}")
                continue

            # 找出擁有舊群組的用戶
            users = env['res.users'].search([('groups_id', 'in', [old_group.id])])

            if not users:
                _logger.info(f"群組 {old_xmlid} 沒有用戶，跳過")
                continue

            # 將用戶加入新群組
            for user in users:
                user.write({
                    'groups_id': [
                        (4, new_level_group.id),  # 加入權限等級群組
                        (4, new_org_group.id),    # 加入組織類型群組
                    ]
                })

            total_migrated += len(users)
            _logger.info(
                f"✓ 遷移完成: {old_xmlid} → {new_level_xmlid} + {new_org_xmlid} "
                f"({len(users)} 位用戶)"
            )

        except Exception as e:
            _logger.error(f"遷移群組 {old_xmlid} 時發生錯誤: {str(e)}")
            continue

    _logger.info(f"群組架構遷移完成！共遷移 {total_migrated} 位用戶")

    # 驗證：確認沒有用戶遺漏
    all_old_groups = []
    for old_xmlid in old_to_new.keys():
        old_group = env.ref(f'{module_name}.{old_xmlid}', raise_if_not_found=False)
        if old_group:
            all_old_groups.append(old_group.id)

    if all_old_groups:
        remaining_users = env['res.users'].search([
            ('groups_id', 'in', all_old_groups),
            ('id', '!=', SUPERUSER_ID),  # 排除 admin
        ])

        if remaining_users:
            _logger.warning(
                f"警告：仍有 {len(remaining_users)} 位用戶擁有舊群組，請手動檢查"
            )
        else:
            _logger.info("驗證通過：所有用戶已成功遷移到新群組")
