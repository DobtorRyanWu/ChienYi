"""M7 測試共用：一場大會、一場研討會、報到台使用者。"""

from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase


class MeetingCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.begin = fields.Datetime.now().replace(microsecond=0)
        cls.admin_user = cls.env['res.users'].create({
            'name': '公會管理員（M7）', 'login': 'm7_admin',
            'company_id': cls.company.id, 'company_ids': [(6, 0, cls.company.ids)],
            'groups_id': [(6, 0, [cls.env.ref('assoc_base.group_assoc_admin').id])],
        })
        cls.desk_user = cls.env['res.users'].create({
            'name': '報到台（M7）', 'login': 'm7_desk',
            'company_id': cls.company.id, 'company_ids': [(6, 0, cls.company.ids)],
            'groups_id': [(6, 0, [cls.env.ref('assoc_meeting.group_meeting_desk').id])],
        })

    @classmethod
    def new_member(cls, member_no, company=None):
        company = company or cls.company
        partner = cls.env['res.partner'].create(
            {'name': '會員 %s' % member_no, 'company_id': company.id})
        return cls.env['assoc.member'].create({
            'partner_id': partner.id, 'member_no': member_no, 'company_id': company.id,
            # M8 起 `fee_paid_until` 是算出來的，可編輯的是期初值
            'fee_paid_opening': fields.Date.today() + timedelta(days=365)})

    @classmethod
    def new_meeting(cls, name='大會', kind='assembly', **vals):
        values = {'name': name, 'kind': kind, 'company_id': cls.company.id,
                  'date_begin': cls.begin}
        if kind == 'seminar':
            values['date_end'] = cls.begin + timedelta(hours=3)
            values.setdefault('credit_points', 3)
        values.update(vals)
        return cls.env['assoc.meeting'].create(values)

    def scan(self, meeting, code, user=None):
        """模擬報到台掃一筆。"""
        return self.env['assoc.meeting.attendance'].with_user(
            user or self.desk_user)._checkin_by_code(meeting, code)

    def attendance_of(self, meeting, member):
        return self.env['assoc.meeting.attendance'].sudo().search([
            ('meeting_id', '=', meeting.id), ('member_id', '=', member.id)], limit=1)
