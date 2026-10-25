# -*- coding: utf-8 -*-
"""計畫送審核章表（新北市政府工程契約附表6-2，無委託專案管理廠商版）—— docx 對照表（一筆計畫一張）。

裝訂在計畫首頁。資料來自計畫書送審管制（supervision.plan.control）：
    提報次數  有第二次送審日期就是第 2 次，否則第 1 次（系統只記兩次）
    提報日期  最近一次送審日期
    審查合格  有監造審查日期就勾，並印日期與文號
    同意核定  有機關核定日期就勾，並印日期與文號
「依審查意見重新提報」「依修正意見重新提報」系統沒有記，留給人工勾。
"""

from ..utils.formatters import contractor_name, roc_date_cn
from .progress_report import authority_name

MODEL = 'supervision.plan.control'
MODE = 'docx'
BOX_ON, BOX_OFF = '■', '□'


def build_context(plan):
    project = plan.project_id
    second = plan.second_submit_date
    return {
        'projectName': project.name or '',
        'planName': plan.name or '',
        'contractor': contractor_name(project),
        'submitCount': 2 if second else (1 if plan.first_submit_date else ''),
        'submitDate': roc_date_cn(second or plan.first_submit_date),
        'supervisorName': project.management_company_name or '',
        'passBox': BOX_ON if plan.supervisor_review_date else BOX_OFF,
        'reviewDate': roc_date_cn(plan.supervisor_review_date),
        'reviewDocNo': plan.supervisor_review_doc_no or '',
        'authorityName': authority_name(project),
        'approveBox': BOX_ON if plan.authority_approve_date else BOX_OFF,
        'approveDate': roc_date_cn(plan.authority_approve_date),
        'approveDocNo': plan.authority_approve_doc_no or '',
    }


def FILENAME(plan):
    return '計畫送審核章表_%s_%s.docx' % (plan.project_id.name or '', plan.name or plan.id)
