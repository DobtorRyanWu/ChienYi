# -*- coding: utf-8 -*-
"""開參觀帳號的精靈（淞源 C11）：指定工程、能不能看照片、能看哪幾份公文、給幾天。

按「建立」後一次做完：建帳號（只帶參觀群組）、設有效期、建授權，並把系統產生的密碼顯示一次。
密碼只存在這筆暫存紀錄上給開帳號的人抄下來（精靈紀錄會被系統定期清掉），不寫進 log。
"""
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.construction_supervision_base.utils.local_date import local_today

from ..models.visit_grant import DEFAULT_VISIT_DAYS, DOC_MODEL, MAX_VISIT_DAYS, VISITOR_GROUP

PASSWORD_LENGTH = 12
# 不含容易看錯的字（0／O、1／l／I）
PASSWORD_ALPHABET = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
STATE_DRAFT = 'draft'
STATE_DONE = 'done'


class ConstructionVisitAccountWizard(models.TransientModel):
    _name = 'construction.visit.account.wizard'
    _description = '開參觀帳號'

    state = fields.Selection([(STATE_DRAFT, '填寫'), (STATE_DONE, '已建立')], default=STATE_DRAFT, required=True)
    name = fields.Char(string='給誰用', required=True, help='例：水利局 王先生')
    login = fields.Char(string='登入帳號', required=True, help='對方登入時輸入的帳號，例：visit-wang')
    days = fields.Integer(string='可以看幾天', default=DEFAULT_VISIT_DAYS, required=True,
                          help='有效期＝今天＋這個天數；那一天結束後就進不來，帳號隨後自動停用')
    project_ids = fields.Many2many('project.project', string='可以看的工程', required=True)
    allow_photos = fields.Boolean(string='可看照片', default=True, help='上面每個工程的全部照片')
    official_doc_ids = fields.Many2many(
        DOC_MODEL, string='可看的公文', domain="[('project_id', 'in', project_ids)]",
        help='只有挑出來的公文（含附件）看得到；只能挑上面那些工程的公文')
    valid_until = fields.Date(string='可以看到', compute='_compute_valid_until')
    created_user_id = fields.Many2one('res.users', string='建立的帳號', readonly=True)
    created_password = fields.Char(string='密碼（只顯示這一次）', readonly=True)

    @api.depends('days')
    def _compute_valid_until(self):
        today = local_today()
        for wizard in self:
            wizard.valid_until = today + timedelta(days=wizard.days) if wizard.days > 0 else False

    @api.constrains('days')
    def _check_days(self):
        for wizard in self:
            if not 1 <= wizard.days <= MAX_VISIT_DAYS:
                raise ValidationError('參觀帳號的天數要在 1 到 %s 天之間。' % MAX_VISIT_DAYS)

    @api.onchange('project_ids')
    def _onchange_project_ids(self):
        self.official_doc_ids = self.official_doc_ids.filtered(lambda doc: doc.project_id in self.project_ids)

    def _generate_password(self):
        return ''.join(secrets.choice(PASSWORD_ALPHABET) for _index in range(PASSWORD_LENGTH))

    def action_create(self):
        self.ensure_one()
        if self.state != STATE_DRAFT:
            raise UserError('這個帳號已經建立了。')
        login = (self.login or '').strip()
        if not login:
            raise UserError('請填登入帳號。')
        Users = self.env['res.users'].sudo().with_context(active_test=False)
        if Users.search_count([('login', '=', login)]):
            raise UserError('登入帳號「%s」已經有人用了，請換一個。' % login)
        stray = self.official_doc_ids.filtered(lambda doc: doc.project_id not in self.project_ids)
        if stray:
            raise UserError('這些公文不屬於上面挑的工程：%s' % '、'.join(stray.mapped('subject')[:5]))
        password = self._generate_password()
        user = Users.with_context(no_reset_password=True).create({
            'name': self.name.strip(),
            'login': login,
            'password': password,
            'groups_id': [(6, 0, [self.env.ref(VISITOR_GROUP).id])],
            'company_id': self.env.company.id,
            'company_ids': [(6, 0, self.env.company.ids)],
            'portal_valid_until': self.valid_until,
        })
        self.env['construction.visit.grant'].create([{
            'user_id': user.id,
            'project_id': project.id,
            'allow_photos': self.allow_photos,
            'official_doc_ids': [(6, 0, self.official_doc_ids.filtered(lambda doc: doc.project_id == project).ids)],
        } for project in self.project_ids])
        self.write({'state': STATE_DONE, 'created_user_id': user.id, 'created_password': password})
        return {
            'type': 'ir.actions.act_window',
            'name': _('參觀帳號已建立'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
