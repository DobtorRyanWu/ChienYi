# -*- coding: utf-8 -*-
# 將既有由「計畫基準校正」產生的負值過渡明細回填 from_plan_correction 旗標，
# 使其在跨版本複製/重新驗證時仍視為合法歷史校正。


def migrate(cr, version):
    cr.execute("""
        UPDATE progress_schedule_line
        SET from_plan_correction = TRUE
        WHERE planned_progress < 0
    """)
