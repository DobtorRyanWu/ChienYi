# -*- coding: utf-8 -*-
"""自主檢查總表 —— 佔位符對照表（專案層級）。

與施工日誌不同，這是**整個專案的彙總表**：一列排兩筆檢查（左右兩欄），
所以資料來源是 project.project 而不是單筆自主檢查。

版面：
    R2-R4  工程名稱／契約編號／監造單位／開工日期／竣工日期／施工廠商
    R7     ${table:inspections.left.*}  ｜  ${table:inspections.right.*}
           一列兩筆，左欄排前半、右欄排後半（報紙分欄式）

一般式專案用 general.self.inspection，預約式用 reservation.self.inspection。
"""

from ..utils.formatters import roc_date

MODEL = 'project.project'
MODE = 'placeholder'

QUALIFIED_MARK = '✓'
# overall_result: pass 合格 / conditional_pass 條件合格 / fail 不合格
# 條件合格歸在「合格」欄並於處理情形註記，符合表單只有兩欄的實況
PASSING_RESULTS = ('pass', 'conditional_pass')


def _inspection_model(project):
    """預約式專案用 reservation.self.inspection，其餘走一般式"""
    return ('reservation.self.inspection' if project.project_type == 'reservation'
            else 'general.self.inspection')


def _row(inspection, seq):
    result = inspection.overall_result if 'overall_result' in inspection._fields else False
    passing = result in PASSING_RESULTS
    note = inspection.note or ''
    if result == 'conditional_pass':
        note = ('條件合格。%s' % note).strip('。 ')
    return {
        'seq': seq,
        'name': inspection.inspection_type_id.display_name or inspection.display_name or '',
        'inspectedAt': roc_date(inspection.inspection_date),
        'isQualified': QUALIFIED_MARK if passing and result else '',
        'isUnqualified': QUALIFIED_MARK if result == 'fail' else '',
        'result': note,
    }


def build_context(project):
    Inspection = project.env[_inspection_model(project)]
    records = Inspection.search([('project_id', '=', project.id)],
                                order='inspection_date, id')
    rows = [_row(insp, i + 1) for i, insp in enumerate(records)]
    # 報紙分欄：前半排左欄、後半排右欄，兩欄列數相同
    half = (len(rows) + 1) // 2
    left, right = rows[:half], rows[half:]

    contractors = project.contractor_partner_ids.mapped('name')
    return {
        'project.name': project.name or '',
        'project.constructionNo': project.contract_no or '',
        'project.beginAt': roc_date(project.contract_start_date),
        'project.extendFinishAt': roc_date(project.contract_end_date),
        'project.supervision': project.management_company_name or '',
        'project.contractor': '、'.join(contractors),
        'inspections.left': left,
        'inspections.right': right,
    }


def FILENAME(project):
    return '自主檢查總表_%s.xlsx' % (project.name or project.id)
