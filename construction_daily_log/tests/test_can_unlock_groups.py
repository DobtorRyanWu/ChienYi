# -*- coding: utf-8 -*-
"""can_unlock 不再含人資管理群組（公司儀表板合約 §13-8）；原本能解鎖的監造方角色照樣能。"""
from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

HR_MANAGER = 'hr.group_hr_manager'
# 原本能解鎖的角色（_compute_can_unlock 的其餘分支）
STILL_UNLOCK_GROUPS = (
    'base.group_system',
    # group_supervision_manager 這個 xmlid 目前不存在（_compute_can_unlock 原有的死分支，has_group 回 False），不測
    'construction_supervision_base.group_portal_subscriber',
    'construction_supervision_base.group_portal_leader',
    'construction_supervision_base.group_operator',
)
LOCKED_AGE_DAYS = 20


@tagged('post_install', '-at_install', 'construction_daily_log')
class TestCanUnlockGroups(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        project = cls.env['project.project'].create({
            'name': 'UNLOCK 測試工程', 'code': 'UNLOCK-1', 'project_type': 'general',
            'state': 'construction', 'company_id': company.id})
        employee = cls.env['hr.employee'].create({'name': 'UNLOCK 填表人', 'company_id': company.id})
        schedule = cls.env['progress.schedule'].create({
            'project_id': project.id, 'change_date': fields.Date.today()})
        schedule.write({'state': 'active'})
        cls.sheet = cls.env['daily.log.sheet'].create({
            'supervision_project_id': project.id, 'company_id': company.id,
            'employee_id': employee.id, 'log_date': fields.Date.today() - timedelta(days=LOCKED_AGE_DAYS)})

    def _user(self, login, xmlids):
        # 前台角色群組隱含 base.group_portal，不能再加內部使用者（核心「不能同時有多個使用者類型」）
        portal = any('portal_' in x for x in xmlids)
        base = [] if portal else [self.env.ref('base.group_user').id]
        groups = base + [self.env.ref(x).id for x in xmlids]
        vals = {'name': login, 'login': login, 'groups_id': [(6, 0, groups)]}
        if portal:
            # 監造方前台帳號（不勾的話建帳號會自動勾營造組織＝營造方；S2 起 can_unlock 與解鎖路由同一把尺，營造方不能解鎖）
            vals['is_supervision_org'] = True
        return self.env['res.users'].create(vals)

    def test_hr_manager_cannot_unlock(self):
        user = self._user('unlock_hr', [HR_MANAGER])
        self.assertTrue(user.has_group(HR_MANAGER), '前提：帳號帶人資管理群組')
        self.assertFalse(self.sheet.with_user(user).can_unlock)

    def test_other_groups_still_unlock(self):
        """兩個方向都比：被拿掉的不能，其餘（監造方原本能解鎖的）照樣能。"""
        for xmlid in STILL_UNLOCK_GROUPS:
            user = self._user('unlock_' + xmlid.split('.')[-1], [xmlid])
            self.assertTrue(self.sheet.with_user(user).can_unlock, xmlid)
