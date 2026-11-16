# -*- coding: utf-8 -*-
"""期限提醒：到期前先提醒現場，快到期還沒辦完再提醒主管（淞源 2026-11-10 會議 C8）。

老闆：「例如七天前給現場的人通知，剩三天如果他還沒去安排，就到我們主管的控台亮紅燈」。
七天、三天是他舉的例子，所以做成公司設定（res.company.deadline_site_days／deadline_manager_days）。

每天一次的排程（_cron_send_deadline_reminders）掃 project_deadline.DEADLINE_SOURCES 的每個來源：
* 還剩 0～site_days 天、還沒辦完 → 「提醒現場」：通知權責人；沒有權責人就通知那個工程的現場人員成員。
* 還剩 0～manager_days 天、還沒辦完 → 「提醒主管」：通知那個工程的老闆／主管成員。
* 已經逾期的不再提醒（部署當天不會把幾年前的逾期缺失一次灌給大家；逾期在儀表板和手機首頁看得到）。
* 只通知「自己讀得到那一筆」的人（例：公文屬於所屬公司，同工程的另一方不會收到）。
  讀得到那一筆不等於讀得到它的工程（例：行事曆事項的權責人不是工程成員）——收件人讀不到工程時，
  內文不寫工程名稱、改寫泛稱（PROJECT_HIDDEN_LABEL）。
* 同一筆、同一階段、同一個期限只提醒一次（本表就是那張紀錄）；期限改了算新的一輪；辦完就不在清單上、不會再提醒。

只發站內通知，不寄 email：
  用 message_post 的話，前台帳號（notification_type 被核心強制是 email）會排一封外寄郵件。
  這裡直接建 mail.message＋mail.notification（inbox 型、未讀）——後台帳號在收件匣看到、
  前台帳號在通知中心看到（通知中心查的是 notified_partner_ids，不分型別），不會產生 mail.mail。
"""
import logging
from datetime import timedelta

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.construction_supervision_base.models.res_users import PORTAL_LEVEL_FIELD, PORTAL_MANAGE_LEVELS
from odoo.addons.construction_supervision_base.utils.local_date import local_today, to_local_date

from .project_deadline import DEADLINE_SOURCES

_logger = logging.getLogger(__name__)

STAGE_SITE = 'site'
STAGE_MANAGER = 'manager'
STAGE_SELECTION = [(STAGE_SITE, '提醒現場'), (STAGE_MANAGER, '提醒主管')]
REMINDER_KEEP_DAYS = 90         # 提醒紀錄留到期限過後幾天（之後清掉；那時那個期限早就不會再提醒）
MEMBER_MODEL = 'supervision.project.member'
# 收件人讀不到那個工程時，內文裡工程名稱的位置改寫這個泛稱（淞源權限審查 low #1：
# 行事曆事項的權責人不一定是工程成員——讀得到事項、讀不到工程，不能從通知看到工程名稱）
PROJECT_HIDDEN_LABEL = '某工程'


class ConstructionDeadlineReminder(models.Model):
    _name = 'construction.deadline.reminder'
    _description = '期限提醒紀錄'
    _order = 'id desc'

    res_model = fields.Char(string='來源模型', required=True, index=True)
    res_id = fields.Many2oneReference(string='來源紀錄', model_field='res_model', required=True, index=True)
    stage = fields.Selection(STAGE_SELECTION, string='階段', required=True)
    deadline = fields.Date(string='提醒當時的期限', required=True, index=True)
    notified_on = fields.Date(string='提醒日期', required=True)
    partner_ids = fields.Many2many('res.partner', string='通知了誰')
    message_id = fields.Many2one('mail.message', string='通知訊息', ondelete='set null')

    _sql_constraints = [
        ('uniq_record_stage_deadline', 'unique(res_model, res_id, stage, deadline)',
         '同一筆、同一階段、同一個期限只提醒一次'),
    ]

    # ── 門檻 ──────────────────────────────────────────────────────────────
    @api.model
    def _reminder_company(self, source, record):
        """這一筆的提醒天數看哪家公司的設定：工程的管理公司；沒掛工程就看紀錄自己的公司；都沒有用主公司。"""
        project = record[source['project_field']]
        if project.company_id:
            return project.company_id
        if 'company_id' in record._fields and record.company_id:
            return record.company_id
        return self.env.company

    # ── 通知誰 ────────────────────────────────────────────────────────────
    @api.model
    def _reminder_can_read(self, user, record):
        """user 自己讀不讀得到這一筆（ACL＋紀錄規則）。讀不到的人不通知——通知內文會帶出標題。"""
        try:
            Model = self.env[record._name].with_user(user).sudo(False).with_context(active_test=False)
            return bool(Model.search_count([('id', '=', record.id)]))
        except AccessError:
            return False

    @api.model
    def _reminder_recipients(self, source, record, stage):
        """這一筆在這個階段要通知的帳號（res.users，已濾掉停用與讀不到的人）。"""
        project = record[source['project_field']]
        members = self.env[MEMBER_MODEL].search([('project_id', '=', project.id)]).user_id if project else \
            self.env['res.users']
        if stage == STAGE_MANAGER:
            users = members.filtered(lambda u: u._portal_role_level() in PORTAL_MANAGE_LEVELS)
        else:
            responsible = record[source['user_field']] if source['user_field'] else self.env['res.users']
            users = responsible or members.filtered(lambda u: u._portal_role_level() == PORTAL_LEVEL_FIELD)
        return users.filtered(lambda u: u.active and self._reminder_can_read(u, record))

    # ── 通知內容 ──────────────────────────────────────────────────────────
    @api.model
    def _reminder_project_label(self, project, users):
        """內文裡的工程名稱：收件人每一位都讀得到這個工程才寫名稱，否則寫泛稱。
        同一則通知所有收件人看到的內文相同，所以要每一位都讀得到（以收件人本人身分查，不用排程的 sudo）。"""
        if all(self._reminder_can_read(user, project) for user in users):
            return project.name
        return PROJECT_HIDDEN_LABEL

    @api.model
    def _reminder_body(self, source, record, stage, title, deadline, days_left, users):
        project = record[source['project_field']]
        remaining = Markup('今天到期') if days_left == 0 else Markup('還剩 <b>%s</b> 天') % days_left
        tail = Markup('請安排辦理。') if stage == STAGE_SITE else Markup('目前還沒辦完，請主管留意。')
        where = Markup('（%s）') % self._reminder_project_label(project, users) if project else Markup('')
        return Markup('%s「<b>%s</b>」%s的期限是 <b>%s</b>，%s。%s') % (
            source['label'], title, where, fields.Date.to_string(deadline), remaining, tail)

    @api.model
    def _reminder_send(self, record, title, body, users):
        """建一則站內通知給 users（不經 message_post，所以不會排外寄郵件）。回傳 mail.message。"""
        root = self.env.ref('base.partner_root')
        return self.env['mail.message'].sudo().create({
            'model': record._name,
            'res_id': record.id,
            'record_name': title,
            'body': body,
            'message_type': 'notification',
            'subtype_id': self.env.ref('mail.mt_comment').id,
            'author_id': root.id,
            'email_from': root.email_formatted or False,
            'notification_ids': [(0, 0, {
                'res_partner_id': partner.id, 'notification_type': 'inbox', 'is_read': False,
            }) for partner in users.partner_id],
        })

    # ── 排程 ──────────────────────────────────────────────────────────────
    @api.model
    def _cron_send_deadline_reminders(self):
        """每天跑一次。回傳 {'site': 幾則, 'manager': 幾則}（測試與手動執行看結果用）。"""
        self = self.sudo()
        Project = self.env['project.project']
        today = local_today()
        companies = self.env['res.company'].with_context(active_test=False).search([])
        horizon = today + timedelta(days=max(companies.mapped('deadline_site_days') or [0]) + 1)
        sent = {STAGE_SITE: 0, STAGE_MANAGER: 0}
        for source in DEADLINE_SOURCES:
            if source['model'] not in self.env:
                continue
            Model = self.env[source['model']]
            date_field = source['date_field']
            field = Model._fields[date_field]
            domain = Project._cy_deadline_source_domain(source, Project.browse(), False) + [
                (date_field, '>=', Project._cy_deadline_bound(field, today)),
                (date_field, '<', Project._cy_deadline_bound(field, horizon)),
            ]
            for record in Model.search(domain, order=f'{date_field}, id'):
                deadline = record[date_field]
                if field.type == 'datetime':
                    deadline = to_local_date(deadline)
                days_left = (deadline - today).days
                company = self._reminder_company(source, record)
                stages = [stage for stage, days in ((STAGE_SITE, company.deadline_site_days),
                                                    (STAGE_MANAGER, company.deadline_manager_days))
                          if 0 <= days_left <= days]
                for stage in stages:
                    key = [('res_model', '=', record._name), ('res_id', '=', record.id), ('stage', '=', stage),
                           ('deadline', '=', deadline)]
                    if self.search_count(key):
                        continue
                    users = self._reminder_recipients(source, record, stage)
                    if not users:
                        continue        # 沒有人可通知就不記：之後加了成員還來得及提醒
                    title = Project._cy_deadline_title(source, record)
                    message = self._reminder_send(
                        record, title,
                        self._reminder_body(source, record, stage, title, deadline, days_left, users), users)
                    self.create({
                        'res_model': record._name, 'res_id': record.id, 'stage': stage, 'deadline': deadline,
                        'notified_on': today, 'partner_ids': [(6, 0, users.partner_id.ids)],
                        'message_id': message.id})
                    sent[stage] += 1
        self.search([('deadline', '<', today - timedelta(days=REMINDER_KEEP_DAYS))]).unlink()
        _logger.info('期限提醒：提醒現場 %s 則、提醒主管 %s 則', sent[STAGE_SITE], sent[STAGE_MANAGER])
        return sent
