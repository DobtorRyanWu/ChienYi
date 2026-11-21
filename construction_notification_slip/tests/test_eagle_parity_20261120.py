# -*- coding: utf-8 -*-
"""回復原版（1118 會議）：通報單裡舊系統沒有的限制拿掉後，這些動作要做得成。

舊系統（EAGLE）的通報單每一欄離開輸入框就存，狀態是下拉自己選，沒有依狀態鎖欄位或擋動作
（前端 components/resource/m_appointment/AppointmentSheet.vue）。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（NS 開頭的編號）。
退單（新功能）之後整張唯讀的規則不動。
"""
from lxml import etree

from psycopg2 import IntegrityError

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import mute_logger

FORM_XMLID = 'construction_notification_slip.view_reservation_notification_slip_form'
# 已結案後照舊系統還能改的欄位（NS-14）
EDITABLE_AFTER_CLOSED = ('location', 'location_detail', 'latitude', 'longitude', 'detail_line_ids')


@tagged('post_install', '-at_install', 'construction_notification_slip')
class TestEagleParitySlipForm(TransactionCase):

    def test_closed_slip_fields_not_readonly_in_form(self):
        """NS-14：已結案的通報單，明細與施工地點在表單上不再唯讀；退單後照舊唯讀。"""
        arch = etree.fromstring(self.env.ref(FORM_XMLID).arch)
        for name in EDITABLE_AFTER_CLOSED:
            nodes = arch.xpath("//field[@name='%s']" % name)
            self.assertTrue(nodes, name)
            readonly = nodes[0].get('readonly') or ''
            self.assertNotIn('closed', readonly, '%s 已結案後不該唯讀' % name)
            self.assertIn('cancelled', readonly, '%s 退單後仍要唯讀' % name)
        add_button = arch.xpath("//button[@name='action_open_add_lines_wizard']")[0]
        self.assertNotIn('closed', add_button.get('invisible') or '', '已結案後「加入工項」按鈕不該消失')


@tagged('post_install', '-at_install', 'construction_notification_slip')
class TestEagleParitySlipFlow(TransactionCase):

    def _slip(self, code):
        project = self.env['project.project'].create({
            'name': '回復原版通報單 %s' % code, 'code': code, 'project_type': 'reservation',
            'state': 'construction', 'company_id': self.env.company.id})
        return self.env['reservation.notification.slip'].create({'project_id': project.id, 'location': '回復原版測試地點'})

    def test_confirm_without_detail_lines(self):
        """NS-01：沒有明細的通報單也能確認。"""
        slip = self._slip('EP-NS-1')
        self.assertFalse(slip.detail_line_ids, '前提：沒有明細')
        slip.action_confirm()
        self.assertEqual(slip.state, 'not_started')

    def test_close_without_actual_qty_or_amount(self):
        """NS-03：沒有填實際完成數量或金額也能結案。"""
        slip = self._slip('EP-NS-3')
        slip.action_confirm()
        slip.action_start()
        slip.action_close()
        self.assertEqual(slip.state, 'closed')
        self.assertTrue(slip.actual_end_date, '結案時仍要記下實際竣工日')


SECOND_SLIP_NO = 2


@tagged('post_install', '-at_install', 'construction_notification_slip')
class TestEagleParitySlipInput(TransactionCase):
    """NS-12：數量與單價正負不再檢查。NS-07（日期先後）2026-11-22 使用者決定加回。
    NS-16：工程地點不必填（2026-11-22）。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '回復原版通報單輸入值', 'code': 'EP-NS-I', 'project_type': 'reservation',
            'state': 'construction', 'company_id': cls.env.company.id})
        cls.task = cls.env['project.task'].create({
            'name': '回復原版通報單工項', 'project_id': cls.project.id, 'item_no': 'EPN-1',
            'unit': 'M', 'planned_qty': 100.0, 'unit_price': 10.0})
        cls.slip = cls.env['reservation.notification.slip'].create({
            'project_id': cls.project.id, 'location': '回復原版測試地點'})

    def test_dates_left_blank_or_in_order_accepted(self):
        """NS-07：開口契約還不知道日期時留空不擋；只填一個、或同一天也不擋。"""
        self.assertFalse(self.slip.planned_start_date or self.slip.actual_start_date, '前提：日期都還沒填')
        self.slip.write({'planned_end_date': '2026-06-01', 'actual_end_date': '2026-06-05'})
        self.env.flush_all()
        self.slip.write({'planned_start_date': '2026-06-01', 'actual_start_date': '2026-06-05'})
        self.env.flush_all()

    def test_planned_end_before_start_blocked(self):
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.slip.write({'planned_start_date': '2026-06-10', 'planned_end_date': '2026-06-01'})
            self.env.flush_all()          # 預定日期是資料庫層的 CHECK 約束，flush 才會擋

    def test_actual_end_before_start_blocked(self):
        with self.assertRaises(ValidationError):
            self.slip.write({'actual_start_date': '2026-06-10', 'actual_end_date': '2026-06-05'})

    def test_location_not_required(self):
        """NS-16：不填工程地點也能建通報單；名稱不留尾巴，確認時的通知不印 False。"""
        slip = self.env['reservation.notification.slip'].create({
            'project_id': self.project.id, 'slip_no': SECOND_SLIP_NO})    # 同工程的通報單次不可重複
        self.assertFalse(slip.location)
        self.assertEqual(slip.name, '第%s次通報單' % slip.slip_no)
        self.assertFalse(self.env['reservation.notification.slip']._fields['location'].required)

    def test_negative_line_qty_and_price_allowed(self):
        line = self.env['reservation.notification.slip.line'].create({
            'slip_id': self.slip.id, 'task_id': self.task.id, 'item_no': '1', 'unit': 'M'})
        line.write({'planned_qty': -1.0, 'actual_qty': -2.0, 'unit_price': -3.0})
        self.env.flush_all()
        self.assertEqual((line.planned_qty, line.actual_qty, line.unit_price), (-1.0, -2.0, -3.0))


@tagged('post_install', '-at_install', 'construction_notification_slip')
class TestEagleParitySlipDelete(TransactionCase):
    """NS-05（使用者 2026-11-20 選 B）：通報單任何狀態都能刪，但底下還有會被連帶刪掉的單據時擋下。

    舊系統刪通報單不看狀態，只刪通報單本身與成員名單（後端 models/schemas/project.js 的 post('remove')），
    底下的自主檢查、缺失、照片留在資料庫。新系統這三種單據的 slip_id 是 ondelete='cascade'，
    會被資料庫直接刪掉，所以有這些單據時先擋。自主檢查、缺失的案例在 construction_reservation。
    已退單的通報單保留編號、不能刪，是退單功能的一部分，維持。
    """

    def _slip(self, code, state):
        project = self.env['project.project'].create({
            'name': '回復原版刪通報單 %s' % code, 'code': code, 'project_type': 'reservation',
            'state': 'construction', 'company_id': self.env.company.id})
        slip = self.env['reservation.notification.slip'].create({
            'project_id': project.id, 'location': '回復原版測試地點'})
        if state == 'cancelled':
            slip.sudo().write({'state': state, 'cancel_reason': 'return'})   # 退單一定要有原因
        elif state != 'draft':
            slip.sudo().write({'state': state})
        return slip

    def _photo(self, slip):
        attachment = self.env['ir.attachment'].create({
            'name': 'ep-slip.png', 'raw': b'ep', 'res_model': 'supervision.photo'})
        return self.env['supervision.photo'].create({
            'project_id': slip.project_id.id, 'slip_id': slip.id, 'attachment_id': attachment.id})

    def test_any_state_without_children_can_be_deleted(self):
        # 停工要先有停工紀錄才設得成，這裡不列；刪除不看狀態，四個狀態足以代表
        for i, state in enumerate(('draft', 'not_started', 'in_progress', 'closed')):
            slip = self._slip('EP-ND-%d' % i, state)
            slip.unlink()                      # 修改前：非草稿一律「只有草稿狀態的通報單可以刪除」
            self.assertFalse(slip.exists(), state)

    def test_slip_with_photo_blocked_until_photo_removed(self):
        slip = self._slip('EP-ND-P', 'closed')
        photo = self._photo(slip)
        with self.assertRaises(UserError) as caught:
            slip.unlink()
        self.assertIn('照片 1 張', str(caught.exception))
        self.assertIn(slip.name, str(caught.exception))
        self.assertTrue(photo.exists(), '被擋下時照片不能已經被刪掉')
        photo.unlink()
        slip.unlink()
        self.assertFalse(slip.exists())

    def test_draft_slip_with_photo_blocked_too(self):
        slip = self._slip('EP-ND-DP', 'draft')
        self._photo(slip)
        with self.assertRaises(UserError):
            slip.unlink()

    def test_archived_photo_still_blocks(self):
        slip = self._slip('EP-ND-AP', 'in_progress')
        photo = self._photo(slip)
        if 'active' not in photo._fields:
            self.skipTest('照片沒有封存欄位')
        photo.active = False
        with self.assertRaises(UserError):
            slip.unlink()

    def test_slip_with_merged_in_slip_blocked_with_message(self):
        """審查員案例 1：有已退單的通報單併入本單時，要給看得懂的訊息（原本是資料庫的外鍵錯誤）。"""
        target = self._slip('EP-ND-M', 'in_progress')
        merged = self.env['reservation.notification.slip'].create({
            'project_id': target.project_id.id, 'location': '回復原版併入的通報單',
            'slip_no': target.slip_no + 1})        # 同一工程未退單的通報單次不能重複
        merged.sudo().write({'state': 'cancelled', 'cancel_reason': 'merge', 'merged_into_slip_id': target.id})
        with self.assertRaises(UserError) as caught:
            target.unlink()
        self.assertIn('併入本單的已退單通報單 1 張', str(caught.exception))
        self.assertTrue(target.exists())

    def test_slip_with_daily_log_blocked_and_link_kept(self):
        """審查員案例 2：通報單上還掛著施工日誌時擋下（原本會刪成功、日誌的通報單欄位被悄悄清空）。"""
        Log = self.env.get('daily.log.sheet')
        if Log is None or 'notification_slip_id' not in Log._fields:
            self.skipTest('沒有裝施工日誌模組')
        slip = self._slip('EP-ND-L', 'in_progress')
        employee = self.env['hr.employee'].create({'name': '回復原版刪通報單員工', 'company_id': self.env.company.id})
        log = Log.create({
            'supervision_project_id': slip.project_id.id, 'company_id': self.env.company.id,
            'employee_id': employee.id, 'log_date': '2026-11-19', 'notification_slip_id': slip.id})
        with self.assertRaises(UserError) as caught:
            slip.unlink()
        self.assertIn('施工日誌 1 筆', str(caught.exception))
        self.assertEqual(log.notification_slip_id, slip, '被擋下時日誌的通報單不能已經被清掉')
        log.notification_slip_id = False
        slip.unlink()
        self.assertFalse(slip.exists())

    def test_cancelled_slip_still_refused(self):
        slip = self._slip('EP-ND-C', 'cancelled')
        with self.assertRaises(UserError) as caught:
            slip.unlink()
        self.assertIn('已退單', str(caught.exception))
