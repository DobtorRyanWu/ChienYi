# -*- coding: utf-8 -*-
"""計畫書送審管制總表 —— xlsx 佔位符對照表（專案層級，明細動態展開）。

樣板來源：既有案件「管制表」的 `1.計畫` 工作表，去識別化後存成
data/templates_blank/plan_control.xlsx。表頭六個值走 `${project.xxx}`，
明細只有一列 `${table:items.*}` 樣板列，套印時依筆數展開（不分頁——
樣板保留 Print_Titles $1:$5，超過一頁會自動重印表頭）。

## 日期與文號為什麼在同一格

原表一格裡是「113年1月1日 ⏎ ○○字第1130101001號」——日期與發文文號擠在
同一個儲存格用換行分開。模型端拆成 Date + Char 兩欄（日期要能排序、算逾期），
這裡再用 `\n` 組回去，印出來與原表一致。
"""

from ..utils import record_filter
from ..utils.formatters import contractor_name, roc_date_cn

MODEL = 'project.project'
MODE = 'placeholder'

# 批次下載中心可用 context 限定期間；本表以「第一次送審日期」為準
DATE_FIELD = 'first_submit_date'
DATE_LABEL = '第一次送審日期'

# 計畫書／分項計畫／施工圖三張表的欄位完全一樣，只有表名不同，所以共用這一份
# 空白樣板與這一份對照表：要印哪一種由 context 的 plan_control_type 指定，
# 表名以 ${project.reportTitle} 代入。表名取自既有案件三張工作表的 A2 標題。
CTX_CONTROL_TYPE = 'plan_control_type'
DEFAULT_CONTROL_TYPE = 'plan'
REPORT_TITLES = {
    'plan': '計畫書送審管制總表(含工程保險)',
    'sub_plan': '分項計畫送審管制總表',
    'drawing': '施工圖送審管制總表',
}


def _control_type(env):
    value = env.context.get(CTX_CONTROL_TYPE)
    return value if value in REPORT_TITLES else DEFAULT_CONTROL_TYPE


def SOURCE_DOMAIN(env):
    """來源記錄的額外條件——下載中心算筆數與這裡取資料都要帶上類別，
    否則三種管制表會互相把對方的記錄算進去。"""
    return [('control_type', '=', _control_type(env))]

# 原表沒有資料的欄位印「-」而不是留白（見 F8/G6/I8）
DASH = '-'


def source_model(project):
    """資料來源模型——批次下載中心用它算「符合條件的記錄數」"""
    return 'supervision.plan.control'


def WARNINGS(project):
    """日期空白的記錄一律列入，但要讓人知道有哪幾筆"""
    return record_filter.project_warning(
        project, source_model(project), DATE_FIELD, DATE_LABEL,
        extra_domain=SOURCE_DOMAIN(project.env))


def _dated_doc(date, doc_no):
    """一格兩行：民國日期 + 發文文號；兩者都空白時印 -"""
    lines = [text for text in (roc_date_cn(date), (doc_no or '').strip()) if text]
    return '\n'.join(lines) if lines else DASH


def _item(record):
    return {
        'itemNo': record.item_no or '',
        'name': record.name or '',
        'timing': record.required_timing or '',
        'deadline': roc_date_cn(record.deadline_date),
        'firstSubmit': _dated_doc(record.first_submit_date,
                                  record.first_submit_doc_no),
        'secondSubmit': _dated_doc(record.second_submit_date,
                                   record.second_submit_doc_no),
        'supervisorReview': _dated_doc(record.supervisor_review_date,
                                       record.supervisor_review_doc_no),
        'authorityApprove': _dated_doc(record.authority_approve_date,
                                       record.authority_approve_doc_no),
        'note': record.note or '',
    }


def build_context(project):
    records = project.env[source_model(project)].search(
        [('project_id', '=', project.id)]
        + SOURCE_DOMAIN(project.env)
        + record_filter.date_domain(project.env, DATE_FIELD),
        # 依項次排序（item_sequence 是 item_no 的數值化欄位；☆ 這類非數字算 0，
        # 排在項次 1 之前——與原表把監造自提的兩列放最上面一致）
        order='item_sequence, sequence, id')

    return {
        'project.name': project.name or '',
        'project.reportTitle': REPORT_TITLES[_control_type(project.env)],
        'project.contractor': contractor_name(project),
        'project.supervision': project.management_company_name or '',
        'project.awardDate': roc_date_cn(project.award_date),
        'project.signDate': roc_date_cn(project.contract_sign_date),
        # 開工日期印實際開工日（原表表頭寫的就是實際開工那天）
        'project.beginAt': roc_date_cn(project.actual_start_date),
        'project.finishAt': roc_date_cn(project.contract_end_date),
        'items': [_item(r) for r in records],
    }


def FILENAME(project):
    title = REPORT_TITLES[_control_type(project.env)]
    return '%s_%s.xlsx' % (title, project.name or project.id)
