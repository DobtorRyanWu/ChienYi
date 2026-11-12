# -*- coding: utf-8 -*-
"""公文測試共用的資料：兩家營造廠、一家監造公司、兩個工程、各種帳號。

帳號的「允許公司」照正式資料的樣子設（dev 的前台營造帳號，範圍公司都在自己的允許公司內）。
不是測試模組（檔名不是 test_ 開頭），只給各測試檔匯入。
"""
from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase

ADMIN_GROUP = 'construction_supervision_base.group_supervisor_admin'
BOSS = 'construction_supervision_base.group_portal_subscriber'
FIELD = 'construction_supervision_base.group_portal_user'
VIEWER = 'construction_supervision_base.group_portal_viewer'
DASHBOARD_MODULE = 'construction_company_dashboard'
DOC_MODEL = 'construction.official.doc'


class OfficeCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        Company = env['res.company']
        cls.co_s = Company.create({'name': 'OFFICE 監造 S', 'company_type': 'supervision'})
        cls.co_a = Company.create({'name': 'OFFICE 營造 A', 'company_type': 'contractor'})
        cls.co_b = Company.create({'name': 'OFFICE 營造 B', 'company_type': 'contractor'})
        Project = env['project.project']
        cls.p1 = Project.create({
            'name': 'OFFICE 工程一', 'code': 'OFFICE-P1', 'project_type': 'general', 'state': 'construction',
            'company_id': cls.co_s.id, 'contractor_company_ids': [(6, 0, cls.co_a.ids)]})
        cls.p2 = Project.create({
            'name': 'OFFICE 工程二', 'code': 'OFFICE-P2', 'project_type': 'general', 'state': 'construction',
            'company_id': cls.co_s.id, 'contractor_company_ids': [(6, 0, cls.co_b.ids)]})
        cls.today = fields.Date.today()
        cls.yesterday = cls.today - timedelta(days=1)
        cls.tomorrow = cls.today + timedelta(days=1)

        # 後台人員（監造公司 S，另外開了營造 A，代操時才看得到 A 的公文）
        cls.staff = cls._user('office_staff', ['base.group_user', ADMIN_GROUP], cls.co_s, cls.co_s | cls.co_a)
        # 監造方前台帳號：工程一的現場人員、老闆、不是任何工程成員的現場人員
        cls.sup_field = cls._user('office_sup_field', [FIELD], cls.co_s, supervision=True, member_of=cls.p1)
        cls.sup_boss = cls._user('office_sup_boss', [BOSS], cls.co_s, supervision=True)
        cls.sup_outsider = cls._user('office_sup_outsider', [FIELD], cls.co_s, supervision=True)
        # 營造 A 的前台帳號：現場人員（工程一成員）、閱覽者（工程一成員）
        cls.a_field = cls._user('office_a_field', [FIELD], cls.co_s, cls.co_s | cls.co_a,
                                contractor=cls.co_a, member_of=cls.p1)
        cls.a_viewer = cls._user('office_a_viewer', [VIEWER], cls.co_s, cls.co_s | cls.co_a,
                                 contractor=cls.co_a, member_of=cls.p1)
        cls.Doc = env[DOC_MODEL]
        cls.dashboard_installed = bool(env['ir.module.module'].sudo().search_count(
            [('name', '=', DASHBOARD_MODULE), ('state', '=', 'installed')]))

    @classmethod
    def _user(cls, login, groups, company, companies=None, supervision=False, contractor=None, member_of=None):
        vals = {'name': login, 'login': login, 'groups_id': [(6, 0, [cls.env.ref(g).id for g in groups])],
                'company_id': company.id, 'company_ids': [(6, 0, (companies or company).ids)]}
        if supervision:
            vals['is_supervision_org'] = True
        if contractor:
            vals.update(is_contractor_org=True, dash_scope_company_id=contractor.id)
        user = cls.env['res.users'].with_context(no_reset_password=True).create(vals)
        if member_of:
            cls.env['supervision.project.member'].create({'project_id': member_of.id, 'user_id': user.id})
        return user

    @classmethod
    def _doc(cls, subject, company, project=None, **vals):
        values = {'subject': subject, 'company_id': company.id, 'project_id': project.id if project else False}
        values.update(vals)
        return cls.Doc.create(values)

    def _visible(self, user, docs):
        """docs 之中 user 讀得到的（以本人身分搜尋，含封存）。"""
        return self.Doc.with_user(user).with_context(active_test=False).search([('id', 'in', docs.ids)])
