# -*- coding: utf-8 -*-
"""期限待辦彙整（models/project_deadline.py；淞源 2026-11-10 會議 C5／C8）。

老闆：主管儀表板的待辦要依期限排序；快到期還沒安排就亮燈（七天、三天是他舉的例子）。
這裡鎖住清單本身（公司儀表板、手機首頁、每日提醒都讀這一份）：
* 只列「有期限、還沒辦完」的；辦完（缺失已改善、文件已上傳）就從清單消失；
* 期限由近到遠、逾期在最前面；
* 燈號門檻：逾期／3 天內（含今天）／4–7 天／其餘，門檻可調；
* 件數＝各來源同條件的筆數相加，不受筆數上限影響；
* 「今天」是台灣日期；期限欄位是 Datetime 的來源（行事曆的送件期限）也以台灣日期算；
* 指定工程就只看那些工程——指定了空的＝什麼都沒有，不能退回「全部」；
* 讀不到的來源標出來（denied），不報錯、不當成 0。
期望值依夾具寫死，不是拿實作再算一次。
"""
from datetime import date, datetime

from freezegun import freeze_time

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models.project_deadline import TITLE_MAX_LENGTH

FROZEN_NOW = '2026-11-05 04:00:00'       # UTC；台灣 2026-11-05 12:00
FOUND_DATE = date(2026, 10, 1)           # 缺失發現日（期限不得早於它）
DEFECT_MODEL = 'general.defect.improvement'
DOCUMENT_MODEL = 'supervision.document'
EVENT_MODEL = 'construction.calendar.event'   # construction_office（選裝）
PLENTY = 500


@tagged('post_install', '-at_install', 'construction_portal')
class TestProjectDeadline(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.Project = env['project.project']
        cls.p1 = cls._project('DL 工程一', 'DL-P1')
        cls.p2 = cls._project('DL 工程二', 'DL-P2')
        cls.both = cls.p1 | cls.p2
        # 工程一的缺失：逾期 1 天、今天到期、剩 3／4／7／8 天（門檻兩側）、沒有期限、已改善
        cls.d_overdue = cls._defect(cls.p1, date(2026, 11, 4))
        cls.d_today = cls._defect(cls.p1, date(2026, 11, 5))
        cls.d_3 = cls._defect(cls.p1, date(2026, 11, 8))
        cls.d_4 = cls._defect(cls.p1, date(2026, 11, 9))
        cls.d_7 = cls._defect(cls.p1, date(2026, 11, 12))
        cls.d_8 = cls._defect(cls.p1, date(2026, 11, 13))
        cls._defect(cls.p1, None)
        cls._defect(cls.p1, date(2026, 11, 1), state='improved')
        # 工程二的缺失：逾期 3 天
        cls.d_p2 = cls._defect(cls.p2, date(2026, 11, 2))
        # 工程一的應交文件：草稿（剩 1 天）、已上傳（不列）、草稿但沒設日期（不列）
        category = env['supervision.document.category'].create({'name': 'DL 文件分類'})
        cls.doc_due = cls._document(cls.p1, category, 'DL 施工計畫書', date(2026, 11, 6))
        cls._document(cls.p1, category, 'DL 已上傳', date(2026, 11, 1), state='uploaded')
        cls._document(cls.p1, category, 'DL 沒設日期', False)
        cls.plain = env['res.users'].with_context(no_reset_password=True).create({
            'name': 'dl_plain', 'login': 'dl_plain', 'groups_id': [(6, 0, [env.ref('base.group_user').id])]})

    @classmethod
    def _project(cls, name, code):
        project = cls.env['project.project'].create({
            'name': name, 'code': code, 'project_type': 'general', 'state': 'construction'})
        cls.env['defect.improvement.prefix.config'].create({
            'project_id': project.id, 'supervision_prefix': code.replace('-', '') + 'S',
            'contractor_prefix': code.replace('-', '') + 'C'})
        return project

    @classmethod
    def _defect(cls, project, deadline, state='notified'):
        return cls.env[DEFECT_MODEL].create({
            'project_id': project.id, 'record_type': 'supervision', 'check_type': 'construction',
            'defect_category': 'workmanship', 'defect_description': 'DL 缺失', 'defect_location': 'B1',
            'source_type': 'daily_check', 'state': state, 'deadline': deadline,
            'found_date': FOUND_DATE, 'notification_date': FOUND_DATE})

    @classmethod
    def _document(cls, project, category, name, due, state='draft'):
        return cls.env[DOCUMENT_MODEL].create({
            'name': name, 'project_id': project.id, 'document_category_id': category.id,
            'due_date': due, 'state': state})

    def _data(self, projects='both', user=None, **kw):
        Project = self.Project.with_user(user) if user else self.Project
        kw.setdefault('limit', PLENTY)
        return Project._cy_deadline_data(projects=self.both if isinstance(projects, str) else projects, **kw)

    @staticmethod
    def _brief(data):
        return [(item['model'], item['res_id'], item['deadline'], item['days_left'], item['level'])
                for item in data['items']]

    # ── 燈號門檻 ────────────────────────────────────────────────────────
    def test_level_thresholds(self):
        level = self.Project._cy_deadline_level
        self.assertEqual([level(days) for days in (-30, -1, 0, 3, 4, 7, 8, 365)],
                         ['overdue', 'overdue', 'urgent', 'urgent', 'soon', 'soon', 'normal', 'normal'])
        # 門檻可調（C8 會改讀公司設定）：現場 10 天、主管 1 天
        self.assertEqual([level(days, site_days=10, manager_days=1) for days in (0, 1, 2, 10, 11)],
                         ['urgent', 'urgent', 'soon', 'soon', 'normal'])

    # ── 清單內容、排序、件數 ────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_list_is_exact_sorted_and_counted(self):
        data = self._data()
        self.assertEqual(self._brief(data), [
            (DEFECT_MODEL, self.d_p2.id, '2026-11-02', -3, 'overdue'),
            (DEFECT_MODEL, self.d_overdue.id, '2026-11-04', -1, 'overdue'),
            (DEFECT_MODEL, self.d_today.id, '2026-11-05', 0, 'urgent'),
            (DOCUMENT_MODEL, self.doc_due.id, '2026-11-06', 1, 'urgent'),
            (DEFECT_MODEL, self.d_3.id, '2026-11-08', 3, 'urgent'),
            (DEFECT_MODEL, self.d_4.id, '2026-11-09', 4, 'soon'),
            (DEFECT_MODEL, self.d_7.id, '2026-11-12', 7, 'soon'),
            (DEFECT_MODEL, self.d_8.id, '2026-11-13', 8, 'normal'),
        ])
        self.assertEqual(data['counts'], {'overdue': 2, 'urgent': 3, 'soon': 2, 'normal': 1, 'total': 8})
        self.assertEqual((data['today'], data['site_days'], data['manager_days'], data['denied']),
                         ('2026-11-05', 7, 3, []))
        # 件數＝各來源同條件的筆數相加（條件由測試獨立寫）
        in_scope = [('project_id', 'in', self.both.ids)]
        expected = (
            self.env[DEFECT_MODEL].search_count(in_scope + [
                ('deadline', '!=', False), ('state', 'not in', ('improved', 'verified', 'closed'))])
            + self.env[DOCUMENT_MODEL].search_count(in_scope + [('due_date', '!=', False), ('state', '=', 'draft')]))
        self.assertEqual(data['counts']['total'], expected)
        # 每一筆帶的資訊
        doc_item = next(item for item in data['items'] if item['model'] == DOCUMENT_MODEL)
        self.assertEqual({key: doc_item[key] for key in ('source', 'source_label', 'title', 'project_id',
                                                         'project_name', 'user_id')},
                         {'source': 'document', 'source_label': '應交文件', 'title': 'DL 施工計畫書',
                          'project_id': self.p1.id, 'project_name': 'DL 工程一', 'user_id': False})
        # 標題要看得出是什麼事：文件用名稱（不帶編號前綴）、缺失是「編號＋描述」
        self.assertTrue(self.d_today.defect_no, '前提：缺失有編號')
        self.assertEqual(data['items'][2]['title'], '%s DL 缺失' % self.d_today.defect_no)

    @freeze_time(FROZEN_NOW)
    def test_long_multiline_title_is_one_short_line(self):
        self.d_today.write({'defect_description': '第一行\n第二行　' + '很長的描述' * 30})
        title = next(item['title'] for item in self._data()['items'] if item['res_id'] == self.d_today.id
                     and item['model'] == DEFECT_MODEL)
        self.assertEqual(len(title), TITLE_MAX_LENGTH)
        self.assertTrue(title.startswith('%s 第一行 第二行 很長的描述' % self.d_today.defect_no), title)
        self.assertTrue(title.endswith('…'))
        self.assertNotIn('\n', title)

    @freeze_time(FROZEN_NOW)
    def test_thresholds_can_be_changed(self):
        data = self._data(site_days=10, manager_days=1)
        levels = {item['res_id']: item['level'] for item in data['items'] if item['model'] == DEFECT_MODEL}
        self.assertEqual((levels[self.d_today.id], levels[self.d_3.id], levels[self.d_8.id]),
                         ('urgent', 'soon', 'soon'))
        self.assertEqual(data['counts'], {'overdue': 2, 'urgent': 2, 'soon': 4, 'normal': 0, 'total': 8})
        self.assertEqual((data['site_days'], data['manager_days']), (10, 1))

    @freeze_time(FROZEN_NOW)
    def test_limit_cuts_list_not_counts(self):
        data = self._data(limit=3)
        self.assertEqual([item['res_id'] for item in data['items']],
                         [self.d_p2.id, self.d_overdue.id, self.d_today.id], '留下期限最近的三筆')
        self.assertEqual(data['counts']['total'], 8)

    @freeze_time(FROZEN_NOW)
    def test_finished_items_drop_out(self):
        self.d_overdue.write({'state': 'improved'})
        self.doc_due.write({'state': 'uploaded'})
        data = self._data()
        listed = {(item['model'], item['res_id']) for item in data['items']}
        self.assertNotIn((DEFECT_MODEL, self.d_overdue.id), listed)
        self.assertNotIn((DOCUMENT_MODEL, self.doc_due.id), listed)
        self.assertEqual(data['counts'], {'overdue': 1, 'urgent': 2, 'soon': 2, 'normal': 1, 'total': 6})

    # ── 工程範圍 ────────────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_project_filter_and_empty_means_nothing(self):
        only_p2 = self._data(projects=self.p2)
        self.assertEqual(self._brief(only_p2), [(DEFECT_MODEL, self.d_p2.id, '2026-11-02', -3, 'overdue')])
        self.assertEqual(only_p2['counts']['total'], 1)
        nothing = self._data(projects=self.Project.browse())
        self.assertEqual((nothing['items'], nothing['counts']['total']), ([], 0), '指定了空的工程不能退回「全部」')
        everything = self._data(projects=None, limit=PLENTY * 10)
        self.assertGreaterEqual(everything['counts']['total'], 8)
        mine = {(self.d_p2._name, self.d_p2.id), (self.doc_due._name, self.doc_due.id)}
        self.assertTrue(mine <= {(item['model'], item['res_id']) for item in everything['items']})

    # ── 台灣日期 ────────────────────────────────────────────────────────
    @freeze_time('2026-11-04 23:59:00')      # 台灣 11-05 07:59；UTC 日期還在 11-04
    def test_today_is_taiwan_date_at_0759(self):
        data = self._data()
        self.assertEqual(data['today'], '2026-11-05')
        days = {item['res_id']: (item['days_left'], item['level']) for item in data['items']
                if item['model'] == DEFECT_MODEL}
        self.assertEqual(days[self.d_overdue.id], (-1, 'overdue'), '11-04 到期的在台灣 11-05 早上已經逾期')
        self.assertEqual(days[self.d_today.id], (0, 'urgent'))
        self.assertEqual(data['counts']['overdue'], 2)

    @freeze_time(FROZEN_NOW)
    def test_calendar_deadline_uses_taiwan_date(self):
        """行事曆的「送件期限」：UTC 11-05 16:30＝台灣 11-06 00:30，算 11-06（剩 1 天），不是今天。會議、已完成的不列。"""
        if EVENT_MODEL not in self.env:
            self.skipTest('沒裝 construction_office')
        Event = self.env[EVENT_MODEL]

        def event(name, start, **vals):
            return Event.create({'name': name, 'project_id': self.p1.id, 'company_id': self.env.company.id,
                                 'start': start, 'responsible_user_id': self.env.uid, **vals})

        due = event('DL 送施工計畫', datetime(2026, 11, 5, 16, 30), event_type='deadline')
        event('DL 開會', datetime(2026, 11, 5, 16, 30), event_type='meeting')
        event('DL 已送出', datetime(2026, 11, 6, 2, 0), event_type='deadline', state='done')
        data = self._data(projects=self.p1)
        items = [item for item in data['items'] if item['model'] == EVENT_MODEL]
        self.assertEqual([(item['res_id'], item['deadline'], item['days_left'], item['level'], item['source_label'],
                           item['user_id']) for item in items],
                         [(due.id, '2026-11-06', 1, 'urgent', '送件期限', self.env.uid)])
        # 件數的分界和清單上的燈號是同一條線：主管門檻設成 0 天（只有今天算緊急）時，它在清單與件數都落在「快到了」
        strict = self._data(projects=self.p1, manager_days=0)
        level = next(item['level'] for item in strict['items'] if item['model'] == EVENT_MODEL)
        self.assertEqual(level, 'soon')
        without_event = strict['counts']['soon'] - 1
        due.write({'state': 'done'})
        self.assertEqual(self._data(projects=self.p1, manager_days=0)['counts']['soon'], without_event)

    # ── 讀不到的來源 ────────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_unreadable_source_is_marked_not_zero(self):
        """只有內部使用者群組的帳號讀不到缺失：標在 denied、清單裡沒有缺失、不報錯。"""
        self.assertFalse(self.env[DEFECT_MODEL].with_user(self.plain).has_access('read'), '前提：這個帳號讀不到缺失')
        data = self._data(user=self.plain)
        self.assertIn('缺失改善', data['denied'])
        self.assertEqual(data['denied'].count('缺失改善'), 1, '兩個缺失模型同一個說法，只列一次')
        self.assertFalse([item for item in data['items'] if item['model'] == DEFECT_MODEL])
