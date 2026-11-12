# -*- coding: utf-8 -*-
"""公司儀表板「統計圖表」頁的資料（淞源 2026-11-10 會議 C9）。

淞源技師：查核常常很趕，要馬上抓得到「總共抽查了多少」，不要再回 Excel 做圖；
老闆：把簡報常用的圓餅圖、雷達圖、柱狀圖做成一個檢視模組，點一點、選時間就好。

* get_dash_chart_catalog()：有哪些資料集（名稱、可用圖型、依哪個日期篩）。
* get_dash_chart_data(dataset, project_ids, date_from, date_to)：一個資料集的「類別 × 數列」表。
  畫面上三種圖型與下方的數字總表都讀同一份。
* 以看的人自己的權限算（不 sudo）：範圍條件沿用公司儀表板的 _dash_project_field；讀不到模型
  → status=no_access，不補算、不顯示 0（合約 §1-8）。帳號整個被預設拒絕時同樣回 no_access。
* 件數類的資料集：total＝同一組條件的 search_count 加總（測試鎖住）。
* 封存、終止工程底下的事項也算（與卡片合計相同，active_test=False）。
* 兩支方法要列在 models/method_gate.py 的 DASHBOARD_METHODS，受限帳號才叫得到。
"""
import logging
from datetime import date, timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.construction_supervision_base.utils.local_date import local_today

from .project_dashboard import (
    BLOCKED_MESSAGES, DEFECT_MODELS, PROJECT_STATE_CONSTRUCTION, STATUS_ERROR, STATUS_MESSAGES,
    STATUS_NO_ACCESS, STATUS_OK,
)

_logger = logging.getLogger(__name__)

INSPECTION_MODELS = ('general.self.inspection', 'reservation.self.inspection')
TEST_MODEL = 'supervision.test.record'
INSPECTION_STATE_DRAFT = 'draft'       # 草稿＝還沒檢查完，不算一次檢查

CHART_BAR = 'bar'
CHART_PIE = 'pie'
CHART_RADAR = 'radar'
UNIT_COUNT = '件'
UNIT_PERCENT = '%'
# 類別的角色：畫面依它上色。狀態色只用在「好／壞」有明確意義的類別，其餘一律用序列色
ROLE_SERIES = 'series'
ROLE_GOOD = 'good'
ROLE_WARNING = 'warning'
ROLE_CRITICAL = 'critical'
ROLE_NEUTRAL = 'neutral'

# 依類型／依工程這種「類別數不固定」的資料集最多列幾類，其餘併成「其他」
MAX_CHART_CATEGORIES = 10
OTHER_KEY = 'other'
OTHER_LABEL = '其他'
EMPTY_KEY = 'none'
# 每月件數沒指定期間時看最近幾個月；指定的期間太長也只取最後這幾個月（柱子多到看不清）
MONTHLY_DEFAULT_MONTHS = 12
MONTH_KEY_FORMAT = '%Y-%m'

# 自主檢查整體結果 → (顯示順序內的角色)；False＝沒有檢查項目、沒有整體結果
INSPECTION_RESULT_ROLES = (
    ('pass', ROLE_GOOD),
    ('conditional_pass', ROLE_WARNING),
    ('fail', ROLE_CRITICAL),
)
INSPECTION_RESULT_EMPTY_LABEL = '未判定'
# 檢試驗：先看結果，沒有合格／不合格的再看處理狀態
TEST_RESULT_PASS = 'pass'
TEST_RESULT_FAIL = 'fail'
TEST_CATEGORIES = (
    ('pass', '合格', ROLE_GOOD),
    ('fail', '不合格', ROLE_CRITICAL),
    ('in_progress', '檢驗中', ROLE_NEUTRAL),
    ('not_started', '尚未檢驗', ROLE_NEUTRAL),
    ('pending', '待判定', ROLE_NEUTRAL),
)
TEST_STATUS_IN_PROGRESS = 'in_progress'
TEST_STATUS_NOT_STARTED = 'not_started'

# 資料集目錄：key → 標題、可用圖型、依哪個日期欄位篩（None＝不看期間）、日期欄位的說法
# 圓餅只給「單一數列、類別是整體的一部分」的資料集
CHART_CATALOG = (
    {'key': 'inspection_type', 'label': '自主檢查次數（依檢查類型）', 'unit': UNIT_COUNT,
     'chart_types': (CHART_BAR, CHART_PIE, CHART_RADAR), 'date_label': '檢查日期'},
    {'key': 'inspection_result', 'label': '自主檢查結果', 'unit': UNIT_COUNT,
     'chart_types': (CHART_BAR, CHART_PIE), 'date_label': '檢查日期'},
    {'key': 'defect_state', 'label': '缺失改善狀態', 'unit': UNIT_COUNT,
     'chart_types': (CHART_BAR, CHART_PIE, CHART_RADAR), 'date_label': '發現日期'},
    {'key': 'test_result', 'label': '檢試驗結果', 'unit': UNIT_COUNT,
     'chart_types': (CHART_BAR, CHART_PIE), 'date_label': '實際進場日期'},
    {'key': 'monthly', 'label': '每月件數（自主檢查／缺失／檢試驗）', 'unit': UNIT_COUNT,
     'chart_types': (CHART_BAR, CHART_RADAR), 'date_label': '各自的日期'},
    {'key': 'progress', 'label': '各工程進度（預定／實際）', 'unit': UNIT_PERCENT,
     'chart_types': (CHART_BAR, CHART_RADAR), 'date_label': False},
)
CATALOG_BY_KEY = {entry['key']: entry for entry in CHART_CATALOG}
SERIES_COUNT_LABEL = '件數'
MONTHLY_SERIES = (
    ('inspection', '自主檢查'),
    ('defect', '缺失'),
    ('test', '檢試驗'),
)
PROGRESS_SERIES = (
    ('planned', '預定進度', 'dash_progress_planned'),
    ('actual', '實際進度', 'dash_progress_actual'),
)
PROGRESS_DIGITS = 2
PROGRESS_LINE_MODEL = 'progress.schedule.line'
PROGRESS_SCHEDULE_DRAFT = 'draft'
PROGRESS_SCAN_LIMIT = 40           # 各工程進度最多算幾個工程（每個都要內插整條進度曲線；超過就只取前面這些）


class ProjectProjectDashCharts(models.Model):
    _inherit = 'project.project'

    # ── 對外 ──────────────────────────────────────────────────────────────
    @api.model
    def get_dash_chart_catalog(self):
        """統計圖表頁的資料集清單（畫面的下拉選單與各資料集可用的圖型）。"""
        return [dict(entry, chart_types=list(entry['chart_types'])) for entry in CHART_CATALOG]

    @api.model
    def get_dash_chart_data(self, dataset, project_ids=None, date_from=None, date_to=None):
        """一個資料集的「類別 × 數列」表。

        project_ids：只看這些工程（看不到的自動略過）；沒給＝看得到的全部工程。
        date_from／date_to：'YYYY-MM-DD'，含頭含尾；沒給＝不限。
        回傳 {'dataset', 'label', 'unit', 'chart_types', 'date_label', 'date_from', 'date_to',
              'status'（ok／no_access／error）, 'message',
              'categories': [{'key', 'label', 'role'}],
              'series': [{'key', 'label', 'values': [各類別的值]}],
              'total'（件數類＝各值加總；百分比類為 None）,
              'note'（要讓使用者知道的說明，例：只列出一部分；沒有就 False）}
        """
        entry = CATALOG_BY_KEY.get(dataset)
        if not entry:
            raise UserError(f'不認得的統計圖表資料集：{dataset}')
        start, end = self._dash_chart_period(date_from, date_to)
        result = dict(entry, chart_types=list(entry['chart_types']), dataset=dataset,
                      date_from=fields.Date.to_string(start) if start else False,
                      date_to=fields.Date.to_string(end) if end else False,
                      status=STATUS_OK, message=False, categories=[], series=[], total=None, note=False)
        del result['key']
        blocked = self._dash_blocked_reason()
        if blocked:
            result.update(status=STATUS_NO_ACCESS, message=BLOCKED_MESSAGES[blocked])
            return result
        try:
            projects, limited = self._dash_chart_projects(project_ids)
            builder = getattr(self, '_dash_chart_' + dataset)
            result.update(builder(projects, limited, start, end))
        except AccessError:
            result.update(status=STATUS_NO_ACCESS, message=STATUS_MESSAGES[STATUS_NO_ACCESS])
        except UserError:
            raise
        except Exception:
            _logger.exception('統計圖表 %s 計算失敗', dataset)
            result.update(status=STATUS_ERROR, message=STATUS_MESSAGES[STATUS_ERROR])
        return result

    # ── 共用 ──────────────────────────────────────────────────────────────
    @api.model
    def _dash_chart_period(self, date_from, date_to):
        try:
            start = fields.Date.to_date(date_from) if date_from else None
            end = fields.Date.to_date(date_to) if date_to else None
        except (ValueError, TypeError):
            raise UserError('期間的日期格式不正確，請用 YYYY-MM-DD。')
        if start and end and start > end:
            raise UserError('期間的開始日不能晚於結束日。')
        return start, end

    @api.model
    def _dash_chart_projects(self, project_ids):
        """(看得到的指定工程, 有沒有指定)。有指定但一個都看不到 → 空的工程＋有指定＝什麼都不算，
        不能退回「全部」。"""
        ids = [int(pid) for pid in (project_ids or []) if isinstance(pid, int) and not isinstance(pid, bool)]
        if not ids:
            return self.browse(), False
        return self.with_context(active_test=False).search([('id', 'in', ids)]), True

    @api.model
    def _dash_chart_domain(self, model, projects, limited, date_field, start, end, extra=()):
        field = self._dash_project_field(model)
        domain = [(field, 'in', projects.ids)] if limited else [(field, '!=', False)]
        if date_field and start:
            domain.append((date_field, '>=', start))
        if date_field and end:
            domain.append((date_field, '<=', end))
        return domain + list(extra)

    @api.model
    def _dash_chart_model(self, model):
        """讀得到才回模型（以看的人的權限、含封存）；讀不到丟 AccessError → 整個資料集標無權限。"""
        Model = self.env[model].with_context(active_test=False)
        Model.check_access('read')
        return Model

    @api.model
    def _dash_chart_counts(self, model, domain, groupby):
        """{分組值: 件數}；Many2one 的分組值是紀錄、Selection 是值、沒有值是 False。"""
        return dict(self._dash_chart_model(model)._read_group(domain, [groupby], ['__count']))

    @api.model
    def _dash_chart_selection_labels(self, model, field_name):
        return dict(self.env[model]._fields[field_name]._description_selection(self.env))

    @api.model
    def _dash_chart_single_series(self, categories, values):
        return {
            'categories': categories,
            'series': [{'key': 'count', 'label': SERIES_COUNT_LABEL, 'values': values}],
            'total': sum(values),
        }

    # ── 各資料集 ──────────────────────────────────────────────────────────
    @api.model
    def _dash_chart_inspection_domain(self, model, projects, limited, start, end):
        return self._dash_chart_domain(model, projects, limited, 'inspection_date', start, end,
                                       [('state', '!=', INSPECTION_STATE_DRAFT)])

    @api.model
    def _dash_chart_inspection_type(self, projects, limited, start, end):
        """自主檢查次數，依檢查類型（一般式＋預約式合併；類型太多時尾巴併成「其他」）。"""
        totals = {}
        for model in INSPECTION_MODELS:
            domain = self._dash_chart_inspection_domain(model, projects, limited, start, end)
            for itype, count in self._dash_chart_counts(model, domain, 'inspection_type_id').items():
                totals[itype] = totals.get(itype, 0) + count
        ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0].display_name or '', item[0].id))
        head, tail = ranked[:MAX_CHART_CATEGORIES], ranked[MAX_CHART_CATEGORIES:]
        categories = [{'key': str(itype.id or EMPTY_KEY), 'label': itype.display_name or '未指定類型',
                       'role': ROLE_SERIES} for itype, _count in head]
        values = [count for _itype, count in head]
        if tail:
            categories.append({'key': OTHER_KEY, 'label': OTHER_LABEL, 'role': ROLE_NEUTRAL})
            values.append(sum(count for _itype, count in tail))
        return self._dash_chart_single_series(categories, values)

    @api.model
    def _dash_chart_inspection_result(self, projects, limited, start, end):
        """自主檢查結果：合格／條件合格／不合格／未判定（沒有檢查項目的沒有整體結果）。"""
        totals = {}
        for model in INSPECTION_MODELS:
            domain = self._dash_chart_inspection_domain(model, projects, limited, start, end)
            for result, count in self._dash_chart_counts(model, domain, 'overall_result').items():
                totals[result or False] = totals.get(result or False, 0) + count
        labels = self._dash_chart_selection_labels(INSPECTION_MODELS[0], 'overall_result')
        categories = [{'key': key, 'label': labels.get(key, key), 'role': role}
                      for key, role in INSPECTION_RESULT_ROLES]
        values = [totals.get(key, 0) for key, _role in INSPECTION_RESULT_ROLES]
        if totals.get(False):
            categories.append({'key': EMPTY_KEY, 'label': INSPECTION_RESULT_EMPTY_LABEL, 'role': ROLE_NEUTRAL})
            values.append(totals[False])
        return self._dash_chart_single_series(categories, values)

    @api.model
    def _dash_chart_defect_state(self, projects, limited, start, end):
        """缺失改善狀態（一般式＋預約式合併；依狀態欄位的順序列）。"""
        totals = {}
        for model in DEFECT_MODELS:
            domain = self._dash_chart_domain(model, projects, limited, 'found_date', start, end)
            for state, count in self._dash_chart_counts(model, domain, 'state').items():
                totals[state or False] = totals.get(state or False, 0) + count
        labels = self._dash_chart_selection_labels(DEFECT_MODELS[0], 'state')
        categories = [{'key': key, 'label': label, 'role': ROLE_SERIES} for key, label in labels.items()]
        values = [totals.get(key, 0) for key in labels]
        return self._dash_chart_single_series(categories, values)

    @api.model
    def _dash_chart_test_result(self, projects, limited, start, end):
        """檢試驗結果：合格／不合格；還沒有結果的再分檢驗中、尚未檢驗、待判定。"""
        domain = self._dash_chart_domain(TEST_MODEL, projects, limited, 'in_site_date', start, end)
        groups = self._dash_chart_model(TEST_MODEL)._read_group(
            domain, ['result', 'processing_status'], ['__count'])
        totals = {key: 0 for key, _label, _role in TEST_CATEGORIES}
        for result, status, count in groups:
            if result in (TEST_RESULT_PASS, TEST_RESULT_FAIL):
                totals[result] += count
            elif status in (TEST_STATUS_IN_PROGRESS, TEST_STATUS_NOT_STARTED):
                totals[status] += count
            else:
                totals['pending'] += count
        categories = [{'key': key, 'label': label, 'role': role} for key, label, role in TEST_CATEGORIES]
        return self._dash_chart_single_series(categories, [totals[key] for key, _l, _r in TEST_CATEGORIES])

    @api.model
    def _dash_chart_months(self, start, end):
        """要列的月份（每月 1 日），最多 MONTHLY_DEFAULT_MONTHS 個、取最後幾個月。"""
        last = (end or local_today()).replace(day=1)
        months = [last]
        while len(months) < MONTHLY_DEFAULT_MONTHS:
            previous = (months[-1] - timedelta(days=1)).replace(day=1)
            if start and previous < start.replace(day=1):
                break
            months.append(previous)
        return list(reversed(months))

    @api.model
    def _dash_chart_monthly(self, projects, limited, start, end):
        """每月件數：自主檢查（檢查日期）、缺失（發現日期）、檢試驗（實際進場日期）三條數列。"""
        months = self._dash_chart_months(start, end)
        # 沒指定開始日時，只算列得出來的這幾個月（否則總數會含畫面上沒有的月份）
        span_start = max(start, months[0]) if start else months[0]
        span_end = end or (months[-1] + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        sources = {
            'inspection': [(model, 'inspection_date', [('state', '!=', INSPECTION_STATE_DRAFT)])
                           for model in INSPECTION_MODELS],
            'defect': [(model, 'found_date', []) for model in DEFECT_MODELS],
            'test': [(TEST_MODEL, 'in_site_date', [])],
        }
        series = []
        for key, label in MONTHLY_SERIES:
            by_month = {}
            for model, date_field, extra in sources[key]:
                domain = self._dash_chart_domain(model, projects, limited, date_field, span_start, span_end, extra)
                counts = self._dash_chart_counts(model, domain, date_field + ':month')
                for month, count in counts.items():
                    month_start = fields.Date.to_date(month) if month else None
                    if isinstance(month_start, date):
                        by_month[month_start] = by_month.get(month_start, 0) + count
            series.append({'key': key, 'label': label, 'values': [by_month.get(month, 0) for month in months]})
        categories = [{'key': month.strftime(MONTH_KEY_FORMAT), 'label': month.strftime(MONTH_KEY_FORMAT),
                       'role': ROLE_SERIES} for month in months]
        return {'categories': categories, 'series': series,
                'total': sum(sum(item['values']) for item in series),
                'date_from': fields.Date.to_string(span_start), 'date_to': fields.Date.to_string(span_end)}

    @api.model
    def _dash_chart_progress(self, projects, limited, start, end):
        """各工程今天的預定／實際累計進度（與總覽表同一支 _dash_fill_progress）。
        只列施工中、進度表裡有數字的工程；太多時列落後最多的幾個並在 note 說明。"""
        if not self._dash_group_readable('progress'):
            raise AccessError(STATUS_MESSAGES[STATUS_NO_ACCESS])
        domain = [('state', '=', PROJECT_STATE_CONSTRUCTION), ('active', '=', True)]
        if limited:
            domain.append(('id', 'in', projects.ids))
        candidates = self.search(domain, order='name, id')
        # 先用進度明細篩出「真的有進度數字」的工程（非草稿進度表、預定或實際大於 0），再只算「進度」那一組
        # （_dash_fill_progress，總覽表同一支）。不讀 dash_* 欄位、也不逐一算全部工程：dev 165 個施工中工程
        # 只算進度就要近 10 秒，而其中今天進度不是 0 的只有十來個（舊案的進度表全是 0）。
        lines = self.env[PROGRESS_LINE_MODEL].search([
            ('schedule_id.project_id', 'in', candidates.ids), ('schedule_id.state', '!=', PROGRESS_SCHEDULE_DRAFT),
            '|', ('planned_progress', '>', 0), ('actual_progress', '>', 0)])
        with_numbers = set(lines.schedule_id.project_id.ids)
        scanned = [project for project in candidates if project.id in with_numbers][:PROGRESS_SCAN_LIMIT]
        today = local_today()
        rows = []
        for project in scanned:
            values = project._dash_fill_progress(today)[project.id]
            if values['dash_has_schedule']:
                rows.append((project, values))
        # 落後最多的排前面（主管要看的是哪裡會出問題）；同分依名稱
        rows.sort(key=lambda row: (row[1]['dash_progress_variance'], row[0].name or '', row[0].id))
        note = False
        if len(rows) > MAX_CHART_CATEGORIES or len(with_numbers) > len(scanned):
            note = '施工中有進度數字的工程共 %s 個，列出進度落後最多的 %s 個。' % (
                len(with_numbers), min(len(rows), MAX_CHART_CATEGORIES))
        rows = rows[:MAX_CHART_CATEGORIES]
        categories = [{'key': str(project.id), 'label': project.name or '', 'role': ROLE_SERIES}
                      for project, _values in rows]
        series = [{'key': key, 'label': label,
                   'values': [round(values[field_name] or 0.0, PROGRESS_DIGITS) for _project, values in rows]}
                  for key, label, field_name in PROGRESS_SERIES]
        return {'categories': categories, 'series': series, 'total': None, 'note': note}
