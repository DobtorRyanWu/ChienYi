# -*- coding: utf-8 -*-
"""材料設備檢（試）驗管制總表 —— docx 對照表（專案層級，分頁彙總）。

樣板語法同送審管制（`FOR item IN $page`，page 本身是清單），
但多用了 `+++IF $item.standard+++ … +++END-IF+++`——既有的
dobtor_doc_editor 轉換器不處理 IF，由 utils/docx_render.py 先移除標記；
所以這裡的 standard 一定要給值（取不到就空字串），不能讓它是 None。

token → supervision.test.record：
    no / payItem.fullItemNo / payItem.quantity / inSiteDate / sampleDate /
    standard.norm / inSiteSumQuantity / result …
"""

from ..utils import docx_render, record_filter
from ..utils.formatters import roc_date, selection_label

MODEL = 'project.project'
MODE = 'docx'

# 批次下載中心可用 context 限定期間；本表以「進場日期」為準（與既有 order 一致）
DATE_FIELD = 'in_site_date'
DATE_LABEL = '進場日期'


def WARNINGS(project):
    """日期空白的檢試驗記錄一律列入，但要讓人知道有哪幾筆"""
    return record_filter.project_warning(
        project, source_model(project), DATE_FIELD, DATE_LABEL)

# 每頁 10 筆——取自 EAGLE 原系統 models/testRecord.js（data.splice(0,10)）
ROWS_PER_PAGE = 10


def source_model(project):
    """資料來源模型——批次下載中心用它算「符合條件的記錄數」"""
    return 'supervision.test.record'


def _qty(value):
    if not value:
        return ''
    return ('%g' % value) if isinstance(value, float) else str(value)


def _item(rec):
    task = rec.task_id
    standard = rec.standard_id
    return {
        'no': rec.name or '',
        # payItem 對應契約工項；IF 已被移除，欄位一律給字串不給 None。
        # ⚠️ 樣板實際用的是 ${item.payItem.description}（2026-08-06 逐一比對 token
        # 清單發現），先前只給 fullItemNo，那一欄一直印空白。
        'payItem': {
            'description': task.display_name or '',
            'fullItemNo': (task.code if 'code' in task._fields else '') or task.display_name or '',
            'quantity': _qty(getattr(task, 'planned_qty', False) or False),
        },
        # 抽驗及會同人員——樣板的 ${item.member}，先前完全沒提供
        'member': '、'.join(
            (rec.contractor_member_ids | rec.supervision_member_ids).mapped('display_name')),
        'standard': {
            'norm': (standard.norm if standard and 'norm' in standard._fields else '') or '',
            'name': standard.display_name if standard else '',
        },
        'inSiteDate': roc_date(rec.in_site_date),
        'sampleDate': roc_date(rec.sample_date),
        'inSiteQuantity': _qty(rec.in_site_quantity),
        'inSiteSumQuantity': _qty(rec.in_site_sum_quantity),
        'sampleQuantity': _qty(rec.sample_quantity),
        'sampleSumQuantity': _qty(rec.sample_sum_quantity),
        # 印中文標籤而不是 Selection 的值（pass/fail/pending）
        'result': selection_label(rec.result, rec, 'result'),
        'resultDate': roc_date(rec.result_date),
        'archiveNumber': rec.archive_number or '',
        'note': rec.note or '',
    }


def build_context(project):
    records = project.env['supervision.test.record'].search(
        [('project_id', '=', project.id)]
        + record_filter.date_domain(project.env, DATE_FIELD),
        order='in_site_date, id')
    pages = docx_render.paginate_plain([_item(r) for r in records], ROWS_PER_PAGE)
    return {
        'projectName': project.name or '',
        'projectConstructionNo': project.contract_no or '',
        'supervision': project.management_company_name or '',
        'contractor': '、'.join(project.contractor_partner_ids.mapped('name')),
        'totalPage': len(pages),
        'pages': pages,
    }


def FILENAME(project):
    return '材料設備檢試驗管制總表_%s.docx' % (project.name or project.id)
