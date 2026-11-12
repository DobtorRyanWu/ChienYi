# -*- coding: utf-8 -*-
"""期限提醒的每日排程（models/deadline_reminder.py、models/res_company.py；淞源 2026-11-10 會議 C8）。

老闆：「七天前給現場的人通知，剩三天如果他還沒去安排，就到主管的控台亮紅燈」。這裡鎖住：
① 到了「提醒現場」的天數，權責人收到一則；沒有權責人就給該工程的現場人員；同一個期限不重複。
② 到了「提醒主管」的天數還沒辦完，該工程的老闆／主管各收到一則。
③ 辦完就不再提醒。  ④ 改了期限算新的一輪。  ⑤ 只有站內通知，不產生外寄郵件。
另外：已逾期的不提醒；閱覽者、非成員、自己讀不到那一筆的人不通知；天數讀公司設定。
"""
from datetime import date, datetime, timedelta

from freezegun import freeze_time

from odoo.addons.website.tools import MockRequest
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.construction_supervision_base.utils.local_date import local_today

from ..controllers.portal import PORTAL_DEADLINE_LIMIT, ConstructionPortal
from ..models.deadline_reminder import REMINDER_KEEP_DAYS
from ..models.res_company import MAX_REMIND_DAYS

BOSS = 'construction_supervision_base.group_portal_subscriber'
LEADER = 'construction_supervision_base.group_portal_leader'
FIELD = 'construction_supervision_base.group_portal_user'
VIEWER = 'construction_supervision_base.group_portal_viewer'
FROZEN_NOW = '2026-11-05 04:00:00'       # UTC；台灣 2026-11-05 12:00
TODAY = date(2026, 11, 5)
FOUND_DATE = date(2026, 10, 1)
DEFECT_MODEL = 'general.defect.improvement'
DOCUMENT_MODEL = 'supervision.document'
EVENT_MODEL = 'construction.calendar.event'   # construction_office（選裝）
REMINDER_MODEL = 'construction.deadline.reminder'


@tagged('post_install', '-at_install', 'construction_portal')
class TestDeadlineReminder(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.Reminder = env[REMINDER_MODEL]
        cls.company = env.company
        cls.company.write({'deadline_site_days': 7, 'deadline_manager_days': 3})
        cls.p1 = env['project.project'].create({
            'name': 'RMD 工程一', 'code': 'RMD-P1', 'project_type': 'general', 'state': 'construction',
            'company_id': cls.company.id})
        env['defect.improvement.prefix.config'].create({
            'project_id': cls.p1.id, 'supervision_prefix': 'RMDP1S', 'contractor_prefix': 'RMDP1C'})
        cls.category = env['supervision.document.category'].create({'name': 'RMD 文件分類'})
        # 工程一的成員：現場兩位、主管、老闆、閱覽者；另有一位不是成員的現場人員
        cls.field = cls._user('rmd_field', FIELD, member=True)
        cls.field2 = cls._user('rmd_field2', FIELD, member=True)
        cls.leader = cls._user('rmd_leader', LEADER, member=True)
        cls.boss = cls._user('rmd_boss', BOSS, member=True)
        cls.viewer = cls._user('rmd_viewer', VIEWER, member=True)
        cls.outsider = cls._user('rmd_outsider', FIELD, member=False)
        # 營造方但範圍公司空白的成員：預設拒絕，什麼都讀不到
        cls.blank = cls._user('rmd_blank', FIELD, member=True, supervision=False, is_contractor_org=True)
        cls.everyone = (cls.field | cls.field2 | cls.leader | cls.boss | cls.viewer | cls.outsider | cls.blank)

    @classmethod
    def _user(cls, login, group, member, supervision=True, **extra):
        vals = {'name': login, 'login': login, 'groups_id': [(6, 0, [cls.env.ref(group).id])],
                'company_id': cls.company.id, 'company_ids': [(6, 0, cls.company.ids)], **extra}
        if supervision:
            vals['is_supervision_org'] = True
        user = cls.env['res.users'].with_context(no_reset_password=True).create(vals)
        if member:
            cls.env['supervision.project.member'].create({'project_id': cls.p1.id, 'user_id': user.id})
        return user

    def _defect(self, deadline, responsible=None, state='notified'):
        return self.env[DEFECT_MODEL].create({
            'project_id': self.p1.id, 'record_type': 'supervision', 'check_type': 'construction',
            'defect_category': 'workmanship', 'defect_description': 'RMD 缺失', 'defect_location': 'B1',
            'source_type': 'daily_check', 'state': state, 'deadline': deadline,
            'responsible_user_id': responsible.id if responsible else False,
            'found_date': FOUND_DATE, 'notification_date': FOUND_DATE})

    def _document(self, due):
        return self.env[DOCUMENT_MODEL].create({
            'name': 'RMD 施工計畫書', 'project_id': self.p1.id, 'document_category_id': self.category.id,
            'due_date': due})

    def _run(self):
        return self.Reminder._cron_send_deadline_reminders()

    def _notified(self, record):
        """這一筆至今通知過誰：[(階段, 收到的帳號 login 排序後)]，依發出順序。"""
        rows = self.Reminder.search([('res_model', '=', record._name), ('res_id', '=', record.id)], order='id')
        return [(row.stage, sorted(self.everyone.filtered(lambda u: u.partner_id in row.partner_ids).mapped('login')))
                for row in rows]

    def _inbox(self, user, record):
        """user 在這一筆上收到的站內通知（mail.notification）。"""
        return self.env['mail.notification'].search([
            ('res_partner_id', '=', user.partner_id.id), ('mail_message_id.model', '=', record._name),
            ('mail_message_id.res_id', '=', record.id)])

    # ── ① 提醒現場 ──────────────────────────────────────────────────────
    def test_site_stage_goes_to_responsible_once(self):
        with freeze_time(FROZEN_NOW):
            at_threshold = self._defect(TODAY + timedelta(days=7), responsible=self.field2)
            too_early = self._defect(TODAY + timedelta(days=8), responsible=self.field2)
            self.assertTrue(self.env[DEFECT_MODEL].with_user(self.field2).search([('id', '=', at_threshold.id)]),
                            '前提：權責人讀得到這筆缺失')
            self._run()
            self.assertEqual(self._notified(at_threshold), [('site', ['rmd_field2'])])
            self.assertEqual(self._notified(too_early), [], '還剩 8 天：還不到提醒現場的天數')
            notification = self._inbox(self.field2, at_threshold)
            self.assertEqual(len(notification), 1)
            self.assertEqual((notification.notification_type, notification.is_read), ('inbox', False))
            body = str(notification.mail_message_id.body)
            for text in ('缺失改善', 'RMD 缺失', 'RMD 工程一', '2026-11-12', '還剩 <b>7</b> 天', '請安排辦理'):
                self.assertIn(text, body)
            self.assertFalse(self._inbox(self.field, at_threshold), '有權責人就不通知其他現場人員')
            self._run()
            self.assertEqual(len(self._inbox(self.field2, at_threshold)), 1, '同一天再跑一次不重複')
        with freeze_time('2026-11-06 04:00:00'):
            self._run()
            self.assertEqual(len(self._inbox(self.field2, at_threshold)), 1, '隔天也不重複（同一個期限、同一階段）')
            self.assertEqual(self._notified(too_early), [('site', ['rmd_field2'])], '隔天剩 7 天：輪到它')

    @freeze_time(FROZEN_NOW)
    def test_site_stage_without_responsible_goes_to_field_members(self):
        """應交文件沒有權責人欄位：通知該工程的現場人員成員；主管、老闆、閱覽者、非成員、讀不到的人都不收。"""
        document = self._document(TODAY + timedelta(days=5))
        self._run()
        self.assertEqual(self._notified(document), [('site', ['rmd_field', 'rmd_field2'])])
        for user in (self.leader, self.boss, self.viewer, self.outsider, self.blank):
            self.assertFalse(self._inbox(user, document), user.login)

    # ── ② 提醒主管、③ 辦完不再提醒 ──────────────────────────────────────
    def test_manager_stage_when_still_open_and_not_after_done(self):
        with freeze_time(FROZEN_NOW):
            still_open = self._defect(TODAY + timedelta(days=5), responsible=self.field)
            done_in_time = self._defect(TODAY + timedelta(days=5), responsible=self.field)
            self._run()
            self.assertEqual(self._notified(still_open), [('site', ['rmd_field'])])
            self.assertEqual(self._notified(done_in_time), [('site', ['rmd_field'])])
            done_in_time.write({'state': 'improved'})
        with freeze_time('2026-11-07 04:00:00'):       # 還剩 3 天
            self._run()
            self.assertEqual(self._notified(still_open),
                             [('site', ['rmd_field']), ('manager', ['rmd_boss', 'rmd_leader'])])
            self.assertEqual(self._notified(done_in_time), [('site', ['rmd_field'])], '辦完的不再提醒')
            body = str(self._inbox(self.leader, still_open).mail_message_id.body)
            self.assertIn('還剩 <b>3</b> 天', body)
            self.assertIn('請主管留意', body)
            self.assertFalse(self._inbox(self.viewer, still_open))

    @freeze_time(FROZEN_NOW)
    def test_both_stages_fire_together_when_first_seen_inside_manager_window(self):
        today_due = self._defect(TODAY, responsible=self.field)
        self._run()
        self.assertEqual(self._notified(today_due),
                         [('site', ['rmd_field']), ('manager', ['rmd_boss', 'rmd_leader'])])
        self.assertIn('今天到期', str(self._inbox(self.field, today_due).mail_message_id.body))

    @freeze_time(FROZEN_NOW)
    def test_overdue_is_not_reminded(self):
        overdue = self._defect(TODAY - timedelta(days=1), responsible=self.field)
        self._run()
        self.assertEqual(self._notified(overdue), [])
        self.assertFalse(self._inbox(self.field, overdue))

    # ── ④ 改期限 ────────────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_changed_deadline_starts_a_new_round(self):
        document = self._document(TODAY + timedelta(days=5))
        self._run()
        self.assertEqual(len(self._inbox(self.field, document)), 1)
        document.write({'due_date': TODAY + timedelta(days=6)})
        self._run()
        self.assertEqual(len(self._inbox(self.field, document)), 2, '期限改了：再提醒一次')
        self.assertEqual(sorted(self.Reminder.search([('res_model', '=', DOCUMENT_MODEL),
                                                      ('res_id', '=', document.id)]).mapped('deadline')),
                         [TODAY + timedelta(days=5), TODAY + timedelta(days=6)])

    # ── ⑤ 不寄 email ────────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_no_outgoing_mail_and_portal_notification_center_sees_it(self):
        Mail = self.env['mail.mail'].sudo()
        before = Mail.search_count([])
        defect = self._defect(TODAY + timedelta(days=2), responsible=self.field)
        sent = self._run()
        self.assertGreaterEqual(sent['site'], 1)
        self.assertGreaterEqual(sent['manager'], 1)
        self.assertEqual(Mail.search_count([]), before, '不能產生外寄郵件')
        # 前台通知中心的查法（controllers/portal.py 的 _portal_notif_domain）找得到這則
        found = self.env['mail.message'].sudo().search([
            ('notified_partner_ids', 'in', self.field.partner_id.ids),
            ('subtype_id', '=', self.env.ref('mail.mt_comment').id),
            ('model', '=', DEFECT_MODEL), ('res_id', '=', defect.id)])
        self.assertEqual(len(found), 1)
        self.assertEqual(found.message_type, 'notification')

    # ── 讀不到的人不通知 ────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_responsible_who_cannot_read_is_not_notified(self):
        defect = self._defect(TODAY + timedelta(days=5), responsible=self.blank)
        self.assertFalse(self.env[DEFECT_MODEL].with_user(self.blank).search([('id', '=', defect.id)]),
                         '前提：範圍公司空白的營造方帳號讀不到這筆缺失')
        self._run()
        self.assertEqual(self._notified(defect), [], '沒有人可通知就不留紀錄')
        self.assertFalse(self._inbox(self.blank, defect))

    # ── 公司設定 ────────────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_days_come_from_company_setting(self):
        self.company.write({'deadline_site_days': 10, 'deadline_manager_days': 1})
        nine = self._defect(TODAY + timedelta(days=9), responsible=self.field)
        two = self._defect(TODAY + timedelta(days=2), responsible=self.field)
        self._run()
        self.assertEqual(self._notified(nine), [('site', ['rmd_field'])], '提醒現場改成 10 天')
        self.assertEqual(self._notified(two), [('site', ['rmd_field'])], '提醒主管改成 1 天：還剩 2 天還不通知主管')
        self.assertEqual(self.company._cy_deadline_days(), (10, 1))
        self.assertEqual(self.env['res.company']._cy_deadline_days(), (7, 3), '沒有公司就用預設')

    def test_company_days_are_validated(self):
        for site, manager in ((3, 5), (MAX_REMIND_DAYS + 1, 3), (7, -1)):
            with self.assertRaises(ValidationError, msg=(site, manager)):
                with self.cr.savepoint():
                    self.company.write({'deadline_site_days': site, 'deadline_manager_days': manager})
        self.company.write({'deadline_site_days': MAX_REMIND_DAYS, 'deadline_manager_days': 0})

    # ── 行事曆的送件期限（Datetime 來源） ────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_calendar_deadline_event_reminds_responsible(self):
        if EVENT_MODEL not in self.env:
            self.skipTest('沒裝 construction_office')
        event = self.env[EVENT_MODEL].create({
            'name': 'RMD 送施工計畫', 'event_type': 'deadline', 'company_id': self.company.id,
            'project_id': self.p1.id, 'start': datetime(2026, 11, 9, 16, 30),    # 台灣 11-10 00:30：還剩 5 天
            'responsible_user_id': self.field.id})
        self._run()
        self.assertEqual(self._notified(event), [('site', ['rmd_field'])])
        self.assertIn('還剩 <b>5</b> 天', str(self._inbox(self.field, event).mail_message_id.body))

    # ── 紀錄清理 ────────────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_old_reminder_rows_are_removed(self):
        def row(deadline):
            return self.Reminder.create({'res_model': DEFECT_MODEL, 'res_id': 1, 'stage': 'site',
                                         'deadline': deadline, 'notified_on': deadline})

        old = row(TODAY - timedelta(days=REMINDER_KEEP_DAYS + 1))
        kept = row(TODAY - timedelta(days=REMINDER_KEEP_DAYS))
        self._run()
        self.assertFalse(old.exists())
        self.assertTrue(kept.exists())


@tagged('post_install', '-at_install', 'construction_portal')
class TestPortalDeadlineBlock(TransactionCase):
    """手機的「期限待辦」區塊（工程首頁、工程列表）與通知中心的連結：真實前台帳號跑真實路由，模板實際渲染成 HTML。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.ctrl = ConstructionPortal()
        cls.company = env.company
        cls.company.write({'deadline_site_days': 7, 'deadline_manager_days': 3})
        cls.today = local_today()
        cls.project = env['project.project'].create({
            'name': 'DLB 工程', 'code': 'DLB-P1', 'project_type': 'general', 'state': 'construction',
            'company_id': cls.company.id})
        env['defect.improvement.prefix.config'].create({
            'project_id': cls.project.id, 'supervision_prefix': 'DLBP1S', 'contractor_prefix': 'DLBP1C'})
        cls.category = env['supervision.document.category'].create({'name': 'DLB 文件分類'})
        cls.worker = env['res.users'].with_context(no_reset_password=True).create({
            'name': 'dlb_worker', 'login': 'dlb_worker', 'groups_id': [(6, 0, [env.ref(FIELD).id])],
            'company_id': cls.company.id, 'company_ids': [(6, 0, cls.company.ids)], 'is_supervision_org': True})
        env['supervision.project.member'].create({'project_id': cls.project.id, 'user_id': cls.worker.id})

    def _defect(self, deadline, description='DLB 缺失'):
        return self.env[DEFECT_MODEL].create({
            'project_id': self.project.id, 'record_type': 'supervision', 'check_type': 'construction',
            'defect_category': 'workmanship', 'defect_description': description, 'defect_location': 'B1',
            'source_type': 'daily_check', 'state': 'notified', 'deadline': deadline,
            'responsible_user_id': self.worker.id,
            'found_date': self.today - timedelta(days=30), 'notification_date': self.today - timedelta(days=30)})

    def _document(self, due, name='DLB 施工計畫書'):
        return self.env[DOCUMENT_MODEL].create({
            'name': name, 'project_id': self.project.id, 'document_category_id': self.category.id, 'due_date': due})

    def _drive(self, method, *args):
        """現場人員跑真實路由，路由 render 的模板實際渲染成 HTML。回傳 (values, html)。"""
        self.env.flush_all()
        self.env.invalidate_all()
        env = self.env(user=self.worker)
        seen = {}
        with MockRequest(env) as req:
            req.httprequest.args = {}
            req.params = {}
            req.render = lambda tpl, vals=None, **k: seen.update(tpl=tpl, vals=vals) or '<render>'
            res = method(*args)
            self.assertIn('tpl', seen, '路由沒有 render（被導走了）：%s' % getattr(res, 'headers', res))
            html = env['ir.ui.view']._render_template(seen['tpl'], dict(seen['vals']))
        return seen['vals'], html.decode() if isinstance(html, bytes) else html

    @staticmethod
    def _block(html):
        """HTML 裡「期限待辦」區塊那一段（到下一個分隔標題為止）。"""
        return html.split('<span>期限待辦</span>')[1].split('cy-sec-divider')[0]

    def test_project_home_lists_nearest_deadlines_with_links(self):
        overdue = self._defect(self.today - timedelta(days=2), 'DLB 逾期的缺失')
        due_today = self._defect(self.today, 'DLB 今天到期的缺失')
        document = self._document(self.today + timedelta(days=5))
        self._defect(self.today + timedelta(days=20), 'DLB 還很久的缺失')
        values, html = self._drive(self.ctrl.portal_construction_project_detail, self.project.id)
        block = values['deadline_block']
        self.assertEqual([(item['model'], item['res_id'], item['level']) for item in block['items']][:3], [
            (DEFECT_MODEL, overdue.id, 'overdue'), (DEFECT_MODEL, due_today.id, 'urgent'),
            (DOCUMENT_MODEL, document.id, 'soon')])
        self.assertEqual(block['counts'], {'overdue': 1, 'urgent': 1, 'soon': 1, 'normal': 1, 'total': 4})
        section = self._block(html)
        for text in ('逾期 2 天', '今天到期', '還剩 5 天', 'DLB 逾期的缺失', 'DLB 施工計畫書', '應交文件', '缺失改善',
                     'href="/construction/defect/%s"' % overdue.id,
                     'href="/construction/%s/documents"' % self.project.id,
                     'cy-dl-row cy-dl-overdue', 'cy-dl-row cy-dl-urgent', 'cy-dl-row cy-dl-soon', 'cy-dl-row cy-dl-normal'):
            self.assertIn(text, section)
        self.assertLess(section.index('DLB 逾期的缺失'), section.index('DLB 今天到期的缺失'))
        self.assertLess(section.index('DLB 今天到期的缺失'), section.index('DLB 施工計畫書'))
        self.assertNotIn('DLB 工程', section, '工程首頁不必每列重複工程名稱')

    def test_no_open_deadline_means_no_block(self):
        _values, html = self._drive(self.ctrl.portal_construction_project_detail, self.project.id)
        self.assertNotIn('期限待辦', html)

    def test_lamp_follows_company_setting_and_list_is_capped(self):
        self.company.write({'deadline_site_days': 10, 'deadline_manager_days': 1})
        for day in range(PORTAL_DEADLINE_LIMIT + 2):
            self._document(self.today + timedelta(days=9), 'DLB 第 %s 份' % day)
        values, html = self._drive(self.ctrl.portal_construction_project_detail, self.project.id)
        block = values['deadline_block']
        self.assertEqual((block['site_days'], block['manager_days']), (10, 1))
        self.assertEqual(len(block['items']), PORTAL_DEADLINE_LIMIT)
        self.assertEqual({item['level'] for item in block['items']}, {'soon'}, '剩 9 天：提醒現場改成 10 天後是黃燈')
        section = self._block(html)
        self.assertIn('列出 %s 件（快到期的優先，逾期的從最近的列起），另有 2 件沒列' % PORTAL_DEADLINE_LIMIT, section)
        self.assertIn('10 天內', section)

    def test_project_list_page_shows_block_with_project_name(self):
        """工程列表頁（登入後首頁）：路由帶出期限待辦、模板有呼叫區塊；跨工程所以每列要寫工程名稱。
        整頁的版型（portal.portal_layout）在模擬請求下畫不出來，所以區塊用路由給的值單獨渲染；整頁由瀏覽器實看。"""
        defect = self._defect(self.today + timedelta(days=1), 'DLB 列表頁的缺失')
        self.env.flush_all()
        self.env.invalidate_all()
        env = self.env(user=self.worker)
        seen = {}
        with MockRequest(env) as req:
            req.render = lambda tpl, vals=None, **k: seen.update(tpl=tpl, vals=vals) or '<render>'
            self.ctrl._render_construction_list()
            self.assertEqual(seen['tpl'], 'construction_portal.portal_my_construction_projects')
            block = seen['vals']['deadline_block']
            self.assertIn((DEFECT_MODEL, defect.id), [(item['model'], item['res_id']) for item in block['items']])
            html = env['ir.ui.view']._render_template(
                'construction_portal.portal_deadline_block', {'deadline_block': block})
        html = html.decode() if isinstance(html, bytes) else html
        self.assertIn('DLB 列表頁的缺失', html)
        self.assertIn('缺失改善・DLB 工程', html)
        list_arch = self.env.ref('construction_portal.portal_my_construction_projects').arch
        self.assertIn('t-call="construction_portal.portal_deadline_block"', list_arch)

    def test_notification_center_links_reminders_to_records(self):
        defect = self._defect(self.today + timedelta(days=2))
        document = self._document(self.today + timedelta(days=5))
        self.env[REMINDER_MODEL]._cron_send_deadline_reminders()
        self.env.flush_all()
        self.env.invalidate_all()
        with MockRequest(self.env(user=self.worker)):
            items = self.ctrl._get_portal_notifications(limit=50)
        urls = {(item['msg'].model, item['msg'].res_id): item['url'] for item in items}
        self.assertEqual(urls.get((DEFECT_MODEL, defect.id)), '/construction/defect/%s' % defect.id)
        self.assertEqual(urls.get((DOCUMENT_MODEL, document.id)), '/construction/%s/documents' % self.project.id)
