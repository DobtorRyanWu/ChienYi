# -*- coding: utf-8 -*-
"""H1（稽核 M0.5）回歸測試 — 前台唯讀角色不得建立 / 上傳 / 改專案主檔。

背景：前台 create / upload 路由多走 .sudo() 寫入（繞過 ir.rule / ir.model.access），
唯讀的「定期閱覽者」(group_portal_viewer) 仍可 POST 進來寫入 → 越權（H1）。
修法：在 controller 於 _document_check_access 後加 _require_write guard
（viewer 擋、現場人員以上放行）；專案主檔異動加 _require_manage。

驗證策略：以 website.tools.MockRequest 驅動「真實路由方法」+「真實角色群組使用者」，
斷言 viewer 被 AccessError 擋、現場人員/主管通過 guard 決策。純 TransactionCase —
本環境 HttpCase 於替代埠不穩，故用 MockRequest 直接注入 request 上下文。
"""

from odoo.addons.website.tools import MockRequest
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged
from odoo.addons.construction_portal.controllers.portal import ConstructionPortal

VIEWER = 'construction_supervision_base.group_portal_viewer'   # 定期閱覽者（唯讀）
FIELD = 'construction_supervision_base.group_portal_user'      # 現場人員
LEADER = 'construction_supervision_base.group_portal_leader'   # 主管


@tagged('post_install', '-at_install', 'construction_portal')
class TestPortalRoleGuards(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ctrl = ConstructionPortal()
        cls.project = cls.env['project.project'].create({
            'name': 'H1 Guard 測試工程',
            'code': 'H1-GUARD',
            'state': 'construction',  # 非 draft/terminated → 成員可讀
            'company_id': cls.env.company.id,
        })
        cls.observer = cls._mk_user('h1_observer', VIEWER)
        cls.field = cls._mk_user('h1_field', FIELD)
        cls.leader = cls._mk_user('h1_leader', LEADER)
        # 純內部使用者（監造單位員工）：無任何前台角色群組，仍應可寫入（放寬後）
        cls.internal = cls._mk_user('h1_internal', 'base.group_user')
        # 三人皆設為專案參與成員 → 滿足 read ir.rule（member_user_ids in [user.id]）
        for u in (cls.observer, cls.field, cls.leader):
            cls.env['supervision.project.member'].create({
                'project_id': cls.project.id,
                'user_id': u.id,
            })

    @classmethod
    def _mk_user(cls, login, group_xmlid):
        return cls.env['res.users'].create({
            'name': login,
            'login': login,
            'groups_id': [(6, 0, [cls.env.ref(group_xmlid).id])],
        })

    # ── 前置健全性：viewer 確實「可讀但不可直接寫」專案 ──────────────
    def test_setup_viewer_can_read_but_not_write_project(self):
        proj = self.project.with_user(self.observer)
        # 可讀（成員 + construction 狀態）
        self.assertTrue(proj.name, 'viewer 應可讀取所屬專案')
        # 直接寫入被 ACL/rule 擋（證明前台 sudo 寫入才是越權破口）
        with self.assertRaises(AccessError):
            proj.write({'name': 'hacked'})

    # ── Part A：guard 決策邏輯（真實群組成員）─────────────────────────
    def _guard_verdict(self, user):
        with MockRequest(self.env(user=user)):
            try:
                self.ctrl._require_write()
                writable = True
            except AccessError:
                writable = False
            can_manage = self.ctrl._can_manage()
        return writable, can_manage

    def test_guard_decision_by_role(self):
        obs_write, obs_manage = self._guard_verdict(self.observer)
        self.assertFalse(obs_write, 'H1：viewer 不應可寫入單據')
        self.assertFalse(obs_manage, 'viewer 不應可管理')

        fld_write, fld_manage = self._guard_verdict(self.field)
        self.assertTrue(fld_write, '現場人員應可寫入單據')
        self.assertFalse(fld_manage, '現場人員不應可管理（審核/建案/改主檔）')

        ldr_write, ldr_manage = self._guard_verdict(self.leader)
        self.assertTrue(ldr_write, '主管應可寫入單據')
        self.assertTrue(ldr_manage, '主管應可管理')

        # 放寬：純內部使用者（無前台角色）應可寫入，但不因此取得「管理」權
        int_write, int_manage = self._guard_verdict(self.internal)
        self.assertTrue(int_write, '內部使用者應可寫入（放寬後）')
        self.assertFalse(int_manage, '純內部使用者不應自動具管理權')

    # ── Part B：真實路由已 wired，viewer 端到端被擋 ──────────────────
    def _call_route(self, user, method_name, **post):
        with MockRequest(self.env(user=user)):
            return getattr(self.ctrl, method_name)(**post)

    def test_observer_blocked_on_real_write_routes(self):
        pid = str(self.project.id)
        cases = [
            ('portal_construction_defect_create', {'project_id': pid}),
            ('portal_construction_daily_log_create', {'project_id': pid}),
            ('portal_construction_inspection_create', {'project_id': pid}),
            ('portal_construction_photo_upload', {'project_id': pid}),
        ]
        for method, kw in cases:
            with self.assertRaises(AccessError,
                                   msg=f'H1：{method} 應擋下 viewer 的寫入'):
                self._call_route(self.observer, method, **kw)

    def test_observer_blocked_on_project_master_edit(self):
        """改工程編號（JSON 路由）viewer 應收到 success=False（非管理者）。"""
        with MockRequest(self.env(user=self.observer)):
            res = self.ctrl.portal_construction_project_code_update(
                self.project.id, code='ZZZ-999')
        self.assertFalse(res.get('success'),
                         'H1：viewer 不應能改工程編號')
        # 現場人員同樣不可（改主檔限老闆/主管）
        with MockRequest(self.env(user=self.field)):
            res2 = self.ctrl.portal_construction_project_code_update(
                self.project.id, code='ZZZ-888')
        self.assertFalse(res2.get('success'),
                         '現場人員不應能改工程編號（限老闆/主管）')
