# -*- coding: utf-8 -*-
"""W5 乙組：試算表工作區四條低風險問題（D1～D4，2026-11-25）。

D1 自動版本不可被 context 旗標跳過；直接寫 spreadsheet_binary_data 也要留版本
D2 資料夾改掛別家公司：修改時也要擋（建立本來就擋）
D3 唯讀者不可把表另存為模板
D4 刪試算表／模板後，對應的協作操作列要一併清掉
"""
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import tagged

from .common import WorkspaceCommon

# 舊版 context 旗標的字串（已拿掉常數；這裡用字串確認它不再有作用）
LEGACY_SKIP_KEY = 'spreadsheet_workspace_skip_auto_version'


@tagged('post_install', '-at_install', 'spreadsheet_workspace')
class TestWorkspaceFollowups(WorkspaceCommon):

    def _versions(self, sheet):
        return self.Version.search([('spreadsheet_id', '=', sheet.id)])

    # ── D1 ──
    def test_d1_legacy_skip_context_no_longer_skips(self):
        sheet = self._shared_sheet()
        sheet.with_user(self.owner).with_context(**{LEGACY_SKIP_KEY: True}).write({
            'spreadsheet_raw': self._raw('旗標不該有用'),
        })
        self.assertEqual(len(self._versions(sheet)), 1)

    def test_d1_direct_binary_write_keeps_a_version(self):
        sheet = self._shared_sheet()
        binary = sheet._workspace_binary_from_raw(self._raw('直接寫二進位'))
        sheet.with_user(self.owner).write({'spreadsheet_binary_data': binary})
        versions = self._versions(sheet)
        self.assertEqual(len(versions), 1)
        self.assertEqual(self._a1(sheet.spreadsheet_raw), '直接寫二進位')

    def test_d1_editor_save_still_makes_exactly_one_version(self):
        """編輯器存檔（寫 spreadsheet_raw）走反向欄位再寫一次 binary，不可因此多出一筆。"""
        sheet = self._shared_sheet()
        sheet.with_user(self.owner).write({'spreadsheet_raw': self._raw('正常存檔')})
        self.assertEqual(len(self._versions(sheet)), 1)

    # ── D2 ──
    def test_d2_folder_cannot_be_moved_to_foreign_company(self):
        user = self._make_user('ws_folder_user', 'spreadsheet_oca.group_user')
        folder = self.Folder.with_user(user).create({'name': '甲公司的', 'company_id': self.company_a.id})
        self.assertNotIn(self.company_b, user.company_ids)
        with self.assertRaises(ValidationError):
            folder.with_user(user).write({'company_id': self.company_b.id})
        folder.invalidate_recordset()
        self.assertEqual(folder.company_id, self.company_a)

    def test_d2_folder_company_changes_inside_allowed_companies_still_work(self):
        user = self._make_user('ws_folder_user2', 'spreadsheet_oca.group_user')
        folder = self.Folder.with_user(user).create({'name': '甲公司的', 'company_id': self.company_a.id})
        folder.with_user(user).write({'company_id': False})
        self.assertFalse(folder.company_id)
        folder.with_user(user).write({'company_id': self.company_a.id})
        self.assertEqual(folder.company_id, self.company_a)
        # 系統程式（sudo）改別家公司照常可以：不影響資料修正腳本
        folder.sudo().write({'company_id': self.company_b.id})
        self.assertEqual(folder.company_id, self.company_b)

    # ── D3 ──
    def test_d3_reader_cannot_promote_to_template(self):
        sheet = self._shared_sheet()
        before = self.Template.search_count([])
        with self.assertRaises(AccessError):
            sheet.with_user(self.reader).action_promote_to_template()
        self.assertEqual(self.Template.search_count([]), before)

    def test_d3_contributor_can_promote_to_template(self):
        sheet = self._shared_sheet()
        action = sheet.with_user(self.contributor).action_promote_to_template()
        self.assertEqual(action['res_model'], 'spreadsheet.workspace.template')

    # ── D4 ──
    def test_d4_unlink_sheet_removes_its_revisions(self):
        sheet = self._shared_sheet()
        sheet_id = sheet.id
        self._add_pending_revision(sheet, '待清的操作')
        # 別的試算表的操作列不可被連帶刪掉
        other = self._shared_sheet()
        self._add_pending_revision(other, '別張表的操作')
        sheet.with_user(self.owner).unlink()
        orphans = self.Revision.sudo().search([('model', '=', 'spreadsheet.spreadsheet'), ('res_id', '=', sheet_id)])
        self.assertFalse(orphans)
        self.assertEqual(len(other._workspace_pending_revisions()), 1)

    def test_d4_unlink_template_removes_its_revisions(self):
        template = self.Template.create({'name': 'WS 刪除模板', 'spreadsheet_raw': self._raw('模板')})
        template_id = template.id
        self._add_pending_revision(template, '模板上的操作')
        template.unlink()
        orphans = self.Revision.sudo().search([
            ('model', '=', 'spreadsheet.workspace.template'), ('res_id', '=', template_id)])
        self.assertFalse(orphans)
