# -*- coding: utf-8 -*-
"""說明書修正第 2 批（2026-11-02）：填了沒存或存錯、前台流程。

- P4  新增專案：表單的 owner_org／contractor 要存進 authority_name／contractor_company_name
- P8  缺失改善：預防措施要存進 prevention_action
- P9  create_from_portal：呼叫端給的 source_model 不可被蓋掉
- P10 提報沒填期限：詳情頁「通知改善」旁補填，先寫期限再通知
- P11 缺失通知連結：預約式帶 ?model=reservation，兩模型 id 撞號時查對模型
- P12 檢查詳情頁合格／缺失／N/A 計數由模板算
- P13 缺失詳情頁逾期警示卡
- P14/P15 照片篩選連結與上傳成功導向網格頁
- P16 工期展延輸入框 0 要顯示
"""

import re
from datetime import timedelta

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import file_open

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal

FIELD = 'construction_supervision_base.group_portal_user'      # 現場人員
LEADER = 'construction_supervision_base.group_portal_leader'   # 主管
PNG_B64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='


class _FakeUpload:
    filename = 'p.png'

    def read(self):
        return b'x'


@tagged('post_install', '-at_install', 'construction_portal')
class TestPortalManualFixesBatch2(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.ctrl = ConstructionPortal()
        cls.project = env['project.project'].create({
            'name': 'B2 一般式工程', 'code': 'B2-GEN', 'project_type': 'general',
            'state': 'construction', 'company_id': env.company.id})
        cls.res_project = env['project.project'].create({
            'name': 'B2 預約式工程', 'code': 'B2-RSV', 'project_type': 'reservation',
            'state': 'construction', 'company_id': env.company.id})
        env['defect.improvement.prefix.config'].create({
            'project_id': cls.project.id, 'supervision_prefix': 'B2QA',
            'contractor_prefix': 'B2QR'})
        cls.env['defect.improvement.prefix.config'].create({
            'project_id': cls.res_project.id, 'supervision_prefix': 'B2RS',
            'contractor_prefix': 'B2RC'})
        cls.worker = cls._mk_user('b2_worker', FIELD)
        cls.leader = cls._mk_user('b2_leader', LEADER)
        for u in (cls.worker, cls.leader):
            for p in (cls.project, cls.res_project):
                env['supervision.project.member'].create({
                    'project_id': p.id, 'user_id': u.id})

    @classmethod
    def _mk_user(cls, login, group_xmlid):
        return cls.env['res.users'].create({
            'name': login, 'login': login,
            'groups_id': [(6, 0, [cls.env.ref(group_xmlid).id])]})

    def _drive(self, user, method, *args, params=None, args_qs=None, **kw):
        """同 test_manual_fixes_20261102._drive：真實使用者跑真實路由，模板真的渲染。
        args_qs＝網址的 query string（_browse_defect 讀 request.httprequest.args）。
        回傳 (values, html)；路由回 redirect 時 values 為 None、html 為 Location。"""
        self.env.flush_all()
        self.env.invalidate_all()
        env = self.env(user=user)
        seen = {}
        with MockRequest(env) as req:
            req.httprequest.files.getlist.return_value = []
            req.httprequest.args = args_qs or {}
            req.params = params or {}
            req.render = lambda tpl, vals=None, **k: seen.update(tpl=tpl, vals=vals) or '<render>'
            res = method(*args, **kw)
            if 'tpl' not in seen:
                return None, res.headers.get('Location', '')
            html = env['ir.ui.view']._render_template(seen['tpl'], dict(seen['vals']))
        return seen['vals'], html.decode() if isinstance(html, bytes) else html

    def _general_defect(self, **kw):
        vals = {
            'project_id': self.project.id, 'record_type': 'supervision',
            'check_type': 'construction', 'defect_category': 'workmanship',
            'defect_description': 'B2 牆面裂縫', 'defect_location': 'B1',
            'source_type': 'daily_check', 'state': 'notified',
        }
        vals.update(kw)
        return self.env['general.defect.improvement'].create(vals)

    def _reservation_defect(self, **kw):
        slip = self.env['reservation.notification.slip'].create({
            'project_id': self.res_project.id, 'location': 'B2 地點'})
        slip.sudo().write({'state': 'in_progress'})
        vals = {
            'project_id': self.res_project.id, 'slip_id': slip.id,
            'record_type': 'supervision', 'check_type': 'construction',
            'defect_category': 'workmanship', 'defect_description': 'B2 預約缺失',
            'defect_location': 'B2', 'source_type': 'daily_check', 'state': 'notified',
        }
        vals.update(kw)
        return self.env['reservation.defect.improvement'].create(vals)

    # P4 ----------------------------------------------------------------
    def test_p4_project_create_saves_owner_and_contractor(self):
        loc = self._drive(
            self.leader, self.ctrl.portal_construction_project_create,
            name='B2 新建工程', owner_org='B2 業主機關', contractor='B2 承包廠商')[1]
        self.assertIn('/construction/', loc)
        proj = self.env['project.project'].sudo().search(
            [('authority_name', '=', 'B2 業主機關')])
        self.assertEqual(len(proj), 1, '業主機關應存進 authority_name')
        self.assertEqual(proj.contractor_company_name, 'B2 承包廠商')

    # P8 ----------------------------------------------------------------
    def test_p8_improve_saves_prevention_action(self):
        defect = self._general_defect()
        self._drive(
            self.worker, self.ctrl.portal_construction_defect_improve, defect.id,
            improvement_description='已修補', corrective_action='B2 矯正',
            preventive_action='B2 預防措施')
        self.env.invalidate_all()
        defect = defect.sudo()
        self.assertEqual(defect.prevention_action, 'B2 預防措施')
        self.assertEqual(defect.improvement_action, 'B2 矯正')

    # P9 ----------------------------------------------------------------
    def test_p9_create_from_portal_keeps_source_model(self):
        Photo = self.env['supervision.photo']
        partner = self.worker.partner_id
        keep = Photo.create_from_portal(
            {'project_id': self.project.id, 'filename': 'a.png', 'source_model': 'defect'},
            partner, PNG_B64)
        self.assertEqual(keep.source_model, 'defect', '呼叫端指定的來源分類不可被蓋成 other')
        default = Photo.create_from_portal(
            {'project_id': self.project.id, 'filename': 'b.png'}, partner, PNG_B64)
        self.assertEqual(default.source_model, 'other', '沒指定仍預設 other')

    # P10 ---------------------------------------------------------------
    def test_p10_notify_writes_deadline_then_notifies(self):
        defect = self._general_defect(state='draft')
        self.assertFalse(defect.deadline)
        _v, loc = self._drive(
            self.leader, self.ctrl.portal_defect_notify, defect.id, deadline='2099-12-31')
        self.env.invalidate_all()
        self.assertEqual(defect.state, 'notified', '補期限後應成功通知：%s' % loc)
        self.assertEqual(str(defect.deadline), '2099-12-31')

    def test_p10_bad_date_gives_message_not_500(self):
        defect = self._general_defect(state='draft')
        vals, loc = self._drive(
            self.leader, self.ctrl.portal_defect_notify, defect.id, deadline='不是日期')
        self.assertIsNone(vals)
        self.assertIn('error=', loc)
        self.env.invalidate_all()
        self.assertEqual(defect.state, 'draft')
        self.assertFalse(defect.deadline)

    def test_p10_non_manager_cannot_write_deadline(self):
        defect = self._general_defect(state='draft')
        with self.assertRaises(AccessError):
            self._drive(self.worker, self.ctrl.portal_defect_notify,
                        defect.id, deadline='2099-12-31')
        self.env.invalidate_all()
        self.assertFalse(defect.deadline, '守衛要在寫入之前')

    def test_p10_detail_shows_deadline_input_for_manager(self):
        defect = self._general_defect(state='draft')
        vals, html = self._drive(
            self.leader, self.ctrl.portal_construction_defect_detail, defect.id)
        self.assertIsNotNone(vals, html)
        self.assertRegex(html, r'<input[^>]*name="deadline"')

    # P11 ---------------------------------------------------------------
    def _colliding_defects(self):
        """讓一般式與預約式缺失拿到同一個 id（兩張表各自編號，正式資料會撞）。"""
        cr = self.env.cr
        cr.execute("SELECT GREATEST((SELECT COALESCE(MAX(id),0) FROM general_defect_improvement),"
                   "(SELECT COALESCE(MAX(id),0) FROM reservation_defect_improvement)) + 1000")
        n = cr.fetchone()[0]
        cr.execute("SELECT setval('general_defect_improvement_id_seq', %s, false)", (n,))
        cr.execute("SELECT setval('reservation_defect_improvement_id_seq', %s, false)", (n,))
        gen = self._general_defect()
        res = self._reservation_defect()
        self.assertEqual(gen.id, res.id, '前提：兩模型 id 要撞')
        return gen, res

    def _browse(self, user, defect_id, qs):
        self.env.flush_all()
        self.env.invalidate_all()
        with MockRequest(self.env(user=user)) as req:
            req.httprequest.args = qs
            return self.ctrl._browse_defect(defect_id)

    def test_p11_browse_defect_respects_model_param(self):
        gen, res = self._colliding_defects()
        self.assertEqual(self._browse(self.worker, gen.id, {'model': 'reservation'})._name,
                         'reservation.defect.improvement')
        self.assertEqual(self._browse(self.worker, gen.id, {'model': 'general'})._name,
                         'general.defect.improvement')
        # 沒帶參數＝舊行為（先一般式），已發出的舊連結不壞
        self.assertEqual(self._browse(self.worker, gen.id, {})._name,
                         'general.defect.improvement')

    def test_p11_notification_link_for_reservation_defect_carries_model(self):
        res = self._reservation_defect()
        gen = self._general_defect()
        for rec in (res, gen):
            rec.message_post(
                body='B2 通知', partner_ids=self.worker.partner_id.ids,
                message_type='notification', subtype_xmlid='mail.mt_comment')
        self.env.flush_all()
        self.env.invalidate_all()
        with MockRequest(self.env(user=self.worker)):
            items = self.ctrl._get_portal_notifications()
        urls = {i['msg'].model: i['url'] for i in items}
        self.assertEqual(urls['reservation.defect.improvement'],
                         '/construction/defect/%s?model=reservation' % res.id)
        self.assertEqual(urls['general.defect.improvement'],
                         '/construction/defect/%s' % gen.id)

    def test_p11_notify_post_lands_on_the_reservation_defect(self):
        """id 撞號時，帶 model 的 POST 要改到預約式那筆，一般式不能被動到。"""
        gen, res = self._colliding_defects()
        gen.write({'state': 'draft'})
        res.write({'state': 'draft'})
        _v, loc = self._drive(self.leader, self.ctrl.portal_defect_notify, res.id,
                              deadline='2099-12-31', args_qs={'model': 'reservation'})
        self.env.invalidate_all()
        self.assertEqual(res.state, 'notified', loc)
        self.assertEqual(gen.state, 'draft')
        self.assertFalse(gen.deadline)
        self.assertIn('model=reservation', loc)

    def test_p11_reservation_detail_forms_keep_model(self):
        _gen, res = self._colliding_defects()
        res.write({'state': 'draft'})
        _v, html = self._drive(self.leader, self.ctrl.portal_construction_defect_detail, res.id,
                               args_qs={'model': 'reservation'})
        actions = re.findall(r'action="(/construction/defect/\d+/[^"]*)"', html)
        self.assertTrue(actions, '前提：詳情頁要有表單')
        self.assertFalse([a for a in actions if 'model=reservation' not in a], actions)

    def test_p11_reservation_list_links_keep_model(self):
        self._reservation_defect()
        _v, html = self._drive(self.worker, self.ctrl.portal_construction_defects,
                               self.res_project.id)
        links = re.findall(r'href="(/construction/defect/\d+[^"]*)"', html)
        self.assertTrue(links, '前提：列表要有缺失連結')
        self.assertFalse([a for a in links if 'model=reservation' not in a], links)

    def test_p10_deadline_not_written_unless_draft(self):
        defect = self._general_defect(deadline='2030-01-01')
        _v, loc = self._drive(
            self.leader, self.ctrl.portal_defect_notify, defect.id, deadline='2099-12-31')
        self.env.invalidate_all()
        self.assertEqual(str(defect.deadline), '2030-01-01')
        self.assertIn('error=', loc)

    def test_p10_rejected_deadline_is_message_and_rolled_back(self):
        """期限早於發現日期：回訊息不 500，也不留下改到一半的資料。"""
        defect = self._general_defect(state='draft', found_date='2026-06-01')
        _v, loc = self._drive(
            self.leader, self.ctrl.portal_defect_notify, defect.id, deadline='2026-01-01')
        self.env.invalidate_all()
        self.assertEqual(defect.state, 'draft')
        self.assertFalse(defect.deadline)
        self.assertIn('error=', loc)

    # P12 ---------------------------------------------------------------
    def test_p12_inspection_detail_counts_from_check_result(self):
        itype = self.env['self.inspection.type'].create({'name': 'B2 類型'})
        insp = self.env['general.self.inspection'].create({
            'project_id': self.project.id, 'name': 'B2-INSP', 'inspection_type_id': itype.id,
            'sub_project_name': 'B2', 'inspection_date': fields.Date.today()})
        insp.checklist_ids.unlink()
        for i, res in enumerate(('pass', 'pass', 'defect', 'na', 'na', 'na')):
            self.env['general.self.inspection.item'].create({
                'inspection_id': insp.id, 'check_item': 'B2 題%s' % i, 'check_result': res})
        vals, html = self._drive(
            self.worker, self.ctrl.portal_construction_inspection_detail, insp.id)
        self.assertIsNotNone(vals, html)
        got = {k: re.search(r'insp-count-%s">\s*(\d+)\s*<' % k, html).group(1)
               for k in ('pass', 'defect', 'na')}
        self.assertEqual(got, {'pass': '2', 'defect': '1', 'na': '3'})

    # P13 ---------------------------------------------------------------
    def test_p13_overdue_card_shows_for_overdue_defect(self):
        defect = self._general_defect(
            found_date=fields.Date.today() - timedelta(days=10),
            deadline=fields.Date.today() - timedelta(days=3))
        self.assertTrue(defect.is_overdue, '前提：逾期缺失 is_overdue 為真')
        vals, html = self._drive(
            self.worker, self.ctrl.portal_construction_defect_detail, defect.id)
        self.assertIsNotNone(vals, html)
        self.assertRegex(html, r'已逾期\s*3\s*天')

    def test_p13_no_overdue_card_for_on_time_defect(self):
        defect = self._general_defect(
            deadline=fields.Date.today() + timedelta(days=3))
        vals, html = self._drive(
            self.worker, self.ctrl.portal_construction_defect_detail, defect.id)
        self.assertIsNotNone(vals, html)
        self.assertNotRegex(html, r'已逾期\s*\d+\s*天')

    def test_p13_reservation_defect_has_is_overdue(self):
        defect = self._reservation_defect(
            notification_date=fields.Date.today() - timedelta(days=10),
            deadline=fields.Date.today() - timedelta(days=2))
        self.assertTrue(defect.is_overdue)

    # P14／P15 ----------------------------------------------------------
    def test_p14_photo_filter_links_point_to_grid(self):
        vals, html = self._drive(
            self.worker, self.ctrl.portal_construction_photos, self.project.id)
        self.assertIsNotNone(vals, html)
        self.assertIn('/photos/grid?source=', html)
        self.assertNotIn('/photos?source=', html)
        self.assertNotIn('/photos?category=', html)

    def test_p15_upload_success_redirects_to_grid(self):
        _v, loc = self._drive(
            self.worker, self.ctrl.portal_construction_signboard_photo_upload,
            self.project.id)
        self.assertIn('/photos/grid?message=signboard_added', loc)
        _v, loc = self._drive(
            self.worker, self.ctrl.portal_construction_photo_upload,
            project_id=str(self.project.id), photo=_FakeUpload())
        self.assertIn('/photos/grid?message=uploaded', loc)

    def test_p15_js_redirect_goes_to_grid(self):
        with file_open('construction_portal/static/src/js/portal_v10.js') as f:
            js = f.read()
        self.assertNotIn("'/photos?message=uploaded", js)
        self.assertIn("'/photos/grid?message=uploaded", js)

    # P16 ---------------------------------------------------------------
    def test_p16_extension_input_shows_zero(self):
        sched = self.env['progress.schedule'].create({
            'project_id': self.project.id, 'change_date': fields.Date.today()})
        self.assertEqual(sched.current_extension, 0)
        vals, html = self._drive(
            self.leader, self.ctrl.portal_schedule_extend_page, self.project.id)
        self.assertIsNotNone(vals, html)
        tag = re.search(r'<input[^>]*name="current_extension"[^>]*>', html).group(0)
        self.assertIn('value="0"', tag)
