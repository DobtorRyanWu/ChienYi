# -*- coding: utf-8 -*-
"""契約附表的共用表頭（只帶表頭、其餘現場手填的那批表）—— docx 對照表（一個工程案件一份）。

新北市政府工程契約（2026-10-25，tools/ntpc_forms/ 從契約 Word 原表切出）附的空白表，系統沒有
那些表的內容資料（審查意見、人員名冊、評分…），能帶的只有案件表頭。每張表一種
template_type、各一支三行的對照表，全部 import 這裡（樣板類型有了，案件專用版與
「專案＞公司＞系統預設」的選樣板順序就沿用 document.template，不必另做機制）。

填表日期與「截至今天」的進度：批次下載精靈有給截止日就用截止日，沒有用台北時區的今天。
"""

from datetime import datetime

import pytz

from odoo import fields

from ..utils import progress, record_filter
from ..utils.formatters import contractor_name, money, percent, roc_date_cn
from .progress_report import authority_name

MODEL = 'project.project'
MODE = 'docx'
LOCAL_TZ = 'Asia/Taipei'
THOUSAND = 1000.0


def ref_date(project):
    given = project.env.context.get(record_filter.CTX_TO)
    return fields.Date.to_date(given) if given else datetime.now(pytz.timezone(LOCAL_TZ)).date()


def build_context(project):
    day = ref_date(project)
    award = project.original_contract_amount
    return {
        'projectName': project.name or '',
        'projectCode': project.code or '',
        'contractNo': project.contract_no or '',
        'location': project.location or '',
        'startDate': roc_date_cn(project.actual_start_date or project.contract_start_date),
        'endDate': roc_date_cn(project.contract_end_date),
        'actualEndDate': roc_date_cn(project.actual_end_date),
        'contractAmount': money(project.contract_amount) if project.contract_amount else '',
        # 附表8-1／8-2「決標金額（千元）」：原始契約金額＝決標金額
        'awardAmountK': ('{:,.0f}'.format(award / THOUSAND)) if award else '',
        'authorityName': authority_name(project),
        'authorityContact': project.authority_contact_name or '',
        'supervisorName': project.management_company_name or '',
        'contractor': contractor_name(project),
        'fillDate': roc_date_cn(day),
        'plannedProgress': percent(progress.rounded(progress.planned_cumulative_on(project, day))),
        'actualProgress': percent(progress.rounded(progress.actual_cumulative_on(project, day))),
    }


def filename_for(label):
    def FILENAME(project):
        return '%s_%s.docx' % (label, project.name or project.id)
    return FILENAME
