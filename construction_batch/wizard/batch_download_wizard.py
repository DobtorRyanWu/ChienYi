# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import base64
import io
import logging
import zipfile
from datetime import datetime

from odoo import api, fields, models, Command
from odoo.exceptions import UserError, ValidationError

from odoo.addons.construction_template.utils import record_filter, template_render

from .batch_download_preview import SOURCE_FIELDS as PREVIEW_SOURCE_FIELDS

_logger = logging.getLogger(__name__)

# 可批次下載的狀態。值必須存在於各自模型的 state Selection 裡——
# 這裡曾經寫了 'done' 與 'paid' 兩個不存在的值，導致查詢永遠 0 筆。
# daily.log.sheet: draft / filled / auto_locked / locked
DAILY_LOG_DOWNLOADABLE_STATES = ('filled', 'auto_locked', 'locked')
# payment.estimate: draft / pending_approval / approved / archived
ESTIMATE_DOWNLOADABLE_STATES = ('approved', 'archived')

# 「一個工程案件產一份彙總表」的類型。樣板本身就是全案總表，沒有逐筆的概念，
# 所以工程案件必填，日期區間改由 context 傳進對照表去篩來源記錄。
# progress_schedule 例外：它的樣板刻意只帶工程名稱與工期（工項留白供手填），
# 沒有來源記錄也沒有日期概念——見 mappings/progress_schedule.py 的說明。
PROJECT_LEVEL_TYPES = ('defect', 'self_inspection', 'test', 'review', 'plan',
                       'progress_schedule')
NO_FILTER_TYPES = ('progress_schedule',)

# 「一筆記錄產一個檔」的類型。多筆時打包成 zip。
RECORD_SOURCES = {
    'daily_log': {
        'model': 'daily.log.sheet', 'date_field': 'log_date',
        'date_label': '日誌日期', 'states': DAILY_LOG_DOWNLOADABLE_STATES,
        'limit': 100, 'field': 'daily_log_ids',
    },
    'estimate': {
        'model': 'payment.estimate', 'date_field': 'estimate_date',
        'date_label': '估驗日期', 'states': ESTIMATE_DOWNLOADABLE_STATES,
        'limit': 50, 'field': 'estimate_ids',
    },
    # 進度報告沒有 state 欄位（實查 general.progress.report），不做狀態篩選
    'progress_report': {
        'model': 'general.progress.report', 'date_field': 'report_date',
        'date_label': '報告日期', 'states': None,
        'limit': 50, 'field': 'progress_report_ids',
    },
    'notification_slip': {
        'model': 'reservation.notification.slip', 'date_field': 'survey_date',
        'date_label': '工程會勘日期', 'states': None,
        'limit': 50, 'field': 'notification_slip_ids',
    },
}

# 刻意不放進下載中心的樣板類型（保留紀錄，避免日後又被「補齊」進來）：
#   material_test  —— 樣板實際上是「檢附試驗報告請機關備查」的公文函，不是報表。
#                     2026-08-10 使用者決定先移出報表/下載，待釐清用途後再議。
#                     檢試驗記錄表單上的「匯出送審函」按鈕不受影響，仍可單筆匯出。
#   acceptance_report —— 「驗收結案」App 已停用且全庫 0 筆。

# 只有一種樣板的類型，直接對應；有多種的用 *_variant 欄位讓使用者選
FIXED_TEMPLATE_TYPES = {
    'self_inspection': 'self_inspection',
    'test': 'test_control',
    'review': 'review_control',
    'plan': 'plan_control',
    'progress_report': 'progress_report',
    'progress_schedule': 'progress_schedule',
    'notification_slip': 'notification_slip',
}

# 兩個 compute 都跟著同一組篩選條件走
FILTER_DEPENDS = ('download_type', 'defect_variant', 'plan_variant', 'project_id',
                  'date_from', 'date_to', 'daily_log_ids', 'estimate_ids',
                  'progress_report_ids', 'notification_slip_ids')

# 預覽最多畫幾列（只是畫面上限，匯出仍是全部）
PREVIEW_LIMIT = 200

# 錯誤訊息與 zip 檔名用的名稱，順序同 download_type
TYPE_LABELS = {
    'notification_slip': '通報單',
    'daily_log': '施工日誌',
    'review': '送審管制表',
    'plan': '計畫書管制表',
    'self_inspection': '自主檢查',
    'defect': '缺失改善',
    'test': '檢(試)驗管制紀錄',
    'estimate': '估驗計價表',
    'progress_report': '進度報告',
    'progress_schedule': '工程預定進度表',
}


class BatchDownloadWizard(models.TransientModel):
    """報表 / 下載中心

    正式表單一律交給 construction_template 的樣板套印產生——與各單據表單
    header 上的匯出按鈕走同一條路（get_template_for_report → render），
    這裡不自行排版。施工日誌與估驗另外保留一份「清單彙總」Excel 供查詢用。
    """
    _name = 'batch.download.wizard'
    _description = '批次下載精靈'

    # === 下載類型選擇 ===
    # 順序＝畫面上 radio 的排列順序，由使用者指定（2026-08-10）：
    # 通報單／施工日誌／送審管制表／自主檢查／缺失改善／檢試驗／估驗計價／進度
    # 檢試驗與進度各有兩份文件，分別緊接在該群組後面。
    download_type = fields.Selection([
        ('notification_slip', '通報單'),
        ('daily_log', '施工日誌'),
        ('review', '送審管制表'),
        ('plan', '計畫書管制表'),
        ('self_inspection', '自主檢查'),
        ('defect', '缺失改善'),
        ('test', '檢(試)驗管制紀錄'),
        ('estimate', '估驗計價表'),
        ('progress_report', '進度報告'),
        ('progress_schedule', '工程預定進度表'),
    ], string='下載類型', required=True, default='daily_log',
       help='選擇要下載的文件類型')

    output_format = fields.Selection([
        ('template', '正式表單'),
        ('excel', '清單彙總'),
    ], string='輸出格式', default='template', required=True,
       help='正式表單＝套用樣板設定裡的空白樣板，可直接交付；'
            '清單彙總＝一列一筆的 Excel，供內部查詢統計用')

    # === 樣板變體（同一個下載類型有多份樣板時才出現） ===
    daily_log_variant = fields.Selection([
        ('daily_log_1', '監造日報表（一）'),
        ('daily_log_2', '監造日報表（二）'),
        ('daily_log_c1', '施工日誌（一）營造版'),
        ('daily_log_c2', '施工日誌（二）營造版'),
    ], string='日誌表單', default='daily_log_1')

    estimate_variant = fields.Selection([
        ('estimate_report', '估驗計價表'),
        ('invoice_detail', '估驗詳細表'),
        ('invoice_photo', '估驗照片'),
    ], string='估驗表單', default='estimate_report')

    defect_variant = fields.Selection([
        ('defect_control', '缺失改善管制表（全案彙總）'),
        ('defect_improvement', '矯正與預防處理紀錄（每筆一頁含照片）'),
    ], string='缺失表單', default='defect_control')

    # 這三張表欄位完全一樣、共用同一份空白樣板，差別只在表名與要撈哪一類記錄，
    # 所以不是選 template_type（那是 defect/daily_log 那種真的有兩份樣板的做法），
    # 而是把 supervision.plan.control 的 control_type 傳給對照表。
    plan_variant = fields.Selection([
        ('plan', '計畫書送審管制總表(含工程保險)'),
        ('sub_plan', '分項計畫送審管制總表'),
        ('drawing', '施工圖送審管制總表'),
    ], string='計畫書表單', default='plan')

    # === 日期區間篩選 ===
    date_from = fields.Date(
        string='起始日期',
        help='篩選此日期之後的記錄')

    date_to = fields.Date(
        string='截止日期',
        help='篩選此日期之前的記錄')

    # === 專案篩選 ===
    project_id = fields.Many2one(
        'project.project',
        string='工程案件',
        help='篩選特定工程案件的記錄')

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        default=lambda self: self.env.company,
        help='篩選特定公司的記錄')

    # === 目標記錄 (手動選擇) ===
    daily_log_ids = fields.Many2many(
        'daily.log.sheet',
        'batch_download_daily_log_rel',
        'wizard_id',
        'log_id',
        string='施工日誌',
        help='手動選擇要下載的施工日誌')

    estimate_ids = fields.Many2many(
        'payment.estimate',
        'batch_download_estimate_rel',
        'wizard_id',
        'estimate_id',
        string='估驗計價',
        help='手動選擇要下載的估驗計價表')

    progress_report_ids = fields.Many2many(
        'general.progress.report',
        'batch_download_progress_report_rel',
        'wizard_id',
        'report_id',
        string='進度報告',
        help='手動選擇要下載的進度報告')

    notification_slip_ids = fields.Many2many(
        'reservation.notification.slip',
        'batch_download_slip_rel',
        'wizard_id',
        'slip_id',
        string='通報單',
        help='手動選擇要下載的通報單')

    # === 下載結果 ===
    result_file = fields.Binary(
        string='下載檔案',
        readonly=True,
        attachment=False)

    result_filename = fields.Char(
        string='檔案名稱',
        readonly=True)

    # === 統計資訊 ===
    record_count = fields.Integer(
        string='記錄數量',
        compute='_compute_record_count',
        help='符合條件的記錄數量')

    undated_note = fields.Text(
        string='日期未填提醒',
        compute='_compute_undated_note',
        help='列出日期欄位空白、因此不受日期區間限制的記錄')


    state = fields.Selection([
        ('draft', '設定'),
        ('done', '完成'),
    ], string='狀態', default='draft')

    # -------------------------------------------------------------------------
    # 類型判定
    # -------------------------------------------------------------------------

    def _is_project_level(self):
        self.ensure_one()
        return self.download_type in PROJECT_LEVEL_TYPES

    def _template_type(self):
        """本次要套印的樣板類型（document.template.template_type 的值）"""
        self.ensure_one()
        variant = {
            'daily_log': self.daily_log_variant,
            'estimate': self.estimate_variant,
            'defect': self.defect_variant,
        }.get(self.download_type)
        return variant or FIXED_TEMPLATE_TYPES[self.download_type]

    def _export_context(self):
        """傳給對照表的日期區間與變體。

        對照表沒收到日期就列全部（＝表單 header 按鈕的行為）。
        plan_control_type 是計畫書管制表三張表共用一份樣板時用來指定要印哪一張，
        對照表沒收到就印計畫書（見 mappings/plan_control.py）。
        """
        self.ensure_one()
        return {
            record_filter.CTX_FROM: self.date_from,
            record_filter.CTX_TO: self.date_to,
            'plan_control_type': self.plan_variant,
        }

    def _mapping(self):
        """本次要用的對照表模組"""
        self.ensure_one()
        template_type = self._template_type()
        mapping = template_render.get_mapping(template_type)
        if mapping is None:
            raise UserError('「%s」樣板還沒有建立欄位對照表，無法自動帶入資料。'
                            % template_type)
        return mapping

    def _date_source(self):
        """本次篩選的來源模型、日期欄位、欄位中文名、基本 domain。

        專案層級由對照表宣告（source_model / DATE_FIELD / DATE_LABEL），
        記錄層級查 RECORD_SOURCES。沒有來源可篩時回 None。
        """
        self.ensure_one()
        if self.download_type in NO_FILTER_TYPES:
            return None
        if self._is_project_level():
            if not self.project_id:
                return None
            mapping = self._mapping()
            model, domain = self._project_source_domain()
            return {
                'model': model,
                'date_field': mapping.DATE_FIELD,
                'date_label': mapping.DATE_LABEL,
                'domain': domain,
                # 日期未填提醒要自己組 domain（它不看日期區間），所以額外把
                # 對照表的來源條件帶出去——否則同一個來源模型服務多張報表時
                # （計畫書／分項計畫／施工圖），提醒會把別張表的記錄也算進來
                'extra_domain': self._mapping_source_domain(mapping),
            }
        spec = RECORD_SOURCES[self.download_type]
        return dict(spec, domain=self._get_record_domain())

    # -------------------------------------------------------------------------
    # Compute Methods
    # -------------------------------------------------------------------------

    @api.depends(*FILTER_DEPENDS)
    def _compute_record_count(self):
        for wizard in self:
            try:
                wizard.record_count = wizard._count_records()
            except (KeyError, UserError):
                # 相依模組沒裝、或還沒選工程案件——不該讓整張表單開不起來
                wizard.record_count = 0

    @api.depends(*FILTER_DEPENDS)
    def _compute_undated_note(self):
        """匯出前就把「日期沒填的記錄」講清楚。

        這些記錄不會被日期區間排除（見 record_filter 的說明），但使用者有權
        在按下載之前就知道，而不是拿到檔案才發現多了幾筆或該補資料。
        """
        for wizard in self:
            try:
                wizard.undated_note = wizard._build_undated_note()
            except (KeyError, UserError):
                wizard.undated_note = False

    def _count_records(self):
        """符合目前條件的「來源記錄」筆數。

        專案層級的類型算的是彙總表裡會列出幾筆（缺失／檢查／檢試驗／送審），
        讓使用者按下載前就知道日期區間撈到多少東西。
        """
        self.ensure_one()
        if not self._is_project_level():
            selected = self[RECORD_SOURCES[self.download_type]['field']]
            if selected:
                return len(selected)
        source = self._date_source()
        if not source:
            return 0
        return self.env[source['model']].search_count(source['domain'])

    def _build_undated_note(self):
        self.ensure_one()
        if not (self.date_from or self.date_to):
            return False
        source = self._date_source()
        if not source:
            return False
        messages = record_filter.undated_warning(
            self.with_context(**self._export_context()).env,
            source['model'], source['date_field'], source['date_label'],
            project_id=self.project_id.id or None,
            extra_domain=source.get('extra_domain'))
        return '\n'.join(messages) if messages else False

    # -------------------------------------------------------------------------
    # Onchange / Constraints
    # -------------------------------------------------------------------------

    @api.onchange('download_type')
    def _onchange_download_type(self):
        """換類型時清掉已選記錄，並把不支援清單彙總的類型切回正式表單"""
        for spec in RECORD_SOURCES.values():
            self[spec['field']] = False
        if self.download_type not in ('daily_log', 'estimate'):
            self.output_format = 'template'

    @api.onchange('project_id')
    def _onchange_project_id(self):
        """當專案變更時，限制可選記錄的範圍"""
        if self.project_id:
            in_project = [('project_id', '=', self.project_id.id)]
            return {'domain': {spec['field']: in_project
                               for spec in RECORD_SOURCES.values()}}
        return {}

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        """驗證日期區間"""
        for wizard in self:
            if wizard.date_from and wizard.date_to:
                if wizard.date_from > wizard.date_to:
                    raise ValidationError('起始日期不可晚於截止日期')

    # -------------------------------------------------------------------------
    # Domain Builder Methods
    # -------------------------------------------------------------------------

    def _get_record_domain(self):
        """記錄層級類型的查詢 domain"""
        self.ensure_one()
        spec = RECORD_SOURCES[self.download_type]
        Model = self.env[spec['model']]
        domain = []

        # 公司篩選只在模型真的有這個欄位時才加。
        # payment.estimate 沒有 company_id，原本無條件 append 會直接拋
        # ValueError: Invalid field payment.estimate.company_id。
        if self.company_id and 'company_id' in Model._fields:
            domain.append(('company_id', '=', self.company_id.id))

        if self.project_id:
            domain.append(('project_id', '=', self.project_id.id))

        # 日期空白的記錄一律列入（見 record_filter 的說明），
        # 由 undated_note 在畫面上與下載時提醒使用者。
        domain += record_filter.date_domain(
            self.with_context(**self._export_context()).env, spec['date_field'])

        if spec['states']:
            domain.append(('state', 'in', spec['states']))

        return domain

    def _project_source_domain(self):
        """專案層級彙總表的「來源記錄」模型與 domain。

        來源模型與日期欄位都由對照表宣告（source_model / DATE_FIELD），
        避免這裡重複一份「一般式 vs 預約式」的判斷邏輯而日後走鐘。
        """
        self.ensure_one()
        mapping = self._mapping()
        env = self.with_context(**self._export_context()).env
        domain = ([('project_id', '=', self.project_id.id)]
                  + self._mapping_source_domain(mapping)
                  + record_filter.date_domain(env, mapping.DATE_FIELD))
        return mapping.source_model(self.project_id), domain

    def _mapping_source_domain(self, mapping):
        """對照表對來源記錄的額外條件。

        同一個來源模型服務多張報表時（計畫書／分項計畫／施工圖共用
        supervision.plan.control），對照表用 SOURCE_DOMAIN 宣告要撈哪一類；
        沒宣告的對照表就是沒有額外條件。
        """
        self.ensure_one()
        if not hasattr(mapping, 'SOURCE_DOMAIN'):
            return []
        return mapping.SOURCE_DOMAIN(self.with_context(**self._export_context()).env)

    # -------------------------------------------------------------------------
    # Action Methods
    # -------------------------------------------------------------------------

    def action_download(self):
        """執行下載"""
        self.ensure_one()

        if self._is_project_level():
            content, filename = self._download_project_summary()
        elif (self.output_format == 'excel'
                and self.download_type in ('daily_log', 'estimate')):
            # 清單彙總只有這兩種類型有，其餘一律走正式表單
            content, filename = self._download_records_as_excel()
        else:
            content, filename = self._download_records_as_templates()

        self.write({
            'state': 'done',
            'result_file': base64.b64encode(content),
            'result_filename': filename,
        })
        return self._wrap_with_warnings(self._get_download_action())

    def _wrap_with_warnings(self, action):
        """有需要提醒的事就先跳通知，再進到下載畫面。

        使用者在設定畫面已經看得到 undated_note，但那是一塊容易被略過的說明；
        真的按下下載時再跳一次 sticky 通知（要自己關掉），確保不會漏看。
        """
        self.ensure_one()
        if not self.undated_note:
            return action
        _logger.info('批次下載 %s：%s', self.download_type,
                     self.undated_note.replace('\n', ' '))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '檔案已產生，但有資料需要注意',
                'message': self.undated_note,
                'type': 'warning',
                'sticky': True,
                'next': action,
            },
        }

    def _reopen(self):
        """把精靈本身再開一次（同一筆記錄，設定全部留著）。

        **按鈕方法不能回傳 None**：web/.../action_service.js 的 doActionButton 是
            action = action && typeof action === "object"
                ? action : { type: "ir.actions.act_window_close" };
        回傳 None 會被當成 act_window_close，在對話框裡就是把精靈關掉——
        這與按鈕放在 <footer> 或表單內無關，任何 type="object" 按鈕都一樣。
        又因為 action 對話框不會堆疊（_updateUI 會先 _removeDialog()），
        也不能另開一個對話框，所以「留在原地」只能靠重開自己。
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '批次下載',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref(
                'construction_batch.batch_download_wizard_form_view').id, 'form')],
            'target': 'new',
        }

    def action_preview(self):
        """另開預覽視窗，用來源模型自己的 list view 列出會被匯出的記錄。

        為什麼要包一層 batch.download.preview 而不是直接對來源模型開 act_window：
        對話框不會堆疊（見 _reopen 的說明），直接開來源模型的 list 等於把精靈丟掉，
        而別人的 list view 上又沒地方掛「返回設定」按鈕。包一層之後，記錄本身仍是
        用 Many2many 裝著，畫面上顯示的就是該模型原本的 list view。
        """
        self.ensure_one()
        # 日期欄位名不用在這裡交代：清單是來源模型自己的 list view，欄位標題本來就有；
        # 日期區間與「日期未填提醒」也都在精靈那一頁講過了。
        records = self._preview_records()[0]
        total = len(records)

        field_name = PREVIEW_SOURCE_FIELDS.get(records._name)
        if not field_name:
            # 新增下載類型時忘了在 batch_download_preview 補欄位才會走到這裡
            raise UserError(
                '「%s」的來源模型 %s 還沒有加進預覽視窗，無法預覽。'
                % (TYPE_LABELS[self.download_type], records._name))

        note = ''
        if total > PREVIEW_LIMIT:
            note = '僅列出前 %s 筆，匯出時仍會全部列入。' % PREVIEW_LIMIT
        preview = self.env['batch.download.preview'].create({
            'wizard_id': self.id,
            'source_model': records._name,
            'summary': '共 %s 筆會列入本次匯出。' % total,
            'note': note,
            field_name: [Command.set(records[:PREVIEW_LIMIT].ids)],
        })
        return {
            'type': 'ir.actions.act_window',
            'name': '%s：預覽記錄' % TYPE_LABELS[self.download_type],
            'res_model': 'batch.download.preview',
            'res_id': preview.id,
            'view_mode': 'form',
            'views': [(self.env.ref(
                'construction_batch.batch_download_preview_form_view').id, 'form')],
            'target': 'new',
        }

    def _preview_records(self):
        """本次會列入報表的記錄，以及要一起顯示的日期欄位。

        :return: (recordset, 日期欄位名, 日期欄位中文名)
        """
        self.ensure_one()
        label = TYPE_LABELS[self.download_type]

        if self.download_type in NO_FILTER_TYPES:
            raise UserError(
                '「%s」只帶入工程名稱與預定工期（工項需自行填寫），沒有可預覽的記錄。'
                % label)

        if not self._is_project_level():
            spec = RECORD_SOURCES[self.download_type]
            selected = self[spec['field']]
            if selected:
                return selected, spec['date_field'], spec['date_label']
        elif not self.project_id:
            raise UserError('請先選擇工程案件。')

        source = self._date_source()
        if not source:
            raise UserError('目前的條件沒有可預覽的來源記錄。')
        records = self.env[source['model']].search(source['domain'])
        return records, source['date_field'], source['date_label']

    def action_reset(self):
        """重設精靈"""
        self.ensure_one()
        vals = {'state': 'draft', 'result_file': False, 'result_filename': False}
        vals.update({spec['field']: [Command.clear()]
                     for spec in RECORD_SOURCES.values()})
        self.write(vals)
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # -------------------------------------------------------------------------
    # 樣板套印（正式表單）
    # -------------------------------------------------------------------------

    def _get_template(self, template_type, project):
        """依樣板優先序取得樣板：專案專屬 > 公司預設 > 系統預設"""
        self.ensure_one()
        Template = self.env['document.template']
        template = Template.get_template_for_report(
            template_type, project_id=project.id or None)
        if not template:
            label = dict(Template._fields['template_type'].selection).get(
                template_type, template_type)
            raise UserError(
                '找不到「%s」樣板。\n請到「系統設定 > 樣板設定」確認該類型有可用的樣板。'
                % label)
        return template[:1]

    def _download_project_summary(self):
        """專案層級彙總表：一個工程案件產一份檔案"""
        self.ensure_one()
        if not self.project_id:
            raise UserError(
                '「%s」是整個工程案件的彙總表，請先選擇工程案件。'
                % TYPE_LABELS[self.download_type])

        template_type = self._template_type()
        template = self._get_template(template_type, self.project_id)
        project = self.project_id.with_context(**self._export_context())
        content, filename = template_render.render(template, project)
        template.record_usage()
        return content, filename

    def _download_records_as_templates(self):
        """記錄層級：一筆一個檔，多筆打包 zip"""
        self.ensure_one()
        records = self._get_records()
        template_type = self._template_type()

        # 樣板依專案而異（專案專屬 > 公司 > 系統），跨專案時要各查各的
        cache = {}
        used = self.env['document.template']
        rendered = []
        for record in records:
            project = record.project_id
            template = cache.get(project.id)
            if template is None:
                template = self._get_template(template_type, project)
                cache[project.id] = template
            rendered.append(template_render.render(template, record))
            used |= template
        used.record_usage()

        if len(rendered) == 1:
            return rendered[0]

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return (self._zip(rendered),
                '%s_%s.zip' % (TYPE_LABELS[self.download_type], timestamp))

    def _get_records(self):
        """取得要下載的記錄，並套用單次上限"""
        self.ensure_one()
        spec = RECORD_SOURCES[self.download_type]
        records = self[spec['field']]
        if not records:
            records = self.env[spec['model']].search(self._get_record_domain())

        label = TYPE_LABELS[self.download_type]
        if not records:
            raise UserError('沒有符合條件的%s可下載。請放寬篩選條件。' % label)
        if len(records) > spec['limit']:
            raise UserError(
                '單次下載最多 %s 筆，目前符合條件的有 %s 筆。請縮小日期區間或改用手動選取。'
                % (spec['limit'], len(records)))
        return records

    @staticmethod
    def _zip(rendered):
        """把多份 (bytes, filename) 打包。同名檔案加序號，避免互相覆蓋。"""
        output = io.BytesIO()
        seen = {}
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
            for content, filename in rendered:
                count = seen.get(filename, 0)
                seen[filename] = count + 1
                if count:
                    stem, dot, ext = filename.rpartition('.')
                    filename = ('%s_%s%s%s' % (stem, count + 1, dot, ext)
                                if dot else '%s_%s' % (filename, count + 1))
                zf.writestr(filename, content)
        output.seek(0)
        return output.getvalue()

    # -------------------------------------------------------------------------
    # 清單彙總 Excel（僅施工日誌／估驗，供內部查詢用）
    # -------------------------------------------------------------------------

    def _download_records_as_excel(self):
        self.ensure_one()
        records = self._get_records()
        if self.download_type == 'daily_log':
            return self._generate_daily_logs_excel(records)
        return self._generate_estimates_excel(records)

    @staticmethod
    def _count_man_machine(log, record_type):
        """統計日誌的人數／機具數。

        daily.log.sheet 沒有 total_worker_count / total_equipment_count 欄位
        （原本的程式直接讀，會 AttributeError），改由人機明細依 record_type 加總。
        """
        return sum(
            d.quantity or 0
            for d in log.man_machine_detail_ids
            if d.record_type == record_type
        )

    @staticmethod
    def _workbook():
        try:
            import xlsxwriter
        except ImportError:
            raise UserError(
                '系統缺少 xlsxwriter 套件，無法產生 Excel 檔案。\n'
                '請聯繫系統管理員安裝此套件。'
            )
        output = io.BytesIO()
        return output, xlsxwriter.Workbook(output, {'in_memory': True})

    def _generate_daily_logs_excel(self, logs):
        """產生施工日誌清單 Excel"""
        output, workbook = self._workbook()

        header_format = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter',
            'bg_color': '#4472C4', 'font_color': 'white', 'border': 1,
        })
        cell_format = workbook.add_format({
            'align': 'left', 'valign': 'vcenter', 'border': 1,
        })
        date_format = workbook.add_format({
            'align': 'center', 'valign': 'vcenter', 'border': 1,
            'num_format': 'yyyy-mm-dd',
        })

        worksheet = workbook.add_worksheet('施工日誌')

        # 原本有「起始日期／截止日期」兩欄，但 daily.log.sheet 是單日一張，
        # 只有 log_date，date_start / date_end 這兩個欄位根本不存在。
        headers = [
            '序號', '日誌名稱', '工程案件', '日誌日期',
            '總人機工時', '總人數', '總機具數', '狀態', '提交人', '備註'
        ]
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)

        for row, log in enumerate(logs, start=1):
            worksheet.write(row, 0, row, cell_format)
            worksheet.write(row, 1, log.complete_name or '', cell_format)
            worksheet.write(row, 2, log.project_id.name or '', cell_format)
            worksheet.write(row, 3, log.log_date, date_format)
            worksheet.write(row, 4, log.total_man_machine_hours or 0, cell_format)
            worksheet.write(row, 5, self._count_man_machine(log, 'personnel'), cell_format)
            worksheet.write(row, 6, self._count_man_machine(log, 'equipment'), cell_format)
            worksheet.write(row, 7, dict(log._fields['state'].selection).get(log.state, ''), cell_format)
            worksheet.write(row, 8, log.employee_id.name or '', cell_format)
            worksheet.write(row, 9, log.notes or '', cell_format)

        worksheet.set_column(0, 0, 6)
        worksheet.set_column(1, 1, 30)
        worksheet.set_column(2, 2, 25)
        worksheet.set_column(3, 3, 12)
        worksheet.set_column(4, 6, 10)
        worksheet.set_column(7, 7, 10)
        worksheet.set_column(8, 8, 15)
        worksheet.set_column(9, 9, 30)

        workbook.close()
        output.seek(0)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return output.getvalue(), '施工日誌清單_%s.xlsx' % timestamp

    def _generate_estimates_excel(self, estimates):
        """產生估驗計價清單 Excel（摘要表 + 每張估驗一個明細分頁）"""
        output, workbook = self._workbook()

        header_format = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter',
            'bg_color': '#4472C4', 'font_color': 'white', 'border': 1,
        })
        cell_format = workbook.add_format({
            'align': 'left', 'valign': 'vcenter', 'border': 1,
        })
        money_format = workbook.add_format({
            'align': 'right', 'valign': 'vcenter', 'border': 1,
            'num_format': '#,##0',
        })
        percent_format = workbook.add_format({
            'align': 'right', 'valign': 'vcenter', 'border': 1,
            'num_format': '0.00%',
        })

        ws_summary = workbook.add_worksheet('估驗摘要')

        # payment.estimate 只有 estimate_date / subtotal / contract_amount，
        # 原本的 period_start / period_end / cumulative_amount / contract_total /
        # completion_rate 全都不存在（讀了會 AttributeError）。
        # 完成率改由 subtotal ÷ contract_amount 現算，沒有契約金額就留白。
        headers = [
            '序號', '估驗期次', '工程案件', '估驗日期',
            '本期金額', '契約金額', '本期佔契約比', '狀態'
        ]
        for col, header in enumerate(headers):
            ws_summary.write(0, col, header, header_format)

        for row, est in enumerate(estimates, start=1):
            contract_amount = est.contract_amount or 0
            ratio = (est.subtotal or 0) / contract_amount if contract_amount else 0
            ws_summary.write(row, 0, row, cell_format)
            ws_summary.write(row, 1, est.name or '', cell_format)
            ws_summary.write(row, 2, est.project_id.name or '', cell_format)
            ws_summary.write(row, 3, str(est.estimate_date or ''), cell_format)
            ws_summary.write(row, 4, est.subtotal or 0, money_format)
            ws_summary.write(row, 5, contract_amount, money_format)
            ws_summary.write(row, 6, ratio, percent_format)
            ws_summary.write(row, 7, dict(est._fields['state'].selection).get(est.state, ''), cell_format)

        ws_summary.set_column(0, 0, 6)
        ws_summary.set_column(1, 1, 15)
        ws_summary.set_column(2, 2, 25)
        ws_summary.set_column(3, 3, 12)
        ws_summary.set_column(4, 5, 15)
        ws_summary.set_column(6, 6, 12)
        ws_summary.set_column(7, 7, 10)

        for idx, est in enumerate(estimates, start=1):
            # Excel 工作表名稱最長 31 字元且不可重複（大小寫不敏感）。
            # estimate_no 會重號（已知問題：同一專案可能有多筆相同期次），
            # 只用期次當名稱會拋 DuplicateWorksheetName，故前綴序號保證唯一。
            sheet_name = f'{idx}_第{est.estimate_no}期明細'[:31]
            ws_detail = workbook.add_worksheet(sheet_name)

            # payment.estimate.line 實際欄位：contract_qty / estimate_qty /
            # estimate_amount / approved_qty / unit_price。
            # 契約金額與完成率沒有對應欄位，改為現算。
            detail_headers = [
                '項次', '項目說明', '單位', '契約數量', '契約單價', '契約金額',
                '本期估驗數量', '本期估驗金額', '核定數量', '估驗比例'
            ]
            for col, header in enumerate(detail_headers):
                ws_detail.write(0, col, header, header_format)

            for row, line in enumerate(est.line_ids, start=1):
                contract_qty = line.contract_qty or 0
                contract_amount = contract_qty * (line.unit_price or 0)
                ratio = (line.estimate_qty or 0) / contract_qty if contract_qty else 0
                ws_detail.write(row, 0, line.item_no or '', cell_format)
                ws_detail.write(row, 1, line.description or '', cell_format)
                ws_detail.write(row, 2, line.unit or '', cell_format)
                ws_detail.write(row, 3, contract_qty, cell_format)
                ws_detail.write(row, 4, line.unit_price or 0, money_format)
                ws_detail.write(row, 5, contract_amount, money_format)
                ws_detail.write(row, 6, line.estimate_qty or 0, cell_format)
                ws_detail.write(row, 7, line.estimate_amount or 0, money_format)
                ws_detail.write(row, 8, line.approved_qty or 0, cell_format)
                ws_detail.write(row, 9, ratio, percent_format)

            ws_detail.set_column(0, 0, 8)
            ws_detail.set_column(1, 1, 30)
            ws_detail.set_column(2, 2, 8)
            ws_detail.set_column(3, 9, 12)

        workbook.close()
        output.seek(0)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return output.getvalue(), '估驗計價清單_%s.xlsx' % timestamp

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _get_download_action(self):
        """取得下載動作。

        ⚠️ `views` 一定要自己填。按鈕直接回傳的 action 會經過 web 的 clean_action()，
        它會依 view_mode 幫忙補出 views；但本方法的回傳值還會被 _wrap_with_warnings()
        塞進 display_notification 的 `params.next`，而 **next 不經過 clean_action**。
        少了 views，前端 _preprocessAction() 的 `action.views.map(...)` 就會噴
        「Cannot read properties of undefined (reading 'map')」——症狀是設了日期區間
        且有記錄日期空白時，一按下載就跳 UncaughtPromiseError（2026-08-12 實測重現）。
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref(
                'construction_batch.batch_download_wizard_result_view').id, 'form')],
            'target': 'new',
        }
