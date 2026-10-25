# -*- coding: utf-8 -*-
"""估驗附件：工程施工進度報告表＋品質管理文件查對表 —— docx 對照表（一張估驗一份）。

樣板來自新北市政府工程契約（2026-10-25，tools/ntpc_forms/build_forms.py 從契約 Word 原表切出）：
    第五條附件一  承攬廠商品質管理文件查對表——只填表頭，15 項由廠商與監造人工勾選
    第五條附件二  工程施工進度報告表
兩張都寫明「廠商申請估驗時應檢附」，所以放在同一份檔、同一顆估驗按鈕。
系統預設版的機關名稱用 {{ authorityName }}（案件的「主辦機關」）；八里／中正橋另有案件專用版。

進度的算法見 utils/progress.py（使用者 2026-10-25 裁示：預定＝進度表內插到迄日的累計，
實際＝迄日當天或之前最後一次有填的累計）。

規則（hypothesis，交使用者確認）：
    估驗起迄  起＝同案上一張估驗日的隔天，第一張用實際開工日、沒有用契約開工日；迄＝本張估驗日
    填表日期  提出日期，沒有用估驗日期（不用今天：重印時日期不能跑掉）
    剩餘工期  總核定工期 −（迄 − 契約開工日 + 1），不小於 0——與施工日誌同一算法
    超前／落後 實際 − 預定，取兩位小數；相等或任一邊沒資料兩格都不勾
"""

from datetime import timedelta

import pytz

from ..utils import progress
from ..utils.formatters import contractor_name, money, percent, roc_date_cn
from .invoice_photo import _period
from .progress_report import authority_name, estimate_warnings

MODEL = 'payment.estimate'
MODE = 'docx'

WARNINGS = estimate_warnings
BOX_ON, BOX_OFF = '■', '□'
LOCAL_TZ = 'Asia/Taipei'


def _start_date(project):
    return project.actual_start_date or project.contract_start_date


def period(estimate):
    """(起, 迄)：起＝上一張估驗日的隔天，第一張用開工日"""
    previous, end = _period(estimate)
    if not end:
        return None, None
    start = previous + timedelta(days=1) if previous else _start_date(estimate.project_id)
    return start, end


def _local_date(utc_datetime):
    """提出時間存 UTC；填表日期是在台灣發生的事，固定用台北時區換日期——
    不能跟著看報表的人的時區走（2026-09-23 教訓：帳號時區繼承自範本、是歐洲）"""
    return pytz.utc.localize(utc_datetime).astimezone(pytz.timezone(LOCAL_TZ)).date()


def _remaining_days(project, end):
    if not end or not project.contract_start_date:
        return ''
    used = (end - project.contract_start_date).days + 1
    return str(max(0, (project.total_approved_duration or 0) - used))


def build_context(estimate):
    project = estimate.project_id
    start, end = period(estimate)
    planned = progress.rounded(progress.planned_cumulative_on(project, end))
    actual = progress.rounded(progress.actual_cumulative_on(project, end))
    diff = None if planned is None or actual is None else round(actual - planned, 2)
    fill = (_local_date(estimate.submitted_date) if estimate.submitted_date
            else estimate.estimate_date)
    return {
        'authorityName': authority_name(project),
        'projectName': project.name or '',
        'contractNo': estimate.contract_no or project.contract_no or '',
        'contractor': contractor_name(project),
        'supervisorName': project.management_company_name or '',
        'startDate': roc_date_cn(_start_date(project)),
        # 履約期限：契約完工日（展延後的最新日），契約備註 1 要求填展延後的期限
        'deadline': roc_date_cn(project.contract_end_date),
        # 契約價金：含契約變更（備註 1）
        'contractAmount': money(project.contract_amount) if project.contract_amount else '',
        'estimateNo': estimate.estimate_no or '',
        'periodStart': roc_date_cn(start),
        'periodEnd': roc_date_cn(end),
        'fillDate': roc_date_cn(fill),
        'plannedProgress': percent(planned),
        'actualProgress': percent(actual),
        'aheadBox': BOX_ON if diff is not None and diff > 0 else BOX_OFF,
        'behindBox': BOX_ON if diff is not None and diff < 0 else BOX_OFF,
        'aheadValue': percent(diff) if diff is not None and diff > 0 else '',
        'behindValue': percent(-diff) if diff is not None and diff < 0 else '',
        'remainingDays': _remaining_days(project, end),
    }


def FILENAME(estimate):
    return '工程施工進度報告表_%s_第%s期.docx' % (
        estimate.project_id.name or '', estimate.estimate_no or estimate.id)
