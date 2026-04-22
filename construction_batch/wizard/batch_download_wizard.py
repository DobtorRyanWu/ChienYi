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

_logger = logging.getLogger(__name__)


class BatchDownloadWizard(models.TransientModel):
    """
    批次下載精靈

    支援批次下載施工日誌、估驗計價表等
    參考規格書 4.17 節實作
    """
    _name = 'batch.download.wizard'
    _description = '批次下載精靈'

    # === 下載類型選擇 ===
    download_type = fields.Selection([
        ('daily_log', '施工日誌'),
        ('self_inspection', '自主檢查表'),
        ('estimate', '估驗計價表'),
        ('test_record', '檢試驗記錄'),
    ], string='下載類型', required=True, default='daily_log',
       help='選擇要批次下載的文件類型')

    # === 日誌下載選項 ===
    log_format = fields.Selection([
        ('pdf', 'PDF 格式'),
        ('excel', 'Excel 格式'),
    ], string='輸出格式', default='pdf',
       help='選擇下載文件的格式')

    include_photos = fields.Boolean(
        string='包含照片',
        default=False,
        help='勾選後將在輸出中包含相關照片')

    include_weather = fields.Boolean(
        string='包含天氣記錄',
        default=True,
        help='勾選後將在輸出中包含天氣記錄')

    # === 日期區間篩選 ===
    date_from = fields.Date(
        string='起始日期',
        help='篩選此日期之後的記錄')

    date_to = fields.Date(
        string='截止日期',
        help='篩選此日期之前的記錄')

    # === 專案篩選 ===
    project_id = fields.Many2one(
        'supervision.project',
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

    state = fields.Selection([
        ('draft', '設定'),
        ('done', '完成'),
    ], string='狀態', default='draft')

    # -------------------------------------------------------------------------
    # Compute Methods
    # -------------------------------------------------------------------------

    @api.depends('download_type', 'daily_log_ids', 'estimate_ids',
                 'project_id', 'date_from', 'date_to')
    def _compute_record_count(self):
        """計算符合條件的記錄數量"""
        for wizard in self:
            if wizard.download_type == 'daily_log':
                if wizard.daily_log_ids:
                    wizard.record_count = len(wizard.daily_log_ids)
                else:
                    domain = wizard._get_daily_log_domain()
                    wizard.record_count = self.env['daily.log.sheet'].search_count(domain)
            elif wizard.download_type == 'estimate':
                if wizard.estimate_ids:
                    wizard.record_count = len(wizard.estimate_ids)
                else:
                    domain = wizard._get_estimate_domain()
                    wizard.record_count = self.env['payment.estimate'].search_count(domain)
            else:
                # 其他類型暫時顯示 0
                wizard.record_count = 0

    # -------------------------------------------------------------------------
    # Onchange Methods
    # -------------------------------------------------------------------------

    @api.onchange('download_type')
    def _onchange_download_type(self):
        """當下載類型變更時，清空已選記錄"""
        self.daily_log_ids = False
        self.estimate_ids = False

    @api.onchange('project_id')
    def _onchange_project_id(self):
        """當專案變更時，更新可選記錄的 domain"""
        # 返回 domain 以限制可選記錄
        if self.project_id:
            return {
                'domain': {
                    'daily_log_ids': [
                        ('project_id', '=', self.project_id.project_id.id)
                    ],
                    'estimate_ids': [
                        ('project_id', '=', self.project_id.id)
                    ],
                }
            }
        return {}

    # -------------------------------------------------------------------------
    # Constraint Methods
    # -------------------------------------------------------------------------

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

    def _get_daily_log_domain(self):
        """建立施工日誌查詢 domain"""
        self.ensure_one()
        domain = []

        # 公司篩選
        if self.company_id:
            domain.append(('company_id', '=', self.company_id.id))

        # 專案篩選
        if self.project_id:
            domain.append(('project_id', '=', self.project_id.project_id.id))

        # 日期篩選
        if self.date_from:
            domain.append(('date_start', '>=', self.date_from))
        if self.date_to:
            domain.append(('date_end', '<=', self.date_to))

        # 只下載已核准的日誌
        domain.append(('state', '=', 'done'))

        return domain

    def _get_estimate_domain(self):
        """建立估驗計價查詢 domain"""
        self.ensure_one()
        domain = []

        # 公司篩選
        if self.company_id:
            domain.append(('company_id', '=', self.company_id.id))

        # 專案篩選
        if self.project_id:
            domain.append(('project_id', '=', self.project_id.id))

        # 日期篩選
        if self.date_from:
            domain.append(('period_start', '>=', self.date_from))
        if self.date_to:
            domain.append(('period_end', '<=', self.date_to))

        # 只下載已核定的估驗
        domain.append(('state', 'in', ['approved', 'paid']))

        return domain

    # -------------------------------------------------------------------------
    # Action Methods
    # -------------------------------------------------------------------------

    def action_download(self):
        """執行批次下載"""
        self.ensure_one()

        if self.download_type == 'daily_log':
            return self._download_daily_logs()
        elif self.download_type == 'estimate':
            return self._download_estimates()
        elif self.download_type == 'self_inspection':
            return self._download_self_inspections()
        elif self.download_type == 'test_record':
            return self._download_test_records()
        else:
            raise UserError('尚未支援的下載類型')

    def action_preview(self):
        """預覽符合條件的記錄"""
        self.ensure_one()

        if self.download_type == 'daily_log':
            domain = self._get_daily_log_domain()
            if self.daily_log_ids:
                domain = [('id', 'in', self.daily_log_ids.ids)]

            return {
                'type': 'ir.actions.act_window',
                'name': '施工日誌預覽',
                'res_model': 'daily.log.sheet',
                'view_mode': 'list,form',
                'domain': domain,
                'target': 'new',
                'context': {'create': False},
            }

        elif self.download_type == 'estimate':
            domain = self._get_estimate_domain()
            if self.estimate_ids:
                domain = [('id', 'in', self.estimate_ids.ids)]

            return {
                'type': 'ir.actions.act_window',
                'name': '估驗計價預覽',
                'res_model': 'payment.estimate',
                'view_mode': 'list,form',
                'domain': domain,
                'target': 'new',
                'context': {'create': False},
            }

        raise UserError('尚未支援此類型的預覽功能')

    def action_reset(self):
        """重設精靈"""
        self.ensure_one()
        self.write({
            'state': 'draft',
            'result_file': False,
            'result_filename': False,
            'daily_log_ids': [Command.clear()],
            'estimate_ids': [Command.clear()],
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # -------------------------------------------------------------------------
    # Download Implementation Methods
    # -------------------------------------------------------------------------

    def _download_daily_logs(self):
        """下載施工日誌"""
        self.ensure_one()

        # 取得記錄
        if self.daily_log_ids:
            logs = self.daily_log_ids
        else:
            domain = self._get_daily_log_domain()
            logs = self.env['daily.log.sheet'].search(domain)

        if not logs:
            raise UserError('沒有符合條件的施工日誌可下載')

        # 限制單次下載數量
        max_records = 100
        if len(logs) > max_records:
            raise UserError(
                f'單次下載最多 {max_records} 筆記錄，'
                f'目前選擇了 {len(logs)} 筆。請縮小篩選範圍。'
            )

        # 產生檔案
        if self.log_format == 'excel':
            file_data, filename = self._generate_daily_logs_excel(logs)
        else:
            file_data, filename = self._generate_daily_logs_zip(logs)

        # 儲存結果
        self.write({
            'state': 'done',
            'result_file': base64.b64encode(file_data),
            'result_filename': filename,
        })

        # 返回下載動作
        return self._get_download_action()

    def _download_estimates(self):
        """下載估驗計價表"""
        self.ensure_one()

        # 取得記錄
        if self.estimate_ids:
            estimates = self.estimate_ids
        else:
            domain = self._get_estimate_domain()
            estimates = self.env['payment.estimate'].search(domain)

        if not estimates:
            raise UserError('沒有符合條件的估驗計價表可下載')

        # 限制單次下載數量
        max_records = 50
        if len(estimates) > max_records:
            raise UserError(
                f'單次下載最多 {max_records} 筆記錄，'
                f'目前選擇了 {len(estimates)} 筆。請縮小篩選範圍。'
            )

        # 產生檔案
        if self.log_format == 'excel':
            file_data, filename = self._generate_estimates_excel(estimates)
        else:
            file_data, filename = self._generate_estimates_zip(estimates)

        # 儲存結果
        self.write({
            'state': 'done',
            'result_file': base64.b64encode(file_data),
            'result_filename': filename,
        })

        return self._get_download_action()

    def _download_self_inspections(self):
        """下載自主檢查表 (預留實作)"""
        self.ensure_one()
        raise UserError(
            '自主檢查表批次下載功能開發中，請稍後再試。\n'
            '您可以先使用個別下載功能。'
        )

    def _download_test_records(self):
        """下載檢試驗記錄 (預留實作)"""
        self.ensure_one()
        raise UserError(
            '檢試驗記錄批次下載功能開發中，請稍後再試。\n'
            '您可以先使用個別下載功能。'
        )

    # -------------------------------------------------------------------------
    # File Generation Methods
    # -------------------------------------------------------------------------

    def _generate_daily_logs_excel(self, logs):
        """產生施工日誌 Excel 檔案"""
        try:
            import xlsxwriter
        except ImportError:
            raise UserError(
                '系統缺少 xlsxwriter 套件，無法產生 Excel 檔案。\n'
                '請聯繫系統管理員安裝此套件。'
            )

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        # 定義樣式
        header_format = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#4472C4',
            'font_color': 'white',
            'border': 1,
        })
        cell_format = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
        })
        date_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'num_format': 'yyyy-mm-dd',
        })

        # 建立工作表
        worksheet = workbook.add_worksheet('施工日誌')

        # 標題列
        headers = [
            '序號', '日誌名稱', '工程案件', '起始日期', '截止日期',
            '總工時', '總人數', '總機具數', '狀態', '提交人', '備註'
        ]
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)

        # 資料列
        for row, log in enumerate(logs, start=1):
            worksheet.write(row, 0, row, cell_format)
            worksheet.write(row, 1, log.complete_name or '', cell_format)
            worksheet.write(row, 2, log.project_id.name or '', cell_format)
            worksheet.write(row, 3, log.date_start, date_format)
            worksheet.write(row, 4, log.date_end, date_format)
            worksheet.write(row, 5, log.total_work_hours or 0, cell_format)
            worksheet.write(row, 6, log.total_worker_count or 0, cell_format)
            worksheet.write(row, 7, log.total_equipment_count or 0, cell_format)
            worksheet.write(row, 8, dict(log._fields['state'].selection).get(log.state, ''), cell_format)
            worksheet.write(row, 9, log.employee_id.name or '', cell_format)
            worksheet.write(row, 10, log.notes or '', cell_format)

        # 調整欄寬
        worksheet.set_column(0, 0, 6)   # 序號
        worksheet.set_column(1, 1, 30)  # 日誌名稱
        worksheet.set_column(2, 2, 25)  # 工程案件
        worksheet.set_column(3, 4, 12)  # 日期
        worksheet.set_column(5, 7, 10)  # 統計數字
        worksheet.set_column(8, 8, 10)  # 狀態
        worksheet.set_column(9, 9, 15)  # 提交人
        worksheet.set_column(10, 10, 30)  # 備註

        workbook.close()
        output.seek(0)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'施工日誌_{timestamp}.xlsx'

        return output.getvalue(), filename

    def _generate_daily_logs_zip(self, logs):
        """產生施工日誌 ZIP 壓縮檔 (包含 PDF)"""
        output = io.BytesIO()

        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
            # 產生每筆日誌的資料
            for log in logs:
                # 產生文字摘要檔案
                content = self._format_daily_log_text(log)
                safe_name = self._safe_filename(log.complete_name or f'log_{log.id}')
                filename = f'{safe_name}.txt'
                zf.writestr(filename, content.encode('utf-8'))

            # 加入索引檔案
            index_content = self._generate_daily_logs_index(logs)
            zf.writestr('_索引.txt', index_content.encode('utf-8'))

        output.seek(0)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'施工日誌批次下載_{timestamp}.zip'

        return output.getvalue(), filename

    def _generate_estimates_excel(self, estimates):
        """產生估驗計價 Excel 檔案"""
        try:
            import xlsxwriter
        except ImportError:
            raise UserError(
                '系統缺少 xlsxwriter 套件，無法產生 Excel 檔案。\n'
                '請聯繫系統管理員安裝此套件。'
            )

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        # 定義樣式
        header_format = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#4472C4',
            'font_color': 'white',
            'border': 1,
        })
        cell_format = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
        })
        money_format = workbook.add_format({
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '#,##0',
        })
        percent_format = workbook.add_format({
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '0.00%',
        })

        # 建立摘要工作表
        ws_summary = workbook.add_worksheet('估驗摘要')

        headers = [
            '序號', '估驗期次', '工程案件', '期間起', '期間迄',
            '本期金額', '累計金額', '契約總價', '完成率', '狀態'
        ]
        for col, header in enumerate(headers):
            ws_summary.write(0, col, header, header_format)

        for row, est in enumerate(estimates, start=1):
            ws_summary.write(row, 0, row, cell_format)
            ws_summary.write(row, 1, est.name or '', cell_format)
            ws_summary.write(row, 2, est.project_id.name or '', cell_format)
            ws_summary.write(row, 3, str(est.period_start or ''), cell_format)
            ws_summary.write(row, 4, str(est.period_end or ''), cell_format)
            ws_summary.write(row, 5, est.subtotal or 0, money_format)
            ws_summary.write(row, 6, est.cumulative_amount or 0, money_format)
            ws_summary.write(row, 7, est.contract_total or 0, money_format)
            ws_summary.write(row, 8, (est.completion_rate or 0) / 100, percent_format)
            ws_summary.write(row, 9, dict(est._fields['state'].selection).get(est.state, ''), cell_format)

        # 調整欄寬
        ws_summary.set_column(0, 0, 6)
        ws_summary.set_column(1, 1, 15)
        ws_summary.set_column(2, 2, 25)
        ws_summary.set_column(3, 4, 12)
        ws_summary.set_column(5, 7, 15)
        ws_summary.set_column(8, 8, 10)
        ws_summary.set_column(9, 9, 10)

        # 為每個估驗建立明細工作表
        for idx, est in enumerate(estimates, start=1):
            sheet_name = f'第{est.estimate_no}期明細'[:31]  # Excel 工作表名稱最長 31 字元
            ws_detail = workbook.add_worksheet(sheet_name)

            detail_headers = [
                '項次', '項目說明', '單位', '契約數量', '契約單價', '契約金額',
                '前期累計', '本期完成', '累計完成', '本期金額', '累計金額', '完成率'
            ]
            for col, header in enumerate(detail_headers):
                ws_detail.write(0, col, header, header_format)

            for row, line in enumerate(est.line_ids, start=1):
                ws_detail.write(row, 0, line.item_no or '', cell_format)
                ws_detail.write(row, 1, line.description or '', cell_format)
                ws_detail.write(row, 2, line.unit or '', cell_format)
                ws_detail.write(row, 3, line.planned_qty or 0, cell_format)
                ws_detail.write(row, 4, line.unit_price or 0, money_format)
                ws_detail.write(row, 5, line.planned_amount or 0, money_format)
                ws_detail.write(row, 6, line.previous_qty or 0, cell_format)
                ws_detail.write(row, 7, line.current_qty or 0, cell_format)
                ws_detail.write(row, 8, line.cumulative_qty or 0, cell_format)
                ws_detail.write(row, 9, line.current_amount or 0, money_format)
                ws_detail.write(row, 10, line.cumulative_amount or 0, money_format)
                ws_detail.write(row, 11, (line.completion_rate or 0) / 100, percent_format)

            # 調整欄寬
            ws_detail.set_column(0, 0, 8)
            ws_detail.set_column(1, 1, 30)
            ws_detail.set_column(2, 2, 8)
            ws_detail.set_column(3, 11, 12)

        workbook.close()
        output.seek(0)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'估驗計價_{timestamp}.xlsx'

        return output.getvalue(), filename

    def _generate_estimates_zip(self, estimates):
        """產生估驗計價 ZIP 壓縮檔"""
        output = io.BytesIO()

        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
            for est in estimates:
                content = self._format_estimate_text(est)
                safe_name = self._safe_filename(f'{est.project_id.name}_{est.name}')
                filename = f'{safe_name}.txt'
                zf.writestr(filename, content.encode('utf-8'))

            # 加入索引檔案
            index_content = self._generate_estimates_index(estimates)
            zf.writestr('_索引.txt', index_content.encode('utf-8'))

        output.seek(0)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'估驗計價批次下載_{timestamp}.zip'

        return output.getvalue(), filename

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _format_daily_log_text(self, log):
        """格式化施工日誌為文字"""
        lines = [
            '=' * 60,
            f'施工日誌: {log.complete_name}',
            '=' * 60,
            '',
            f'工程案件: {log.project_id.name or ""}',
            f'起始日期: {log.date_start}',
            f'截止日期: {log.date_end}',
            f'提交人員: {log.employee_id.name or ""}',
            f'狀態: {dict(log._fields["state"].selection).get(log.state, "")}',
            '',
            '-' * 40,
            '統計資訊',
            '-' * 40,
            f'總工時: {log.total_work_hours or 0} 小時',
            f'總人數: {log.total_worker_count or 0} 人',
            f'總機具數: {log.total_equipment_count or 0} 台',
            '',
        ]

        # 天氣記錄
        if log.weather_ids:
            lines.extend([
                '-' * 40,
                '天氣記錄',
                '-' * 40,
            ])
            for weather in log.weather_ids:
                weather_str = f'  {weather.date}: '
                if hasattr(weather, 'weather_am'):
                    weather_str += f'上午 {weather.weather_am or ""} / '
                if hasattr(weather, 'weather_pm'):
                    weather_str += f'下午 {weather.weather_pm or ""}'
                lines.append(weather_str)
            lines.append('')

        # 工作摘要
        if log.work_summary:
            lines.extend([
                '-' * 40,
                '工作摘要',
                '-' * 40,
                log.work_summary,
                '',
            ])

        # 備註
        if log.notes:
            lines.extend([
                '-' * 40,
                '備註',
                '-' * 40,
                log.notes,
                '',
            ])

        return '\n'.join(lines)

    def _format_estimate_text(self, est):
        """格式化估驗計價為文字"""
        lines = [
            '=' * 60,
            f'估驗計價表: {est.name}',
            '=' * 60,
            '',
            f'工程案件: {est.project_id.name or ""}',
            f'估驗期次: 第 {est.estimate_no} 期',
            f'期間: {est.period_start} ~ {est.period_end}',
            f'提送公司: {est.company_id.name or ""}',
            f'狀態: {dict(est._fields["state"].selection).get(est.state, "")}',
            '',
            '-' * 40,
            '金額摘要',
            '-' * 40,
            f'本期估驗金額: {est.subtotal:,.0f}',
            f'累計估驗金額: {est.cumulative_amount:,.0f}',
            f'契約總價: {est.contract_total:,.0f}',
            f'估驗進度: {est.completion_rate:.2f}%',
            f'保留款: {est.retention:,.0f} ({est.retention_rate}%)',
            f'應付金額: {est.payable_amount:,.0f}',
            '',
            '-' * 40,
            '計價明細',
            '-' * 40,
        ]

        # 明細
        for line in est.line_ids:
            lines.extend([
                f'  {line.item_no or ""} {line.description or ""}',
                f'    契約: {line.planned_qty} {line.unit or ""} x {line.unit_price:,.0f} = {line.planned_amount:,.0f}',
                f'    本期: {line.current_qty} {line.unit or ""} = {line.current_amount:,.0f}',
                f'    累計: {line.cumulative_qty} {line.unit or ""} = {line.cumulative_amount:,.0f} ({line.completion_rate:.2f}%)',
                '',
            ])

        return '\n'.join(lines)

    def _generate_daily_logs_index(self, logs):
        """產生施工日誌索引"""
        lines = [
            '施工日誌批次下載索引',
            '=' * 60,
            f'下載時間: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            f'總筆數: {len(logs)}',
            '',
            '-' * 60,
            '檔案清單',
            '-' * 60,
        ]

        for idx, log in enumerate(logs, start=1):
            lines.append(f'{idx:3d}. {log.complete_name} ({log.date_start} ~ {log.date_end})')

        return '\n'.join(lines)

    def _generate_estimates_index(self, estimates):
        """產生估驗計價索引"""
        lines = [
            '估驗計價批次下載索引',
            '=' * 60,
            f'下載時間: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            f'總筆數: {len(estimates)}',
            '',
            '-' * 60,
            '檔案清單',
            '-' * 60,
        ]

        for idx, est in enumerate(estimates, start=1):
            lines.append(
                f'{idx:3d}. {est.project_id.name} - {est.name} '
                f'(金額: {est.subtotal:,.0f})'
            )

        return '\n'.join(lines)

    def _safe_filename(self, name):
        """產生安全的檔案名稱"""
        # 移除不安全的字元
        unsafe_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        safe_name = name
        for char in unsafe_chars:
            safe_name = safe_name.replace(char, '_')
        # 限制長度
        if len(safe_name) > 50:
            safe_name = safe_name[:50]
        return safe_name

    def _get_download_action(self):
        """取得下載動作"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'form_view_ref': 'construction_batch.batch_download_wizard_result_view'},
        }
