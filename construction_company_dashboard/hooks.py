# -*- coding: utf-8 -*-
"""安裝後回填營造廠歸屬並驗算（合約 §3.5）。

安裝時 ORM 會對既有資料算一次 contractor_company_id（新的 stored compute 欄位）；
這裡再用 SQL 補填「工程只有一家營造廠」的父單（安全網），然後**用另一套 SQL 獨立驗算**：

* 應填＝所屬工程恰好一家營造廠（承包廠商中公司類型是營造廠的）的筆數；實填＝其中歸屬等於那一家的筆數 → 兩者必須相等；
* 錯填＝有歸屬但不是營造廠、或不在所屬工程營造廠內的筆數 → 必須是 0；
* 照片跟著所屬單據（合約 §0b-11）：掛在有歸屬單據上的照片，歸屬必須等於單據的（補填後數「不一致」→ 必須是 0）。

不一致就丟例外讓安裝失敗（不可以「裝起來了但沒填」）。log 印每個模型的筆數。
明細（日誌明細、估驗明細）不加欄位，走父單路徑，不需回填。
"""
import logging

from odoo.exceptions import UserError
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

COMPANY_TYPE_CONTRACTOR = 'contractor'

# 模型 → 所屬工程欄位（與 contractor_attribution.py 的 _dash_project_field 一致）
ATTRIBUTION_MODELS = {
    'daily.log.sheet': 'supervision_project_id',
    'supervision.photo': 'project_id',
    'general.defect.improvement': 'project_id',
    'reservation.defect.improvement': 'project_id',
    'supervision.test.record': 'project_id',
    'general.self.inspection': 'project_id',
    'reservation.self.inspection': 'project_id',
    'payment.estimate': 'project_id',
}

# 工程 ↔ 承包廠商 的關聯表（construction_supervision_base supervision_project.py contractor_company_ids）
PROJECT_CONTRACTOR_REL = 'supervision_project_contractor_rel'

# 照片跟著所屬單據的歸屬（合約 §0b-11）：照片上的來源欄位 → 單據模型。
# 在這裡獨立寫一份（驗算不 import 實作的清單），並與實作的清單比對：兩邊不同就是有一邊漏了。
PHOTO_PARENT_FIELDS = {
    'daily_log_id': 'daily.log.sheet',
    'general_defect_id': 'general.defect.improvement',
    'reservation_defect_id': 'reservation.defect.improvement',
    'test_record_id': 'supervision.test.record',
    'general_inspection_id': 'general.self.inspection',
    'reservation_inspection_id': 'reservation.self.inspection',
    'estimate_id': 'payment.estimate',
}


def _single_contractor_sql():
    """所屬工程恰好一家營造廠：project_id → company_id。

    只算公司類型是營造廠的承包廠商（真實資料有把監造公司填進承包廠商的工程，那一家不算營造廠）。
    """
    return SQL(
        """SELECT rel.project_id, MIN(rel.company_id) AS company_id
           FROM %s rel JOIN res_company c ON c.id = rel.company_id
           WHERE c.company_type = %s
           GROUP BY rel.project_id HAVING COUNT(*) = 1""",
        SQL.identifier(PROJECT_CONTRACTOR_REL), COMPANY_TYPE_CONTRACTOR,
    )


def _attribution_counts(cr, table, project_col):
    """回傳 (總筆數, 應填, 實填, 錯填, 留空)。全部直接查 SQL，不經 ORM。"""
    single = _single_contractor_sql()
    t, p = SQL.identifier(table), SQL.identifier(project_col)
    cr.execute(SQL("SELECT COUNT(*) FROM %s", t))
    total = cr.fetchone()[0]
    cr.execute(SQL("SELECT COUNT(*) FROM %s r JOIN (%s) s ON s.project_id = r.%s", t, single, p))
    expected = cr.fetchone()[0]
    cr.execute(SQL(
        "SELECT COUNT(*) FROM %s r JOIN (%s) s ON s.project_id = r.%s WHERE r.contractor_company_id = s.company_id",
        t, single, p))
    actual = cr.fetchone()[0]
    cr.execute(SQL(
        """SELECT COUNT(*) FROM %s r
           LEFT JOIN res_company c ON c.id = r.contractor_company_id
           WHERE r.contractor_company_id IS NOT NULL
             AND (c.company_type IS DISTINCT FROM %s
                  OR NOT EXISTS (SELECT 1 FROM %s rel
                                 WHERE rel.project_id = r.%s AND rel.company_id = r.contractor_company_id))""",
        t, COMPANY_TYPE_CONTRACTOR, SQL.identifier(PROJECT_CONTRACTOR_REL), p))
    wrong = cr.fetchone()[0]
    cr.execute(SQL("SELECT COUNT(*) FROM %s WHERE contractor_company_id IS NULL", t))
    blank = cr.fetchone()[0]
    return total, expected, actual, wrong, blank


def _photo_parent_problems(env):
    """照片跟著所屬單據（合約 §0b-11）：掛在有歸屬單據上的照片，歸屬必須等於單據的歸屬（含都空白）。

    上面的單據回填（工程恰一家營造廠的 SQL 補填）在照片之後才補到部分單據，所以這裡先用 SQL 把
    「照片空白、單據有值」的補上，再獨立數「不一致」的筆數，必須是 0。回傳問題清單。
    """
    cr = env.cr
    photo = env['supervision.photo']
    implemented = set(photo._dash_parent_fields())
    if implemented != set(PHOTO_PARENT_FIELDS):
        return [f'supervision.photo：跟著單據的來源欄位，驗算清單 {sorted(PHOTO_PARENT_FIELDS)} '
                f'與實作 {sorted(implemented)} 不同']
    problems = []
    for field, parent_model in PHOTO_PARENT_FIELDS.items():
        parent_table = SQL.identifier(env[parent_model]._table)
        col = SQL.identifier(field)
        cr.execute(SQL(
            "UPDATE supervision_photo p SET contractor_company_id = d.contractor_company_id FROM %s d "
            "WHERE d.id = p.%s AND p.contractor_company_id IS NULL AND d.contractor_company_id IS NOT NULL",
            parent_table, col))
        sql_filled = cr.rowcount
        cr.execute(SQL(
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE p.contractor_company_id IS DISTINCT FROM d.contractor_company_id) "
            "FROM supervision_photo p JOIN %s d ON d.id = p.%s",
            parent_table, col))
        attached, mismatch = cr.fetchone()
        _logger.info('營造廠歸屬回填 照片跟著%s：掛在單據上 %d、與單據不一致 %d（SQL 補填 %d）',
                     parent_model, attached, mismatch, sql_filled)
        if mismatch:
            problems.append(f'supervision.photo（{field}）：{mismatch} 張照片的歸屬與所屬單據不同')
    # 跟著單據補上的值也要合法（是營造廠、在照片所屬工程的營造廠內）：照片與單據的工程不同時會在這裡抓到
    wrong = _attribution_counts(cr, photo._table, 'project_id')[3]
    if wrong:
        problems.append(f'supervision.photo：跟著單據補上後錯填 {wrong}')
    return problems


def post_init_hook(env):
    # 先讓安裝時排進去的 ORM 計算跑完，下面的 SQL 才看得到結果
    env.flush_all()
    cr = env.cr
    problems = []
    for model_name, project_field in ATTRIBUTION_MODELS.items():
        model = env[model_name]
        table, project_col = model._table, model._fields[project_field].name
        cr.execute(SQL(
            "UPDATE %s r SET contractor_company_id = s.company_id FROM (%s) s "
            "WHERE s.project_id = r.%s AND r.contractor_company_id IS NULL",
            SQL.identifier(table), _single_contractor_sql(), SQL.identifier(project_col)))
        sql_filled = cr.rowcount
        total, expected, actual, wrong, blank = _attribution_counts(cr, table, project_col)
        _logger.info(
            '營造廠歸屬回填 %s：總 %d、應填（工程恰一家營造廠）%d、實填 %d、錯填 %d、留空 %d（SQL 補填 %d）',
            model_name, total, expected, actual, wrong, blank, sql_filled)
        if expected != actual or wrong:
            problems.append(f'{model_name}：應填 {expected}、實填 {actual}、錯填 {wrong}')
    problems += _photo_parent_problems(env)
    # 回填改了資料表，ORM 快取要作廢
    env.invalidate_all()
    if problems:
        raise UserError('營造廠歸屬回填驗算不一致，安裝中止：\n' + '\n'.join(problems))
