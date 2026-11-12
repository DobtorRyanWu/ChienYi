# -*- coding: utf-8 -*-
"""期限待辦彙整（淞源 2026-11-10 會議 C5／C8）。

淞源技師：一登入就要看到今天最重要的是什麼、什麼時候要交什麼。
老闆：主管儀表板的待辦要依期限排序；快到期還沒安排就在主管的控台亮燈。

系統裡「有期限、還沒辦完」的東西散在好幾張表。這裡把它們排成同一張清單，
公司儀表板（C5）、手機首頁與每日提醒（C8）都讀這一份，不各算各的。

* 來源見 DEADLINE_SOURCES：送審管制的限定提送日、應交文件的應上傳日期、缺失的改善期限、
  公文的辦理期限、行事曆裡類型是「送件期限」的待辦事項。模型以「在不在」判斷（選裝模組沒裝就略過）。
* 期限欄位是 Datetime 的來源（行事曆）：以台灣時間換成日期再比，不是 UTC 日期。
* 以呼叫者自己的權限讀（不 sudo）：讀不到的來源略過並記在 denied，不補算、不當成 0。
* 「今天」＝台灣日期。逾期判斷每次現算，不讀各模型儲存的逾期旗標（那些要等排程重算，會過期）。
* 已封存工程的事項不列（那不是待辦）；沒掛工程的照列。指定了工程（projects）時由呼叫端決定，不另外濾。
* 清單有筆數上限時怎麼挑：快到期的（urgent＋soon）一定先列（期限近的優先），再補逾期的（從最近逾期的補起），
  最後才是還很久的。不然幾年前的逾期缺失會把清單佔滿，真正快到期的反而看不到（2026-11-13 dev 實看：
  48 筆逾期把 30 筆的清單佔滿）。顯示順序不變：期限由近到遠、逾期在最前面；件數永遠是全部。
* 燈號：逾期＝期限已過；urgent＝還剩 manager_days 天以內（預設 3）；soon＝還剩 site_days 天以內（預設 7）。
  七天／三天是老闆在會中舉的例子，所以做成參數（C8 會改讀公司設定）。
* 方法都以底線開頭：只給伺服器端程式呼叫。
"""
from datetime import datetime, time, timedelta

import pytz

from odoo import api, models

from odoo.addons.construction_supervision_base.utils.local_date import LOCAL_TZ, local_today, to_local_date

# 預設門檻（天）：到期前幾天算「快到了」（提醒現場）、前幾天算「緊急」（提醒主管、儀表板亮燈）
DEFAULT_SITE_DAYS = 7
DEFAULT_MANAGER_DAYS = 3
DEFAULT_ITEM_LIMIT = 50
TITLE_MAX_LENGTH = 60       # 清單上一筆的標題最多幾個字（缺失描述可能是一大段）

LEVEL_OVERDUE = 'overdue'
LEVEL_URGENT = 'urgent'
LEVEL_SOON = 'soon'
LEVEL_NORMAL = 'normal'
LEVELS = (LEVEL_OVERDUE, LEVEL_URGENT, LEVEL_SOON, LEVEL_NORMAL)

# 來源：key、模型、清單上的說法、到工程的欄位、期限欄位、「還沒辦完」的條件、權責人欄位（沒有就 None）、
# 標題用哪些欄位（依序接起來；沒列或都是空的就用 display_name）。
# 標題不直接用 display_name 的原因：缺失的 display_name 只有編號（看不出是什麼事）、文件與送審的帶編號前綴（太長）。
# portal_url：手機前台看這一筆的網址（%(id)s＝紀錄、%(project_id)s＝工程）；沒有手機頁的來源不給（送審管制只有後台）。
DEADLINE_SOURCES = (
    {'key': 'plan_control', 'model': 'supervision.plan.control', 'label': '送審管制',
     'project_field': 'project_id', 'date_field': 'deadline_date',
     'open_domain': [('first_submit_date', '=', False)], 'user_field': None, 'title_fields': ('name',)},
    {'key': 'document', 'model': 'supervision.document', 'label': '應交文件',
     'project_field': 'project_id', 'date_field': 'due_date',
     'open_domain': [('state', '=', 'draft')], 'user_field': None, 'title_fields': ('name',),
     'portal_url': '/construction/%(project_id)s/documents'},
    {'key': 'defect_general', 'model': 'general.defect.improvement', 'label': '缺失改善',
     'project_field': 'project_id', 'date_field': 'deadline',
     'open_domain': [('state', 'not in', ('improved', 'verified', 'closed'))], 'user_field': 'responsible_user_id',
     'title_fields': ('defect_no', 'defect_description'), 'portal_url': '/construction/defect/%(id)s'},
    {'key': 'defect_reservation', 'model': 'reservation.defect.improvement', 'label': '缺失改善',
     'project_field': 'project_id', 'date_field': 'deadline',
     'open_domain': [('state', 'not in', ('improved', 'verified', 'closed'))], 'user_field': 'responsible_user_id',
     'title_fields': ('defect_no', 'defect_description'),
     'portal_url': '/construction/defect/%(id)s?model=reservation'},
    {'key': 'official_doc', 'model': 'construction.official.doc', 'label': '公文',
     'project_field': 'project_id', 'date_field': 'reply_deadline',
     'open_domain': [('state', '=', 'pending')], 'user_field': 'responsible_user_id',
     'portal_url': '/construction/official-doc/%(id)s'},
    # 行事曆只收「送件期限」：會議、會勘是「那天要到場」，不是「那天以前要交」，放進來會把清單灌滿
    {'key': 'calendar_deadline', 'model': 'construction.calendar.event', 'label': '送件期限',
     'project_field': 'project_id', 'date_field': 'start',
     'open_domain': [('event_type', '=', 'deadline'), ('state', '=', 'planned')],
     'user_field': 'responsible_user_id', 'portal_url': '/construction/calendar'},
)
SOURCE_BY_MODEL = {source['model']: source for source in DEADLINE_SOURCES}


class ProjectProject(models.Model):
    _inherit = 'project.project'

    @api.model
    def _cy_deadline_level(self, days_left, site_days=DEFAULT_SITE_DAYS, manager_days=DEFAULT_MANAGER_DAYS):
        if days_left < 0:
            return LEVEL_OVERDUE
        if days_left <= manager_days:
            return LEVEL_URGENT
        if days_left <= site_days:
            return LEVEL_SOON
        return LEVEL_NORMAL

    @api.model
    def _cy_deadline_source_domain(self, source, projects, limited):
        """某個來源「有期限、還沒辦完」的條件；limited＝只看 projects 這些工程（空的就是什麼都沒有）。"""
        domain = [(source['date_field'], '!=', False)] + list(source['open_domain'])
        project_field = source['project_field']
        if limited:
            domain.append((project_field, 'in', projects.ids))
        else:
            # 看得到的全部：已封存工程的事項不算待辦（沒掛工程的照列）
            domain += ['|', (project_field, '=', False), (project_field + '.active', '=', True)]
        return domain

    @api.model
    def _cy_deadline_title(self, source, record):
        """清單上這一筆叫什麼：來源指定的欄位接起來（多行壓成一行、太長就截斷）；都沒有就用 display_name。"""
        parts = [' '.join(str(record[name]).split()) for name in source.get('title_fields', ()) if record[name]]
        title = ' '.join(parts) or record.display_name or ''
        return title if len(title) <= TITLE_MAX_LENGTH else title[:TITLE_MAX_LENGTH - 1] + '…'

    @api.model
    def _cy_deadline_portal_url(self, model, res_id, project_id):
        """手機前台看這一筆的網址；這個來源沒有手機頁、或網址需要工程而這筆沒掛工程 → False。"""
        template = SOURCE_BY_MODEL.get(model, {}).get('portal_url')
        if not template or ('%(project_id)s' in template and not project_id):
            return False
        return template % {'id': res_id, 'project_id': project_id}

    @api.model
    def _cy_deadline_bound(self, field, day):
        """「day 這一天的開始」換成期限欄位比得了的值：Date 欄位就是那一天；
        Datetime 欄位（資料庫存 naive UTC）是台灣那一天 00:00 的 UTC 時間。"""
        if field.type != 'datetime':
            return day
        return LOCAL_TZ.localize(datetime.combine(day, time.min)).astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def _cy_deadline_data(self, projects=None, limit=DEFAULT_ITEM_LIMIT,
                          site_days=DEFAULT_SITE_DAYS, manager_days=DEFAULT_MANAGER_DAYS):
        """期限待辦清單與各燈號的件數。

        projects：只看這些工程；None＝呼叫者看得到的全部（含沒掛工程的，例如公司共通的公文）。
        回傳 {'today', 'items': [...最多 limit 筆，期限由近到遠、逾期在最前面；超過 limit 時的挑法見檔頭],
              'counts': {'total', 'overdue', 'urgent', 'soon', 'normal'}（不受 limit 影響）,
              'denied': [讀不到的來源說法], 'site_days', 'manager_days'}
        item：source、source_label、model、res_id、title、project_id、project_name、deadline（ISO）、
              days_left（負數＝逾期幾天）、level、user_id（權責人，沒有就 False）、url（手機前台的網址，沒有就 False）
        """
        today = local_today()
        limited = projects is not None
        projects = projects if limited else self.browse()
        # 三條分界（都是「那一天的開始」）：今天、緊急的隔天、快到了的隔天——各燈號是前閉後開的區間
        day_marks = (today, today + timedelta(days=manager_days + 1), today + timedelta(days=site_days + 1))
        counts = dict.fromkeys(LEVELS, 0)
        items, denied = [], []
        for source in DEADLINE_SOURCES:
            if source['model'] not in self.env:
                continue
            Model = self.env[source['model']]
            if not Model.has_access('read'):
                if source['label'] not in denied:
                    denied.append(source['label'])
                continue
            base = self._cy_deadline_source_domain(source, projects, limited)
            date_field = source['date_field']
            field = Model._fields[date_field]
            from_today, after_urgent, after_soon = (self._cy_deadline_bound(field, day) for day in day_marks)
            counts[LEVEL_OVERDUE] += Model.search_count(base + [(date_field, '<', from_today)])
            counts[LEVEL_URGENT] += Model.search_count(
                base + [(date_field, '>=', from_today), (date_field, '<', after_urgent)])
            counts[LEVEL_SOON] += Model.search_count(
                base + [(date_field, '>=', after_urgent), (date_field, '<', after_soon)])
            counts[LEVEL_NORMAL] += Model.search_count(base + [(date_field, '>=', after_soon)])
            # 每個來源各取「還沒到期的最近 limit 筆」與「逾期的最近 limit 筆」，合起來再挑
            upcoming = Model.search(base + [(date_field, '>=', from_today)], order=f'{date_field}, id', limit=limit)
            overdue = Model.search(base + [(date_field, '<', from_today)], order=f'{date_field} desc, id desc',
                                   limit=limit)
            for record in upcoming + overdue:
                deadline = record[date_field]
                if field.type == 'datetime':
                    deadline = to_local_date(deadline)
                days_left = (deadline - today).days
                project = record[source['project_field']]
                user = record[source['user_field']] if source['user_field'] else self.env['res.users']
                items.append({
                    'source': source['key'],
                    'source_label': source['label'],
                    'model': source['model'],
                    'res_id': record.id,
                    'title': self._cy_deadline_title(source, record),
                    'project_id': project.id or False,
                    # sudo 只讀工程名稱：紀錄本身已以本人身分讀到（它所屬的工程名稱不是另一層祕密）
                    'project_name': project.sudo().name or '',
                    'deadline': deadline.isoformat(),
                    'days_left': days_left,
                    'level': self._cy_deadline_level(days_left, site_days, manager_days),
                    'user_id': user.id or False,
                    'url': self._cy_deadline_portal_url(source['model'], record.id, project.id),
                })
        def nearest_first(item):
            return (item['deadline'], item['source'], item['res_id'])

        # 超過上限時：快到期的先（期限近的優先）→ 逾期的（最近逾期的優先）→ 還很久的
        actionable = sorted((i for i in items if i['level'] in (LEVEL_URGENT, LEVEL_SOON)), key=nearest_first)
        late = sorted((i for i in items if i['level'] == LEVEL_OVERDUE), key=nearest_first, reverse=True)
        later = sorted((i for i in items if i['level'] == LEVEL_NORMAL), key=nearest_first)
        chosen = sorted((actionable + late + later)[:limit], key=nearest_first)
        counts['total'] = sum(counts[level] for level in LEVELS)
        return {
            'today': today.isoformat(),
            'items': chosen,
            'counts': counts,
            'denied': denied,
            'site_days': site_days,
            'manager_days': manager_days,
        }
