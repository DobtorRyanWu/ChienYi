# -*- coding: utf-8 -*-
"""系統預設樣板的附件不公開（T7）。

原本 seed 建附件時 public=True，未登入的人用 /web/content/<id>（id 連號）就能下載每一份預設樣板。
改成非公開後，附件的存取改看 res_model/res_id 指到的 document.template：
內部帳號（後台、代操作員）照 record rule 讀得到預設樣板；前台帳號的匯出走 sudo
（portal 的 _document_check_access 回傳 superuser 記錄），不經過這條。
res_id 必須有值，否則非公開附件變孤兒，只有建立者與 base.group_system 讀得到。
"""

import importlib.util
import os

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.hooks import seed_default_templates
from odoo.addons.construction_template.utils import template_render

TTYPE = 'invoice_detail'
PLAN_TYPE = 'plan_review_opinion_construction'   # 以案件為資料來源，不需另外建單據
MIGRATION = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'migrations', '18.0.3.8.2', 'post-migrate.py')


def _run_migration(env):
    spec = importlib.util.spec_from_file_location('mig_3_8_2_private', MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.migrate(env.cr, '18.0.3.8.1')


@tagged('post_install', '-at_install', 'construction_template')
class TestTemplateAttachmentPrivate(TransactionCase):

    def _default(self, ttype):
        return self.env['document.template'].search([
            ('template_type', '=', ttype), ('is_default', '=', True)], limit=1)

    def _reseed(self, ttype):
        """用 seed 重建一次預設樣板（模擬全新安裝／升級後的結果）"""
        tmpl = self._default(ttype)
        self.assertTrue(tmpl, '測資前提：有 %s 預設樣板' % ttype)
        seed_default_templates(self.env, types=(ttype,),
                               replaceable={ttype: {tmpl.attachment_id.checksum}})
        return self._default(ttype)

    def _user(self, login, xmlids):
        groups = [self.env.ref(x).id for x in xmlids]
        return self.env['res.users'].with_context(no_reset_password=True).create({
            'name': login, 'login': login, 'email': '%s@example.test' % login,
            'groups_id': [(6, 0, groups)],
        })

    # ------------------------------------------------------------ seed 本身
    def test_seeded_attachment_is_private_and_linked(self):
        tmpl = self._reseed(TTYPE)
        att = tmpl.attachment_id
        self.assertFalse(att.public, '預設樣板附件不該公開')
        self.assertEqual((att.res_model, att.res_id), ('document.template', tmpl.id))

    def test_anonymous_cannot_download_default_template(self):
        tmpl = self._reseed(TTYPE)
        public_user = self.env.ref('base.public_user')
        with self.assertRaises(AccessError):
            tmpl.attachment_id.with_user(public_user).raw  # noqa: B018

    # ------------------------------------------------------------ 仍然讀得到的人
    def test_backend_operator_can_download_and_export(self):
        tmpl = self._reseed(TTYPE)
        operator = self._user('tpl_operator_t7', ['base.group_user',
                                                  'construction_supervision_base.group_operator'])
        att = tmpl.attachment_id.with_user(operator)
        self.assertTrue(att.raw, '代操作員下載預設樣板')
        # 匯出：套印時以操作員身分讀樣板附件
        plan_tmpl = self._reseed(PLAN_TYPE).with_user(operator)
        project = self.env['project.project'].create({
            'name': 'T7 匯出測試', 'code': 'TPL-T7', 'company_id': self.env.company.id})
        content, _name = template_render.render(plan_tmpl, project.with_user(operator))
        self.assertTrue(content)

    def test_portal_role_user_export_path_uses_sudo(self):
        """前台帳號直接讀不到樣板（沒有 ACL），匯出靠 portal 回傳的 superuser 記錄；
        那一條不受附件是否公開影響。"""
        tmpl = self._reseed(PLAN_TYPE)
        portal = self._user('tpl_portal_t7', ['base.group_portal',
                                              'construction_supervision_base.group_portal_user'])
        project = self.env['project.project'].create({
            'name': 'T7 前台匯出', 'code': 'TPL-T7P', 'company_id': self.env.company.id})
        content, _name = template_render.render(
            tmpl.with_user(portal).sudo(), project.with_user(portal).sudo())
        self.assertTrue(content)

    # ------------------------------------------------------------ migration
    def test_migration_privatises_and_backfills_res_id(self):
        tmpl = self._default(TTYPE)
        att = tmpl.attachment_id
        att.write({'public': True, 'res_id': 0})     # 升級前的舊狀態
        self.env.flush_all()
        _run_migration(self.env)
        att.invalidate_recordset()
        self.assertFalse(att.public)
        self.assertEqual(att.res_id, tmpl.id)

    def test_migration_leaves_no_public_template_attachment(self):
        _run_migration(self.env)
        self.env.cr.execute(
            "SELECT count(*) FROM ir_attachment WHERE res_model='document.template' AND public")
        self.assertEqual(self.env.cr.fetchone()[0], 0)
