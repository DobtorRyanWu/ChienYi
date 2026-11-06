# -*- coding: utf-8 -*-
"""呼叫端自帶 context 不能偽造操作軌跡（11-06 抗辯 F4；合約 §0b-23，線 H）。

``audit.trail.create`` 原本只要 ``context.get('audit_trail_create')`` 為真就換成 sudo 建立（在 ACL 之前），
RPC 的 context 由呼叫端給 → 唯讀帳號、前台帳號都能建一筆「操作者＝管理員、狀態 draft→approved」的假軌跡，
而模型的 write／unlink 一律拒，一般管理者在介面上刪不掉。修法：旗標值只認本模組的憑證物件（``is`` 比對）。

鎖住：各種「看起來為真」的值都被拒、沒有留下紀錄；正當路徑 ``log_operation`` 照常建立、操作者是本人。
"""
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_audit.models.audit_trail import AUDIT_CREATE_CTX, AUDIT_CREATE_TOKEN

SUPERVISOR_ADMIN = 'construction_supervision_base.group_supervisor_admin'
PORTAL_LEADER = 'construction_supervision_base.group_portal_leader'
# 呼叫端可能送來的「為真」值（XML-RPC／JSON-RPC 能表達的型別）
SPOOF_VALUES = (True, 1, 'yes', [1], {'x': 1})
FORGED_NOTE = 'H forged audit entry'


@tagged('post_install', '-at_install', 'construction_audit')
class TestAuditTrailForge(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.co_c = env['res.company'].create({'name': 'H 稽核營造', 'company_type': 'contractor'})
        cls.sup = cls._user('ha_sup', [SUPERVISOR_ADMIN], env.company, env.company)
        cls.viewer = cls._user('ha_internal', ['base.group_user'], env.company, env.company)
        cls.portal = cls._user('ha_portal', [PORTAL_LEADER], cls.co_c, cls.co_c | env.company,
                               extra={'is_contractor_org': True, 'dash_scope_company_id': cls.co_c.id})
        cls.model = env['ir.model']._get('res.partner')

    @classmethod
    def _user(cls, login, groups, company, companies, extra=None):
        vals = {'name': login, 'login': login, 'company_id': company.id,
                'company_ids': [(6, 0, companies.ids)],
                'groups_id': [(6, 0, [cls.env.ref(g).id for g in groups])]}
        vals.update(extra or {})
        return cls.env['res.users'].with_context(no_reset_password=True).create(vals)

    def _forged_count(self):
        self.env.flush_all()
        self.env.cr.execute('SELECT count(*) FROM audit_trail WHERE note = %s', [FORGED_NOTE])
        return self.env.cr.fetchone()[0]

    def test_caller_flag_cannot_create(self):
        admin = self.env.ref('base.user_admin')
        for user in (self.sup, self.viewer, self.portal):
            for value in SPOOF_VALUES:
                with self.subTest(user=user.login, value=value):
                    Trail = self.env['audit.trail'].with_user(user).with_context(**{AUDIT_CREATE_CTX: value})
                    with self.assertRaisesRegex(UserError, '請使用 log_operation'):
                        Trail.create({'model_id': self.model.id, 'res_id': 1, 'operation_type': 'state_change',
                                      'user_id': admin.id, 'old_state': 'draft', 'new_state': 'approved',
                                      'note': FORGED_NOTE})
        self.assertEqual(self._forged_count(), 0, '偽造的軌跡一筆都不可留下')

    def test_token_is_not_a_plain_truthy_value(self):
        self.assertIsNot(AUDIT_CREATE_TOKEN, True)
        self.assertNotIn(AUDIT_CREATE_TOKEN, SPOOF_VALUES)

    def test_log_operation_still_records(self):
        """正當路徑：log_operation（@api.private，只能從伺服器端程式呼叫）照常建立，操作者是本人。"""
        for user in (self.sup, self.viewer, self.portal):
            with self.subTest(user=user.login):
                trail = self.env['audit.trail'].with_user(user).log_operation(
                    'res.partner', user.partner_id.id, 'write', note='H 正當軌跡')
                self.assertTrue(trail, 'log_operation 要建出紀錄')
                self.assertEqual(trail.sudo().user_id, user)
                self.assertEqual(trail.sudo().operation_type, 'write')
