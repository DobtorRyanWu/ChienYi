# -*- coding: utf-8 -*-
"""合約 §0b-29（使用者 11-06「營造方可讀寫受邀文件」）：dobtor 線上文件的受邀協作。

1. 範圍合格的前台營造帳號：讀、寫得到協作者含自己的文件；沒受邀的讀不到、寫不了；
   本規則對建、刪照拒（ACL 本來也沒給前台建刪，這裡另外驗規則本身，不靠 ACL）。
2. 範圍公司空白的營造方即使被列為協作者也照拒（合約 §1-7 預設拒絕）。
3. 營造廠主管、控台讀取帳號被列為協作者也讀不到（沒有 dobtor 群組＝ACL 擋；控台讀取另外規則就拒）。
4. 監造方（文件建立者）照舊讀寫得到自己的文件。
5. 內部營造方（主要公司是營造廠的內部帳號，帶 dobtor 群組）只讀得到受邀的、寫不了（寫只給前台帳號）。
6. 正當入口：帶範本的受邀文件，編輯器開檔讀得到範本（範本照核心值讀、寫照拒）。

沒裝 dobtor 文件編輯器的庫整個類別 skip（可見的 skip，不默默變綠）。
"""
from odoo.exceptions import AccessError
from odoo.osv import expression
from odoo.tests import tagged

from .test_scope_rules import DENIED, DashScopeCase

DOC = 'doc.document'
DOC_PORTAL_GROUP = 'dobtor_doc_editor.group_doc_portal'
DOC_EDITOR_GROUP = 'dobtor_doc_editor.group_doc_editor'
DOC_MANAGER_GROUP = 'dobtor_doc_editor.group_doc_manager'
DOC_TEMPLATE = 'doc.template'
DOC_TEMPLATE_MODELS = ('doc.template', 'doc.template.field', 'doc.template.field.option', 'doc.template.signer')
CONTRACTOR_EDIT = '<p>營造方編輯過</p>'


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestInvitedDocs(DashScopeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if DOC not in cls.env:
            return
        env = cls.env
        portal_group = env.ref(DOC_PORTAL_GROUP)
        (cls.portal_a | cls.portal_blank).write({'groups_id': [(4, portal_group.id)]})
        cls.sup.write({'groups_id': [(4, env.ref(DOC_EDITOR_GROUP).id)]})
        Doc = env[DOC].with_user(cls.sup)
        cls.doc_invited = Doc.create({'name': 'DASH 受邀文件', 'content_html': '<p>受邀</p>',
                                      'company_id': cls.co_s.id})
        cls.doc_other = Doc.create({'name': 'DASH 未受邀文件', 'content_html': '<p>沒受邀</p>',
                                    'company_id': cls.co_s.id})
        # 主要公司是營造廠的內部帳號（合約 §0b-5：營造方；不是營造廠主管，所以群組允許清單不管它）帶 dobtor 管理者群組：
        # 核心規則讓它讀寫全部文件——本規則的「只限受邀」條件對它才不是多餘的（前台帳號的核心規則本來就限協作者）
        cls.internal_contractor = cls._user(
            'dash_internal_contractor', ['base.group_user', DOC_MANAGER_GROUP], company=cls.co_a,
            companies=cls.co_a | cls.co_s, scope=cls.co_a)
        invited = cls.portal_a | cls.portal_blank | cls.mgr_a | cls.console | cls.internal_contractor
        cls.doc_invited.sudo().collaborator_ids = [(6, 0, invited.ids)]
        cls.both = (cls.doc_invited | cls.doc_other).ids
        # 帶範本的受邀文件（自動建立的線上文件都帶範本；編輯器開檔會讀範本的別名與名稱）
        cls.template = env[DOC_TEMPLATE].create({'name': 'DASH 範本'})
        cls.doc_with_template = Doc.create({'name': 'DASH 帶範本的受邀文件', 'content_html': '<p>範本</p>',
                                            'company_id': cls.co_s.id, 'template_id': cls.template.id})
        cls.doc_with_template.sudo().collaborator_ids = [(6, 0, cls.portal_a.ids)]

    def setUp(self):
        super().setUp()
        if DOC not in self.env:
            self.skipTest('這個庫沒有裝 dobtor 文件編輯器')

    def test_rig_portal_is_contractor_with_doc_portal_group(self):
        """前提：前台帳號真的是營造方、範圍合格、有 dobtor 前台群組（否則下面的「讀得到」不是本規則給的）。"""
        self.assertTrue(self.portal_a._dash_is_contractor_side())
        self.assertTrue(self.portal_a._dash_scope_ok())
        self.assertTrue(self.env['ir.model.access'].with_user(self.portal_a).check(DOC, 'write', raise_exception=False))
        self.assertFalse(self.portal_blank._dash_scope_ok())

    def test_contractor_reads_and_writes_invited_only(self):
        env = self._env_of(self.portal_a)
        self.assertEqual(self._visible_ids(self.portal_a, DOC, [('id', 'in', self.both)]), {self.doc_invited.id})
        doc = env[DOC].browse(self.doc_invited.id)
        doc.invalidate_recordset()
        self.assertEqual(doc.name, 'DASH 受邀文件', '受邀文件讀得到（清快取後實際讀）')
        doc.write({'content_html': CONTRACTOR_EDIT})
        self.doc_invited.invalidate_recordset()
        self.assertIn('營造方編輯過', self.doc_invited.sudo().content_html, '受邀文件寫得進去')
        other = env[DOC].browse(self.doc_other.id)
        with self.assertRaises(AccessError):
            other.check_access('read')
        with self.assertRaises(AccessError):
            other.write({'content_html': CONTRACTOR_EDIT})

    def test_rule_itself_denies_create_and_unlink(self):
        """建、刪由本規則拒（不靠 ACL：ACL 改了也不會因此放行）；寫的條件只限受邀。"""
        rules = self._env_of(self.portal_a)['ir.rule']
        self.assertEqual(rules._compute_domain(DOC, 'create'), DENIED)
        self.assertEqual(rules._compute_domain(DOC, 'unlink'), DENIED)
        self.assertNotEqual(rules._compute_domain(DOC, 'write'), DENIED)

    def test_contractor_opens_invited_doc_with_template_via_editor(self):
        """正當入口：編輯器開檔（/dobtor_doc/load）讀範本的別名與名稱——受邀的帶範本文件要開得起來（第二輪抗辯 F1）。"""
        from odoo.addons.dobtor_doc_editor.controllers.doc_controller import DocEditorController
        from odoo.addons.website.tools import MockRequest
        with MockRequest(self._env_of(self.portal_a)):
            data = DocEditorController().load_document(self.doc_with_template.id)
        self.assertEqual(data['template_name'], 'DASH 範本')
        rules = self._env_of(self.portal_a)['ir.rule']
        for model in DOC_TEMPLATE_MODELS:
            self.assertEqual(rules._compute_domain(model, 'write'), DENIED, f'{model}：營造方讀得到範本但寫不了')
            # 讀取放行（另外三個模型開檔的欄位／簽核人／選項路由會讀；第三輪抗辯 skeptic 指出原本只驗了 doc.template）
            self.assertNotEqual(rules._compute_domain(model, 'read'), DENIED, f'{model}：營造方讀得到')
        blank_rules = self._env_of(self.portal_blank)['ir.rule']
        self.assertEqual(blank_rules._compute_domain(DOC_TEMPLATE, 'read'), DENIED, '範圍不合格的營造方讀不到範本')

    def test_contractor_with_broad_core_rule_still_invited_only(self):
        """核心規則放行全部的營造方（內部帳號＋dobtor 管理者群組）：只讀得到受邀的那份，而且不能寫（寫只給前台帳號）。

        內部帳號不受 dobtor「前台寫不動的欄位」限制（只看 share），放寫等於讓它改協作者、別名運算式、綁定對象
        （第二輪抗辯 skeptic B F2 實測）。"""
        user = self.internal_contractor
        self.assertTrue(user._dash_is_contractor_side() and user._dash_scope_ok(), '前提：範圍合格的營造方')
        core = self._core_domain(user, DOC)
        core_seen = set(self.env[DOC].sudo().search(expression.AND([core, [('id', 'in', self.both)]])).ids)
        self.assertEqual(core_seen, set(self.both), '前提：核心規則讓它兩份都讀得到（否則下面的斷言證明不了本規則）')
        self.assertEqual(self._visible_ids(user, DOC, [('id', 'in', self.both)]), {self.doc_invited.id})
        env = self._env_of(user)
        for doc in (self.doc_other, self.doc_invited):
            with self.assertRaises(AccessError, msg=f'內部營造方寫不了 {doc.name}'):
                env[DOC].browse(doc.id).write({'collaborator_ids': [(4, self.sup.id)]})
        self.assertEqual(env['ir.rule']._compute_domain(DOC, 'write'), DENIED)

    def test_blank_scope_invited_still_denied(self):
        env = self._env_of(self.portal_blank)
        self.assertEqual(self._visible_ids(self.portal_blank, DOC, [('id', 'in', self.both)]), set())
        with self.assertRaises(AccessError):
            env[DOC].browse(self.doc_invited.id).write({'content_html': CONTRACTOR_EDIT})
        self.assertEqual(env['ir.rule']._compute_domain(DOC, 'write'), DENIED)

    def test_manager_and_console_cannot_read_invited(self):
        for user in (self.mgr_a, self.console):
            with self.assertRaises(AccessError, msg=f'{user.login}：被列為協作者也讀不到'):
                self._env_of(user)[DOC].browse(self.doc_invited.id).check_access('read')
        self.assertEqual(self._env_of(self.console)['ir.rule']._compute_domain(DOC, 'read'), DENIED)

    def test_supervision_owner_unchanged(self):
        self.assertEqual(self._visible_ids(self.sup, DOC, [('id', 'in', self.both)]), set(self.both))
        self._env_of(self.sup)[DOC].browse(self.doc_other.id).write({'content_html': '<p>監造方</p>'})
