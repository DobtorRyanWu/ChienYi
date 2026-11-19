# -*- coding: utf-8 -*-
"""模板的協作操作列只有對模板有寫入權的人能動（2026-11-19 權限審查 F1）。

修正前：任何內部帳號都能直接建一筆操作列掛到模板上，等於改寫模板內容。
"""
import json

from odoo.exceptions import AccessError
from odoo.tests.common import tagged

from .common import SHEET_ID, WorkspaceCommon

TEMPLATE_MODEL = 'spreadsheet.workspace.template'
SHEET_MODEL = 'spreadsheet.spreadsheet'
POISON = 'POISON'


@tagged('post_install', '-at_install', 'spreadsheet_workspace')
class TestWorkspaceRevisionGuard(WorkspaceCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 沒有試算表群組的內部帳號：OCA 的操作列模型對它也是全開的
        cls.plain = cls._make_user('ws_plain_guard')
        cls.template = cls.Template.with_user(cls.manager).create({'name': '官方模板'})

    def _revision_vals(self, model, res_id, content=POISON):
        return {
            'model': model,
            'res_id': res_id,
            'type': 'REMOTE_REVISION',
            'client_id': 'ws-guard',
            'server_revision_id': 'START_REVISION',
            'next_revision_id': 'ws-guard-next',
            'commands': json.dumps({
                'type': 'REMOTE_REVISION', 'version': 1,
                'commands': [{'type': 'UPDATE_CELL', 'sheetId': SHEET_ID, 'col': 0, 'row': 0, 'content': content}],
            }),
        }

    def _message(self, content):
        """OCA 編輯器送出的協作訊息（send_spreadsheet_message 的參數）。"""
        return {
            'type': 'REMOTE_REVISION', 'version': 1, 'clientId': 'ws-guard',
            'serverRevisionId': 'START_REVISION', 'nextRevisionId': 'ws-guard-next',
            'commands': [{'type': 'UPDATE_CELL', 'sheetId': SHEET_ID, 'col': 0, 'row': 0, 'content': content}],
        }

    def _template_revisions(self):
        return self.Revision.search([('model', '=', TEMPLATE_MODEL), ('res_id', '=', self.template.id)])

    def test_cannot_inject_revision_into_template(self):
        for user in (self.plain, self.owner):
            with self.subTest(who=user.login), self.assertRaises(AccessError):
                self.Revision.with_user(user).create(self._revision_vals(TEMPLATE_MODEL, self.template.id))
        self.assertFalse(self._template_revisions())
        # 所以預覽與從模板建出來的試算表都不會帶到別人塞的內容
        self.assertEqual(self.template.with_user(self.owner).get_spreadsheet_data()['revisions'], [])

    def test_cannot_inject_via_default_context(self):
        """model／res_id 不寫在 vals、改用 context 預設值帶進來，也要擋（守衛看的是建立後的實際值）。"""
        vals = self._revision_vals(TEMPLATE_MODEL, self.template.id)
        del vals['model'], vals['res_id']
        Revision = self.Revision.with_user(self.owner).with_context(
            default_model=TEMPLATE_MODEL, default_res_id=self.template.id)
        with self.assertRaises(AccessError):
            Revision.create(vals)
        self.assertFalse(self._template_revisions())

    def test_rejected_revision_not_left_behind_when_caller_swallows_error(self):
        """不用 assertRaises（它自己會開 savepoint 把寫入退回，看不出守衛有沒有清乾淨）。"""
        try:
            self.Revision.with_user(self.owner).create(self._revision_vals(TEMPLATE_MODEL, self.template.id))
        except AccessError:
            pass
        else:
            self.fail('應該要被擋下')
        self.assertFalse(self._template_revisions(), '被擋下的操作列不可以留在資料庫裡')

    def test_cannot_inject_in_mixed_batch(self):
        """一次建多筆、其中一筆掛模板：整批都不可以留下。"""
        sheet = self.Sheet.with_user(self.owner).create({'name': '自己的表'})
        with self.assertRaises(AccessError):
            self.Revision.with_user(self.owner).create([
                self._revision_vals(SHEET_MODEL, sheet.id, '正常'),
                self._revision_vals(TEMPLATE_MODEL, self.template.id),
            ])
        self.assertFalse(self._template_revisions())

    def test_cannot_delete_or_edit_template_revisions(self):
        revision = self.Revision.with_user(self.manager).create(
            self._revision_vals(TEMPLATE_MODEL, self.template.id, '管理員編輯中'))
        for user in (self.plain, self.owner):
            with self.subTest(who=user.login, op='unlink'), self.assertRaises(AccessError):
                self.Revision.with_user(user).browse(revision.id).unlink()
            with self.subTest(who=user.login, op='write'), self.assertRaises(AccessError):
                self.Revision.with_user(user).browse(revision.id).write({'commands': '{}'})
        self.assertEqual(self._template_revisions(), revision)

    def test_cannot_repoint_own_revision_to_template(self):
        sheet = self.Sheet.with_user(self.owner).create({'name': '自己的表'})
        revision = self.Revision.with_user(self.owner).create(self._revision_vals(SHEET_MODEL, sheet.id))
        with self.assertRaises(AccessError):
            revision.with_user(self.owner).write({'model': TEMPLATE_MODEL, 'res_id': self.template.id})
        self.assertFalse(self._template_revisions())

    def test_manager_edits_template_through_editor(self):
        """對照組：有寫入權的人走 OCA 編輯器的正常路徑照常可用（守衛沒有把模板鎖死）。"""
        self.assertTrue(self.template.with_user(self.manager).send_spreadsheet_message(self._message('管理員改的')))
        self.assertEqual(len(self._template_revisions()), 1)
        with self.assertRaises(AccessError):
            self.template.with_user(self.owner).send_spreadsheet_message(self._message(POISON))
        # 管理員存檔時 OCA 會清掉操作列，這一步也要過
        self.template.with_user(self.manager).write({'spreadsheet_raw': self._raw('存檔後')})
        self.assertFalse(self._template_revisions())

    def test_own_spreadsheet_revisions_unchanged(self):
        """對照組：一般試算表的操作列行為不變（守衛只管受保護的模型）。"""
        sheet = self.Sheet.with_user(self.owner).create({'name': '自己的表'})
        revision = self.Revision.with_user(self.owner).create(self._revision_vals(SHEET_MODEL, sheet.id, '正常編輯'))
        revision.with_user(self.owner).write({'client_id': 'ws-guard-2'})
        revision.with_user(self.owner).unlink()
        self.assertFalse(revision.exists())
