# -*- coding: utf-8 -*-
"""產生上報金鑰要先過權限檢查，不能靠交易 rollback 擋（2026-11-16）。

action_generate_api_key 原本先 sudo 寫金鑰雜湊、再 message_post。前台帳號經 RPC 呼叫時，
是 message_post 拋 AccessError、整筆交易 rollback 才把新雜湊收回——擋住它的是
「後面剛好有一步會失敗」：哪天 message_post 那行被移走、改成 sudo、或模型允許讀者留言，
前台帳號（工程／社區前台讀得到設備的成員）就能讓設備的舊金鑰失效、現場設備上報全斷。
改成寫入前先檢查：非內部帳號直接 AccessError；內部帳號要有這台設備的寫入權。
"""

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged

from .common import site_vals


@tagged('post_install', '-at_install', 'water_level_core')
class TestApiKeyAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        site = env['water.level.site'].create(site_vals(env, '金鑰權限測試場域'))
        cls.device = env['water.level.device'].create({
            'name': 'KEY-ACL', 'site_id': site.id, 'device_uid': 'TEST-KEY-ACL'})
        cls.device.action_generate_api_key()    # 先有一把舊金鑰
        cls.portal = env['res.users'].create({
            'name': 'wl_key_portal', 'login': 'wl_key_portal',
            'groups_id': [(6, 0, [env.ref('base.group_portal').id])]})
        cls.internal = env['res.users'].create({
            'name': 'wl_key_internal', 'login': 'wl_key_internal',
            'groups_id': [(6, 0, [env.ref('base.group_user').id])]})

    def test_portal_rejected_before_any_write(self):
        before = self.device.api_key_hash
        self.assertTrue(before, '前提：設備已有一把金鑰')
        # 刻意不用 assertRaises：它會開 savepoint，例外時把例外之前的寫入一起 rollback，
        # 正好遮掉「先寫了才失敗」（memory odoo_assertraises_savepoint_rollback）
        raised = None
        try:
            self.device.with_user(self.portal).action_generate_api_key()
        except AccessError as exc:
            raised = exc
        self.assertIsNotNone(raised, '前台帳號不可產生上報金鑰')
        self.device.invalidate_recordset(['api_key_hash'])
        self.assertEqual(self.device.api_key_hash, before,
                         '被拒之前不可先寫入新雜湊（不能靠交易 rollback 收回）')

    def test_internal_user_can_generate(self):
        """正當入口：內部帳號（有設備寫入權）照常產生，舊金鑰換掉、回傳顯示明文的通知。"""
        before = self.device.api_key_hash
        action = self.device.with_user(self.internal).action_generate_api_key()
        self.assertEqual(action['tag'], 'display_notification')
        self.device.invalidate_recordset(['api_key_hash'])
        self.assertTrue(self.device.api_key_hash)
        self.assertNotEqual(self.device.api_key_hash, before)
