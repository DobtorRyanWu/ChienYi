# -*- coding: utf-8 -*-
"""progress.schedule.line.create 的草稿狀態守衛（與 write/unlink 一致）。

根因：write()/unlink() 皆擋「非草稿進度表」修改/刪除明細，但 create() 只擋
actual_progress、不看進度表狀態，於是繞過 action_generate_lines/extend/add/copy/
correction（這些 action 皆已 gate state=='draft'）的程式化或匯入裸 create，可在
「使用中／已歸檔」進度表灌入明細——髒值當初就是從這個缺口進去，且事後因 write
被擋還得繞 SQL 才能修，是「防了修改、沒防新增」最糟的組合。

本測試鎖住 create 的狀態守衛，並確認合法遷移／回填批次可用
allow_line_on_active_schedule 旗標放行（否則會把自己的工具擋死）。
"""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_progress')
class TestLineCreateGuard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': 'line_guard 測試工程',
            'code': 'LINEGUARD-TEST',
            'project_type': 'general',
        })

    def _schedule(self, state='draft'):
        sch = self.env['progress.schedule'].create({
            'project_id': self.project.id,
            'calculation_mode': 'weekly',
            'change_date': '2026-08-01',
        })
        if state != 'draft':
            sch.state = state       # 測試直接落狀態，跳過 action 的前置流程
        return sch

    def _line_vals(self, sch):
        return {
            'schedule_id': sch.id,
            'sequence': 1,
            'date_start': '2026-08-01',
            'date_end': '2026-08-07',
            'planned_progress': 0.0,
        }

    def test_create_allowed_on_draft(self):
        """草稿進度表可以新增明細——合法路徑不受守衛影響。"""
        sch = self._schedule('draft')
        line = self.env['progress.schedule.line'].create(self._line_vals(sch))
        self.assertTrue(line.exists())

    def test_create_blocked_on_active(self):
        """使用中進度表不得新增明細（與 write/unlink 的狀態守衛一致）。"""
        sch = self._schedule('active')
        with self.assertRaises(UserError):
            self.env['progress.schedule.line'].create(self._line_vals(sch))

    def test_create_blocked_on_archived(self):
        """已歸檔進度表不得新增明細。"""
        sch = self._schedule('archived')
        with self.assertRaises(UserError):
            self.env['progress.schedule.line'].create(self._line_vals(sch))

    def test_create_allowed_on_active_with_context(self):
        """遷移／回填批次帶 allow_line_on_active_schedule 旗標時放行（不擋死工具）。"""
        sch = self._schedule('active')
        line = self.env['progress.schedule.line'].with_context(
            allow_line_on_active_schedule=True).create(self._line_vals(sch))
        self.assertTrue(line.exists())
