# -*- coding: utf-8 -*-
"""矯正與預防紀錄管制表（缺失改善管制表）—— docx 對照表（專案層級，分頁彙總）。

樣板語法：
    +++FOR page IN pages+++
      … 表頭（每頁重印）…
      +++FOR record IN $page.errorRecords+++ … +++END-FOR record+++
    +++END-FOR page+++

所以 pages 必須是「物件」清單（要有 currentPage 與 errorRecords），
與送審／檢試驗那種 `FOR item IN $page`（page 本身是清單）不同。
"""

from ..utils import docx_render, record_filter
from ..utils.formatters import contractor_name, roc_date_cn
from .defect_improvement import source_model

MODEL = 'project.project'
MODE = 'docx'

# 批次下載中心可用 context 限定期間；這裡跟原系統一樣以「通知日期」為準
DATE_FIELD = 'notification_date'
DATE_LABEL = '通知日期'


def WARNINGS(project):
    """日期空白的缺失一律列入，但要讓人知道有哪幾筆"""
    return record_filter.project_warning(
        project, source_model(project), DATE_FIELD, DATE_LABEL)

# 每頁列數。表頭（工程名稱／頁碼）是每頁重印的，所以要實際分頁而不是塞成一頁。
# 每頁 13 筆——取自 EAGLE 原系統 models/errorRecord.js/generateListFile。
# 註：原系統那段分頁其實有 bug（count 不重置，只會在第 13 筆切一次頁），
# 我們跟「13」這個數字，但不跟那個 bug。
ROWS_PER_PAGE = 13


def _record(defect, contractor):
    return {
        'no': defect.defect_no or defect.name or '',
        'projectContractor': contractor,
        # 管制表的日期是民國「年月日」，與 xlsx 的點格式不同（原系統即如此）
        'notifiedAt': roc_date_cn(defect.notification_date),
        'description': defect.defect_description or '',
        'result': defect.improvement_result or '',
        'finishedAt': roc_date_cn(defect.improvement_date),
    }


def build_context(project):
    Defect = project.env[source_model(project)]
    defects = Defect.search(
        [('project_id', '=', project.id)]
        + record_filter.date_domain(project.env, DATE_FIELD),
        order='notification_date, id')
    contractor = contractor_name(project)
    rows = [_record(d, contractor) for d in defects]
    pages = docx_render.paginate_pages(rows, ROWS_PER_PAGE)
    return {
        # 原系統的 title 是填報單位（依 unitType 給營造或監造），不是表名
        'title': contractor or (project.management_company_name or ''),
        'projectName': project.name or '',
        'projectContractor': contractor,
        'totalPage': len(pages),
        'pages': pages,
    }


def FILENAME(project):
    return '矯正與預防紀錄管制表_%s.docx' % (project.name or project.id)
