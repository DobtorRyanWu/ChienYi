# -*- coding: utf-8 -*-
"""寫說明書時查到的兩個帳號管理問題（2026-11-25）。

- 只勾「工程管理者」的帳號要能建使用者：建使用者會連帶建一筆聯絡人，需要「聯絡人建立」群組。
- 使用者表單上要改得到「帳號有效期至」：定期閱覽者、參觀帳號要延長或提前結束，沒有別的畫面可以改。
"""
from datetime import timedelta

from lxml import etree

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from ..models.res_users import PORTAL_LEVEL_OBSERVER

MANAGER = 'construction_supervision_base.group_engineering_manager'
VALID_UNTIL_FIELD = 'portal_valid_until'
EXTEND_DAYS = 30


@tagged('post_install', '-at_install', 'construction_supervision_base')
class TestManualFixes20261125(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 只給「工程管理者」一個群組（不另外勾新帳號預設會帶的「聯絡人建立」），和示範站的工程管理者帳號相同
        cls.manager = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'M1125 工程管理者', 'login': 'm1125_manager',
            'groups_id': [(6, 0, [cls.env.ref(MANAGER).id])]})

    def _new_observer(self, login):
        """以工程管理者的身分建一個定期閱覽者（後台「設定 > 使用者 > 新增」做的事）。"""
        return self.env['res.users'].with_user(self.manager).with_context(no_reset_password=True).create({
            'name': login, 'login': login, 'portal_role': PORTAL_LEVEL_OBSERVER})

    def test_engineering_manager_can_create_users(self):
        """修前：AccessError「無權限建立 Contact」。"""
        observer = self._new_observer('m1125_observer')
        self.assertTrue(observer.sudo().share, '建出來的是前台帳號')
        self.assertTrue(observer.sudo().partner_id, '連帶建了聯絡人')
        internal = self.env['res.users'].with_user(self.manager).with_context(no_reset_password=True).create({
            'name': 'M1125 內部帳號', 'login': 'm1125_internal'})
        self.assertFalse(internal.sudo().share)

    def test_user_form_can_change_account_valid_until(self):
        """修前：使用者表單沒有這一欄（全系統沒有任何畫面改得到它）。"""
        form = self.env.ref('base.view_users_form')
        arch = self.env['res.users'].with_user(self.manager).get_view(form.id, 'form')['arch']
        nodes = etree.fromstring(arch).xpath("//field[@name='%s']" % VALID_UNTIL_FIELD)
        self.assertTrue(nodes, '使用者表單要有「帳號有效期至」')
        self.assertFalse(any(node.get('readonly') in ('1', 'True') for node in nodes), '而且要改得動')
        # 管理者真的改得動：延長、提前結束
        observer = self._new_observer('m1125_observer_date')
        later = fields.Date.today() + timedelta(days=EXTEND_DAYS)
        observer.with_user(self.manager).write({VALID_UNTIL_FIELD: later})
        self.assertEqual(observer.sudo().portal_valid_until, later)
