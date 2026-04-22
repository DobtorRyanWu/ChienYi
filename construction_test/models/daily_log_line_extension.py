# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class DailyLogLineTestExtension(models.Model):
    """
    擴展施工日誌明細，加入即時檢試驗需求檢查

    當日誌明細的完成數量變更時：
    1. 檢查累計數量是否達到檢驗頻率條件，自動建立檢試驗管制記錄
    2. 檢查累計數量是否達到 95% 預警門檻，自動建立預警通知
    """
    _inherit = 'daily.log.line'

    # =========================================================================
    # CRUD 覆寫
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        """建立日誌明細後，檢查檢試驗需求"""
        lines = super().create(vals_list)
        lines._check_test_requirements()
        return lines

    def write(self, vals):
        """更新日誌明細後，若數量相關欄位變更則檢查檢試驗需求"""
        result = super().write(vals)
        if any(f in vals for f in ('daily_qty', 'work_item_id', 'date')):
            self._check_test_requirements()
        return result

    # =========================================================================
    # 核心檢查邏輯
    # =========================================================================

    def _check_test_requirements(self):
        """
        檢查所有受影響的日誌明細，判斷是否需要：
        1. 自動建立檢試驗管制記錄（累計達到門檻）
        2. 建立預警通知（累計達到 95%）
        """
        for line in self:
            if not line.work_item_id or not line.cumulative_qty or line.cumulative_qty <= 0:
                continue

            # 取得 supervision.project（test.record 需要的 project_id）
            sup_project = line.sheet_id.supervision_project_id if line.sheet_id else None
            if not sup_project:
                continue

            # 檢查完工提醒（累計達契約數量 95%）
            self._check_completion_warnings(line, sup_project)

            # 找出與此工項關聯的所有檢試驗項目
            standards = self.env['supervision.test.standard'].search([
                ('task_ids', 'in', line.work_item_id.id),
                ('active', '=', True),
            ])
            if not standards:
                continue

            for standard in standards:
                self._process_standard(line, standard, sup_project)

    def _process_standard(self, line, standard, sup_project):
        """
        處理單一檢試驗項目的自動建立與預警

        :param line: daily.log.line 記錄
        :param standard: supervision.test.standard 記錄
        :param sup_project: supervision.project 記錄
        """
        cumulative_qty = line.cumulative_qty
        daily_qty = line.daily_qty or 0
        conditions = standard.frequency_condition_ids.filtered('active').sorted('sequence')

        # === 步驟 1：計算應有檢驗次數，自動建立不足的記錄 ===
        # 統一入口：頻率條件 + 自訂公式（並存相加）
        # daily_qty 傳入以支援「每日澆築量」型自訂公式
        required_count = standard.calculate_required_tests(cumulative_qty, daily_qty=daily_qty)

        if required_count > 0:
            existing_count = self.env['supervision.test.record'].search_count([
                ('project_id', '=', sup_project.id),
                ('task_id', '=', line.work_item_id.id),
                ('standard_id', '=', standard.id),
            ])

            shortage = required_count - existing_count
            if shortage > 0:
                self._create_test_records(
                    line, standard, sup_project, shortage)

        # === 步驟 2：檢查 95% 預警 ===
        # 標準條件預警
        if conditions:
            self._check_95_warnings(line, standard, sup_project, conditions, cumulative_qty)

        # 自訂公式預警
        if standard.use_custom_formula and standard.custom_warning_formula:
            self._check_custom_formula_warning(line, standard, sup_project, cumulative_qty)

        # === 步驟 3：自訂公式施工提醒（純通知，不建立實體記錄）===
        if standard.use_custom_formula:
            self._create_custom_formula_daily_notification(line, standard, sup_project)

    # =========================================================================
    # 自動建立檢試驗記錄
    # =========================================================================

    def _create_test_records(self, line, standard, sup_project, count):
        """
        建立不足的檢試驗管制記錄

        :param line: daily.log.line 記錄
        :param standard: supervision.test.standard 記錄
        :param sup_project: supervision.project 記錄
        :param count: 需要建立的數量
        """
        TestRecord = self.env['supervision.test.record']

        for _i in range(count):
            TestRecord.create({
                'name': '/',
                'project_id': sup_project.id,
                'task_id': line.work_item_id.id,
                'standard_id': standard.id,
                'auto_created': True,
                'trigger_log_line_id': line.id,
                'trigger_cumulative_qty': line.cumulative_qty,
                'in_site_date': line.date,
            })

        _logger.info(
            '自動建立 %d 筆檢驗記錄：工程=%s, 工項=%s, 項目=%s, 累計=%s',
            count, sup_project.code, line.work_item_id.item_no,
            standard.name, line.cumulative_qty
        )

    # =========================================================================
    # 95% 預警邏輯
    # =========================================================================

    def _check_95_warnings(self, line, standard, sup_project, conditions, cumulative_qty):
        """
        檢查各條件的 95% 預警

        每種條件類型有各自的 95% 判定邏輯：
        - exempt_below: 不適用
        - range_once: 累計距 range_start 的 95%
        - exceed_interval: 距下一個加驗點間隔的 95%
        - every_n: 距下一個 interval 倍數間隔的 95%
        - every_batch: 不適用
        """
        TestWarning = self.env['supervision.test.warning']

        for cond in conditions:
            next_threshold, interval = self._get_next_threshold(
                cond, cumulative_qty, standard, sup_project, line.work_item_id)

            if next_threshold is None:
                continue

            # 計算 95% 預警點 = 門檻 - 間隔的 5%
            warning_point = next_threshold - interval * 0.05

            # 判斷是否達到 95% 但尚未達到 100%
            if cumulative_qty >= warning_point and cumulative_qty < next_threshold:
                # 檢查是否已存在相同門檻的未處理預警
                existing = TestWarning.search([
                    ('standard_id', '=', standard.id),
                    ('task_id', '=', line.work_item_id.id),
                    ('next_threshold_qty', '=', next_threshold),
                    ('state', '=', 'pending'),
                ], limit=1)

                if not existing:
                    warning = TestWarning.create({
                        'project_id': sup_project.id,
                        'standard_id': standard.id,
                        'task_id': line.work_item_id.id,
                        'condition_id': cond.id,
                        'trigger_log_line_id': line.id,
                        'current_cumulative_qty': cumulative_qty,
                        'next_threshold_qty': next_threshold,
                        'warning_date': line.date,
                    })

                    # 建立 mail.activity
                    self._create_warning_activity(warning, sup_project)

                    _logger.info(
                        '建立 95%% 預警：工程=%s, 工項=%s, 項目=%s, '
                        '累計=%s, 門檻=%s, 達成率=%.1f%%',
                        sup_project.code, line.work_item_id.item_no,
                        standard.name, cumulative_qty, next_threshold,
                        (cumulative_qty / next_threshold) * 100
                    )

    def _get_next_threshold(self, condition, cumulative_qty, standard, sup_project, task):
        """
        計算各條件類型的下一個檢驗門檻

        :param condition: supervision.test.frequency.condition 記錄
        :param cumulative_qty: float, 當前累計數量
        :param standard: supervision.test.standard 記錄
        :param sup_project: supervision.project 記錄
        :param task: project.task 記錄
        :return: (next_threshold, interval) 或 (None, None)
                 interval 用於計算 95% 預警點 = next_threshold - interval * 0.05
        """
        ctype = condition.condition_type

        # (1) 未達數量免檢 - 不產生檢驗需求，無預警
        if ctype == 'exempt_below':
            return (None, None)

        # (2) 數量區間檢驗1次
        elif ctype == 'range_once':
            # 尚未達 range_start 時，以 range_start 為門檻
            if cumulative_qty < condition.range_start:
                return (condition.range_start, condition.range_start)
            return (None, None)  # 已超過區間，此條件不再產生新門檻

        # (3) 超過數量每N加驗
        elif ctype == 'exceed_interval':
            if condition.interval_qty <= 0:
                return (None, None)

            # 測試點 = interval_qty 的倍數中 > exceed_qty 的那些
            # 例：exceed=150, interval=100 → 免驗區間數=1, 測試點: 200, 300, 400...
            exempt = int(condition.exceed_qty / condition.interval_qty)
            completed = int(cumulative_qty / condition.interval_qty)
            next_idx = max(completed, exempt) + 1
            next_threshold = next_idx * condition.interval_qty
            return (next_threshold, condition.interval_qty)

        # (4) 每N數量檢驗1次
        elif ctype == 'every_n':
            if condition.interval_qty <= 0:
                return (None, None)

            # 下一個 interval 倍數
            completed_intervals = int(cumulative_qty / condition.interval_qty)
            next_threshold = (completed_intervals + 1) * condition.interval_qty
            return (next_threshold, condition.interval_qty)

        # (5) 每批檢驗1次 - 與累計數量無關，無預警
        elif ctype == 'every_batch':
            return (None, None)

        return (None, None)

    # =========================================================================
    # 自訂公式預警
    # =========================================================================

    def _check_custom_formula_warning(self, line, standard, sup_project, cumulative_qty):
        """
        檢查自訂公式的預警門檻

        :param line: daily.log.line 記錄
        :param standard: supervision.test.standard 記錄
        :param sup_project: supervision.project 記錄
        :param cumulative_qty: float, 當前累計數量
        """
        next_threshold = standard._eval_custom_warning_formula(cumulative_qty)
        if next_threshold is None:
            return

        # 預警點 = 門檻的 95%
        interval = next_threshold - cumulative_qty
        warning_point = next_threshold - interval * 0.05

        if cumulative_qty >= warning_point and cumulative_qty < next_threshold:
            TestWarning = self.env['supervision.test.warning']

            existing = TestWarning.search([
                ('standard_id', '=', standard.id),
                ('task_id', '=', line.work_item_id.id),
                ('next_threshold_qty', '=', next_threshold),
                ('state', '=', 'pending'),
            ], limit=1)

            if not existing:
                warning = TestWarning.create({
                    'project_id': sup_project.id,
                    'standard_id': standard.id,
                    'task_id': line.work_item_id.id,
                    'trigger_log_line_id': line.id,
                    'current_cumulative_qty': cumulative_qty,
                    'next_threshold_qty': next_threshold,
                    'warning_date': line.date,
                })

                self._create_warning_activity(warning, sup_project)

                _logger.info(
                    '建立自訂公式預警：工程=%s, 工項=%s, 項目=%s, '
                    '累計=%s, 門檻=%s',
                    sup_project.code, line.work_item_id.item_no,
                    standard.name, cumulative_qty, next_threshold
                )

    # =========================================================================
    # 完工提醒
    # =========================================================================

    def _check_completion_warnings(self, line, sup_project):
        """
        檢查工項累計數量是否達契約數量 95%，建立完工提醒

        提醒內容：請確認該項目的檢試驗項目是否都完成紀錄
        """
        task = line.work_item_id
        planned_qty = task.planned_qty

        # 契約數量為 0 或未設定則跳過
        if not planned_qty or planned_qty <= 0:
            return

        cumulative_qty = line.cumulative_qty
        if cumulative_qty < planned_qty * 0.95:
            return

        # 檢查是否已存在此工項的完工提醒
        TestWarning = self.env['supervision.test.warning']
        existing = TestWarning.search([
            ('warning_type', '=', 'completion'),
            ('project_id', '=', sup_project.id),
            ('task_id', '=', task.id),
        ], limit=1)

        if not existing:
            warning = TestWarning.create({
                'warning_type': 'completion',
                'project_id': sup_project.id,
                'task_id': task.id,
                'trigger_log_line_id': line.id,
                'current_cumulative_qty': cumulative_qty,
                'next_threshold_qty': planned_qty,
                'warning_date': line.date,
            })

            # 建立 mail.activity
            self._create_warning_activity(warning, sup_project)

            _logger.info(
                '建立完工提醒：工程=%s, 工項=%s, 累計=%s, 契約數量=%s, 達成率=%.1f%%',
                sup_project.code, task.item_no,
                cumulative_qty, planned_qty,
                (cumulative_qty / planned_qty) * 100
            )

    # =========================================================================
    # 活動建立
    # =========================================================================

    def _create_warning_activity(self, warning, sup_project):
        """
        為預警記錄建立 mail.activity

        :param warning: supervision.test.warning 記錄
        :param sup_project: supervision.project 記錄
        """
        # 根據預警類型選擇活動類型
        if warning.warning_type == 'frequency':
            activity_type = self.env.ref(
                'construction_test.activity_type_test_warning', raise_if_not_found=False)
            note = (f'工項「{warning.task_id.name}」累計數量已達 '
                    f'{warning.achievement_rate:.0f}%，即將達到檢驗門檻 '
                    f'{warning.next_threshold_qty}，請提早安排取樣檢驗。')
        else:
            activity_type = self.env.ref(
                'construction_test.activity_type_completion_reminder', raise_if_not_found=False)
            note = (f'工項「{warning.task_id.name}」累計數量已達契約數量 '
                    f'{warning.achievement_rate:.0f}%，'
                    f'請確認該項目的檢試驗項目是否都完成紀錄。')

        if not activity_type:
            return

        # 取得指派對象
        # TODO: 權限設計完成後改回 sup_project._get_activity_user('test')
        user = self.env.ref('base.user_admin')

        warning.activity_schedule(
            activity_type_id=activity_type.id,
            summary=activity_type.summary,
            note=note,
            user_id=user.id,
        )

        # 同步發送收件匣通知
        warning.message_post(
            body=note,
            subject=activity_type.summary,
            partner_ids=user.partner_id.ids,
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

    # =========================================================================
    # 自訂公式施工提醒
    # =========================================================================

    def _create_custom_formula_daily_notification(self, line, standard, sup_project):
        """
        自訂公式施工提醒：今日有施工時，發送日曆通知

        不建立 test.record 或 test.warning，僅建立 mail.activity 通知。
        去重：同日 + 同 standard + 同 task 只通知一次。

        :param line: daily.log.line 記錄
        :param standard: supervision.test.standard 記錄
        :param sup_project: supervision.project 記錄
        """
        activity_type = self.env.ref(
            'construction_test.activity_type_custom_formula_reminder',
            raise_if_not_found=False)
        if not activity_type:
            return

        today = fields.Date.today()
        task = line.work_item_id

        # 去重：檢查今日是否已存在此 standard + task 的通知
        # summary 格式包含 [task_id] 用於去重識別
        existing = self.env['mail.activity'].search([
            ('res_model', '=', 'supervision.test.standard'),
            ('res_id', '=', standard.id),
            ('activity_type_id', '=', activity_type.id),
            ('date_deadline', '=', today),
            ('summary', 'like', f'[{task.id}]'),
        ], limit=1)

        if existing:
            return

        # 組裝通知內容
        formula_desc = standard.custom_formula_description or '（未填寫公式說明）'
        note = (
            f'<p>今日有進行此工項施工，條件為自訂公式，請確認是否需要進行檢試驗。</p>'
            f'<ul>'
            f'<li>工項名稱：{task.name}</li>'
            f'<li>今日施工數量：{line.daily_qty}</li>'
            f'<li>累計施工數量：{line.cumulative_qty}</li>'
            f'<li>公式說明：{formula_desc}</li>'
            f'</ul>'
        )

        # 取得指派對象
        # TODO: 權限設計完成後改回 sup_project._get_activity_user('test')
        user = self.env.ref('base.user_admin')

        summary = f'{activity_type.summary} [{task.id}]'

        standard.activity_schedule(
            activity_type_id=activity_type.id,
            summary=summary,
            note=note,
            user_id=user.id,
            date_deadline=today,
        )

        # 同步發送收件匣通知
        standard.message_post(
            body=note,
            subject=f'自訂公式施工提醒：{task.name}',
            partner_ids=user.partner_id.ids,
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

        _logger.info(
            '建立自訂公式施工提醒：工程=%s, 工項=%s, 項目=%s, '
            '今日數量=%s, 累計=%s',
            sup_project.code, task.item_no,
            standard.name, line.daily_qty, line.cumulative_qty
        )
