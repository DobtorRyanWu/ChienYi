# -*- coding: utf-8 -*-
"""手機行事曆頁（淞源 C7）：接下來的事項（依日期分組）、新增、改時間、標為已完成。

* 讀取以登入者自己的權限查（不 sudo）：看得到哪些由 ACL 與 security/office_rules.xml 決定。
* 新增、改時間限老闆／主管（_portal_can_manage，老闆在會中說的是「主管專用的行事曆」）；
  標為已完成：權責人本人或老闆／主管。寫入走 sudo＋守衛（前台帳號沒有寫入 ACL）。
* 時間：資料庫存 UTC；表單輸入與畫面顯示一律是台灣時間（專案慣例：不隨帳號的時區設定。
  dev 就有帳號的時區還是預設的 Europe/Brussels；後台網頁用的是瀏覽器時區，大家的瀏覽器都在台灣）。
* 獨立類別（不繼承 ConstructionPortal），理由同公文那支。
"""
import logging
from datetime import datetime, time, timedelta

from odoo import _, fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from odoo.addons.construction_supervision_base.utils.local_date import local_today

from ..models.calendar_event import (
    EVENT_TYPE_MEETING, EVENT_TYPE_SELECTION, STATE_PLANNED, TIME_FORMAT, WEEKDAY_LABELS, local_to_utc, utc_to_local,
)

_logger = logging.getLogger(__name__)

EVENT_MODEL = 'construction.calendar.event'
# 列表的範圍選項：代碼 → (顯示文字, 從今天起算幾天；None＝不設上限)
RANGE_WEEK = 'week'
RANGE_MONTH = 'month'
RANGE_ALL = 'all'
RANGES = {
    RANGE_WEEK: ('7 天內', 7),
    RANGE_MONTH: ('30 天內', 30),
    RANGE_ALL: ('全部待辦', None),
}
DEFAULT_RANGE = RANGE_MONTH
LIST_LIMIT = 200                    # 一頁最多列幾件（行事曆不分頁；超過就請縮小範圍）
DATE_FORMAT = '%Y-%m-%d'
MESSAGES = {
    'created': ('ok', '事項已新增'),
    'updated': ('ok', '時間已更新'),
    'done': ('ok', '已標為已完成'),
    'no_name': ('bad', '請填事項名稱'),
    'bad_date': ('bad', '日期或時間格式不正確'),
    'bad_user': ('bad', '權責人不在可選名單內'),
    'bad_project': ('bad', '工程不在可選名單內'),
    'invalid': ('bad', '資料不正確，沒有存檔'),
    'forbidden': ('bad', '權限不足：新增與改時間限老闆或主管'),
}


class ConstructionCalendarPortal(http.Controller):

    # ── 時區 ──────────────────────────────────────────────────────────────
    def _to_utc(self, local_naive):
        """台灣時間的日期時間（naive）→ UTC（naive，Odoo 的存法）。"""
        return local_to_utc(local_naive)

    def _to_local(self, utc_naive):
        return utc_to_local(utc_naive)

    def _parse_times(self, post):
        """表單的日期、開始時間、結束時間 → (start_utc, stop_utc, allday)。格式不對丟 ValueError。
        沒填開始時間＝整天；沒填結束時間＝交給模型帶預設長度。"""
        day = datetime.strptime((post.get('date') or '').strip(), DATE_FORMAT).date()
        start_text = (post.get('time_start') or '').strip()
        stop_text = (post.get('time_stop') or '').strip()
        if not start_text:
            start = self._to_utc(datetime.combine(day, time.min))
            return start, start, True
        start = self._to_utc(datetime.combine(day, datetime.strptime(start_text, TIME_FORMAT).time()))
        stop = (self._to_utc(datetime.combine(day, datetime.strptime(stop_text, TIME_FORMAT).time()))
                if stop_text else False)
        return start, stop, False

    # ── 可選名單 ──────────────────────────────────────────────────────────
    def _projects(self):
        """本人看得到的工程（新增事項時可掛的工程）。"""
        Project = request.env['project.project']
        return Project.search(Project._get_portal_projects_domain(request.env.user.partner_id), order='name')

    def _responsible_candidates(self, projects):
        """可指定的權責人：自己＋自己看得到的工程的成員裡「同一家公司」的人。

        事項屬於建立者的公司，別家的人就算是同一個工程的成員也看不到它，指定給他沒有意義。
        同一家＝營造方看範圍公司相同；其他帳號看主要公司相同、而且對方不是營造方。
        sudo 只讀姓名與公司（前台帳號讀不到別人的使用者紀錄）。"""
        me = request.env.user
        members = request.env['supervision.project.member'].sudo().search(
            [('project_id', 'in', projects.ids)]).user_id.filtered('active')
        if me._dash_is_contractor_side():
            scope = me.sudo().dash_scope_company_id
            same = members.filtered(lambda u: u._dash_is_contractor_side() and u.dash_scope_company_id == scope)
        else:
            company = me.sudo().company_id
            same = members.filtered(lambda u: not u._dash_is_contractor_side() and u.company_id == company)
        return (me | same).sudo().sorted('name')

    def _readable_event(self, event_id):
        try:
            return request.env[EVENT_MODEL].search([('id', '=', event_id)], limit=1)
        except AccessError:
            return request.env[EVENT_MODEL].browse()

    def _row(self, event):
        day, when = event._office_local_when()
        return {
            'event': event,
            'day': day,
            'when': when,
            # sudo 只讀權責人的姓名：事項本身已由呼叫端以本人身分讀到
            'responsible': event.sudo().responsible_user_id.name,
            'mine': event.sudo().responsible_user_id == request.env.user,
        }

    # ── 列表 ──────────────────────────────────────────────────────────────
    @http.route(['/construction/calendar'], type='http', auth='user', website=True)
    def calendar(self, **kw):
        range_key = kw.get('range') if kw.get('range') in RANGES else DEFAULT_RANGE
        mine_only = kw.get('mine') == '1'
        today_local = local_today()
        Event = request.env[EVENT_MODEL]
        # 今天起的待辦事項，加上還沒完成的過期事項（過期的排在最前面，不然會被忘掉）；條件與公司儀表板的行事曆區塊同一份
        domain = Event._office_upcoming_domain(RANGES[range_key][1])
        if mine_only:
            domain.append(('responsible_user_id', '=', request.env.uid))
        try:
            events = Event.search(domain, limit=LIST_LIMIT)
            total = Event.search_count(domain)
            no_access = False
        except AccessError:
            events, total, no_access = Event.browse(), 0, True
        groups = []
        for row in map(self._row, events):
            overdue = row['day'] < today_local
            key = '已過期未完成' if overdue else row['day'].strftime(DATE_FORMAT)
            if not groups or groups[-1]['key'] != key:
                label = key if overdue else '%s（%s）%s' % (
                    key, WEEKDAY_LABELS[row['day'].weekday()], '　今天' if row['day'] == today_local else '')
                groups.append({'key': key, 'label': label, 'overdue': overdue, 'rows': []})
            groups[-1]['rows'].append(row)
        tone, text = MESSAGES.get(kw.get('message') or kw.get('error') or '', (False, False))
        values = {
            'groups': groups,
            'event_count': total,
            'shown_count': len(events),
            'no_access': no_access,
            'ranges': [(key, label) for key, (label, _days) in RANGES.items()],
            'range_key': range_key,
            'mine_only': mine_only,
            'type_labels': dict(EVENT_TYPE_SELECTION),
            'can_manage': request.env.user._portal_can_manage(),
            'flash_tone': tone,
            'flash_text': text,
            'project': False,
            'page_name': 'construction_calendar',
        }
        return request.render('construction_office.portal_calendar', values)

    # ── 新增／改時間 ──────────────────────────────────────────────────────
    def _form_values(self, event=None, error=None):
        projects = self._projects()
        tone, text = MESSAGES.get(error or '', (False, False))
        start = self._to_local(event.start) if event else self._to_local(fields.Datetime.now())
        stop = self._to_local(event.stop) if event and event.stop else False
        timed = bool(event) and not event.allday
        return {
            'event': event,
            'projects': projects,
            'candidates': self._responsible_candidates(projects),
            'event_types': EVENT_TYPE_SELECTION,
            'default_type': event.event_type if event else EVENT_TYPE_MEETING,
            'form_date': start.strftime(DATE_FORMAT),
            'form_time_start': start.strftime(TIME_FORMAT) if timed else '',
            'form_time_stop': stop.strftime(TIME_FORMAT) if timed and stop and stop != start else '',
            'flash_tone': tone,
            'flash_text': text,
            'project': False,
            'page_name': 'construction_calendar_form',
        }

    @http.route(['/construction/calendar/new'], type='http', auth='user', website=True)
    def calendar_new(self, **kw):
        if not request.env.user._portal_can_manage():
            return request.redirect('/construction/calendar?error=forbidden')
        return request.render('construction_office.portal_calendar_form', self._form_values(error=kw.get('error')))

    @http.route(['/construction/calendar/create'], type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def calendar_create(self, **post):
        if not request.env.user._portal_can_manage():
            raise AccessError(_('權限不足：新增行事曆事項限老闆或主管'))
        back = '/construction/calendar/new'
        name = (post.get('name') or '').strip()
        if not name:
            return request.redirect(back + '?error=no_name')
        try:
            start, stop, allday = self._parse_times(post)
        except ValueError:
            return request.redirect(back + '?error=bad_date')
        projects = self._projects()
        project_id = int(post['project_id']) if (post.get('project_id') or '').isdigit() else False
        if project_id and project_id not in projects.ids:
            return request.redirect(back + '?error=bad_project')
        responsible_id = int(post['responsible_user_id']) if (post.get('responsible_user_id') or '').isdigit() \
            else request.env.uid
        if responsible_id not in self._responsible_candidates(projects).ids:
            return request.redirect(back + '?error=bad_user')
        vals = {
            'name': name,
            'start': start,
            'stop': stop,
            'allday': allday,
            'project_id': project_id,
            'responsible_user_id': responsible_id,
            'location': (post.get('location') or '').strip() or False,
            'note': (post.get('note') or '').strip() or False,
        }
        if post.get('event_type') in dict(EVENT_TYPE_SELECTION):
            vals['event_type'] = post['event_type']
        # sudo 建立：前台帳號沒有寫入 ACL。所屬公司不收表單值（營造方由模型強制成自己的範圍公司）；
        # 工程與權責人已確認在本人可選的名單內
        try:
            with request.env.cr.savepoint():
                request.env[EVENT_MODEL].sudo().create(vals)
        except (UserError, ValidationError, AccessError) as exc:
            _logger.info('前台新增行事曆事項失敗（使用者 %s）：%s', request.env.uid, exc)
            return request.redirect(back + '?error=invalid')
        return request.redirect('/construction/calendar?message=created')

    @http.route(['/construction/calendar/<int:event_id>/reschedule'], type='http', auth='user', website=True)
    def calendar_reschedule(self, event_id, **kw):
        if not request.env.user._portal_can_manage():
            return request.redirect('/construction/calendar?error=forbidden')
        event = self._readable_event(event_id)
        if not event:
            return request.redirect('/construction/calendar')
        return request.render('construction_office.portal_calendar_form',
                              self._form_values(event=event, error=kw.get('error')))

    @http.route(['/construction/calendar/<int:event_id>/update'], type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def calendar_update(self, event_id, **post):
        """改時間（只改日期與起訖時間；其他內容在後台改）。"""
        if not request.env.user._portal_can_manage():
            raise AccessError(_('權限不足：改時間限老闆或主管'))
        event = self._readable_event(event_id)
        if not event:
            return request.redirect('/construction/calendar')
        back = f'/construction/calendar/{event.id}/reschedule'
        try:
            start, stop, allday = self._parse_times(post)
        except ValueError:
            return request.redirect(back + '?error=bad_date')
        if not stop:
            # 沒填結束時間：保留原本的長度
            stop = start + ((event.stop - event.start) if event.stop and event.stop > event.start else timedelta())
        try:
            with request.env.cr.savepoint():
                event.sudo().write({'start': start, 'stop': stop, 'allday': allday})   # event 已以本人身分確認讀得到
        except (UserError, ValidationError, AccessError) as exc:
            _logger.info('前台改行事曆時間失敗（事項 %s，使用者 %s）：%s', event.id, request.env.uid, exc)
            return request.redirect(back + '?error=invalid')
        return request.redirect('/construction/calendar?message=updated')

    @http.route(['/construction/calendar/<int:event_id>/done'], type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def calendar_done(self, event_id, **post):
        event = self._readable_event(event_id)
        if not event:
            return request.redirect('/construction/calendar')
        user = request.env.user
        if not (user._portal_can_manage() or event.sudo().responsible_user_id == user):
            raise AccessError(_('權限不足：只有權責人本人或老闆／主管可以標為已完成'))
        if event.state == STATE_PLANNED:
            event.sudo().action_mark_done()     # event 已以本人身分確認讀得到
        return request.redirect('/construction/calendar?message=done')
