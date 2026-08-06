# -*- coding: utf-8 -*-
"""自主檢查總表 —— 佔位符對照表（專案層級、左右雙欄、分頁）。

規格取自 EAGLE 原系統 `models/inspection.js / generateListFile()`
（2026-08-06 由 TKU source map 還原）：

    const maxRow = 8
    while (inspections[currentIndex]) {
      for (rowIndex = 0..7) {
        left  = inspections[currentIndex + rowIndex]        // 本頁 1~8
        right = inspections[currentIndex + rowIndex + 8]    // 本頁 9~16
        left.seq  = rowIndex + 1 + (page-1)*8
        right.seq = rowIndex + 1 + 8 + (page-1)*8
        data.push({ left, right })
      }
      currentIndex += maxRow
      if (還有) copySheet(`第${page}頁`, `第${page+1}頁`)
      substitute(page, { project, inspections: data })
    }
    isQualified   = !hasMistake ? 'V' : ''
    isUnqualified =  hasMistake ? 'V' : ''

**先前做錯的兩處（已修正）**：
  ① 左右欄用「全域前半／後半」對切 → 應為**同一頁內** i 與 i+8，
     否則多頁時整個順序都錯
  ② 勾記號用 '✓' → 原系統是 'V'

合格判定維持 Odoo 的 `overall_result`（合格／條件合格／不合格三態），
比原系統的 hasMistake 語意完整；條件合格歸「合格」欄並於處理情形註記。
"""

from ..utils.formatters import roc_date

MODEL = 'project.project'
MODE = 'placeholder'

# 每頁左右兩欄各 8 列，一頁 16 筆
ROWS_PER_PAGE = 8
QUALIFIED_MARK = 'V'          # 原系統用 V 不是 ✓
PASSING_RESULTS = ('pass', 'conditional_pass')

PAGINATE = {
    'source': 'inspections',
    'page_size': ROWS_PER_PAGE,      # 一頁 8 列（每列含左右兩筆）
}


def _inspection_model(project):
    """預約式專案用 reservation.self.inspection，其餘走一般式"""
    return ('reservation.self.inspection' if project.project_type == 'reservation'
            else 'general.self.inspection')


def _cell(inspection, seq):
    if not inspection:
        return {}
    result = (inspection.overall_result
              if 'overall_result' in inspection._fields else False)
    note = inspection.note or ''
    if result == 'conditional_pass':
        note = ('條件合格。%s' % note).strip('。 ')
    return {
        'seq': seq,
        'name': inspection.inspection_type_id.display_name or inspection.display_name or '',
        'inspectedAt': roc_date(inspection.inspection_date),
        'isQualified': QUALIFIED_MARK if result in PASSING_RESULTS else '',
        'isUnqualified': QUALIFIED_MARK if result == 'fail' else '',
        'result': note,
    }


def build_context(project):
    Inspection = project.env[_inspection_model(project)]
    records = Inspection.search([('project_id', '=', project.id)],
                               order='inspection_date, id')

    # 依原系統：一頁 16 筆，左欄放本頁 1~8、右欄放本頁 9~16
    rows = []
    per_page = ROWS_PER_PAGE * 2
    for page_start in range(0, max(len(records), 1), per_page):
        page = records[page_start:page_start + per_page]
        for offset in range(ROWS_PER_PAGE):
            left = page[offset] if offset < len(page) else None
            right_idx = offset + ROWS_PER_PAGE
            right = page[right_idx] if right_idx < len(page) else None
            rows.append({
                'left': _cell(left, page_start + offset + 1),
                'right': _cell(right, page_start + right_idx + 1),
            })

    contractors = project.contractor_partner_ids.mapped('name')
    return {
        'project.name': project.name or '',
        'project.constructionNo': project.contract_no or '',
        'project.beginAt': roc_date(project.contract_start_date),
        'project.extendFinishAt': roc_date(project.contract_end_date),
        'project.supervision': project.management_company_name or '',
        'project.contractor': '、'.join(contractors),
        'inspections': rows,
    }


def FILENAME(project):
    return '自主檢查總表_%s.xlsx' % (project.name or project.id)
