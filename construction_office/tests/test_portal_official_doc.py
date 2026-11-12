# -*- coding: utf-8 -*-
"""手機公文頁（controllers/portal_official_doc.py；淞源 2026-11-10 會議 C10）。

淞源技師：「在外面用手機要能方便找到公文，不用一個個點半天」。真實帳號跑真實路由，模板實際渲染成 HTML。
另外鎖住寫入與下載的把關：前台帳號沒有寫入 ACL，新增走 sudo，所以守衛只能在這裡驗。
"""
from io import BytesIO

from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import NotFound

from odoo.addons.website.tools import MockRequest
from odoo.exceptions import AccessError
from odoo.tests import tagged

from ..controllers.portal_official_doc import MAX_UPLOAD_FILES, ConstructionOfficialDocPortal
from .common import DOC_MODEL, OfficeCase

PLAIN_INTERNAL = 'base.group_user'


@tagged('post_install', '-at_install', 'construction_office')
class TestPortalOfficialDoc(OfficeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ctrl = ConstructionOfficialDocPortal()
        cls.water = cls._doc('護岸施工計畫審查意見', cls.co_s, cls.p1, organization='新北市政府水利局',
                             doc_number='新北水工字第1150012345號')
        cls.traffic = cls._doc('交通維持計畫核定', cls.co_s, cls.p1, organization='臺北市政府交通局',
                               doc_number='北市交工字第1150054321號', reply_deadline=cls.tomorrow)
        cls.on_p2 = cls._doc('工程二的公文', cls.co_s, cls.p2)
        cls.company_wide = cls._doc('公司共通公文', cls.co_s)
        cls.scan = cls.env['ir.attachment'].create({
            'name': '審查意見.pdf', 'raw': b'%PDF-scan', 'res_model': DOC_MODEL, 'res_id': cls.water.id})

    def _drive(self, user, method, *args, files=None, **kw):
        """user 跑真實路由。回傳 (values, html)；路由回 redirect 時 values 為 None、html 為 Location。"""
        self.env.flush_all()
        self.env.invalidate_all()
        env = self.env(user=user)
        seen = {}
        with MockRequest(env) as req:
            req.httprequest.files.getlist.return_value = files or []
            req.httprequest.args = {}
            req.params = dict(kw)
            req.render = lambda tpl, vals=None, **k: seen.update(tpl=tpl, vals=vals) or '<render>'
            res = method(*args, **kw)
            if 'tpl' not in seen:
                return None, res.headers.get('Location', '')
            html = env['ir.ui.view']._render_template(seen['tpl'], dict(seen['vals']))
        return seen['vals'], html.decode() if isinstance(html, bytes) else html

    @staticmethod
    def _upload(name, content=b'data'):
        return FileStorage(stream=BytesIO(content), filename=name, content_type='application/pdf')

    # ── 列表與搜尋 ──────────────────────────────────────────────────────
    def test_project_list_shows_only_that_project_and_searches(self):
        values, html = self._drive(self.sup_field, self.ctrl.official_docs, self.p1.id)
        self.assertEqual(values['docs'], self.traffic | self.water)
        self.assertEqual(values['doc_count'], 2)
        self.assertIn('護岸施工計畫審查意見', html)
        self.assertIn('新北水工字第1150012345號', html)
        self.assertIn(f'/construction/{self.p1.id}/official-doc/{self.water.id}', html)
        self.assertNotIn('工程二的公文', html)
        self.assertIn('新增公文', html, '現場人員看得到新增按鈕')
        # 關鍵字找文號
        values, html = self._drive(self.sup_field, self.ctrl.official_docs, self.p1.id, q='1150054321')
        self.assertEqual(values['docs'], self.traffic)
        self.assertIn('還剩 1 天', html)
        self.assertNotIn('護岸施工計畫審查意見', html)
        # 找不到：明講找不到，不是空白
        values, html = self._drive(self.sup_field, self.ctrl.official_docs, self.p1.id, q='不存在的字')
        self.assertEqual(values['doc_count'], 0)
        self.assertIn('找不到符合條件的公文', html)
        # 日期格式被亂改：當成沒填，不報錯
        values, _html = self._drive(self.sup_field, self.ctrl.official_docs, self.p1.id, date_from='abc')
        self.assertEqual(values['doc_count'], 2)

    def test_list_of_project_user_cannot_see_redirects(self):
        values, location = self._drive(self.sup_outsider, self.ctrl.official_docs, self.p1.id)
        self.assertIsNone(values)
        self.assertEqual(location, '/my')

    def test_all_projects_list_follows_who_can_see_what(self):
        values, html = self._drive(self.sup_boss, self.ctrl.official_docs_all)
        mine = values['docs'].filtered(lambda d: d in (self.water | self.traffic | self.on_p2 | self.company_wide))
        self.assertEqual(mine, self.water | self.traffic | self.on_p2 | self.company_wide)
        self.assertIn('公司共通公文', html)
        self.assertIn(f'/construction/official-doc/{self.company_wide.id}', html, '沒掛工程的也點得進去')
        values, html = self._drive(self.sup_field, self.ctrl.official_docs_all)
        self.assertEqual(values['docs'], self.traffic | self.water, '成員的總表只有自己參與工程的')
        self.assertNotIn('公司共通公文', html)

    def test_account_without_read_access_sees_reason_not_error(self):
        plain = self._user('office_plain', [PLAIN_INTERNAL], self.co_s)
        values, html = self._drive(plain, self.ctrl.official_docs_all)
        self.assertTrue(values['no_access'])
        self.assertIn('沒有查看公文的權限', html)

    # ── 詳情與下載 ──────────────────────────────────────────────────────
    def test_detail_lists_attachments_with_guarded_links(self):
        values, html = self._drive(self.sup_field, self.ctrl.official_doc_detail, self.water.id, self.p1.id)
        self.assertEqual(values['doc'], self.water)
        self.assertIn('審查意見.pdf', html)
        self.assertIn(f'/construction/official-doc/{self.water.id}/file/{self.scan.id}', html)
        # 別的工程的公文、看不到的公文：導回列表
        values, location = self._drive(self.sup_field, self.ctrl.official_doc_detail, self.on_p2.id, self.p1.id)
        self.assertIsNone(values)
        self.assertEqual(location, f'/construction/{self.p1.id}/official-docs')

    def test_company_wide_doc_opens_without_project_only_for_who_can_see(self):
        values, html = self._drive(self.sup_boss, self.ctrl.official_doc_detail, self.company_wide.id)
        self.assertEqual(values['doc'], self.company_wide)
        self.assertIn('公司共通公文', html)
        values, location = self._drive(self.sup_field, self.ctrl.official_doc_detail, self.company_wide.id)
        self.assertIsNone(values)
        self.assertEqual(location, '/construction/official-docs')
        # 掛了工程的公文走不帶工程的網址 → 導去工程底下（讓工程的可見性檢查照常跑）
        values, location = self._drive(self.sup_boss, self.ctrl.official_doc_detail, self.water.id)
        self.assertEqual(location, f'/construction/{self.p1.id}/official-doc/{self.water.id}')

    def _downloadable(self, user, doc, attachment):
        with MockRequest(self.env(user=user)):
            return self.ctrl._downloadable_attachment(doc.id, attachment.id)

    def test_download_only_attachment_of_a_readable_doc(self):
        self.assertEqual(self._downloadable(self.sup_field, self.water, self.scan), self.scan)
        # 看不到那筆公文
        with self.assertRaises(NotFound):
            self._downloadable(self.sup_outsider, self.water, self.scan)
        # 附件不是掛在那筆公文上：拿自己看得到的公文 id 配別人的附件 id
        other_scan = self.env['ir.attachment'].create({
            'name': '工程二.pdf', 'raw': b'%PDF-p2', 'res_model': DOC_MODEL, 'res_id': self.on_p2.id})
        unrelated = self.env['ir.attachment'].create({'name': '無關.pdf', 'raw': b'%PDF-x'})
        project_file = self.env['ir.attachment'].create({
            'name': '工程檔.pdf', 'raw': b'%PDF-y', 'res_model': 'project.project', 'res_id': self.p1.id})
        for attachment in (other_scan, unrelated, project_file):
            with self.assertRaises(NotFound, msg=attachment.name):
                self._downloadable(self.sup_field, self.water, attachment)

    # ── 新增 ────────────────────────────────────────────────────────────
    def test_create_with_attachments_as_contractor_field_user(self):
        files = [self._upload('掃描1.pdf', b'one'), self._upload('掃描2.pdf', b'two')]
        before = self.Doc.search([('project_id', '=', self.p1.id)])
        values, location = self._drive(
            self.a_field, self.ctrl.official_doc_create, self.p1.id, files=files,
            subject='  營造 A 的收文  ', organization='新北市政府水利局', doc_number='新北水工字第1150077777號',
            direction='incoming', doc_date=str(self.yesterday), reply_deadline=str(self.tomorrow),
            # 表單裡沒有的欄位：不能被帶進去
            company_id=str(self.co_b.id), state='done', responsible_user_id=str(self.staff.id))
        self.assertIsNone(values)
        doc = self.Doc.search([('project_id', '=', self.p1.id)]) - before
        self.assertEqual(len(doc), 1)
        self.assertEqual(location, f'/construction/{self.p1.id}/official-doc/{doc.id}?message=created')
        self.assertEqual((doc.subject, doc.company_id, doc.project_id, doc.state, doc.doc_date),
                         ('營造 A 的收文', self.co_a, self.p1, 'pending', self.yesterday))
        self.assertEqual(doc.create_uid, self.a_field)
        self.assertFalse(doc.responsible_user_id)
        attachments = doc.attachment_ids
        self.assertEqual(sorted(attachments.mapped('name')), ['掃描1.pdf', '掃描2.pdf'])
        self.assertEqual(set(attachments.mapped('public')), {False})
        self.assertEqual(sorted(a.raw for a in attachments), [b'one', b'two'])

    def test_create_rejects_missing_subject_bad_date_too_many_files(self):
        count = self.Doc.search_count([])
        new_url = f'/construction/{self.p1.id}/official-doc/new'
        _values, location = self._drive(self.sup_field, self.ctrl.official_doc_create, self.p1.id, subject='   ')
        self.assertEqual(location, new_url + '?error=no_subject')
        _values, location = self._drive(self.sup_field, self.ctrl.official_doc_create, self.p1.id,
                                        subject='日期亂填', doc_date='2026-13-45')
        self.assertEqual(location, new_url + '?error=bad_date')
        files = [self._upload(f'{index}.pdf') for index in range(MAX_UPLOAD_FILES + 1)]
        _values, location = self._drive(self.sup_field, self.ctrl.official_doc_create, self.p1.id,
                                        files=files, subject='太多檔')
        self.assertEqual(location, new_url + '?error=too_many_files')
        # 收文日早於公文日：模型擋下，整筆不存（連附件都不留）
        attachments = self.env['ir.attachment'].search_count([('res_model', '=', DOC_MODEL)])
        _values, location = self._drive(self.sup_field, self.ctrl.official_doc_create, self.p1.id,
                                        files=[self._upload('x.pdf')], subject='日期顛倒',
                                        doc_date=str(self.today), receive_date=str(self.yesterday))
        self.assertEqual(location, new_url + '?error=invalid')
        self.assertEqual(self.Doc.search_count([]), count)
        self.assertEqual(self.env['ir.attachment'].search_count([('res_model', '=', DOC_MODEL)]), attachments)

    def test_viewer_and_outsider_cannot_create(self):
        count = self.Doc.search_count([])
        with self.assertRaises(AccessError):
            self._drive(self.a_viewer, self.ctrl.official_doc_create, self.p1.id, subject='閱覽者建的')
        _values, location = self._drive(self.sup_outsider, self.ctrl.official_doc_create, self.p1.id, subject='外人建的')
        self.assertEqual(location, '/my')
        self.assertEqual(self.Doc.search_count([]), count)
        # 新增頁：閱覽者被導回列表並說明
        _values, location = self._drive(self.a_viewer, self.ctrl.official_doc_new, self.p1.id)
        self.assertEqual(location, f'/construction/{self.p1.id}/official-docs?error=forbidden')

    # ── 標為已辦 ────────────────────────────────────────────────────────
    def test_mark_done_needs_write_role_and_readable_doc(self):
        _values, location = self._drive(self.sup_field, self.ctrl.official_doc_done, self.traffic.id, self.p1.id)
        self.assertEqual(location, f'/construction/{self.p1.id}/official-doc/{self.traffic.id}?message=done')
        self.assertEqual(self.traffic.state, 'done')
        # 看不到的公文（別的工程）：不動它
        pending_p2 = self._doc('工程二待辦', self.co_s, self.p2, reply_deadline=self.tomorrow)
        _values, location = self._drive(self.sup_field, self.ctrl.official_doc_done, pending_p2.id, self.p2.id)
        self.assertEqual(location, '/my')
        self.assertEqual(pending_p2.state, 'pending')
