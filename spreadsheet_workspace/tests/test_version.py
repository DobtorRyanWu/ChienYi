# -*- coding: utf-8 -*-
"""版本紀錄：手動存版本、存檔自動存版本（去重、合併、保留筆數）。"""
import json
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import tagged

from odoo.addons.spreadsheet_workspace.models.spreadsheet_spreadsheet import (
    AUTO_VERSION_KEEP,
    AUTO_VERSION_MERGE_MINUTES,
    AUTO_VERSION_MESSAGE,
    SKIP_AUTO_VERSION_KEY,
)

from .common import WorkspaceCommon

# 把既有版本的時間往前推到合併時間窗之外
OUTSIDE_MERGE_WINDOW = timedelta(minutes=AUTO_VERSION_MERGE_MINUTES + 1)
EXTRA_AUTO_VERSIONS = 5


@tagged('post_install', '-at_install', 'spreadsheet_workspace')
class TestWorkspaceVersion(WorkspaceCommon):

    def _versions(self, sheet):
        return self.Version.search([('spreadsheet_id', '=', sheet.id)])

    def _age_versions(self, sheet):
        self._versions(sheet).write({'version_date': fields.Datetime.now() - OUTSIDE_MERGE_WINDOW})

    def _save(self, sheet, user, content):
        """模擬編輯器存檔：write({'spreadsheet_raw': …})。"""
        sheet.with_user(user).write({'spreadsheet_raw': self._raw(content)})

    # ── 手動 ──
    def test_manual_version_keeps_content_after_later_saves(self):
        sheet = self._shared_sheet()
        self._save(sheet, self.owner, '第一版內容')
        version = sheet.with_user(self.owner).action_save_version('  送審前  ')
        self.assertFalse(version.is_auto)
        self.assertEqual(version.commit_message, '送審前')
        self.assertEqual(version.user_id, self.owner)
        self._age_versions(sheet)
        self._save(sheet, self.owner, '之後又改了')
        version.invalidate_recordset()
        self.assertEqual(self._a1(json.loads(version.snapshot_raw)), '第一版內容', '舊版本不可以跟著原檔變')
        self.assertEqual(self._a1(sheet.spreadsheet_raw), '之後又改了')

    def test_manual_version_includes_pending_revisions(self):
        sheet = self._shared_sheet()
        self._save(sheet, self.owner, '底稿')
        self._add_pending_revision(sheet, '編輯中還沒存檔')
        version = sheet.with_user(self.owner).action_save_version('含編輯中的內容')
        revisions = json.loads(version.snapshot_revisions)
        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0]['commands'][0]['content'], '編輯中還沒存檔')
        self.assertEqual(revisions[0]['serverRevisionId'], 'START_REVISION')
        # 之後存檔，OCA 會清掉原檔的操作列；版本裡那份要還在
        self._age_versions(sheet)
        self._save(sheet, self.owner, '存檔後')
        version.invalidate_recordset()
        self.assertEqual(len(json.loads(version.snapshot_revisions)), 1)

    def test_reader_cannot_save_version(self):
        sheet = self._shared_sheet()
        with self.assertRaises(AccessError):
            sheet.with_user(self.reader).action_save_version('偷存')
        wizard = self.env['spreadsheet.workspace.version.save'].with_user(self.reader).create({
            'spreadsheet_id': sheet.id, 'commit_message': '偷存',
        })
        with self.assertRaises(AccessError):
            wizard.action_confirm()
        self.assertFalse(self._versions(sheet))

    def test_contributor_can_save_version_via_wizard(self):
        """對照組：有寫入權的人走同一條路是成功的（上一支不是因為小視窗本來就壞掉才擋住）。"""
        sheet = self._shared_sheet()
        wizard = self.env['spreadsheet.workspace.version.save'].with_user(self.contributor).create({
            'spreadsheet_id': sheet.id, 'commit_message': '可編輯者存的',
        })
        wizard.action_confirm()
        self.assertEqual(self._versions(sheet).mapped('commit_message'), ['可編輯者存的'])

    def test_user_cannot_touch_versions_directly(self):
        sheet = self._shared_sheet()
        version = sheet.with_user(self.owner).action_save_version('原始')
        Version = self.Version.with_user(self.owner)
        with self.assertRaises(AccessError):
            Version.create({'spreadsheet_id': sheet.id, 'commit_message': '假版本'})
        with self.assertRaises(AccessError):
            Version.browse(version.id).write({'snapshot_raw': '{}'})
        with self.assertRaises(AccessError):
            Version.browse(version.id).unlink()

    # ── 自動 ──
    def test_auto_version_on_save_dedup_and_merge(self):
        sheet = self._shared_sheet()
        self._save(sheet, self.owner, 'v1')
        versions = self._versions(sheet)
        self.assertEqual(len(versions), 1)
        self.assertTrue(versions.is_auto)
        self.assertEqual(versions.commit_message, AUTO_VERSION_MESSAGE)
        self.assertEqual(versions.user_id, self.owner)

        self._save(sheet, self.owner, 'v1')
        self.assertEqual(len(self._versions(sheet)), 1, '內容沒變不該多一版')

        self._save(sheet, self.owner, 'v2')
        versions = self._versions(sheet)
        self.assertEqual(len(versions), 1, '同一人在合併時間窗內的連續自動儲存要併成一筆')
        self.assertEqual(self._a1(json.loads(versions.snapshot_raw)), 'v2', '併進去的要是最新內容')

        self._age_versions(sheet)
        self._save(sheet, self.owner, 'v3')
        self.assertEqual(len(self._versions(sheet)), 2, '超過合併時間窗要另存一版')

        self._save(sheet, self.contributor, 'v4')
        versions = self._versions(sheet)
        self.assertEqual(len(versions), 3, '換人存檔不可以併進別人的版本')
        self.assertEqual(versions[0].user_id, self.contributor)
        self.assertEqual(versions[0].parent_version_id, versions[1])

    def test_auto_version_not_merged_into_manual(self):
        sheet = self._shared_sheet()
        manual = sheet.with_user(self.owner).action_save_version('手動')
        snapshot_before = manual.snapshot_raw
        self._save(sheet, self.owner, '手動之後馬上存檔')
        versions = self._versions(sheet)
        self.assertEqual(len(versions), 2, '手動版本不可以被之後的自動儲存覆蓋')
        manual.invalidate_recordset()
        self.assertFalse(manual.is_auto)
        self.assertEqual(manual.snapshot_raw, snapshot_before)

    def test_auto_versions_pruned_but_manual_kept(self):
        sheet = self._shared_sheet()
        manual = sheet.with_user(self.owner).action_save_version('要一直留著的')
        for index in range(AUTO_VERSION_KEEP + EXTRA_AUTO_VERSIONS):
            self._age_versions(sheet)
            self._save(sheet, self.owner, 'auto-%d' % index)
        versions = self._versions(sheet)
        autos = versions.filtered('is_auto')
        self.assertEqual(len(autos), AUTO_VERSION_KEEP)
        self.assertIn(manual, versions, '手動版本不可以被自動清理刪掉')
        newest = 'auto-%d' % (AUTO_VERSION_KEEP + EXTRA_AUTO_VERSIONS - 1)
        self.assertEqual(self._a1(json.loads(autos[0].snapshot_raw)), newest, '留下來的要是最近的')

    def test_skip_context_and_non_content_write(self):
        sheet = self._shared_sheet()
        sheet.with_user(self.owner).write({'name': '只改名'})
        self.assertFalse(self._versions(sheet), '沒動到內容的寫入不該存版本')
        sheet.with_user(self.owner).with_context(**{SKIP_AUTO_VERSION_KEY: True}).write({
            'spreadsheet_raw': self._raw('批次匯入'),
        })
        self.assertFalse(self._versions(sheet))

    def test_portal_owner_save_still_works(self):
        """前台編輯器（dobtor_spreadsheet_editor）用前台帳號直接 write；它對版本模型沒有任何權限。"""
        portal = self.env['res.users'].create({
            'name': 'ws_portal', 'login': 'ws_portal',
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        access = self.env['ir.model.access'].with_user(portal)
        if not access.check('spreadsheet.spreadsheet', 'write', raise_exception=False):
            self.skipTest('前台帳號對試算表沒有寫入權（dobtor_spreadsheet_editor 沒裝），這條路不存在')
        sheet = self.Sheet.sudo().create({'name': '前台的表', 'owner_id': portal.id})
        # 先確認「不存版本」時前台存檔本來就會成功，這樣下面失敗才能算在自動存版本頭上
        try:
            with self.cr.savepoint():
                sheet.with_user(portal).with_context(**{SKIP_AUTO_VERSION_KEY: True}).write({
                    'spreadsheet_raw': self._raw('基準'),
                })
        except AccessError as error:
            self.skipTest('前台存檔在沒有本模組的情況下就已經失敗（範圍外）：%s' % error)
        sheet.with_user(portal).write({'spreadsheet_raw': self._raw('前台存檔')})
        versions = self._versions(sheet)
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions.user_id, portal)
        self.assertFalse(access.check('spreadsheet.workspace.version', 'read', raise_exception=False))

    def test_view_versions_action_scoped_to_sheet(self):
        sheet = self._shared_sheet()
        sheet.with_user(self.owner).action_save_version('一')
        self.assertEqual(sheet.version_count, 1)
        action = sheet.action_view_versions()
        self.assertEqual(action['domain'], [('spreadsheet_id', '=', sheet.id)])
