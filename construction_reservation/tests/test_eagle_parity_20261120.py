# -*- coding: utf-8 -*-
"""回復原版（1118 會議）：預約式通報單上建立自主檢查、缺失單，不再限「未開始／施工中／停工」。

舊系統（EAGLE）的通報單狀態是下拉自己選，不拿來擋別的單據
（前端 components/resource/m_appointment/AppointmentSheet.vue）。
草稿、已退單的通報單不能掛單據是退單功能的一部分，維持。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（RS-01）。
"""
from lxml import etree

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

FORM_XMLID = 'construction_reservation.view_reservation_notification_slip_form_reservation'
CREATE_BUTTONS = ('action_create_self_inspection', 'action_create_defect_improvement')
# 2026-11-24 拿掉的欄位「改善進度 (%)」：定義在缺失的共用 mixin，一般式、預約式兩張缺失表都有
REMOVED_FIELD = 'improvement_progress'
DEFECT_MODELS = ('reservation.defect.improvement', 'general.defect.improvement')


@tagged('post_install', '-at_install', 'construction_reservation')
class TestEagleParityReservationSlip(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        project = cls.env['project.project'].create({
            'name': '回復原版預約式', 'code': 'EP-RS', 'project_type': 'reservation',
            'state': 'construction', 'company_id': cls.env.company.id})
        cls.slip = cls.env['reservation.notification.slip'].create({'project_id': project.id, 'location': '回復原版測試地點'})

    def test_closed_slip_can_open_create_forms(self):
        self.slip.sudo().write({'state': 'closed'})
        self.assertEqual(self.slip.action_create_self_inspection()['res_model'], 'reservation.self.inspection')
        self.assertEqual(self.slip.action_create_defect_improvement()['res_model'], 'reservation.defect.improvement')

    def test_draft_slip_still_refused(self):
        self.assertEqual(self.slip.state, 'draft')
        for name in CREATE_BUTTONS:
            with self.assertRaises(UserError, msg=name):
                getattr(self.slip, name)()

    def test_buttons_shown_on_closed_slip(self):
        arch = etree.fromstring(self.env.ref(FORM_XMLID).arch)
        for name in CREATE_BUTTONS:
            invisible = arch.xpath("//button[@name='%s']" % name)[0].get('invisible') or ''
            self.assertNotIn('closed', invisible, name)
            self.assertNotIn('not in', invisible, '%s 不再用「只有這幾個狀態才顯示」的寫法' % name)
            self.assertIn('draft', invisible, '%s 草稿時仍隱藏' % name)
            self.assertIn('cancelled', invisible, '%s 退單後仍隱藏' % name)


@tagged('post_install', '-at_install', 'construction_reservation')
class TestEagleParityReservationDates(TransactionCase):
    """RS-03、RS-05：自主檢查日、缺失通知日不再跟通報單起算日比；改善進度不限 0～100。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        project = env['project.project'].create({
            'name': '回復原版預約式日期', 'code': 'EP-RS-D', 'project_type': 'reservation',
            'state': 'construction', 'company_id': env.company.id})
        env['defect.improvement.prefix.config'].create({
            'project_id': project.id, 'supervision_prefix': 'EPDS', 'contractor_prefix': 'EPDC'})
        cls.slip = env['reservation.notification.slip'].create({
            'project_id': project.id, 'location': '回復原版測試地點', 'planned_start_date': '2026-06-01'})
        cls.slip.sudo().write({'state': 'in_progress'})
        cls.itype = env['self.inspection.type'].create({'name': '回復原版預約式類型'})

    def test_inspection_date_before_slip_start_allowed(self):
        insp = self.env['reservation.self.inspection'].create({
            'slip_id': self.slip.id, 'inspection_type_id': self.itype.id, 'sub_project_name': '回復原版分項',
            'inspection_date': '2026-05-01'})
        self.assertTrue(insp.exists())

    def test_defect_notification_before_slip_start_allowed(self):
        defect = self.env['reservation.defect.improvement'].create({
            'slip_id': self.slip.id, 'record_type': 'supervision', 'check_type': 'construction',
            'defect_category': 'workmanship', 'defect_description': '回復原版預約式缺失',
            'notification_date': '2026-05-01'})
        self.assertTrue(defect.exists())

    def test_improvement_progress_removed_and_reopen_still_works(self):
        """2026-11-24：「改善進度 (%)」整個拿掉（鈺鈞：用不到；原本只測它不限 0～100）。
        兩張缺失表都沒有這個欄位、資料庫也沒有這一欄；預約式缺失重新開啟照舊清掉複查資料、不報錯
        （以前重新開啟會順便把改善進度寫回 0）。"""
        for model in DEFECT_MODELS:
            if model in self.env:
                self.assertNotIn(REMOVED_FIELD, self.env[model]._fields, model)
        self.env.cr.execute(
            'SELECT table_name FROM information_schema.columns WHERE column_name = %s AND table_name IN %s',
            [REMOVED_FIELD, tuple(model.replace('.', '_') for model in DEFECT_MODELS)])
        self.assertEqual(self.env.cr.fetchall(), [], '資料庫的欄位也要刪掉')
        defect = self.env['reservation.defect.improvement'].create({
            'slip_id': self.slip.id, 'record_type': 'supervision', 'check_type': 'construction',
            'defect_category': 'workmanship', 'defect_description': '回復原版預約式缺失（重新開啟）',
            'notification_date': '2026-06-02'})
        defect.sudo().write({'state': 'closed', 'recheck_date': '2026-06-10', 'recheck_note': '複查說明'})
        defect.action_reopen()
        self.assertEqual((defect.state, defect.recheck_date, defect.recheck_note), ('improving', False, False))


@tagged('post_install', '-at_install', 'construction_reservation')
class TestEagleParitySlipDeleteChildren(TransactionCase):
    """NS-05（使用者 2026-11-20 選 B）：通報單底下還有自主檢查或缺失改善時不能刪，處理掉之後任何狀態都能刪。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        project = env['project.project'].create({
            'name': '回復原版刪通報單（單據）', 'code': 'EP-RS-DEL', 'project_type': 'reservation',
            'state': 'construction', 'company_id': env.company.id})
        env['defect.improvement.prefix.config'].create({
            'project_id': project.id, 'supervision_prefix': 'EPXS', 'contractor_prefix': 'EPXC'})
        cls.slip = env['reservation.notification.slip'].create({
            'project_id': project.id, 'location': '回復原版測試地點'})
        cls.slip.sudo().write({'state': 'closed'})
        cls.itype = env['self.inspection.type'].create({'name': '回復原版刪通報單類型'})

    def test_blocked_while_inspection_and_defect_exist(self):
        insp = self.env['reservation.self.inspection'].create({
            'slip_id': self.slip.id, 'inspection_type_id': self.itype.id, 'sub_project_name': '回復原版分項'})
        defect = self.env['reservation.defect.improvement'].create({
            'slip_id': self.slip.id, 'record_type': 'supervision', 'check_type': 'construction',
            'defect_category': 'workmanship', 'defect_description': '回復原版刪通報單缺失', 'defect_location': 'B1'})
        with self.assertRaises(UserError) as caught:
            self.slip.unlink()
        message = str(caught.exception)
        self.assertIn('自主檢查 1 筆', message)
        self.assertIn('缺失改善 1 筆', message)
        self.assertTrue(insp.exists() and defect.exists(), '被擋下時底下的單據不能已經被刪掉')

        defect.unlink()
        with self.assertRaises(UserError) as caught:
            self.slip.unlink()
        self.assertNotIn('缺失改善', str(caught.exception))
        insp.unlink()
        self.slip.unlink()                     # 已結案、底下沒有單據：可以刪（修改前只有草稿能刪）
        self.assertFalse(self.slip.exists())
