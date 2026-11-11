# -*- coding: utf-8 -*-
"""選單設定檔：MENUS_OFF 照舊關、MENUS_ON 會開回來、工程後台使用者真的看得到 Spreadsheets。

背景（2026-11-11）：Spreadsheets 在 08-10 被列進 MENUS_OFF；使用者 11-11 決定開回。
_apply_chienyi_menu_profile 原本只關不開，只刪掉 MENUS_OFF 那行的話，已經關掉的站永遠不會恢復。
"""
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_menu_profile.models import ir_ui_menu as profile

SPREADSHEETS_MENU = 'spreadsheet_oca.spreadsheet_spreadsheet_menu'
ENGINEERING_GROUP = 'construction_supervision_base.group_supervisor_admin'


@tagged('post_install', '-at_install', 'construction_menu_profile')
class TestMenuProfile(TransactionCase):

    def _apply(self):
        self.env['ir.ui.menu']._apply_chienyi_menu_profile()

    def test_reopened_menu_comes_back(self):
        """已經被關掉的 Spreadsheets，套用設定檔後要回到啟用"""
        menu = self.env.ref(SPREADSHEETS_MENU)
        menu.active = False
        self._apply()
        self.assertTrue(menu.active, 'MENUS_ON 的選單套用後仍是停用＝設定檔只關不開')

    def test_engineering_user_sees_spreadsheets(self):
        """只有「工程後台使用者」的新帳號，選單樹裡要有 Spreadsheets（使用者實際看到的結果）"""
        menu = self.env.ref(SPREADSHEETS_MENU)
        user = self.env['res.users'].create({
            'name': 'menu_profile_engineer',
            'login': 'menu_profile_engineer',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id, self.env.ref(ENGINEERING_GROUP).id])],
        })
        self._apply()
        menus = self.env['ir.ui.menu'].with_user(user).load_menus(False)
        self.assertIn(menu.id, menus['root']['children'],
                      '工程後台使用者的頂層 App 清單裡沒有 Spreadsheets')

    def test_off_list_still_applied(self):
        """MENUS_OFF 照舊：被勾回啟用的選單，套用後又關掉"""
        target = next((self.env.ref(xml_id, raise_if_not_found=False) for xml_id, _l, _c in profile.MENUS_OFF
                       if self.env.ref(xml_id, raise_if_not_found=False)), None)
        self.assertTrue(target, 'MENUS_OFF 一個選單都找不到，這支測試等於沒驗')
        target.active = True
        self._apply()
        self.assertFalse(target.active, 'MENUS_OFF 的選單套用後沒有被關掉')

    def test_lists_disjoint(self):
        """同一個選單不可同時在 ON 與 OFF（否則每次升級開了又關），而且 Spreadsheets 要在 ON"""
        on_ids = {xml_id for xml_id, _l, _c in getattr(profile, 'MENUS_ON', [])}
        off_ids = {xml_id for xml_id, _l, _c in profile.MENUS_OFF}
        self.assertIn(SPREADSHEETS_MENU, on_ids)
        self.assertFalse(on_ids & off_ids, '同時在 MENUS_ON 與 MENUS_OFF：%s' % sorted(on_ids & off_ids))
