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

from ..utils import docx_render
from ..utils.formatters import roc_date, selection_label

MODEL = 'project.project'
MODE = 'docx'

ROWS_PER_PAGE = 12


def _qty(value):
    if not value:
        return ''
    return ('%g' % value) if isinstance(value, float) else str(value)


def _item(rec):
    task = rec.task_id
    standard = rec.standard_id
    return {
        'no': rec.name or '',
        # payItem 對應契約工項；IF 已被移除，欄位一律給字串不給 None
        'payItem': {
            'fullItemNo': (task.code if 'code' in task._fields else '') or task.display_name or '',
            'quantity': _qty(getattr(task, 'planned_qty', False) or False),
        },
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
        [('project_id', '=', project.id)], order='in_site_date, id')
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
