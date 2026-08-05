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

from ..utils import docx_render
from ..utils.formatters import roc_date

MODEL = 'project.project'
MODE = 'docx'

# 每頁列數。表頭（工程名稱／頁碼）是每頁重印的，所以要實際分頁而不是塞成一頁。
ROWS_PER_PAGE = 15


def _record(defect, contractor):
    return {
        'no': defect.defect_no or defect.name or '',
        'projectContractor': contractor,
        'notifiedAt': roc_date(defect.notification_date),
        'description': defect.defect_description or '',
        'result': defect.improvement_result or '',
        'finishedAt': roc_date(defect.improvement_date),
    }


def build_context(project):
    defects = project.env['general.defect.improvement'].search(
        [('project_id', '=', project.id)], order='found_date, id')
    contractor = '、'.join(project.contractor_partner_ids.mapped('name'))
    rows = [_record(d, contractor) for d in defects]
    pages = docx_render.paginate_pages(rows, ROWS_PER_PAGE)
    return {
        'title': '矯正與預防紀錄管制表',
        'projectName': project.name or '',
        'projectContractor': contractor,
        'totalPage': len(pages),
        'pages': pages,
    }


def FILENAME(project):
    return '矯正與預防紀錄管制表_%s.docx' % (project.name or project.id)
