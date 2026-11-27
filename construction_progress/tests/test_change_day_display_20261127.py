# -*- coding: utf-8 -*-
"""18.0.1.16.0（2026-11-27，決定清單 匯入_本機資料\\進度表變更日與進度圖_決定清單_2026-11-27.md 三～六段）。

例子：第 1 版 1/1～1/10、1/11～1/20、1/21～1/30 各 20%；每天實際 2.5%（D0～D15）；第 2 版變更日 D15。
- 施工日誌「有無進度變更」：照進度表變更日期自動勾、第 1 版不算、不能手動勾。
- 變更那天：原定本日預定進度（＝daily_planned_progress，換版前那一版）＋變更後累計預定／實際（不存、跟進度圖同一套）。
- 變更那天按「查看進度表」開那一天換上的那一版。
- 使用中那一版可以改每一期預定（變更日那一列除外）、變更後累計預定／實際、變更說明、備註；存檔就生效、留痕。
- 重設草稿：前一版自動接手、預定完工日與展延改回；重設、改變更日期、啟用時新舊兩天以後的日誌都重算。
- 進度圖：實際線只連累計有變的日子；時間軸範圍與今日線。
"""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_supervision_base.utils.local_date import local_today

SEGS = [(0, 9, 20.0), (10, 19, 20.0), (20, 29, 20.0)]


@tagged('post_install', '-at_install', 'construction_progress')
class TestChangeDayDisplay(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.co = cls.env.company
        cls.d0 = fields.Date.today() - timedelta(days=120)
        cls.employee = cls.env['hr.employee'].create({'name': '變更日顯示測試員工', 'company_id': cls.co.id})

    def D(self, n):
        return self.d0 + timedelta(days=n)

    # ── 建資料 ────────────────────────────────────────────────────────────
    def _project(self, code, log_days=30, actual_days=16):
        project = self.env['project.project'].create({
            'name': '變更日顯示 ' + code, 'code': code, 'project_type': 'general', 'state': 'draft',
            'company_id': self.co.id, 'contract_start_date': self.D(0), 'contract_end_date': self.D(29)})
        v1 = self.env['progress.schedule'].create({'project_id': project.id, 'change_date': self.D(0)})
        for seq, (start, end, planned) in enumerate(SEGS, 1):
            self.env['progress.schedule.line'].create({
                'schedule_id': v1.id, 'sequence': seq * 10,
                'date_start': self.D(start), 'date_end': self.D(end), 'planned_progress': planned})
        v1._do_activate()
        project.write({'state': 'construction'})
        for n in range(log_days):
            self.env['daily.log.sheet'].create({
                'supervision_project_id': project.id, 'company_id': self.co.id,
                'employee_id': self.employee.id, 'log_date': self.D(n),
                'daily_actual_progress': 2.5 if n < actual_days else 0.0})
        return project, v1

    def _v2(self, v1, day=15, extension=0, after=10.0, cum_target=31.0, act_target=20.0):
        """第 2 版（「建立新版本」建的）：變更日 D(day)，變更日以後各段填 after，兩格照填，啟用。"""
        v2 = v1._create_new_version(self.D(day), '第 1 次變更')
        if extension:
            v2.write({'current_extension': extension})
        for line in v2.line_ids:
            if line.date_start > self.D(day):
                line.write({'planned_progress': after})
        vals = {}
        if cum_target is not None:
            vals['correction_target_cumulative'] = cum_target
        if act_target is not None:
            vals['correction_target_actual'] = act_target
        if vals:
            v2.write(vals)
        v2._do_activate()
        return v2

    def _log(self, project, n):
        self.env.flush_all()
        self.env.invalidate_all()
        return self.env['daily.log.sheet'].search([
            ('supervision_project_id', '=', project.id), ('log_date', '=', self.D(n))], limit=1)

    def _reset(self, schedule):
        """按「重設草稿」：新版先跳提醒視窗、確定了才做；舊版直接做（讓測試在舊程式上也跑得到斷言）。"""
        res = schedule.action_reset_draft()
        if isinstance(res, dict) and res.get('res_model') == 'progress.reset.draft.wizard':
            wiz = self.env['progress.reset.draft.wizard'].with_context(**res.get('context', {})).create({})
            message = wiz.message          # 按確定之前看到的提醒
            wiz.action_confirm()
            return message
        return None

    # ── 施工日誌「有無進度變更」 ─────────────────────────────────────────
    def test_has_progress_change_auto_and_first_version_excluded(self):
        project, v1 = self._project('CDD-A')
        self.assertFalse(self._log(project, 0).has_progress_change, '第 1 版的變更日期＝開工日，不算進度變更')
        self._v2(v1)
        self.assertTrue(self._log(project, 15).has_progress_change, '第 2 版變更日那天自動勾')
        self.assertFalse(self._log(project, 14).has_progress_change)
        self.assertFalse(self._log(project, 16).has_progress_change)
        self.assertTrue(self.env['daily.log.sheet']._fields['has_progress_change'].readonly,
                        '有無進度變更不能手動勾（欄位唯讀）')

    def test_change_day_shows_cumulative(self):
        project, v1 = self._project('CDD-B')
        v2 = self._v2(v1)
        log = self._log(project, 15)
        # 原定本日預定進度＝第 1 版 1/11～1/20 那一段 20% ÷ 10 天
        self.assertAlmostEqual(log.daily_planned_progress, 2.0, places=2)
        self.assertEqual(log.base_progress_schedule_id, v1, '變更那天本日預定用換版前那一版')
        self.assertAlmostEqual(log.change_cumulative_planned, 31.0, places=2, msg='變更後累計預定＝填的 31')
        self.assertAlmostEqual(log.change_cumulative_actual, 20.0, places=2, msg='變更後累計實際＝填的 20')
        # 一般日子兩格是 0（畫面不顯示）
        self.assertEqual(self._log(project, 14).change_cumulative_planned, 0.0)
        # 查看進度表：變更那天開那一天換上的那一版（即使之後又有第 3 版使用中）
        v3 = self._v2(v2, day=22, cum_target=None, act_target=None)
        self.assertEqual(v3.state, 'active')
        action = self._log(project, 15).action_view_progress_schedule()
        self.assertEqual(action.get('res_id'), v2.id, '變更那天開第 2 版')
        action = self._log(project, 18).action_view_progress_schedule()
        self.assertEqual(action.get('res_id'), v3.id, '一般日子開使用中那一版')

    # ── 使用中那一版可以直接改 ─────────────────────────────────────────────
    def test_active_edit_planned_tracked_and_change_row_pinned(self):
        project, v1 = self._project('CDD-C')
        v2 = self._v2(v1)
        lines = v2.line_ids.sorted(lambda l: (l.date_start, l.date_end, l.id))
        first = lines[0]
        row = v2._change_day_line()
        self.assertTrue(row, '前提：第 2 版有變更日那一列')
        msgs_before = len(v2.message_ids)
        first.write({'planned_progress': 18.0})      # 使用中改第 1 期 20 → 18
        self.env.flush_all()
        self.assertAlmostEqual(first.planned_progress, 18.0, places=2)
        bodies = ' '.join(v2.message_ids[:len(v2.message_ids) - msgs_before].mapped('body'))
        self.assertIn('預定 20.00 → 18.00', bodies, '活動紀錄留下改前、改後')
        # 變更日以後的累計被「變更後累計預定 31」釘住：變更日那一列跟著調整
        calc_planned = self._log(project, 15).change_cumulative_planned
        self.assertAlmostEqual(calc_planned, 31.0, places=2, msg='改了前面期別，變更日那天的累計還是 31')
        # 變更日那一列不能直接改
        with self.assertRaises(UserError):
            row.write({'planned_progress': 1.0})
        # 日期使用中照舊不能改
        with self.assertRaises(UserError):
            first.write({'date_end': self.D(8)})

    def test_active_edit_targets_reason_notes(self):
        project, v1 = self._project('CDD-D')
        v2 = self._v2(v1)
        # Odoo 不追蹤同一個交易裡剛建的紀錄（mail.thread.create 會 _track_discard）；實際上建立、修改是兩次存檔 →
        # 這裡先跑一次 commit 前的動作，模擬「建好存檔了」
        self.env.flush_all()
        self.env.cr.precommit.run()
        v2.write({'correction_target_cumulative': 33.0})
        self.env.flush_all()
        self.assertAlmostEqual(self._log(project, 15).change_cumulative_planned, 33.0, places=2,
                               msg='使用中改變更後累計預定，存檔就生效')
        v2.write({'correction_target_actual': 25.0})
        self.assertAlmostEqual(self._log(project, 15).change_cumulative_actual, 25.0, places=2)
        v2.write({'change_reason': '第 1 次變更（修正）', 'notes': '<p>新的備註</p>'})
        self.env.flush_all()
        self.env.cr.precommit.run()     # 欄位追蹤在 commit 前才寫（測試沒有 commit，要自己跑）
        self.env.invalidate_all()
        tracked = self.env['mail.tracking.value'].search([
            ('mail_message_id.model', '=', 'progress.schedule'), ('mail_message_id.res_id', '=', v2.id)])
        names = set(tracked.mapped('field_id.name'))
        self.assertTrue({'correction_target_cumulative', 'correction_target_actual', 'change_reason'} <= names,
                        '三個欄位都留舊值 → 新值（有的：%s）' % names)
        bodies = self.env['mail.message'].search([
            ('model', '=', 'progress.schedule'), ('res_id', '=', v2.id)]).mapped('body')
        self.assertTrue(any('改了備註' in (b or '') and '新的備註' in (b or '') for b in bodies), '備註留痕（改前、改後）')

    # ── 重設草稿 ────────────────────────────────────────────────────────────
    def test_reset_draft_previous_takes_over(self):
        project, v1 = self._project('CDD-E')
        end_v1, ext_v1 = project.contract_end_date, project.extension_duration
        v2 = self._v2(v1, extension=5)
        self.assertEqual(project.contract_end_date, end_v1 + timedelta(days=5), '前提：第 2 版展延 5 天')
        message = self._reset(v2)
        self.assertEqual(message, '重設後先回到第 1 版，改好請重新啟用。', '按之前先提醒回到第幾版')
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual((v1.state, v2.state), ('active', 'draft'), '前一版自動改回使用中')
        self.assertEqual(project.contract_end_date, end_v1, '預定完工日改回前一版的')
        self.assertEqual(project.extension_duration, ext_v1, '累計展延改回前一版的')
        log15 = self._log(project, 15)
        self.assertFalse(log15.has_progress_change, '重設後舊那一天不再勾')
        self.assertEqual(self._log(project, 20).base_progress_schedule_id, v1, '變更日以後改回前一版')
        self.assertEqual(self._log(project, 20).active_progress_schedule_id, v1)

    def test_reset_change_date_reactivate_recomputes_both_days(self):
        project, v1 = self._project('CDD-F')
        v2 = self._v2(v1)
        self._reset(v2)
        v2.write({'change_date': self.D(17)})
        for line in v2.line_ids:
            if line.date_start > self.D(17):
                line.write({'planned_progress': 10.0})
        v2.write({'correction_target_cumulative': 35.0})
        v2._do_activate()
        self.assertFalse(self._log(project, 15).has_progress_change, '舊的變更日不再勾')
        log17 = self._log(project, 17)
        self.assertTrue(log17.has_progress_change, '新的變更日自動勾')
        self.assertEqual(log17.base_progress_schedule_id, v1, '新變更日當天本日預定用換版前那一版')
        self.assertAlmostEqual(log17.daily_planned_progress, 2.0, places=2)
        self.assertEqual(self._log(project, 16).base_progress_schedule_id, v1)
        self.assertEqual(self._log(project, 18).base_progress_schedule_id, v2)

    def test_change_date_fix_on_archived_recomputes_logs(self):
        """資料修正程式直接改已歸檔那一版的變更日期：新舊兩天以後的日誌照新日期重算。"""
        project, v1 = self._project('CDD-G')
        v2 = self._v2(v1)
        v3 = self._v2(v2, day=22, cum_target=None, act_target=None)
        self.assertEqual(v2.state, 'archived')
        v2.write({'change_date': self.D(13)})
        self.assertTrue(self._log(project, 13).has_progress_change)
        self.assertFalse(self._log(project, 15).has_progress_change)
        self.assertEqual(self._log(project, 14).base_progress_schedule_id, v2, '新變更日隔天起用第 2 版')
        self.assertTrue(self._log(project, 22).has_progress_change, '第 3 版的變更日不受影響')
        self.assertEqual(v3.state, 'active')

    def test_reset_button_hidden_for_archived_after_start(self):
        arch = self.env['progress.schedule'].get_views([(False, 'form')])['views']['form']['arch']
        self.assertIn('project_state', arch, '重設草稿按鈕要看工程狀態（開工後已歸檔的不顯示）')

    # ── 進度圖 ──────────────────────────────────────────────────────────────
    def test_chart_actual_points_and_axis(self):
        project, v1 = self._project('CDD-H', log_days=12, actual_days=0)
        # D0～D3 每天 2.5、D4～D9 填 0、D10 填 5 → 累計有變的日子 D0、D1、D2、D3、D10
        for n, value in ((0, 2.5), (1, 2.5), (2, 2.5), (3, 2.5), (10, 5.0)):
            self._log(project, n).write({'daily_actual_progress': value})
        data = project.get_progress_chart_data()
        points = dict(zip(data['dates'], data['actual_points']))
        held = dict(zip(data['dates'], data['actual']))
        iso = lambda n: self.D(n).isoformat()
        for n in (0, 1, 2, 3, 10):
            self.assertIsNotNone(points[iso(n)], '累計有變的日子當點：D%d' % n)
        for n in (4, 5, 9):
            self.assertIsNone(points[iso(n)], '填 0 的日子不當點：D%d' % n)
            self.assertAlmostEqual(held[iso(n)], 10.0, places=2, msg='每一天的值照舊（沿用最後一個）')
        self.assertIsNotNone(points[iso(29)], '最後一個點照舊')
        today = local_today()
        self.assertEqual(data['axis_start'], iso(0))
        self.assertEqual(data['axis_end'], max(self.D(29), today).isoformat(), '沒完工畫到預定完工與今天較晚的那天')
        self.assertTrue(data['show_today'])
        project.write({'actual_end_date': self.D(31)})
        data = project.get_progress_chart_data()
        self.assertEqual(data['axis_end'], iso(31), '已完工畫到預定與實際完工較晚的那天')
        self.assertFalse(data['show_today'], '已完工不畫今日線')

    def test_chart_change_day_vertical_points(self):
        project, v1 = self._project('CDD-I')
        self._v2(v1)
        data = project.get_progress_chart_data()
        iso = self.D(15).isoformat()
        idx = [i for i, d in enumerate(data['dates']) if d == iso]
        self.assertEqual(len(idx), 2, '變更那天兩個點')
        before, after = (data['actual_points'][i] for i in idx)
        self.assertAlmostEqual(before, 40.0, places=2, msg='變更前 40（垂直線上端）')
        self.assertAlmostEqual(after, 20.0, places=2, msg='變更後 20')
