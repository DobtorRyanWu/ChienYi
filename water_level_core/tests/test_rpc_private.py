# -*- coding: utf-8 -*-
"""設備寫入路徑不能被 RPC 呼叫（2026-11-04）。

update_health、ingest_readings 是公開方法，裡面不檢查權限就 sudo 寫設備狀態與讀數。
RPC（/web/dataset/call_kw、xmlrpc）呼叫公開方法前不查 ACL，所以任何登入帳號——
包括自行註冊的 b2c 前台帳號——都能把任一台設備改成「改用備援電力」、亂寫電量，觸發告警。
這兩支只給 controllers/ingest.py（設備金鑰驗過才呼叫）與 water.level.source 的排程用，
標 @api.private 後 Python 照常呼叫、RPC 呼叫不到。
"""
from odoo.exceptions import AccessError
from odoo.service.model import get_public_method
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'water_level_core')
class TestRpcPrivate(TransactionCase):

    def test_device_write_paths_not_callable_remotely(self):
        portal = self.env['res.users'].create({
            'name': 'wl_rpc_portal', 'login': 'wl_rpc_portal',
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])]})
        Device = self.env['water.level.device'].with_user(portal)
        for method in ('update_health', 'ingest_readings'):
            with self.subTest(method=method):
                with self.assertRaises(AccessError):
                    get_public_method(Device, method)
