# -*- coding: utf-8 -*-
"""累計預定進度、累計實際進度（施工日誌與估驗附件「工程施工進度報告表」共用）。

2026-11-24 起直接用進度模組的共用算法（construction_progress/models/progress_calc.py，
project._progress_cumulative_on）：首頁、進度表、進度報告、進度曲線、印出來的日報同一天同一個數字。
規則寫在 progress_calc.py 檔頭；摘要：
- 預定：這一天（含）以前生效的最新一版（契約變更當天用新版）；一段的預定平均分到它自己的每一天、當天算進去；
  交界日算在前一段；空檔停在前一段的值。
- 實際：每一篇日誌的本日實際進度都算（草稿也算），照日期加總、不看分段；基準點＝計畫倒退校正填的
  「校正後累計實際進度」或舊系統 xlsm 匯入的累計值（actual_progress），取日期晚的（同一天以校正為準）。
- 印某一張舊匯入日誌本身＝它自己的累計值（同案同日多張時不會印成別人的，r1 審查 F2）——只有這一條是印的才有。

沒裝 construction_progress：預定沒有進度表 → 空白；實際只看舊系統匯入的累計值。
"""


def _has_progress(project):
    return 'progress.schedule' in project.env and hasattr(project, '_progress_cumulative_on')


def planned_cumulative_on(project, day):
    """截至 day（含）的累計預定進度 %；沒有進度表回 None"""
    if not day or not _has_progress(project):
        return None
    return project._progress_cumulative_on(day)[0]


def actual_cumulative_on(project, day, sheet=None):
    """截至 day（含）的累計實際進度 %；沒有任何實際進度資料回 None。

    :param sheet: 印某一張日誌時傳它自己——舊匯入的日誌印它自己的累計值，不管同日有沒有別張
    """
    if not day:
        return None
    if sheet is not None and (sheet.actual_progress or 0) > 0:
        return sheet.actual_progress
    if _has_progress(project):
        return project._progress_cumulative_on(day)[1]
    Sheet = project.env['daily.log.sheet']
    last = Sheet.search([('supervision_project_id', '=', project.id), ('log_date', '<=', day),
                         ('actual_progress', '>', 0)], order='log_date desc, actual_progress desc', limit=1)
    return last.actual_progress if last else None


def rounded(value, digits=2):
    return None if value is None else round(value, digits)
