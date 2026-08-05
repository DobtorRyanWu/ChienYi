# -*- coding: utf-8 -*-
"""施工日誌 → 日報表／施工日誌樣板的一鍵套印匯出。"""

import logging

from odoo import models

_logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_TYPE = 'daily_log_1'


class DailyLogSheet(models.Model):
    _name = 'daily.log.sheet'
    _inherit = ['daily.log.sheet', 'document.template.export.mixin']

    def action_export_daily_log_template(self):
        """把本張日誌的資料填進樣板並下載。

        要匯出哪一種由 context 的 template_type 決定（按鈕上指定）：
          daily_log_1   監造版 公共工程監造日報表 第一聯
          daily_log_c1  營造版 公共工程施工日誌 第一聯
          daily_log_c2  營造版 公共工程施工日誌 第二聯
        """
        self.ensure_one()
        return self._export_document_template(
            self.env.context.get('template_type', DEFAULT_TEMPLATE_TYPE))
