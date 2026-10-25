# -*- coding: utf-8 -*-
"""材料設備申請及審查紀錄表（新北市政府工程契約附表7）—— docx 對照表（一筆送審一張）。

資料來自材料設備送審管制（supervision.review.application）。系統有記的才帶：
    送審項目  駐廠檢驗（是否廠驗）、型錄樣品審查（型錄或樣品）、材料試驗室檢驗（是否取樣試驗）、其他
    提供文件  供應廠證明文件（協力廠商資料）、樣品、駐廠檢驗試驗報告（相關測試報告）
    審查意見與結果印在細項表第一列
系統沒有記的（供料廠商、送審次數、工地現場檢驗、書面審查、材料規範、出廠證明、逐項規格比對）
留白手填——使用者 2026-10-25 決定附表7 這輪不加欄位。
"""

from ..utils.formatters import roc_date_cn, selection_label

MODEL = 'supervision.review.application'
MODE = 'docx'
BOX_ON, BOX_OFF = '■', '□'
# 送審日期沒有值時印回原表的手填提示（樣板裡這格的「年 月 日」被標記取代了）
BLANK_DATE = '　　　年　　　月　　　日'
UNNUMBERED = '/'      # supervision.review.application.sequence_code 還沒編號時的預設值


def _box(flag):
    return BOX_ON if flag else BOX_OFF


def build_context(app):
    project = app.project_id
    return {
        'projectName': project.name or '',
        'no': '' if app.sequence_code in (False, UNNUMBERED) else app.sequence_code,
        'materialName': app.name or '',
        'submitDate': roc_date_cn(app.final_review_date or app.expected_review_date) or BLANK_DATE,
        'boxFactory': _box(app.is_factory_inspection),
        'boxCatalog': _box(app.has_catalog or app.has_demo),
        'boxLab': _box(app.is_test),
        'boxOther': _box(app.has_others),
        'otherNote': app.others or '',
        'docSupplier': _box(app.has_subcontractor),
        'docSample': _box(app.has_demo),
        'docTestReport': _box(app.has_related_test_report),
        'reviewComment': app.review_comment or '',
        'reviewResult': selection_label(app.final_review_result, app, 'final_review_result'),
    }


def FILENAME(app):
    return '材料設備申請及審查紀錄表_%s_%s.docx' % (app.project_id.name or '', app.name or app.id)
