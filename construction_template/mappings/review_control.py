# -*- coding: utf-8 -*-
"""材料設備送審管制總表 —— docx 對照表（專案層級，分頁彙總）。

樣板語法：`+++FOR page IN pages+++ … +++FOR item IN $page+++ … +++END-FOR item+++`
——page 本身就是清單，用 paginate_plain。

token → supervision.review.application（欄位名幾乎是 camelCase→snake_case 直譯）：
    no / number / isTest / expectedReviewDate / isFactoryInspection / testUnit /
    hasSubcontractor / hasCatalog / hasRelatedTestReport / hasDemo / hasOthers /
    reviewDate / finalReviewResult / archiveNumber
"""

from ..utils import docx_render, record_filter
from ..utils.formatters import contractor_name, roc_date

MODEL = 'project.project'
MODE = 'docx'

# 批次下載中心可用 context 限定期間；本表以「送審預定日」為準（與既有 order 一致）
DATE_FIELD = 'expected_review_date'
DATE_LABEL = '送審預定日期'


def WARNINGS(project):
    """日期空白的送審記錄一律列入，但要讓人知道有哪幾筆"""
    return record_filter.project_warning(
        project, source_model(project), DATE_FIELD, DATE_LABEL)

# 每頁 10 筆——取自 EAGLE 原系統 models/reviewApplication.js（data.splice(0,10)）
ROWS_PER_PAGE = 10
YES, NO = 'ˇ', 'X'      # 樣板自己印的慣例：「（是ˇ、否X）」


def source_model(project):
    """資料來源模型——批次下載中心用它算「符合條件的記錄數」"""
    return 'supervision.review.application'


def _flag(value):
    return YES if value else NO


def _mark(value):
    """勾選欄：只在成立時打勾，不成立留白（不是 X）"""
    return YES if value else ''


def _item(app):
    return {
        'no': app.no or app.name or '',
        # 材料(設備)名稱——樣板的 ${item.name}，先前沒提供、該欄一直印空白
        'name': app.name or '',
        'number': app.number or '',
        'amount': app.review_materials_summary or '',
        'isTest': _flag(app.is_test),
        'expectedReviewDate': roc_date(app.expected_review_date),
        'isFactoryInspection': _flag(app.is_factory_inspection),
        'testUnit': app.test_unit or '',
        'hasSubcontractor': _mark(app.has_subcontractor),
        'hasCatalog': _mark(app.has_catalog),
        'hasRelatedTestReport': _mark(app.has_related_test_report),
        'hasDemo': _mark(app.has_demo),
        'hasOthers': _mark(app.has_others),
        'reviewDate': roc_date(app.review_date),
        'finalReviewDate': roc_date(app.final_review_date),
        'factoryInspectionDate': roc_date(app.factory_inspection_date),
        'doneDate': roc_date(app.done_date),
        # 原系統這欄是打勾不是文字：finalReviewResult ? 'ˇ' : 'X'
        'finalReviewResult': _flag(app.final_review_result == 'pass'),
        'archiveNumber': app.archive_number or '',
        'note': app.archive_note or '',
    }


def build_context(project):
    apps = project.env['supervision.review.application'].search(
        [('project_id', '=', project.id)]
        + record_filter.date_domain(project.env, DATE_FIELD),
        order='expected_review_date, id')
    pages = docx_render.paginate_plain([_item(a) for a in apps], ROWS_PER_PAGE)
    return {
        'projectName': project.name or '',
        'projectConstructionNo': project.contract_no or '',
        'supervision': project.management_company_name or '',
        'contractor': contractor_name(project),
        'totalPage': len(pages),
        'pages': pages,
    }


def FILENAME(project):
    return '材料設備送審管制總表_%s.docx' % (project.name or project.id)
