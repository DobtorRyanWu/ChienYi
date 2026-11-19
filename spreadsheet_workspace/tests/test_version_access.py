# -*- coding: utf-8 -*-
"""版本的可見範圍必須等於所屬試算表的可見範圍。

security.xml 的版本規則是照 spreadsheet_oca 的試算表規則抄一份加上 spreadsheet_id 前綴；
這裡用「同一批人、兩個模型各查一次」鎖住兩邊一致——OCA 規則日後有變、這邊沒跟上就會紅。
"""
from odoo.exceptions import AccessError
from odoo.tests.common import tagged

from .common import COMPANY_TYPE_CONTRACTOR, COMPANY_TYPE_FIELD, USER_GROUP, WorkspaceCommon


@tagged('post_install', '-at_install', 'spreadsheet_workspace')
class TestWorkspaceVersionAccess(WorkspaceCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.share_group = cls.env['res.groups'].create({'name': 'WS 測試共用群組'})
        cls.read_group = cls.env['res.groups'].create({'name': 'WS 測試唯讀群組'})
        cls.group_contributor = cls._make_user('ws_group_contributor', USER_GROUP)
        cls.group_reader = cls._make_user('ws_group_reader', USER_GROUP)
        cls.group_contributor.groups_id = [(4, cls.share_group.id)]
        cls.group_reader.groups_id = [(4, cls.read_group.id)]
        # 別家公司的人：就算被加進可編輯名單，公司隔離也要擋住
        cls.other_company_user = cls._make_user('ws_other_company', USER_GROUP, company=cls.company_b)
        cls.sheet = cls.Sheet.with_user(cls.owner).create({'name': 'WS 權限表'})
        cls.sheet.sudo().write({
            'company_id': cls.company_a.id,
            'contributor_ids': [(6, 0, (cls.contributor | cls.other_company_user).ids)],
            'reader_ids': [(6, 0, cls.reader.ids)],
            'contributor_group_ids': [(6, 0, cls.share_group.ids)],
            'reader_group_ids': [(6, 0, cls.read_group.ids)],
        })
        cls.version = cls.sheet.with_user(cls.owner).action_save_version('權限測試用')
        cls.expected = {
            'owner': (cls.owner, True),
            'contributor': (cls.contributor, True),
            'reader': (cls.reader, True),
            'group_contributor': (cls.group_contributor, True),
            'group_reader': (cls.group_reader, True),
            'manager': (cls.manager, True),
            'outsider': (cls.outsider, False),
            'other_company': (cls.other_company_user, False),
        }

    def _sees(self, model, user, record):
        return bool(model.with_user(user).search([('id', '=', record.id)]))

    def test_version_visibility_equals_spreadsheet_visibility(self):
        for label, (user, expected) in self.expected.items():
            with self.subTest(who=label):
                sheet_visible = self._sees(self.Sheet, user, self.sheet)
                version_visible = self._sees(self.Version, user, self.version)
                self.assertEqual(sheet_visible, expected, '測試前提：%s 對試算表的可見性不如預期' % label)
                self.assertEqual(version_visible, sheet_visible, '%s：版本與試算表的可見性不一致' % label)

    def test_outsider_cannot_read_snapshot_by_id(self):
        for user in (self.outsider, self.other_company_user):
            with self.subTest(who=user.login), self.assertRaises(AccessError):
                self.Version.with_user(user).browse(self.version.id).read(['snapshot_raw'])

    def test_compare_payload_requires_access(self):
        payload = self.version.with_user(self.reader).get_compare_payload()
        self.assertEqual(payload['spreadsheet_name'], 'WS 權限表')
        self.assertEqual(payload['from']['message'], '權限測試用')
        self.assertIn('sheets', payload['to']['data'])
        with self.assertRaises(AccessError):
            self.version.with_user(self.outsider).get_compare_payload()

    def test_removed_reader_loses_versions(self):
        """被移出共用名單後，舊版本也要跟著看不到。"""
        self.assertTrue(self._sees(self.Version, self.reader, self.version))
        self.sheet.sudo().write({'reader_ids': [(5, 0, 0)]})
        self.assertFalse(self._sees(self.Sheet, self.reader, self.sheet))
        self.assertFalse(self._sees(self.Version, self.reader, self.version))

    def test_plain_internal_user_has_no_access(self):
        """沒有試算表群組的內部帳號，三個新模型都碰不到。"""
        plain = self._make_user('ws_plain_internal')
        access = self.env['ir.model.access']
        for model in ('spreadsheet.workspace.version', 'spreadsheet.workspace.folder',
                      'spreadsheet.workspace.template'):
            with self.subTest(model=model):
                self.assertFalse(access.with_user(plain).check(model, 'read', raise_exception=False))

    def test_restricted_contractor_account_sees_nothing(self):
        """營造方帳號（公司儀表板的受限帳號）：白名單以外預設全拒，三個新模型都不可以例外。"""
        Users = self.env['res.users']
        if not hasattr(Users, '_dash_is_restricted') or 'ir.rule' not in self.env or not hasattr(
                self.env['ir.rule'], '_dash_scope_kind'):
            self.skipTest('沒有裝公司儀表板（construction_company_dashboard），沒有受限帳號這個概念')
        contractor_company = self.env['res.company'].create({
            'name': 'WS 測試營造廠', COMPANY_TYPE_FIELD: COMPANY_TYPE_CONTRACTOR,
        })
        restricted = self._make_user('ws_contractor_side', USER_GROUP, company=contractor_company)
        self.assertTrue(restricted._dash_is_restricted(), '測試前提：這個帳號應該被判成受限帳號')
        folder = self.Folder.create({'name': '共用資料夾', 'company_id': False})
        template = self.Template.create({'name': '共用模板', 'company_id': False})
        self.sheet.sudo().write({'company_id': False, 'reader_ids': [(4, restricted.id)]})
        for model, record in ((self.Folder, folder), (self.Template, template), (self.Version, self.version)):
            with self.subTest(model=model._name):
                self.assertFalse(self._sees(model, restricted, record))
