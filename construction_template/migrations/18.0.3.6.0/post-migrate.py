# -*- coding: utf-8 -*-
"""3.6.0：新北契約表單（2026-10-25）。

- 新增兩種系統預設樣板：material_inspection_record（附表11）、estimate_progress_report（估驗附件）。
- 系統預設 daily_log_c1 換新檔（第四項、第五項(一)勾選改 token、補表報編號與註 8）——
  只在系統裡那份還是舊出貨版時才換；被人換過的不覆蓋，記 WARNING。

不像 2.5.0 那樣整批重灌：那會把所有系統預設附件換成 repo 版、蓋掉有人在系統裡換過的檔。
"""
import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.construction_template.hooks import seed_default_templates

_logger = logging.getLogger(__name__)

# 3.6.0 以前出貨的 daily_log_c1.xlsx（git 43dc86b；odoo18_dev 系統預設附件實查同值）
SHIPPED_DAILY_LOG_C1 = {'163f1de6fa4db303130a99a38995ec9d4db91cab'}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_default_templates(
        env,
        types=('daily_log_c1', 'material_inspection_record', 'estimate_progress_report'),
        replaceable={'daily_log_c1': SHIPPED_DAILY_LOG_C1})
