# -*- coding: utf-8 -*-
"""主管行事曆（淞源 2026-11-10 會議 C7）。

淞源技師：面板上有個行事曆，開會、會勘這類大事一收到就貼進去，在電腦上就看得到。
老闆：行事曆＋權責人＋改時間，先用手建；以後能用公文直接拖進去再說。

所以這裡只有：事項、類型、起訖時間、權責人、地點、所屬工程（可空）、來源公文（可空）、狀態。
* 不用 Odoo 原生的 calendar.event：那個會寄邀請信、有出席者與重複規則，這裡都用不到。
* 誰看得到：和公文同一套——事項屬於「所屬公司」（company_id）；營造方帳號建立的一律是自己的範圍公司。
  規則在 security/office_rules.xml；受限帳號另由 construction_company_dashboard 的 rule_scope 收窄。
* 時間存 UTC（Odoo 的 Datetime 慣例）；手機頁與公司儀表板顯示的一律是台灣時間（不隨帳號的時區設定），
  「哪一天、幾點到幾點」的說法與「幾天內」的條件都在這裡（_office_local_when、_office_upcoming_domain），兩邊共用。
"""
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

from odoo.addons.construction_supervision_base.utils.local_date import LOCAL_TZ, local_today

EVENT_TYPE_MEETING = 'meeting'
EVENT_TYPE_SITE_VISIT = 'site_visit'
EVENT_TYPE_DEADLINE = 'deadline'
EVENT_TYPE_OTHER = 'other'
EVENT_TYPE_SELECTION = [
    (EVENT_TYPE_MEETING, '會議'),
    (EVENT_TYPE_SITE_VISIT, '會勘'),
    (EVENT_TYPE_DEADLINE, '送件期限'),
    (EVENT_TYPE_OTHER, '其他'),
]
STATE_PLANNED = 'planned'
STATE_DONE = 'done'
STATE_CANCELLED = 'cancelled'
STATE_SELECTION = [
    (STATE_PLANNED, '待辦'),
    (STATE_DONE, '已完成'),
    (STATE_CANCELLED, '取消'),
]
DEFAULT_DURATION_HOURS = 1          # 沒填結束時間時預設的長度
UPCOMING_DAYS = 7                   # 「近期」＝今天起幾天內（公司儀表板的行事曆區塊；同手機頁的「7 天內」）
UPCOMING_LIMIT = 20                 # 近期清單最多列幾件（件數另外給全部）
TIME_FORMAT = '%H:%M'
DAY_LABEL_FORMAT = '%m/%d'
WEEKDAY_LABELS = ('一', '二', '三', '四', '五', '六', '日')


def utc_to_local(utc_naive):
    """資料庫的 naive UTC → 台灣時間（naive）。"""
    return pytz.utc.localize(utc_naive).astimezone(LOCAL_TZ).replace(tzinfo=None)


def local_to_utc(local_naive):
    """台灣時間（naive）→ 資料庫存的 naive UTC。"""
    return LOCAL_TZ.localize(local_naive).astimezone(pytz.utc).replace(tzinfo=None)


class ConstructionCalendarEvent(models.Model):
    _name = 'construction.calendar.event'
    _description = '行事曆事項'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start, id'

    active = fields.Boolean(string='啟用', default=True)
    name = fields.Char(string='事項', required=True, tracking=True)
    event_type = fields.Selection(
        EVENT_TYPE_SELECTION, string='類型', required=True, default=EVENT_TYPE_MEETING, index=True, tracking=True)
    start = fields.Datetime(string='開始時間', required=True, index=True, tracking=True)
    stop = fields.Datetime(
        string='結束時間', required=True, tracking=True,
        help='沒填時自動帶開始時間後 %s 小時' % DEFAULT_DURATION_HOURS)
    allday = fields.Boolean(string='整天', default=False)
    responsible_user_id = fields.Many2one(
        'res.users', string='權責人', required=True, index=True, ondelete='restrict', tracking=True,
        default=lambda self: self.env.user)
    location = fields.Char(string='地點')
    project_id = fields.Many2one(
        'project.project', string='所屬工程', index=True, ondelete='restrict', tracking=True,
        help='這件事屬於哪個工程；公司共通的事項可以不填')
    company_id = fields.Many2one(
        'res.company', string='所屬公司', required=True, index=True, ondelete='restrict',
        default=lambda self: self.env.company, tracking=True,
        help='這件事是哪一家公司的行事曆。只有這家公司的帳號看得到；營造方帳號建立的一律是它自己的公司。')
    # 只給後台帳號讀：核心讀 many2one 的名稱一律 sudo（看的是「這筆事項」讀不讀得到，不是那份公文），
    # 前台帳號看得到事項（自己負責、或是工程成員）卻看不到公文時，會經這個欄位拿到公文主旨與 id
    # （2026-11-12 權限審查的重現案例）。手機頁沒有用到這個欄位。
    official_doc_id = fields.Many2one(
        'construction.official.doc', string='來源公文', ondelete='set null', groups='base.group_user',
        help='這件事是哪一份公文交辦的（從公文按「建立行事曆事項」時自動帶入）')
    state = fields.Selection(
        STATE_SELECTION, string='狀態', required=True, default=STATE_PLANNED, index=True, tracking=True)
    note = fields.Text(string='備註')
    is_overdue = fields.Boolean(
        string='已過期未完成', compute='_compute_is_overdue', search='_search_is_overdue',
        help='待辦而且結束時間已過（不儲存：每次讀都以現在計算）')

    # ── 計算 ──────────────────────────────────────────────────────────────
    @api.depends('stop', 'state')
    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for event in self:
            event.is_overdue = bool(event.state == STATE_PLANNED and event.stop and event.stop < now)

    @api.model
    def _search_is_overdue(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise ValidationError('「已過期未完成」只能用「是／不是」篩選。')
        now = fields.Datetime.now()
        if (operator == '=') == value:
            return [('state', '=', STATE_PLANNED), ('stop', '<', now)]
        return ['|', ('state', '!=', STATE_PLANNED), ('stop', '>=', now)]

    # ── 建立／寫入 ────────────────────────────────────────────────────────
    @api.model
    def _acting_contractor_company(self):
        """目前使用者是營造方時回傳它的範圍公司（判定用 env.user，sudo 也一樣）；不是營造方回 None。"""
        user = self.env.user
        if not user._dash_is_contractor_side():
            return None
        scope = user.sudo().dash_scope_company_id
        if not scope:
            raise AccessError('帳號的範圍公司未設定，不能建立行事曆事項。')
        return scope

    @api.model_create_multi
    def create(self, vals_list):
        scope = self._acting_contractor_company()
        for vals in vals_list:
            if scope is not None:
                vals['company_id'] = scope.id       # 營造方建立的一律是自己的公司
            if vals.get('start') and not vals.get('stop'):
                vals['stop'] = fields.Datetime.to_datetime(vals['start']) + timedelta(hours=DEFAULT_DURATION_HOURS)
        return super().create(vals_list)

    def write(self, vals):
        if 'company_id' in vals and self._acting_contractor_company() is not None:
            raise AccessError('營造方帳號不能更改行事曆事項的所屬公司。')
        return super().write(vals)

    @api.constrains('start', 'stop')
    def _check_dates(self):
        for event in self:
            if event.start and event.stop and event.stop < event.start:
                raise ValidationError('結束時間不能早於開始時間。')

    # ── 顯示與近期清單（手機行事曆頁、公司儀表板共用） ────────────────────
    def _office_local_when(self):
        """(台灣日期, 時間的說法)：整天／14:30–16:00／14:30（跨日或沒有長度只寫開始時間）。"""
        self.ensure_one()
        start = utc_to_local(self.start)
        stop = utc_to_local(self.stop) if self.stop else start
        if self.allday:
            when = '整天'
        elif stop.date() == start.date() and stop != start:
            when = '%s–%s' % (start.strftime(TIME_FORMAT), stop.strftime(TIME_FORMAT))
        else:
            when = start.strftime(TIME_FORMAT)
        return start.date(), when

    @api.model
    def _office_upcoming_domain(self, days):
        """待辦，而且開始時間在「台灣今天 00:00 起算 days 天」以前——還沒完成的過期事項也算（不然會被忘掉）。
        days=None＝不設上限（全部待辦）。"""
        domain = [('state', '=', STATE_PLANNED)]
        if days is not None:
            day_start = local_to_utc(datetime.combine(local_today(), time.min))
            domain.append(('start', '<', day_start + timedelta(days=days)))
        return domain

    @api.model
    def _office_upcoming(self, days=UPCOMING_DAYS, limit=UPCOMING_LIMIT):
        """近期的待辦事項（以呼叫者自己的權限讀），由早到晚。

        回傳 {'today', 'days', 'count'（不受 limit 影響）, 'items': [{'id', 'name', 'event_type', 'type_label',
              'day'（ISO）, 'day_label'（11/14（五））, 'when', 'is_today', 'overdue', 'responsible', 'project_name',
              'location'}]}
        """
        today = local_today()
        domain = self._office_upcoming_domain(days)
        type_labels = dict(EVENT_TYPE_SELECTION)
        items = []
        for event in self.search(domain, limit=limit):
            day, when = event._office_local_when()
            items.append({
                'id': event.id,
                'name': event.name,
                'event_type': event.event_type,
                'type_label': type_labels.get(event.event_type, ''),
                'day': day.isoformat(),
                'day_label': '%s（%s）' % (day.strftime(DAY_LABEL_FORMAT), WEEKDAY_LABELS[day.weekday()]),
                'when': when,
                'is_today': day == today,
                'overdue': day < today,
                # sudo 只讀權責人姓名與工程名稱：事項本身已以本人身分讀到
                'responsible': event.sudo().responsible_user_id.name or '',
                'project_name': event.sudo().project_id.name or '',
                'location': event.location or '',
            })
        return {'today': today.isoformat(), 'days': days, 'count': self.search_count(domain), 'items': items}

    # ── 動作 ──────────────────────────────────────────────────────────────
    def action_mark_done(self):
        self.write({'state': STATE_DONE})

    def action_mark_planned(self):
        self.write({'state': STATE_PLANNED})

    def action_cancel(self):
        self.write({'state': STATE_CANCELLED})


class ConstructionOfficialDoc(models.Model):
    """公文 → 行事曆：收到公文就把要辦的事排進行事曆（老闆：「收到公文就派發」）。"""
    _inherit = 'construction.official.doc'

    calendar_event_ids = fields.One2many(
        'construction.calendar.event', 'official_doc_id', string='行事曆事項')
    calendar_event_count = fields.Integer(string='行事曆事項數', compute='_compute_calendar_event_count')

    @api.depends('calendar_event_ids')
    def _compute_calendar_event_count(self):
        for doc in self:
            doc.calendar_event_count = len(doc.calendar_event_ids)

    def action_create_calendar_event(self):
        """開「新增行事曆事項」表單，先帶入這份公文的主旨、工程、所屬公司、承辦人；有辦理期限就排在那一天。"""
        self.ensure_one()
        context = {
            'default_name': self.subject,
            'default_official_doc_id': self.id,
            'default_project_id': self.project_id.id,
            'default_company_id': self.company_id.id,
            'default_responsible_user_id': (self.responsible_user_id or self.env.user).id,
        }
        if self.reply_deadline:
            context.update(default_event_type=EVENT_TYPE_DEADLINE, default_allday=True,
                           default_start=fields.Datetime.to_string(fields.Datetime.to_datetime(self.reply_deadline)),
                           default_stop=fields.Datetime.to_string(fields.Datetime.to_datetime(self.reply_deadline)))
        return {
            'type': 'ir.actions.act_window',
            'name': '新增行事曆事項',
            'res_model': 'construction.calendar.event',
            'view_mode': 'form',
            'target': 'current',
            'context': context,
        }

    def action_view_calendar_events(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '行事曆事項',
            'res_model': 'construction.calendar.event',
            'view_mode': 'list,calendar,form',
            'domain': [('official_doc_id', '=', self.id)],
            'context': {'default_official_doc_id': self.id},
        }
