# -*- coding: utf-8 -*-
"""竣工打包精靈（淞源 2026-11-10 會議 C12）。

老闆在會中答應的是：工程做完，把這個案子的東西一次包成一包交出去（整案舊資料匯入另案處理，不在這裡）。

選一個工程 → 一個 zip：
    00_清冊與缺漏清單.xlsx     清冊（zip 裡每個檔一列，含這個檔自己）＋缺漏清單（缺了什麼）
    01_施工日誌/              每張日誌一個檔（樣板套印，和「批次下載」同一條路）
    02_估驗計價/              每期估驗一個檔
    03_管制表/                全案彙總的管制表（缺失、自主檢查、檢試驗、送審、計畫書）
    04_自主檢查表/            每張檢查紀錄一個檔
    05_文件/<分類>/           已上傳的工程文件
    06_照片/<年-月>/          工程照片

缺漏清單不是「沒有資料」的意思，是「照理該有、這包裡沒有」的東西：工作天沒有日誌、日誌或估驗還沒完成、
估驗期別跳號、檢查紀錄沒有照片、應交文件還沒上傳、某份管制表產生失敗。

原則：
* 以操作者自己的權限讀（不 sudo）；套印沿用批次下載精靈的樣板選擇（專案專屬 > 公司 > 系統預設）。
* 一份表單產生失敗不讓整包失敗：記進缺漏清單，其他照包。
* 空工程不給空的 zip：明講沒有可以打包的資料。
* 大小與份數有上限（具名常數），超過就停下來說明怎麼分批，不默默截斷。
"""
import base64
import io
import logging
import re
import zipfile
from datetime import timedelta

from openpyxl import Workbook
from openpyxl.styles import Font

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.construction_supervision_base.utils.local_date import local_today
from odoo.addons.construction_template.utils import record_filter, template_render

from .batch_download_wizard import DAILY_LOG_DOWNLOADABLE_STATES, ESTIMATE_DOWNLOADABLE_STATES

_logger = logging.getLogger(__name__)

MAX_FORMS = 300                             # 一包最多套印幾份表單（日誌＋估驗＋自主檢查表）；再多請用日期分批
MAX_PACKAGE_BYTES = 300 * 1024 * 1024       # 一包（壓縮前）最多多大；超過請取消照片或用日期分批
MAX_MISSING_WORKDAYS = 366                  # 缺漏清單最多列幾個「沒有日誌的工作天」（其餘只給總數）
BYTES_PER_KB = 1024.0
BYTES_PER_MB = 1024.0 * 1024.0
WEEKEND_START = 5                           # 沒有工作天曆可查時：週六（5）、週日（6）不算工作天

MANIFEST_NAME = '00_清冊與缺漏清單.xlsx'
FOLDER_DAILY = '01_施工日誌'
FOLDER_ESTIMATE = '02_估驗計價'
FOLDER_CONTROL = '03_管制表'
FOLDER_INSPECTION = '04_自主檢查表'
FOLDER_DOCUMENT = '05_文件'
FOLDER_PHOTO = '06_照片'
UNSAFE_NAME = re.compile(r'[\\/:*?"<>|\r\n\t]+')

# 全案彙總的管制表：(說法, 樣板類型, 傳給對照表的 context, 來源模型〔依工程類型〕, 來源的額外條件)
# 來源一筆都沒有的管制表不產（空白表沒有意義），也不算缺漏。
CONTROL_TABLES = (
    ('缺失改善管制表', 'defect_control', {},
     {'general': 'general.defect.improvement', 'reservation': 'reservation.defect.improvement'}, []),
    ('自主檢查總表', 'self_inspection', {},
     {'general': 'general.self.inspection', 'reservation': 'reservation.self.inspection'}, []),
    ('檢(試)驗管制紀錄', 'test_control', {}, {'general': 'supervision.test.record'}, []),
    ('送審管制表', 'review_control', {}, {'general': 'supervision.review.application'}, []),
    ('計畫書送審管制總表', 'plan_control', {'plan_control_type': 'plan'},
     {'general': 'supervision.plan.control'}, [('control_type', '=', 'plan')]),
    ('分項計畫送審管制總表', 'plan_control', {'plan_control_type': 'sub_plan'},
     {'general': 'supervision.plan.control'}, [('control_type', '=', 'sub_plan')]),
    ('施工圖送審管制總表', 'plan_control', {'plan_control_type': 'drawing'},
     {'general': 'supervision.plan.control'}, [('control_type', '=', 'drawing')]),
)
PROJECT_TYPE_RESERVATION = 'reservation'


def safe_name(name, fallback='未命名'):
    """檔名／資料夾名裡不能有的字換成底線（Windows 解壓縮會失敗）。"""
    cleaned = UNSAFE_NAME.sub('_', (name or '').strip()).strip('. ')
    return cleaned or fallback


class CompletionPackage:
    """打包過程的累積：zip 裡的檔、缺漏清單、目前大小。"""

    def __init__(self):
        self.entries = []           # {'folder', 'filename', 'content', 'source'}
        self.missing = []           # {'kind', 'item', 'note'}
        self.size = 0
        self._names = set()

    def add(self, folder, filename, content, source):
        filename = safe_name(filename)
        path, count = '%s/%s' % (folder, filename), 1
        while path in self._names:              # 同名檔案加序號，避免互相覆蓋
            count += 1
            stem, dot, ext = filename.rpartition('.')
            path = '%s/%s' % (folder, '%s_%s%s%s' % (stem, count, dot, ext) if dot else '%s_%s' % (filename, count))
        self._names.add(path)
        self.size += len(content)
        if self.size > MAX_PACKAGE_BYTES:
            raise UserError(
                '這一包超過 %d MB 的上限（加到「%s」時超過）。請取消勾選「照片」另外打包，或設定日期區間分批。'
                % (MAX_PACKAGE_BYTES / BYTES_PER_MB, path))
        self.entries.append({'path': path, 'folder': folder, 'filename': path.split('/')[-1], 'content': content,
                             'source': source})

    def miss(self, kind, item, note):
        self.missing.append({'kind': kind, 'item': item, 'note': note})


class CompletionPackageWizard(models.TransientModel):
    _name = 'completion.package.wizard'
    _description = '竣工打包精靈'

    state = fields.Selection([('draft', '設定'), ('done', '完成')], default='draft', required=True)
    project_id = fields.Many2one('project.project', string='工程案件', required=True)
    date_from = fields.Date(string='開始日期', help='留空＝從開工算起。資料很多、超過上限時用日期分批')
    date_to = fields.Date(string='結束日期', help='留空＝到今天（已竣工的到竣工日）')
    daily_log_variant = fields.Selection(
        selection=lambda self: self.env['batch.download.wizard']._fields['daily_log_variant'].selection,
        string='日誌表單', default='daily_log_1', required=True)
    include_daily_logs = fields.Boolean(string='施工日誌', default=True)
    include_estimates = fields.Boolean(string='估驗計價', default=True)
    include_control_tables = fields.Boolean(string='管制表（全案彙總）', default=True)
    include_inspection_forms = fields.Boolean(string='自主檢查表（每張一份）', default=True)
    include_documents = fields.Boolean(string='工程文件', default=True)
    include_photos = fields.Boolean(string='照片', default=True, help='照片通常最大；超過上限時先取消這一項另外打包')
    result_file = fields.Binary(string='檔案', readonly=True, attachment=True)
    result_filename = fields.Char(string='檔名', readonly=True)
    file_count = fields.Integer(string='檔案數', readonly=True)
    missing_count = fields.Integer(string='缺漏項目數', readonly=True)
    result_note = fields.Text(string='說明', readonly=True)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise UserError('開始日期不能晚於結束日期。')

    # ── 共用 ──────────────────────────────────────────────────────────────
    def _period(self):
        """這次打包看的日期區間（兩端都可能是 False＝不限）。"""
        self.ensure_one()
        return self.date_from, self.date_to

    def _date_domain(self, date_field):
        date_from, date_to = self._period()
        domain = []
        if date_from:
            domain.append((date_field, '>=', date_from))
        if date_to:
            domain.append((date_field, '<=', date_to))
        return domain

    def _project_ctx(self, **extra):
        """給對照表的 context：日期區間（彙總表依它篩來源記錄）＋個別表的參數。"""
        date_from, date_to = self._period()
        return dict({record_filter.CTX_FROM: date_from or False, record_filter.CTX_TO: date_to or False}, **extra)

    def _template(self, template_type):
        template = self.env['document.template'].get_template_for_report(
            template_type, project_id=self.project_id.id)
        if not template:
            label = dict(self.env['document.template']._fields['template_type'].selection).get(
                template_type, template_type)
            raise UserError('找不到「%s」樣板' % label)
        return template[:1]

    def _inspection_model(self):
        return ('reservation.self.inspection' if self.project_id.project_type == PROJECT_TYPE_RESERVATION
                else 'general.self.inspection')

    # ── 各分類 ────────────────────────────────────────────────────────────
    def _collect_daily_logs(self, package):
        Log = self.env['daily.log.sheet']
        logs = Log.search([('project_id', '=', self.project_id.id)] + self._date_domain('log_date'), order='log_date, id')
        done = logs.filtered(lambda log: log.state in DAILY_LOG_DOWNLOADABLE_STATES)
        for log in logs - done:
            package.miss('施工日誌', fields.Date.to_string(log.log_date), '日誌還沒完成（草稿），沒有納入')
        template = self._template(self.daily_log_variant) if done else None
        for log in done:
            try:
                content, filename = template_render.render(template, log)
            except UserError as exc:
                package.miss('施工日誌', fields.Date.to_string(log.log_date), '產生失敗：%s' % exc.args[0])
                continue
            package.add(FOLDER_DAILY, filename, content, '日誌 %s' % fields.Date.to_string(log.log_date))
        self._missing_workdays(package, set(logs.mapped('log_date')))

    def _missing_workdays(self, package, logged_days):
        """區間內沒有日誌的工作天。工作天：有公司儀表板的工作天曆就用它（國定假日、補班、工程的例假日），
        沒有或算不出來就用週一到週五，並在清單上註明。"""
        project = self.project_id
        start = self.date_from or project.actual_start_date or project.contract_start_date
        end = min(self.date_to or project.actual_end_date or local_today(), local_today())
        if not start:
            package.miss('施工日誌', '（整個工程）', '工程沒有開工日期，無法檢查哪些工作天沒有日誌')
            return
        if start > end:
            return
        by_calendar = hasattr(project, '_dash_is_workday')
        missing, day = [], start
        while day <= end:
            if day not in logged_days:
                try:
                    workday = project._dash_is_workday(day) if by_calendar else day.weekday() < WEEKEND_START
                except Exception:
                    by_calendar, workday = False, day.weekday() < WEEKEND_START
                if workday:
                    missing.append(day)
            day += timedelta(days=1)
        basis = '' if by_calendar else '（工作天依週一到週五估算）'
        for day in missing[:MAX_MISSING_WORKDAYS]:
            package.miss('施工日誌', fields.Date.to_string(day), '工作天沒有日誌' + basis)
        if len(missing) > MAX_MISSING_WORKDAYS:
            package.miss('施工日誌', '（其餘 %s 天）' % (len(missing) - MAX_MISSING_WORKDAYS),
                         '沒有日誌的工作天共 %s 天，清單只列前 %s 天' % (len(missing), MAX_MISSING_WORKDAYS))

    def _collect_estimates(self, package):
        Estimate = self.env['payment.estimate']
        every = Estimate.search([('project_id', '=', self.project_id.id)], order='estimate_no, id')
        numbers = set(every.mapped('estimate_no'))
        if numbers and not self.date_from and not self.date_to:
            for number in range(1, max(numbers) + 1):
                if number not in numbers:
                    package.miss('估驗計價', '第 %s 期' % number, '期別跳號：系統裡沒有這一期')
        estimates = every.filtered_domain(self._date_domain('estimate_date')) if (self.date_from or self.date_to) else every
        done = estimates.filtered(lambda est: est.state in ESTIMATE_DOWNLOADABLE_STATES)
        state_labels = dict(Estimate._fields['state'].selection)
        for estimate in estimates - done:
            package.miss('估驗計價', '第 %s 期' % estimate.estimate_no,
                         '還沒核定（%s），沒有納入' % state_labels.get(estimate.state, estimate.state))
        template = self._template('estimate_report') if done else None
        for estimate in done:
            try:
                content, filename = template_render.render(template, estimate)
            except UserError as exc:
                package.miss('估驗計價', '第 %s 期' % estimate.estimate_no, '產生失敗：%s' % exc.args[0])
                continue
            package.add(FOLDER_ESTIMATE, filename, content, '第 %s 期估驗' % estimate.estimate_no)

    def _collect_control_tables(self, package):
        project_type = (PROJECT_TYPE_RESERVATION if self.project_id.project_type == PROJECT_TYPE_RESERVATION
                        else 'general')
        for label, template_type, extra_ctx, models_by_type, extra_domain in CONTROL_TABLES:
            model = models_by_type.get(project_type) or models_by_type['general']
            if model not in self.env or not self.env[model].has_access('read'):
                continue
            if not self.env[model].search_count([('project_id', '=', self.project_id.id)] + extra_domain):
                continue                    # 沒有來源資料：不產空白表
            try:
                project = self.project_id.with_context(**self._project_ctx(**extra_ctx))
                content, filename = template_render.render(self._template(template_type), project)
            except UserError as exc:
                package.miss('管制表', label, '產生失敗：%s' % exc.args[0])
                continue
            extension = filename.rpartition('.')[2]
            package.add(FOLDER_CONTROL, '%s.%s' % (label, extension), content, label)

    def _collect_inspection_forms(self, package):
        Inspection = self.env[self._inspection_model()]
        inspections = Inspection.search(
            [('project_id', '=', self.project_id.id)] + self._date_domain('inspection_date'),
            order='inspection_date, id')
        for inspection in inspections:
            label = '%s %s' % (fields.Date.to_string(inspection.inspection_date) if inspection.inspection_date else '',
                               inspection.display_name or '')
            if inspection.state == 'draft':
                package.miss('自主檢查', label.strip(), '檢查還沒完成（草稿），沒有納入')
                continue
            if not inspection.photo_ids:
                package.miss('自主檢查', label.strip(), '這張檢查沒有照片')
            try:
                content, filename = inspection.render_inspection_form()
            except UserError as exc:
                package.miss('自主檢查', label.strip(), '產生失敗：%s' % exc.args[0])
                continue
            package.add(FOLDER_INSPECTION, filename, content, '自主檢查 %s' % label.strip())

    def _collect_documents(self, package):
        Document = self.env['supervision.document']
        documents = Document.search([('project_id', '=', self.project_id.id)], order='document_category_id, id')
        for document in documents:
            if document.state == 'draft':
                due = '（應上傳日期 %s）' % fields.Date.to_string(document.due_date) if document.due_date else ''
                package.miss('工程文件', document.name, '應交文件還沒上傳' + due)
                continue
            attachments = document.current_attachment_ids
            if not attachments:
                package.miss('工程文件', document.name, '文件沒有附檔')
                continue
            folder = '%s/%s' % (FOLDER_DOCUMENT, safe_name(document.document_category_id.name, '未分類'))
            for attachment in attachments:
                package.add(folder, attachment.name or document.name, attachment.raw or b'', '文件：%s' % document.name)

    def _collect_photos(self, package):
        if 'supervision.photo' not in self.env:
            return                      # 照片模組沒裝
        Photo = self.env['supervision.photo']
        photos = Photo.search([('project_id', '=', self.project_id.id)] + self._date_domain('shot_date'),
                              order='shot_date, id')
        for photo in photos:
            attachment = photo.attachment_id
            day = photo.shot_date
            folder = '%s/%s' % (FOLDER_PHOTO, day.strftime('%Y-%m') if day else '日期不明')
            stem = '%s_%s' % (fields.Date.to_string(day) if day else '日期不明', photo.id)
            extension = (attachment.name or '').rpartition('.')[2] if '.' in (attachment.name or '') else 'jpg'
            package.add(folder, '%s.%s' % (stem, extension), attachment.raw or b'',
                        '照片 %s%s' % (fields.Date.to_string(day) if day else '', ' ' + photo.name if photo.name else ''))

    # ── 份數上限、清冊 ────────────────────────────────────────────────────
    def _check_form_limit(self):
        """套印的份數先數過：超過上限就不開始（每一份都要開樣板填資料，幾百份會跑很久）。"""
        pid = self.project_id.id
        counts = {}
        if self.include_daily_logs:
            counts['施工日誌'] = self.env['daily.log.sheet'].search_count(
                [('project_id', '=', pid), ('state', 'in', DAILY_LOG_DOWNLOADABLE_STATES)] + self._date_domain('log_date'))
        if self.include_estimates:
            counts['估驗計價'] = self.env['payment.estimate'].search_count(
                [('project_id', '=', pid), ('state', 'in', ESTIMATE_DOWNLOADABLE_STATES)]
                + self._date_domain('estimate_date'))
        if self.include_inspection_forms:
            counts['自主檢查表'] = self.env[self._inspection_model()].search_count(
                [('project_id', '=', pid), ('state', '!=', 'draft')] + self._date_domain('inspection_date'))
        total = sum(counts.values())
        if total > MAX_FORMS:
            detail = '、'.join('%s %s 份' % (label, count) for label, count in counts.items())
            raise UserError(
                '這個範圍要套印 %s 份表單（%s），超過一包 %s 份的上限。\n'
                '請設定開始／結束日期分批打包，或先取消勾選份數最多的那一類。' % (total, detail, MAX_FORMS))

    def _build_manifest(self, package, generated_at):
        """清冊與缺漏清單（xlsx）。清冊每個檔一列，最後一列是這個檔自己——列數＝zip 裡的檔案數。"""
        workbook = Workbook()
        bold = Font(bold=True)
        sheet = workbook.active
        sheet.title = '清冊'
        date_from, date_to = self._period()
        sheet.append(['工程', self.project_id.display_name])
        sheet.append(['日期區間', '%s ～ %s' % (date_from or '開工', date_to or '今天')])
        sheet.append(['產生時間', generated_at])
        sheet.append(['檔案數', len(package.entries) + 1, '缺漏項目數', len(package.missing)])
        sheet.append([])
        sheet.append(['序號', '資料夾', '檔名', '來源', '大小（KB）'])
        for cell in sheet[sheet.max_row]:
            cell.font = bold
        for index, entry in enumerate(package.entries, start=1):
            sheet.append([index, entry['path'].rpartition('/')[0], entry['filename'], entry['source'],
                          round(len(entry['content']) / BYTES_PER_KB, 1)])
        sheet.append([len(package.entries) + 1, '', MANIFEST_NAME, '清冊與缺漏清單（本檔）', ''])
        for column, width in (('A', 8), ('B', 26), ('C', 48), ('D', 44), ('E', 12)):
            sheet.column_dimensions[column].width = width

        missing = workbook.create_sheet('缺漏清單')
        missing.append(['類別', '項目', '說明'])
        for cell in missing[1]:
            cell.font = bold
        for row in package.missing:
            missing.append([row['kind'], row['item'], row['note']])
        if not package.missing:
            missing.append(['', '（沒有發現缺漏）', ''])
        for column, width in (('A', 14), ('B', 44), ('C', 60)):
            missing.column_dimensions[column].width = width
        output = io.BytesIO()
        workbook.save(output)
        return output.getvalue()

    # ── 動作 ──────────────────────────────────────────────────────────────
    def _collect(self):
        """依勾選的分類收集檔案與缺漏。回傳 CompletionPackage。"""
        self.ensure_one()
        self._check_form_limit()
        package = CompletionPackage()
        for included, collector in (
                (self.include_daily_logs, self._collect_daily_logs),
                (self.include_estimates, self._collect_estimates),
                (self.include_control_tables, self._collect_control_tables),
                (self.include_inspection_forms, self._collect_inspection_forms),
                (self.include_documents, self._collect_documents),
                (self.include_photos, self._collect_photos)):
            if included:
                collector(package)
        return package

    def action_build(self):
        self.ensure_one()
        if not any((self.include_daily_logs, self.include_estimates, self.include_control_tables,
                    self.include_inspection_forms, self.include_documents, self.include_photos)):
            raise UserError('請至少勾選一類要打包的資料。')
        package = self._collect()
        if not package.entries:
            raise UserError(
                '「%s」在所選的範圍內沒有任何可以打包的資料（沒有已完成的日誌、已核定的估驗、檢查紀錄、文件或照片），'
                '所以沒有產生檔案。' % self.project_id.display_name)
        generated_at = fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.now()))
        manifest = self._build_manifest(package, generated_at)
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_NAME, manifest)
            for entry in package.entries:
                archive.writestr(entry['path'], entry['content'])
        filename = '竣工資料_%s_%s.zip' % (safe_name(self.project_id.code or self.project_id.name),
                                         local_today().strftime('%Y%m%d'))
        kinds = {}
        for row in package.missing:
            kinds[row['kind']] = kinds.get(row['kind'], 0) + 1
        note = '共 %s 個檔（含清冊），壓縮前 %.1f MB。' % (len(package.entries) + 1, package.size / BYTES_PER_MB)
        if package.missing:
            note += '\n缺漏清單 %s 項：%s。明細在壓縮檔裡的「%s」第二張工作表。' % (
                len(package.missing), '、'.join('%s %s' % item for item in kinds.items()), MANIFEST_NAME)
        else:
            note += '\n沒有發現缺漏。'
        self.write({
            'state': 'done',
            'result_file': base64.b64encode(output.getvalue()),
            'result_filename': filename,
            'file_count': len(package.entries) + 1,
            'missing_count': len(package.missing),
            'result_note': note,
        })
        return self._reopen()

    def action_reset(self):
        self.ensure_one()
        self.write({'state': 'draft', 'result_file': False, 'result_filename': False, 'file_count': 0,
                    'missing_count': 0, 'result_note': False})
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': '竣工打包',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('construction_batch.completion_package_wizard_form_view').id, 'form')],
            'target': 'new',
        }
