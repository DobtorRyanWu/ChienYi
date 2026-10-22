"""一次性開通通知單（計畫 P5）。"""

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.assoc_base.tools import GUARD
from odoo.addons.assoc_portal.models.assoc_member import GUARD_LINK

from .common import PASSWORD, PortalCase

REPORT = 'assoc_portal.report_activation_notice'
ACTION_XMLID = 'assoc_portal.action_report_activation_notice'


@tagged('post_install', '-at_install')
class TestActivation(PortalCase):

    def setUp(self):
        super().setUp()
        self.user = self.grant()

    def test_token_sets_password_and_expires(self):
        token = self.print_notice()
        member, user, _nonce = self.env['assoc.member'].sudo()._member_from_token(token)
        self.assertEqual(member, self.member)
        member._consume_activation(PASSWORD)
        # 用過即失效
        self.assertFalse(self.member.sudo().activation_nonce_hash)
        self.assertFalse(self.env['assoc.member'].sudo()._member_from_token(token)[0])

    def test_setting_password_writes_audit(self):
        """通知單被偷用時，只有 login_ok 看不出「密碼是誰設的」。"""
        Audit = self.env['assoc.audit.log']
        before = Audit.sudo().search_count([('action', '=', 'activate_ok')])
        self.activate()
        entries = Audit.sudo().search([('action', '=', 'activate_ok')])
        self.assertEqual(len(entries) - before, 1)
        self.assertEqual(entries[-1].company_id, self.member.company_id)
        self.assertIn(str(self.member.id), entries[-1].res_ids_text)

    def test_reprint_invalidates_previous_notice(self):
        first = self.print_notice()
        second = self.print_notice()
        self.assertFalse(self.env['assoc.member'].sudo()._member_from_token(first)[0],
                         '重印後舊通知單要失效（被偷拍時的唯一補救）')
        self.assertTrue(self.env['assoc.member'].sudo()._member_from_token(second)[0])

    def test_broken_token_is_rejected_quietly(self):
        for bad in ('', 'x', 'not-a-token', 'YWJj.YWJj.YWJj'):
            self.assertEqual(
                self.env['assoc.member'].sudo()._member_from_token(bad),
                (False, False, False))

    def test_token_is_bound_to_user(self):
        """token 綁 member 與 user：換掉帳號後舊通知單不能用。

        這裡**不停用帳號**：停用會順手清掉 nonce，那樣擋下來的是 nonce 檢查，
        驗不到「綁 user」這一關。
        """
        token = self.print_notice()
        other = self.env['res.users'].sudo().create({
            'name': '別的帳號', 'login': 'm6_other_user',
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])]})
        # 換綁要帶哨兵（RPC 直接寫已被守衛擋住）；nonce 刻意留著
        self.member.sudo().with_context(**{GUARD_LINK: GUARD}).user_id = other.id
        self.assertTrue(self.member.sudo().activation_nonce_hash, '前提：開通碼還在')
        self.assertFalse(self.env['assoc.member'].sudo()._member_from_token(token)[0])

    def test_audit_separates_activation_and_reset(self):
        log = self.env['assoc.audit.log']
        self.print_notice()
        self.assertEqual(log.search_count([('action', '=', 'print_activation')]), 1)
        self.assertEqual(log.search_count([('action', '=', 'print_reset')]), 0)
        # 登入過的帳號再印，就是重設
        self.user.sudo().write({'login_date': '2026-09-18 00:00:00'})
        self.print_notice()
        self.assertEqual(log.search_count([('action', '=', 'print_reset')]), 1)

    def test_report_requires_token_in_data(self):
        """直接 GET /report/pdf/<報表>/<id> 拿不到 token，也不能換掉 nonce。"""
        report_model = self.env['report.assoc_portal.report_activation_notice']
        self.print_notice()
        nonce_before = self.member.sudo().activation_nonce_hash
        with self.assertRaises(UserError):
            report_model._get_report_values(self.member.ids, data=None)
        with self.assertRaises(UserError):
            report_model._get_report_values(self.member.ids, data={'token': 'bogus'})
        self.assertEqual(self.member.sudo().activation_nonce_hash, nonce_before,
                         '報表不可以有副作用')

    def test_report_values_render_with_valid_token(self):
        token = self.print_notice()
        values = self.env['report.assoc_portal.report_activation_notice']._get_report_values(
            self.member.ids, data={'token': token})
        self.assertEqual(values['member'], self.member)
        self.assertTrue(values['qr'].startswith('data:image/png;base64,'),
                        'QR 要用 data URI：走 /report/barcode 會讓 token 進 access log')
        self.assertNotIn(token, values['qr'])

    # 註：真的把 PDF 產出來的驗證放在 tools/e2e/e2e_m6_portal.py。
    # 測試庫沒有 report.url，真的呼叫 wkhtmltopdf 會卡住；而「覆寫 _render_qweb_html
    # 連 PDF 一起擋死」這個 critical 正是因為沒有人真的渲染過才沒被抓到，所以 E2E 一定要驗。

    def test_html_route_is_blocked(self):
        """wkhtmltopdf 異常時前端會退回 GET /report/html/...?options=，token 會進 access log。

        擋的是「HTML 那條路由」，不是 `_render_qweb_html`——後者是核心產 PDF 的內部步驟。
        """
        from odoo.addons.assoc_portal.controllers.report_guard import AssocReportController
        controller = AssocReportController()
        token = self.print_notice()
        with self.assertRaises(UserError) as err:
            controller.report_routes(REPORT, docids=str(self.member.id), converter='html',
                                     options={'token': token})
        self.assertIn('PDF', str(err.exception))

    def test_html_route_is_blocked_by_action_xmlid_too(self):
        """核心的 `_get_report()` 先用 report_name 找，找不到再 `env.ref()`
        （ir_actions_report.py:649-672），所以 action 的 xmlid 到得了同一張報表。
        只比 report_name 的話，`/report/html/assoc_portal.action_report_activation_notice`
        就繞過去了。
        """
        from odoo.addons.assoc_portal.controllers.report_guard import AssocReportController
        controller = AssocReportController()
        token = self.print_notice()
        # 先證明這個名字真的指到同一張報表（否則下面的斷言是空的）
        report = self.env['ir.actions.report'].sudo()._get_report(ACTION_XMLID)
        self.assertEqual(report.report_name, REPORT)
        with self.assertRaises(UserError) as err:
            controller.report_routes(ACTION_XMLID, docids=str(self.member.id),
                                     converter='html', options={'token': token})
        self.assertIn('PDF', str(err.exception))

    def test_pdf_refused_when_generator_unavailable(self):
        """產不出 PDF 時要擋下來，不能讓核心退回 HTML（token 會進 log）。"""
        with patch('odoo.addons.base.models.ir_actions_report.IrActionsReport.'
                   'get_wkhtmltopdf_state', return_value='broken'):
            with self.assertRaises(UserError):
                self.env.ref('assoc_portal.action_report_activation_notice')._render_qweb_pdf(
                    self.env.ref('assoc_portal.action_report_activation_notice'),
                    self.member.ids, data={'token': 'x'})

    def test_print_requires_working_pdf(self):
        with patch('odoo.addons.base.models.ir_actions_report.IrActionsReport.'
                   'get_wkhtmltopdf_state', return_value='install'):
            with self.assertRaises(UserError):
                self.member.with_user(self.admin_user).action_print_activation()

    def test_print_requires_account(self):
        member = self.new_member('M6009')
        with self.assertRaises(UserError):
            member.with_user(self.admin_user).action_print_activation()
