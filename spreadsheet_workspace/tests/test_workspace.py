# -*- coding: utf-8 -*-
"""資料夾、清單操作、模板庫。"""
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import tagged

from .common import USER_GROUP, WorkspaceCommon


@tagged('post_install', '-at_install', 'spreadsheet_workspace')
class TestWorkspaceFolder(WorkspaceCommon):

    def test_folder_count_and_path(self):
        parent = self.Folder.create({'name': '估驗'})
        child = self.Folder.create({'name': '第13期', 'parent_id': parent.id})
        self.Sheet.create([
            {'name': 'A', 'folder_id': parent.id},
            {'name': 'B', 'folder_id': parent.id},
            {'name': 'C', 'folder_id': child.id},
        ])
        self.assertEqual(parent.spreadsheet_count, 2, '只算直接放在本資料夾的')
        self.assertEqual(child.spreadsheet_count, 1)
        self.assertEqual(child.display_name, '估驗 / 第13期')

    def test_folder_cycle_blocked(self):
        parent = self.Folder.create({'name': '上層'})
        child = self.Folder.create({'name': '下層', 'parent_id': parent.id})
        # 擋的是核心的 _parent_store（flush 時檢查）
        with self.assertRaises(UserError):
            parent.parent_id = child
            self.env.flush_all()

    def test_folder_company_isolation(self):
        folder_a = self.Folder.create({'name': '甲公司的', 'company_id': self.company_a.id})
        folder_b = self.Folder.create({'name': '乙公司的', 'company_id': self.company_b.id})
        shared = self.Folder.create({'name': '共用的', 'company_id': False})
        visible = self.Folder.with_user(self.owner).search([('id', 'in', (folder_a | folder_b | shared).ids)])
        self.assertEqual(visible, folder_a | shared, '別家公司的資料夾不該看得到；沒填公司的大家都看得到')

    def test_create_blank_lands_in_selected_folder(self):
        folder = self.Folder.create({'name': '月報'})
        action = self.Sheet.with_user(self.owner).with_context(
            default_folder_id=folder.id,
        ).action_create_blank()
        self.assertEqual(action['tag'], 'action_spreadsheet_oca', '新增後要直接進編輯器')
        sheet = self.Sheet.browse(action['params']['spreadsheet_id'])
        self.assertEqual(sheet.folder_id, folder)
        self.assertEqual(sheet.owner_id, self.owner)

    def test_list_opens_editor_on_row_click(self):
        arch = self.Sheet.get_view(view_type='list')['arch']
        self.assertIn('action="open_spreadsheet"', arch)
        self.assertIn('type="object"', arch)
        self.assertIn('js_class="spreadsheet_workspace_list"', arch)
        self.assertIn('name="action_edit_metadata"', arch)

    def test_default_view_is_list_and_default_form_keeps_chatter(self):
        action = self.env.ref('spreadsheet_oca.spreadsheet_spreadsheet_act_window')
        self.assertEqual(action.view_mode.split(',')[0], 'list')
        # 「試算表資訊」小視窗是另一張表單，不可以搶走預設表單
        self.assertIn('<chatter', self.Sheet.get_view(view_type='form')['arch'])

    def test_search_panel_has_folder_and_tags(self):
        arch = self.Sheet.get_view(view_type='search')['arch']
        panel = arch[arch.index('<searchpanel'):arch.index('</searchpanel>')]
        self.assertIn('name="folder_id"', panel)
        self.assertIn('name="spreadsheet_tag_ids"', panel)

    def test_export_xlsx_action_carries_content(self):
        sheet = self.Sheet.with_user(self.owner).create({'name': 'X', 'spreadsheet_raw': self._raw('匯出')})
        self._add_pending_revision(sheet)
        action = sheet.with_user(self.owner).action_export_xlsx()
        self.assertEqual(action['tag'], 'action_download_spreadsheet')
        self.assertEqual(self._a1(action['params']['data']), '匯出')
        self.assertEqual(len(action['params']['stateUpdateMessages']), 1, '編輯中還沒併回底稿的操作也要帶去匯出')


@tagged('post_install', '-at_install', 'spreadsheet_workspace')
class TestWorkspaceTemplate(WorkspaceCommon):

    def _template(self, content='模板內容'):
        return self.Template.create({'name': '估驗模板', 'category': 'payment', 'spreadsheet_raw': self._raw(content)})

    def _revisions_of(self, record):
        return self.Revision.search([('model', '=', record._name), ('res_id', '=', record.id)])

    def test_create_spreadsheet_from_template(self):
        template = self._template()
        pending = self._add_pending_revision(template, '編輯中')
        action = template.with_user(self.owner).action_create_spreadsheet()
        self.assertEqual(action['tag'], 'action_spreadsheet_oca')
        sheet = self.Sheet.browse(action['params']['spreadsheet_id'])
        self.assertEqual(sheet.source_template_id, template)
        self.assertEqual(sheet.owner_id, self.owner)
        self.assertEqual(self._a1(sheet.spreadsheet_raw), '模板內容')
        copied = self._revisions_of(sheet)
        self.assertEqual(copied.mapped('commands'), [pending.commands], '模板編輯中的操作要一起帶過去')
        self.assertEqual(len(self._revisions_of(template)), 1, '模板自己的操作列不可以被搬走')
        self.assertFalse(sheet.version_ids, '從模板建立不算一次存檔，不該自動長出版本')

    def test_promote_spreadsheet_to_template(self):
        sheet = self.Sheet.with_user(self.owner).create({'name': '好用的表', 'spreadsheet_raw': self._raw('來源')})
        pending = self._add_pending_revision(sheet, '編輯中')
        action = sheet.with_user(self.owner).action_promote_to_template()
        template = self.Template.browse(action['res_id'])
        self.assertEqual(template.name, '好用的表')
        self.assertEqual(template.category, 'custom')
        self.assertEqual(self._a1(template.spreadsheet_raw), '來源')
        self.assertEqual(self._revisions_of(template).mapped('commands'), [pending.commands])

    def test_user_previews_template_readonly_manager_edits(self):
        template = self._template()
        self.assertEqual(template.with_user(self.owner).get_spreadsheet_data()['mode'], 'readonly')
        self.assertEqual(template.with_user(self.manager).get_spreadsheet_data()['mode'], 'normal')
        with self.assertRaises(AccessError):
            template.with_user(self.owner).write({'name': '被改掉'})
        with self.assertRaises(AccessError):
            template.with_user(self.owner).unlink()

    def test_template_company_isolation(self):
        template_b = self.Template.create({
            'name': '乙公司模板', 'company_id': self.company_b.id, 'spreadsheet_raw': self._raw('乙'),
        })
        self.assertFalse(self.Template.with_user(self.owner).search([('id', '=', template_b.id)]))
        user_b = self._make_user('ws_user_b', USER_GROUP, company=self.company_b)
        self.assertTrue(self.Template.with_user(user_b).search([('id', '=', template_b.id)]))
