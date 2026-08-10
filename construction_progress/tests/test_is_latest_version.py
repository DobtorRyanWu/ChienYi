# -*- coding: utf-8 -*-
"""progress.schedule.is_latest_version stale stored compute 修復。

根因：`_compute_is_latest_version` 的 @api.depends 只列自己的 project_id/version，
當同工程新增（或刪除）版本更高的進度表時，ORM 不會觸發舊版重算，於是
is_latest_version=True 永遠 stale 地留在舊版上。全庫實測有 15 張假陽性。

修法：create/write/unlink 顯式呼叫 _recompute_latest_for_projects 重算兄弟記錄。
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_progress')
class TestIsLatestVersion(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': 'is_latest 測試工程',
            'code': 'ISLATEST-TEST',
            'project_type': 'general',
        })

    def _schedule(self, version=None):
        vals = {'project_id': self.project.id, 'calculation_mode': 'weekly',
                'change_date': '2026-08-01'}
        if version is not None:
            vals['version'] = version
        return self.env['progress.schedule'].create(vals)

    def test_new_version_flips_old_to_not_latest(self):
        """核心情境：建 v1（最新）後再建 v2，v1 必須自動變成非最新。"""
        v1 = self._schedule()
        self.assertTrue(v1.is_latest_version, 'v1 建立時應是最新版')
        v2 = self._schedule()
        self.assertTrue(v2.is_latest_version, 'v2 建立後應是最新版')
        self.assertFalse(v1.is_latest_version,
                         'v2 建立後 v1 應自動變成非最新（stale compute 已修）')

    def test_only_one_latest_per_project(self):
        """任一時刻同工程只能有一張標最新。"""
        self._schedule()
        self._schedule()
        self._schedule()
        latest = self.env['progress.schedule'].search([
            ('project_id', '=', self.project.id), ('is_latest_version', '=', True)])
        self.assertEqual(len(latest), 1, '同工程應恰有一張最新版')
        self.assertEqual(latest.version, 3, '最新版應是版本號最大的那張')

    def test_unlink_highest_reverts_latest(self):
        """刪掉最高版後，次高版要自動變回最新。"""
        v1 = self._schedule()
        v2 = self._schedule()
        v2.state = 'draft'          # unlink 僅允許草稿
        v2.unlink()
        self.assertTrue(v1.is_latest_version, '刪掉 v2 後 v1 應變回最新')

    def test_line_flag_follows(self):
        """明細的 schedule_is_latest（related+store）要跟著更新。"""
        v1 = self._schedule()
        self.env['progress.schedule.line'].create({
            'schedule_id': v1.id, 'sequence': 1,
            'date_start': '2026-08-01', 'date_end': '2026-08-07',
            'planned_progress': 0.0})
        self.assertTrue(v1.line_ids[0].schedule_is_latest)
        self._schedule()           # v2 → v1 不再最新
        v1.line_ids.invalidate_recordset(['schedule_is_latest'])
        self.assertFalse(v1.line_ids[0].schedule_is_latest,
                         'v1 明細的 schedule_is_latest 應跟著變 False')
